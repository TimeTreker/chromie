from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Protocol

from agent.app.capabilities.validator import validate_args_for_schema
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orchestrator.schemas.route import RouteDecision as CompatibilityRouteDecision
from shared.chromie_contracts.core_interpretation import (
    CognitiveProgressCandidate,
    CoreInterpretationResult,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    MEDIA_CAPABILITY_IDS,
    SkillRequest,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    ExecuteGoalPlanOutcome,
    GoalSatisfactionAssessment,
)
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    DirectResponseComposition,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
    goal_association_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan
from shared.chromie_contracts.social_attention import (
    SocialAttentionActivityAnchor,
    SocialAttentionPlan,
    SocialAttentionRequest,
    normalize_social_attention_mode,
)
from shared.chromie_contracts.user_turn import (
    AttentionReviewResult,
    GatewayContextSnapshot,
    UserTurnEnvelope,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

from orchestrator.runtime.evidence_identity import runtime_identity_reference

from orchestrator.runtime.situation import build_situation_projection

logger = logging.getLogger(__name__)

CognitiveRuntimeMode = Literal["off", "report_only", "apply"]
CognitiveRuntimeStatus = Literal[
    "applied",
    "report_only",
    "skipped",
    "error",
]
CognitiveLane = Literal["chat", "robot_action", "tool", "memory", "unsupported"]


class CognitiveStageFailure(RuntimeError):
    """A stage failure with explicit architecture attribution metadata."""

    def __init__(self, stage: str, metadata: dict[str, Any]) -> None:
        self.stage = stage
        self.failure_metadata = dict(metadata)
        failure_class = str(metadata.get("failure_class") or "stage_failure")
        reason = str(
            metadata.get("error")
            or metadata.get("reason")
            or metadata.get("reason_summary")
            or failure_class
        )
        super().__init__(f"{stage}:{failure_class}:{reason}")


class CognitiveRuntimeResolution(BaseModel):
    """One bounded goal-driven turn resolution before host execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    mode: CognitiveRuntimeMode
    status: CognitiveRuntimeStatus
    lane: CognitiveLane
    turn_envelope: UserTurnEnvelope | None = None
    goal_association: GoalAssociationResolution | None = None
    fast_plan: CanonicalPlan | None = None
    terminal_plan: CanonicalPlan | None = None
    response_composition: ResponseCompositionResolution | None = None
    interaction_response: InteractionResponse | None = None
    goal_state_results: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    fallback_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class CognitiveRuntimePolicy:
    mode: CognitiveRuntimeMode = "off"
    apply_lanes: frozenset[str] = frozenset({"chat", "memory", "robot_action", "tool"})
    fallback_policy: str = "fail_closed"
    max_total_ms: int = 25000
    goal_association_timeout_ms: int = 3500
    fast_planner_timeout_ms: int = 3000
    deep_planner_timeout_ms: int = 10000
    response_composer_timeout_ms: int = 5000

    def lane_enabled(self, lane: str) -> bool:
        return lane in self.apply_lanes


class CognitiveAgentClient(Protocol):
    async def resolve_goal_association(
        self, session: Any, **kwargs: Any
    ) -> GoalAssociationResolution: ...

    async def resolve_fast_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_deep_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_reflection(
        self, session: Any, **kwargs: Any
    ) -> ReflectionResolution: ...

    async def resolve_social_attention(
        self, session: Any, **kwargs: Any
    ) -> SocialAttentionPlan: ...

    async def compose_response_plan(
        self, session: Any, **kwargs: Any
    ) -> ResponseCompositionResolution: ...


class CognitiveEvidenceRecorder:
    """Append-only operational evidence and in-process rollout counters."""

    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        include_text: bool = False,
        run_identity: dict[str, Any] | None = None,
        run_identity_path: Path | None = None,
    ) -> None:
        self.path = path
        self.enabled = enabled
        self.include_text = include_text
        self.run_identity = dict(run_identity) if run_identity is not None else None
        self.run_identity_path = run_identity_path
        self.counters: Counter[str] = Counter()
        self.total_latency_ms = 0.0

    @staticmethod
    def _text_digest(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]

    def _identity_reference(self) -> dict[str, Any]:
        return runtime_identity_reference(
            self.run_identity,
            path=self.run_identity_path,
        )

    def record_gateway(
        self,
        envelope: UserTurnEnvelope,
        *,
        text: str,
        context_snapshot: GatewayContextSnapshot | None = None,
        attention_review: AttentionReviewResult | None = None,
    ) -> None:
        """Append the pre-Core admission decision for one received turn."""

        self.counters[f"gateway_admission:{envelope.admission}"] += 1
        self.counters[f"gateway_attention:{envelope.attention.disposition}"] += 1
        if not self.enabled:
            return
        payload: dict[str, Any] = {
            "schema_version": 2,
            "event": "cognitive_gateway_admission",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": envelope.session_id,
            "turn_id": envelope.turn_id,
            "conversation_id": envelope.conversation_id,
            "channel": envelope.channel,
            "admission": envelope.admission,
            "core_eligible": envelope.admission in {"admit", "reflex_and_admit"},
            "quality": envelope.quality.model_dump(mode="json"),
            "reflex": envelope.reflex.model_dump(mode="json"),
            "attention": envelope.attention.model_dump(mode="json"),
            "context_snapshot_digest": (
                context_snapshot.digest if context_snapshot is not None else None
            ),
            "context_reference_types": [item.context_type for item in envelope.context_refs],
            "text_chars": len(text or ""),
            "text_sha256_16": self._text_digest(text),
            "run_identity": self._identity_reference(),
        }
        if attention_review is not None:
            payload["attention_review"] = attention_review.model_dump(mode="json")
        if self.include_text:
            payload["text"] = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def record(self, resolution: CognitiveRuntimeResolution, *, sid: str, text: str) -> None:
        self.counters[f"status:{resolution.status}"] += 1
        self.counters[f"lane:{resolution.lane}"] += 1
        self.counters[f"mode:{resolution.mode}"] += 1
        failure_class = str(resolution.metadata.get("failure_class") or "").strip()
        attribution = str(resolution.metadata.get("architecture_attribution") or "").strip()
        if failure_class:
            self.counters[f"failure_class:{failure_class}"] += 1
        if attribution:
            self.counters[f"architecture_attribution:{attribution}"] += 1
        fast_path = str(resolution.metadata.get("fast_planner_path") or "").strip()
        if fast_path:
            self.counters[f"fast_planner_path:{fast_path}"] += 1
        if (
            fast_path == "terminal"
            and resolution.fast_plan is not None
            and len(resolution.fast_plan.goal_ids) > 1
        ):
            self.counters["fast_terminal_multi_goal"] += 1
        if fast_path == "semantic_escalation":
            self.counters["fast_semantic_escalation"] += 1
        if fast_path == "contract_failure":
            self.counters["fast_contract_failure"] += 1
        if resolution.fast_plan is not None and bool(
            resolution.fast_plan.metadata.get("contract_repair_attempted")
        ):
            self.counters["fast_contract_repair"] += 1
        if bool(resolution.metadata.get("deep_planner_invoked")):
            reason = str(resolution.metadata.get("deep_planner_invocation_reason") or "unknown")
            self.counters[f"deep_planner_invoked:{reason}"] += 1
        elif fast_path == "terminal":
            self.counters["deep_planner_avoided"] += 1
        self.counters["turns"] += 1
        total_ms = float(resolution.timings_ms.get("total", 0.0))
        self.total_latency_ms += total_ms
        if not self.enabled:
            return
        payload = {
            "schema_version": 2,
            "event": "cognitive_runtime_resolution",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "turn_id": (
                resolution.turn_envelope.turn_id if resolution.turn_envelope is not None else sid
            ),
            "conversation_id": (
                resolution.turn_envelope.conversation_id
                if resolution.turn_envelope is not None
                else None
            ),
            "run_identity": self._identity_reference(),
            "mode": resolution.mode,
            "status": resolution.status,
            "lane": resolution.lane,
            "user_turn_envelope": (
                resolution.turn_envelope.model_dump(mode="json")
                if resolution.turn_envelope is not None
                else None
            ),
            "text_chars": len(text or ""),
            "text_sha256_16": self._text_digest(text),
            "goal_association": (
                resolution.goal_association.model_dump(mode="json", exclude_none=True)
                if resolution.goal_association is not None
                else None
            ),
            "fast_plan": self._plan_summary(resolution.fast_plan),
            "terminal_plan": self._plan_summary(resolution.terminal_plan),
            "composition": self._composition_summary(resolution.response_composition),
            "interaction": self._interaction_summary(resolution.interaction_response),
            "goal_state_results": resolution.goal_state_results,
            "timings_ms": resolution.timings_ms,
            "fallback_reason": resolution.fallback_reason,
            "metadata": resolution.metadata,
            "core_interpretation": (
                resolution.metadata.get("core_interpretation")
                if isinstance(resolution.metadata, dict)
                else None
            ),
            "core_interpretation_projection_digest": (
                resolution.metadata.get("core_interpretation_projection_digest")
                if isinstance(resolution.metadata, dict)
                else None
            ),
        }
        if self.include_text:
            payload["text"] = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def record_outcome(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str,
        final_response: InteractionResponse | None,
        delivery_status: str,
        suppression_reason: str = "",
        goal_state_results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append the trusted post-execution half of a cognitive turn."""

        self.counters["outcome_bundles"] += 1
        self.counters[f"outcome_status:{bundle.aggregate_status}"] += 1
        self.counters[f"outcome_delivery:{delivery_status}"] += 1
        if not self.enabled:
            return
        payload = {
            "schema_version": 2,
            "event": "cognitive_execution_outcome",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "turn_id": bundle.turn_id,
            "interaction_id": bundle.interaction_id,
            "run_identity": self._identity_reference(),
            "outcome_fingerprint": execution_outcome_fingerprint(bundle),
            "outcome_bundle": bundle.model_dump(mode="json", exclude_none=True),
            "goal_state_results": list(goal_state_results or []),
            "final_response": self._interaction_summary(final_response),
            "delivery_status": delivery_status,
            "suppression_reason": suppression_reason,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _plan_summary(plan: CanonicalPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        return {
            "plan_id": plan.plan_id,
            "planner_tier": plan.planner_tier,
            "disposition": plan.disposition,
            "coverage": plan.coverage,
            "confidence": plan.confidence,
            "goal_ids": plan.goal_ids,
            "step_ids": [item.step_id for item in plan.steps],
            "capability_ids": [item.capability_id for item in plan.steps],
            "selected_agent_skills": [
                item.model_dump(mode="json") for item in plan.selected_agent_skills
            ],
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
        }

    @staticmethod
    def _composition_summary(
        resolution: ResponseCompositionResolution | None,
    ) -> dict[str, Any] | None:
        if resolution is None:
            return None
        composition = resolution.composition
        coordinated = composition if isinstance(composition, CoordinatedResponsePlan) else None
        direct = composition if isinstance(composition, DirectResponseComposition) else None
        return {
            "status": resolution.status,
            "composition_id": composition.composition_id if composition else None,
            "phase": composition.phase if composition else None,
            "canonical_plan_fingerprint": (
                coordinated.canonical_plan_fingerprint if coordinated else None
            ),
            "goal_association_fingerprint": (
                direct.goal_association_fingerprint if direct else None
            ),
            "lane_coordination": (
                [
                    {
                        "coordination_id": item.coordination_id,
                        "lanes": list(item.lanes),
                        "activity_step_ids": list(item.activity_step_ids),
                        "relation": item.relation,
                        "start_policy": item.start_policy,
                        "failure_policy": item.failure_policy,
                    }
                    for item in coordinated.lane_coordination
                ]
                if coordinated is not None
                else []
            ),
            "response_truth_audit": (
                dict(composition.metadata.get("response_truth_audit") or {})
                if composition
                and isinstance(composition.metadata, dict)
                and isinstance(composition.metadata.get("response_truth_audit"), dict)
                else None
            ),
        }

    @staticmethod
    def _interaction_summary(response: InteractionResponse | None) -> dict[str, Any] | None:
        if response is None:
            return None
        return {
            "interaction_id": response.interaction_id,
            "status": response.status,
            "speech_count": len(response.speech),
            "capability_ids": [item.capability_id for item in response.skills],
            "requires_confirmation": response.requires_confirmation,
        }

    def snapshot(self) -> dict[str, Any]:
        turns = int(self.counters.get("turns", 0))
        return {
            "turns": turns,
            "mean_total_latency_ms": (round(self.total_latency_ms / turns, 1) if turns else 0.0),
            "counters": dict(sorted(self.counters.items())),
            "path": str(self.path),
            "enabled": self.enabled,
            "include_text": self.include_text,
        }


class CanonicalPlanRuntimeAdapter:
    """Translate validated canonical planning into the existing trusted runtime."""

    TRACE_MODULE = TraceModule(
        name="orchestrator.canonical_plan_adapter",
        component_type="runtime_adapter",
        implementation="CanonicalPlanRuntimeAdapter",
        schema_version=1,
    )

    def __init__(
        self,
        interaction_runtime: Any,
        *,
        social_attention_mode: str = "on",
        recent_auxiliary_evidence_limit: int = 12,
    ) -> None:
        self.interaction_runtime = interaction_runtime
        self.social_attention_mode = normalize_social_attention_mode(
            social_attention_mode,
            default="on",
        )
        self._recent_auxiliary_behavior_evidence: deque[dict[str, Any]] = deque(
            maxlen=max(1, int(recent_auxiliary_evidence_limit))
        )

    def recent_auxiliary_behavior_evidence(
        self,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return bounded host evidence without implying provider completion."""

        evidence = [dict(item) for item in self._recent_auxiliary_behavior_evidence]
        if session_id is None:
            return evidence
        return [item for item in evidence if item.get("session_id") == session_id]

    def _record_auxiliary_behavior_request(
        self,
        request: SkillRequest,
        *,
        session_id: str,
    ) -> None:
        if not request.metadata.get("auxiliary_social_attention"):
            return
        if any(
            item.get("request_id") == request.request_id
            for item in self._recent_auxiliary_behavior_evidence
        ):
            return
        self._recent_auxiliary_behavior_evidence.append(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "evidence_kind": "host_accepted_auxiliary_request",
                "execution_claim": "not_observed",
                "request_id": request.request_id,
                "capability_id": request.capability_id,
                "semantic_args": dict(request.args),
                "purpose": request.metadata.get("social_attention_purpose"),
                "turn_id": request.metadata.get("turn_id"),
                "primary_activity_id": request.metadata.get("primary_activity_id"),
                "primary_activity_kind": request.metadata.get("primary_activity_kind"),
                "canonical_plan_id": request.metadata.get("canonical_plan_id"),
                "policy_mode": request.metadata.get("social_attention_policy_mode"),
            }
        )

    @staticmethod
    def lane_for_plan(plan: CanonicalPlan) -> CognitiveLane:
        if not plan.steps:
            return "chat"
        capability_ids = {step.capability_id for step in plan.steps}
        soridormi_ids = {
            capability_id
            for capability_id in capability_ids
            if capability_id.startswith("soridormi.")
        }
        if soridormi_ids and capability_ids.issubset(
            soridormi_ids | set(MEDIA_CAPABILITY_IDS.values())
        ):
            return "robot_action"
        if all(step.skill_id.startswith("chromie.memory.") for step in plan.steps):
            return "memory"
        if all(step.skill_id.startswith("chromie.") for step in plan.steps):
            return "tool"
        return "unsupported"

    def is_pure_safe_read_plan(self, plan: CanonicalPlan) -> bool:
        if plan.disposition != "execute" or not plan.steps:
            return False
        try:
            definitions = [
                self.interaction_runtime.skill_definition(step.skill_id)
                for step in plan.steps
            ]
        except ValueError:
            return False
        return all(
            definition.available
            and not definition.requires_confirmation
            and str((definition.metadata or {}).get("safety_class") or "")
            == "safe_read"
            and (definition.metadata or {}).get("side_effect_free") is True
            for definition in definitions
        )

    async def validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="validate_plan",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "planner_tier": plan.planner_tier,
            },
        ) as span:
            errors = await self._validation_errors(plan)
            span.set_attribute("error_count", len(errors))
            if errors:
                span.set_status("error")
            return errors

    async def _validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if plan.disposition not in {"execute", "mixed"}:
            if plan.steps:
                errors.append({"type": "non_execute_plan_has_steps"})
            return errors
        skill_ids = [step.skill_id for step in plan.steps]
        try:
            await self.interaction_runtime.ensure_skill_definitions(skill_ids)
        except Exception as exc:
            return [
                {
                    "type": "runtime_catalog_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:400],
                }
            ]

        definitions: dict[str, Any] = {}
        for step in plan.steps:
            try:
                definition = self.interaction_runtime.skill_definition(step.skill_id)
            except Exception as exc:
                errors.append(
                    {
                        "type": "unknown_runtime_skill",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "message": str(exc)[:300],
                    }
                )
                continue
            definitions[step.step_id] = definition
            if not definition.available:
                errors.append(
                    {
                        "type": "runtime_skill_unavailable",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "reason": definition.unavailable_reason,
                    }
                )
                continue
            try:
                validate_output_schema_declaration(definition.output_schema)
                output_schema_sha256(definition.output_schema)
            except (TypeError, ValueError) as exc:
                errors.append(
                    {
                        "type": "runtime_invalid_output_schema",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "message": str(exc)[:160],
                    }
                )
            schema_errors = validate_args_for_schema(step.args, definition.input_schema)
            if schema_errors:
                errors.append(
                    {
                        "type": "runtime_invalid_args",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "errors": schema_errors[:8],
                    }
                )

        parallel_batch: list[Any] = []
        for step in plan.steps:
            if step.timing == "parallel":
                parallel_batch.append(step)
                continue
            errors.extend(
                self._parallel_errors(
                    parallel_batch,
                    definitions,
                    plan_step_count=len(plan.steps),
                )
            )
            parallel_batch = []
        errors.extend(
            self._parallel_errors(
                parallel_batch,
                definitions,
                plan_step_count=len(plan.steps),
            )
        )
        return errors

    @staticmethod
    def _parallel_errors(
        steps: list[Any],
        definitions: dict[str, Any],
        *,
        plan_step_count: int,
    ) -> list[dict[str, Any]]:
        if not steps:
            return []
        if len(steps) == 1 and plan_step_count > 1:
            step = steps[0]
            return [
                {
                    "type": "runtime_parallel_singleton_group",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            ]
        errors: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            definition = definitions.get(step.step_id)
            if definition is None:
                continue
            if not definition.can_run_parallel:
                errors.append(
                    {
                        "type": "runtime_parallel_not_supported",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                    }
                )
            left_group = str(definition.exclusive_group or "")
            left_resources = {
                str(item) for item in definition.metadata.get("resource_claims", []) if str(item)
            }
            for other in steps[index + 1 :]:
                other_definition = definitions.get(other.step_id)
                if other_definition is None:
                    continue
                right_group = str(other_definition.exclusive_group or "")
                right_resources = {
                    str(item)
                    for item in other_definition.metadata.get("resource_claims", [])
                    if str(item)
                }
                if left_group and right_group and left_group == right_group:
                    errors.append(
                        {
                            "type": "runtime_parallel_exclusive_group_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "exclusive_group": left_group,
                        }
                    )
                overlap = sorted(left_resources.intersection(right_resources))
                if overlap:
                    errors.append(
                        {
                            "type": "runtime_parallel_resource_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "resources": overlap,
                        }
                    )
        return errors

    @staticmethod
    def _attention_target_error(attention: Any, context: dict[str, Any]) -> str | None:
        target = attention.target
        if target.source == "none":
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "attention_target_not_available"
        if str(evidence.get("source") or "") != target.source:
            return "attention_target_source_mismatch"
        evidence_target = evidence.get("target")
        if not isinstance(evidence_target, dict):
            return "attention_target_not_available"
        expected_ref = str(evidence_target.get("target_ref") or "").strip()
        if expected_ref and expected_ref != target.target_ref:
            return "attention_target_ref_mismatch"
        expected_direction = str(evidence_target.get("relative_direction") or "").strip()
        claimed_direction = str(target.relative_direction or "").strip()
        if expected_direction and claimed_direction and expected_direction != claimed_direction:
            return "attention_target_direction_mismatch"
        return None

    @staticmethod
    def _attention_target_args_error(
        args: dict[str, Any],
        schema: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        semantic_keys = {"direction", "relative_direction", "target_ref"}
        if not semantic_keys.intersection(args):
            return None
        evidence = context.get("social_attention_target_evidence")
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "targeted_behavior_requires_semantic_evidence"
        target = evidence.get("target")
        if not isinstance(target, dict):
            return "targeted_behavior_requires_semantic_evidence"
        expected_direction = str(target.get("relative_direction") or "").strip()
        actual_direction = str(
            args.get("relative_direction") or args.get("direction") or ""
        ).strip()
        if expected_direction and actual_direction and expected_direction != actual_direction:
            return "direction_mismatch"
        expected_ref = str(target.get("target_ref") or "").strip()
        actual_ref = str(args.get("target_ref") or "").strip()
        if expected_ref and actual_ref and expected_ref != actual_ref:
            return "target_ref_mismatch"
        return None

    @staticmethod
    def _attention_conflicts_with_primary(
        social_definition: Any,
        timing: str,
        primary_definitions: dict[str, Any],
    ) -> bool:
        if not primary_definitions:
            return False
        if timing != "parallel" or not social_definition.can_run_parallel:
            return True
        if social_definition.metadata.get("parallel_metadata_declared") is not True:
            return True
        social_group = str(social_definition.exclusive_group or "")
        social_resources = {
            str(item) for item in social_definition.metadata.get("resource_claims", []) if str(item)
        }
        for definition in primary_definitions.values():
            if not definition.can_run_parallel:
                return True
            if definition.metadata.get("parallel_metadata_declared") is not True:
                return True
            primary_group = str(definition.exclusive_group or "")
            if social_group and primary_group and social_group == primary_group:
                return True
            primary_resources = {
                str(item) for item in definition.metadata.get("resource_claims", []) if str(item)
            }
            if social_resources.intersection(primary_resources):
                return True
        return False

    async def execute_social_attention_event(
        self,
        *,
        plan: SocialAttentionPlan,
        session_id: str,
        turn_id: str,
        event: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate and execute one background Social-Attention decoration proposal.

        This path has no Goal-completion authority and never waits on or rewrites
        the primary response.  It reuses the same Trusted Capability Runtime as
        ordinary Activity work.
        """

        if self.social_attention_mode != "on" or plan.decision != "express":
            return {
                "status": "not_executed",
                "decision": plan.decision,
                "event": event,
                "materialized_count": 0,
            }
        runtime_context = dict(context or {})
        try:
            primary_activity = SocialAttentionActivityAnchor.model_validate(
                runtime_context.get("social_attention_primary_activity")
            )
        except (ValidationError, TypeError, ValueError):
            return {
                "status": "rejected",
                "decision": plan.decision,
                "event": event,
                "materialized_count": 0,
                "reasons": ["missing_or_invalid_primary_activity_anchor"],
            }
        target_error = self._attention_target_error(plan, runtime_context)
        if target_error:
            return {
                "status": "rejected",
                "decision": plan.decision,
                "event": event,
                "materialized_count": 0,
                "reasons": [target_error],
            }

        requests: list[SkillRequest] = []
        reasons: list[str] = []
        interaction_state = runtime_context.get("social_attention_interaction_state")
        if not isinstance(interaction_state, dict):
            interaction_state = {}
        raw_primary_ids = interaction_state.get("primary_capability_ids")
        primary_capability_ids = {
            str(item).strip()
            for item in raw_primary_ids
            if str(item).strip()
        } if isinstance(raw_primary_ids, list) else set()
        primary_definitions: dict[str, Any] = {}
        unresolved_embodied_primary_ids: set[str] = set()
        for capability_id in sorted(primary_capability_ids):
            try:
                await self.interaction_runtime.ensure_skill_definitions([capability_id])
                primary_definition = self.interaction_runtime.skill_definition(capability_id)
            except (TypeError, ValueError, ValidationError, RuntimeError):
                if capability_id.startswith("soridormi."):
                    unresolved_embodied_primary_ids.add(capability_id)
                continue
            primary_metadata = (
                primary_definition.metadata
                if isinstance(primary_definition.metadata, dict)
                else {}
            )
            primary_effects = {
                str(item).strip().lower()
                for item in primary_metadata.get("effects", [])
                if str(item).strip()
            }
            if capability_id.startswith("soridormi.") or primary_effects.intersection(
                {"physical_motion", "visual_expression", "social_expression"}
            ):
                primary_definitions[capability_id] = primary_definition
        seen: set[str] = set()
        for index, behavior in enumerate(plan.behaviors):
            try:
                if behavior.skill_id in primary_capability_ids:
                    reasons.append(
                        f"duplicates_primary_activity:{behavior.skill_id}"
                    )
                    continue
                if unresolved_embodied_primary_ids:
                    reasons.extend(
                        f"primary_definition_unavailable:{capability_id}"
                        for capability_id in sorted(unresolved_embodied_primary_ids)
                    )
                    continue
                await self.interaction_runtime.ensure_skill_definitions([behavior.skill_id])
                definition = self.interaction_runtime.skill_definition(behavior.skill_id)
                metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
                domains = {
                    str(item).strip().lower()
                    for item in metadata.get("behavior_domains", [])
                    if str(item).strip()
                }
                if "social_attention" not in domains:
                    reasons.append(f"not_social_attention:{behavior.skill_id}")
                    continue
                if behavior.skill_id in seen:
                    reasons.append(f"duplicate_social_skill:{behavior.skill_id}")
                    continue
                if not definition.available:
                    reasons.append(f"unavailable:{behavior.skill_id}")
                    continue
                if definition.requires_confirmation:
                    reasons.append(f"confirmation_required:{behavior.skill_id}")
                    continue
                if behavior.timing != "parallel":
                    reasons.append(f"auxiliary_must_be_parallel:{behavior.skill_id}")
                    continue
                if not definition.can_run_parallel:
                    reasons.append(f"parallel_not_supported:{behavior.skill_id}")
                    continue
                if (
                    behavior.skill_id.startswith("soridormi.")
                    and metadata.get("parallel_metadata_declared") is not True
                ):
                    reasons.append(f"parallel_metadata_missing:{behavior.skill_id}")
                    continue
                if self._attention_conflicts_with_primary(
                    definition,
                    behavior.timing,
                    primary_definitions,
                ):
                    reasons.append(f"resource_conflict:{behavior.skill_id}")
                    continue
                schema_errors = validate_args_for_schema(behavior.args, definition.input_schema)
                if schema_errors:
                    reasons.append(f"invalid_args:{behavior.skill_id}")
                    continue
                target_args_error = self._attention_target_args_error(
                    behavior.args,
                    definition.input_schema,
                    runtime_context,
                )
                if target_args_error:
                    reasons.append(
                        f"target_error:{behavior.skill_id}:{target_args_error}"
                    )
                    continue
                schema_digest = output_schema_sha256(definition.output_schema)
                digest = hashlib.sha256(
                    f"{turn_id}|{primary_activity.activity_id}|{event}|{index}|{behavior.skill_id}".encode("utf-8")
                ).hexdigest()[:20]
                request = SkillRequest(
                    request_id=f"social_{digest}",
                    skill_id=behavior.skill_id,
                    skill_version=definition.version,
                    args=dict(behavior.args),
                    timing="parallel",
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=False,
                    idempotency_key=(
                        f"{turn_id}:social:{primary_activity.activity_id}:{event}:{index}"
                    ),
                    committed_output_schema_sha256=schema_digest,
                    metadata={
                        "source": "social_attention_plan",
                        "auxiliary_social_attention": True,
                        "behavior_domain": "social_attention",
                        "interaction_role": "auxiliary_expression",
                        "social_attention_event": event,
                        "social_attention_purpose": plan.purpose,
                        "social_function": behavior.social_function,
                        "target": plan.target.model_dump(mode="json", exclude_none=True),
                        "reason": behavior.reason,
                        "social_attention_policy_mode": self.social_attention_mode,
                        "execution_lane": "activity",
                        "execution_role": "social_decoration",
                        "source_goal_ids": [],
                        "turn_id": turn_id,
                        "primary_activity_id": primary_activity.activity_id,
                        "primary_activity_kind": primary_activity.kind,
                    },
                )
                requests.append(request)
                self._record_auxiliary_behavior_request(request, session_id=session_id)
                seen.add(behavior.skill_id)
            except (TypeError, ValueError, ValidationError, RuntimeError) as exc:
                reasons.append(f"invalid:{behavior.skill_id}:{type(exc).__name__}")

        if not requests:
            return {
                "status": "rejected" if reasons else "not_executed",
                "decision": plan.decision,
                "event": event,
                "materialized_count": 0,
                "reasons": reasons,
            }
        interaction_id = (
            f"social_{turn_id}_"
            f"{hashlib.sha256(primary_activity.activity_id.encode('utf-8')).hexdigest()[:10]}"
        )
        response_metadata: dict[str, Any] = {
            "source": "continuous_social_attention",
            "auxiliary_social_attention": True,
            "turn_id": turn_id,
            "session_id": session_id,
            "social_attention_event": event,
            "primary_activity_id": primary_activity.activity_id,
            "primary_activity_kind": primary_activity.kind,
        }
        envelope = runtime_context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            response_metadata["user_turn_envelope"] = dict(envelope)
        response = InteractionResponse(
            interaction_id=interaction_id,
            status="ok",
            skills=requests,
            metadata=response_metadata,
        )
        execution = await self.interaction_runtime.execute(
            response,
            session_id=session_id,
        )
        return {
            "status": execution.status,
            "decision": plan.decision,
            "event": event,
            "materialized_count": len(requests),
            "request_ids": [item.request_id for item in requests],
            "reasons": reasons,
        }

    def build_adopted_native_response(
        self,
        *,
        association: GoalAssociationResolution,
        candidates: dict[str, CognitiveProgressCandidate],
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse | None:
        """Compile GA-bound native conversation into canonical Vocal work.

        Goal Association owns the binding; the Host only verifies complete,
        non-overlapping spoken-Goal coverage and preserves the Core-authored text.
        No response text is invented or rewritten here.
        """

        if association.clarification or association.associations or not association.new_goals:
            return None
        goal_ids = [
            str(goal.goal_id or "").strip()
            for goal in association.new_goals
            if str(goal.goal_id or "").strip()
        ]
        if len(goal_ids) != len(association.new_goals) or not goal_ids:
            return None
        if any(
            str((goal.metadata or {}).get("responsibility_kind") or "")
            != "vocal_output"
            or bool((goal.metadata or {}).get("provider_required"))
            for goal in association.new_goals
        ):
            return None

        goal_order = {goal_id: index for index, goal_id in enumerate(goal_ids)}
        rows: list[tuple[int, CognitiveProgressCandidate, list[str]]] = []
        covered: set[str] = set()
        for binding in association.progress_bindings:
            candidate = candidates.get(binding.candidate_id)
            if candidate is None or candidate.kind != "native_response":
                return None
            bound_goal_ids = [goal_id for goal_id in binding.goal_ids if goal_id in goal_order]
            if len(bound_goal_ids) != len(binding.goal_ids) or not bound_goal_ids:
                return None
            if covered.intersection(bound_goal_ids):
                return None
            covered.update(bound_goal_ids)
            rows.append(
                (
                    min(goal_order[goal_id] for goal_id in bound_goal_ids),
                    candidate,
                    bound_goal_ids,
                )
            )
        if covered != set(goal_ids) or not rows:
            return None

        fingerprint = goal_association_fingerprint(association)
        runtime_context = context if isinstance(context, dict) else {}
        envelope = runtime_context.get("user_turn_envelope")
        turn_id = (
            str(envelope.get("turn_id") or session_id)
            if isinstance(envelope, dict)
            else session_id
        )
        speech: list[InteractionSpeech] = []
        for _, candidate, bound_goal_ids in sorted(rows, key=lambda item: item[0]):
            speech_digest = hashlib.sha256(
                f"{fingerprint}|native|{candidate.candidate_id}".encode("utf-8")
            ).hexdigest()[:20]
            speech.append(
                InteractionSpeech(
                    id=f"speech_native_{speech_digest}",
                    text=candidate.response_text,
                    timing="immediate",
                    style="brief",
                    metadata={
                        "source": "core_native_response_readiness",
                        "turn_id": turn_id,
                        "phase": "final",
                        "speech_act": candidate.speech_act,
                        "commitment_state": "completed",
                        "must_not_claim_completion": False,
                        "covers_goal_ids": list(bound_goal_ids),
                        "source_goal_ids": list(bound_goal_ids),
                        "goal_association_fingerprint": fingerprint,
                        "claims": [],
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                        "planless_direct_response": True,
                        "native_response_readiness_adoption": True,
                        "progress_candidate_id": candidate.candidate_id,
                        "transient_responsibility": bool(
                            runtime_context.get("transient_responsibility_ids")
                        ),
                        "execution_lane": "vocal",
                        "delivery_role": "response",
                    },
                )
            )

        transient_ids = [
            str(item).strip()
            for item in runtime_context.get("transient_responsibility_ids", [])
            if str(item).strip()
        ]
        metadata: dict[str, Any] = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "planless_direct_response": True,
            "native_response_readiness_adoption": True,
            "transient_responsibility": bool(transient_ids),
            "transient_responsibility_ids": transient_ids,
            "goal_association": association.model_dump(mode="json", exclude_none=True),
            "goal_association_fingerprint": fingerprint,
            "execution_lanes": {
                "vocal": "response_delivery",
                "activity": "idle",
            },
            "lane_coordination_groups": [],
            "planning_result": "direct_response",
            "capability_decision": "respond",
            "goal_ids": goal_ids,
            "planner_tier": "none",
            "native_response_progress_ids": [
                candidate.candidate_id for _, candidate, _ in sorted(rows, key=lambda item: item[0])
            ],
            "operational_speech_authority": "core_native_response_readiness",
        }
        if isinstance(runtime_context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = runtime_context["user_turn_envelope"]
        return InteractionResponse(
            interaction_id=f"cognitive_{session_id}",
            status="ok",
            speech=speech,
            metadata=metadata,
        )

    async def build_direct_response(
        self,
        *,
        composition: DirectResponseComposition,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        association = composition.goal_association
        fingerprint = goal_association_fingerprint(association)
        if composition.goal_association_fingerprint != fingerprint:
            raise ValueError("direct response goal-association fingerprint mismatch")
        final = composition.response_plan.final
        if final is None:
            raise ValueError("direct response requires a final speech stage")
        goal_ids = [
            str(goal.goal_id or "").strip()
            for goal in association.new_goals
            if str(goal.goal_id or "").strip()
        ]
        runtime_context = context if isinstance(context, dict) else {}
        envelope = runtime_context.get("user_turn_envelope")
        turn_id = (
            str(envelope.get("turn_id") or session_id)
            if isinstance(envelope, dict)
            else session_id
        )
        speech = [
            InteractionSpeech(
                text=final.text,
                timing="immediate",
                style="brief",
                metadata={
                    "source": "goal_driven_response_composer",
                    "turn_id": turn_id,
                    "phase": "final",
                    "speech_act": final.speech_act,
                    "commitment_state": final.commitment_state,
                    "must_not_claim_completion": (final.must_not_claim_completion),
                    "covers_goal_ids": list(final.covers_goal_ids),
                    "source_goal_ids": list(final.covers_goal_ids),
                    "goal_association_fingerprint": fingerprint,
                    "claims": list(final.claims),
                    "wait_for_playback_start": True,
                    "playback_start_required_for_delivery": True,
                    "planless_direct_response": True,
                    "execution_lane": "vocal",
                    "delivery_role": "response",
                },
            )
        ]

        skills: list[SkillRequest] = []

        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "planless_direct_response": True,
            "goal_association": association.model_dump(mode="json", exclude_none=True),
            "goal_association_fingerprint": fingerprint,
            "response_composition": composition.model_dump(mode="json", exclude_none=True),
            "execution_lanes": {
                "vocal": "response_delivery",
                "activity": "idle",
            },
            "lane_coordination_groups": [],
            "planning_result": "direct_response",
            "capability_decision": "respond",
            "goal_ids": goal_ids,
            "planner_tier": "none",
            "operational_speech_authority": "llm_direct_response",
        }
        if isinstance(runtime_context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = runtime_context["user_turn_envelope"]
        response = InteractionResponse(
            interaction_id=f"cognitive_{session_id}",
            status="ok",
            speech=speech,
            skills=skills,
            metadata=metadata,
        )
        return response

    async def build_execution_only_response(
        self,
        *,
        plan: CanonicalPlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Materialize a pure safe-read Plan without a presentation-model barrier."""

        fingerprint = canonical_plan_fingerprint(plan)
        composition = CoordinatedResponsePlan(
            composition_id=f"execution_only_{fingerprint[:20]}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan,
            response_plan=ResponsePlan(),
            lane_coordination=[],
            confidence=1.0,
            rationale="Pure safe-read execution does not require pre-evidence response composition.",
            metadata={
                "authority": "advisory",
                "resolver": "readiness_execution",
                "task_plan_immutable": True,
                "safe_read_speech_optional": True,
            },
        )
        return await self.build_response(
            plan=plan,
            composition=composition,
            session_id=session_id,
            language=language,
            context=context,
        )

    async def build_response(
        self,
        *,
        plan: CanonicalPlan,
        composition: CoordinatedResponsePlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="build_response",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "speech_stage_count": sum(
                    1
                    for item in (
                        composition.response_plan.immediate,
                        composition.response_plan.pre_action,
                        composition.response_plan.final,
                    )
                    if item is not None
                )
                + len(composition.response_plan.progress),
            },
        ) as span:
            response = await self._build_response(
                plan=plan,
                composition=composition,
                session_id=session_id,
                language=language,
                context=context,
            )
            span.set_attribute("response_status", response.status)
            span.set_attribute("speech_count", len(response.speech))
            span.set_attribute("skill_count", len(response.skills))
            if response.status == "error":
                span.set_status("error")
            return response

    async def _build_response(
        self,
        *,
        plan: CanonicalPlan,
        composition: CoordinatedResponsePlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        if composition.canonical_plan_id != plan.plan_id:
            raise ValueError("response composition references a different canonical plan")
        if composition.canonical_plan_fingerprint != canonical_plan_fingerprint(plan):
            raise ValueError("response composition canonical-plan fingerprint mismatch")
        errors = await self.validation_errors(plan)
        if errors:
            raise ValueError(
                "runtime canonical-plan validation failed: "
                + json.dumps(errors, ensure_ascii=False)
            )

        fingerprint = canonical_plan_fingerprint(plan)
        runtime_context = context if isinstance(context, dict) else {}
        envelope = runtime_context.get("user_turn_envelope")
        turn_id = (
            str(envelope.get("turn_id") or session_id)
            if isinstance(envelope, dict)
            else session_id
        )
        alternative = str(plan.metadata.get("plan_relation") or "") in {
            "alternative",
            "safe_adjustment",
        } or bool(plan.metadata.get("user_confirmation_required"))
        executable_goal_ids = set(plan.executable_goal_ids())
        confirmation_goal_ids = set(executable_goal_ids) if alternative else set()
        if not alternative:
            for step in plan.steps:
                definition = self.interaction_runtime.skill_definition(step.skill_id)
                if definition.requires_confirmation:
                    confirmation_goal_ids.update(step.source_goal_ids)

        response_plan = composition.response_plan
        lane_coordination_by_id = {
            item.coordination_id: item for item in composition.lane_coordination
        }
        activity_coordination_by_step_id = {
            step_id: item
            for item in composition.lane_coordination
            for step_id in item.activity_step_ids
        }
        vocal_coordination_by_step_id = {
            step_id: item
            for item in composition.lane_coordination
            for step_id in item.vocal_step_ids
        }
        plan_steps_by_id = {step.step_id: step for step in plan.steps}
        media_mixer_by_coordination_id: dict[str, dict[str, Any]] = {}
        for coordination in composition.lane_coordination:
            if "vocal" not in coordination.lanes:
                continue
            media_step_ids = [
                step_id
                for step_id in coordination.activity_step_ids
                if plan_steps_by_id[step_id].capability_id in MEDIA_CAPABILITY_IDS.values()
            ]
            if not media_step_ids:
                continue
            mixer_contracts: list[dict[str, Any]] = []
            for step_id in media_step_ids:
                definition = self.interaction_runtime.skill_definition(
                    plan_steps_by_id[step_id].skill_id
                )
                if definition.metadata.get("mixer_policy") != ("duck_media_during_vocal"):
                    raise ValueError(
                        "speech-over-media coordination requires the declared "
                        "duck_media_during_vocal mixer policy: " + step_id
                    )
                try:
                    mixer_contracts.append(
                        {
                            "media_mixer_policy": "duck_media_during_vocal",
                            "media_ducking_gain_db": float(definition.metadata["ducking_gain_db"]),
                            "media_duck_attack_ms": int(definition.metadata["duck_attack_ms"]),
                            "media_duck_release_ms": int(definition.metadata["duck_release_ms"]),
                        }
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "speech-over-media coordination requires a complete "
                        "ducking gain and timing contract: " + step_id
                    ) from exc
            mixer_contract = mixer_contracts[0]
            if any(item != mixer_contract for item in mixer_contracts[1:]):
                raise ValueError(
                    "speech-over-media coordination requires one unambiguous mixer contract"
                )
            media_mixer_by_coordination_id[coordination.coordination_id] = {
                **mixer_contract,
                "media_ducking_required": True,
                "coordinated_media_step_ids": media_step_ids,
            }
        stage_items = [
            ("immediate", response_plan.immediate),
            ("pre_action", response_plan.pre_action),
            *[("progress", item) for item in response_plan.progress],
            ("final", response_plan.final),
        ]
        effectful_pre_execution = plan.disposition in {"execute", "mixed"} and bool(plan.steps)
        executable_definitions = (
            [self.interaction_runtime.skill_definition(step.skill_id) for step in plan.steps]
            if effectful_pre_execution
            else []
        )
        read_only_plan = bool(executable_definitions) and all(
            str((definition.metadata or {}).get("safety_class") or "") == "safe_read"
            for definition in executable_definitions
        )
        safe_read_parallel = (
            effectful_pre_execution and read_only_plan and not confirmation_goal_ids
        )
        safe_read_speech_optional = (
            safe_read_parallel
            and plan.disposition == "execute"
            and executable_goal_ids == set(plan.goal_ids)
        )
        reusable_turn_speech: dict[str, dict[str, Any]] = {}
        if isinstance(context, dict):
            # A speech-event identity selects the conversational act. Text is
            # checked later only as payload integrity, never as de-duplication
            # identity. Prefer playback-qualified evidence when both projections
            # contain the same event.
            for key in ("scheduled_turn_speech", "delivered_turn_speech"):
                values = context.get(key)
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    event_id = " ".join(
                        str(item.get("event_id") or item.get("speech_event_id") or "")
                        .strip()
                        .split()
                    )
                    status = str(item.get("status") or "").strip()
                    if event_id and status in {
                        "scheduled",
                        "playback_started",
                        "playback_completed",
                    }:
                        reusable_turn_speech[event_id] = dict(item)
        omitted_pre_execution_speech_phases: list[str] = []
        projected_speech_stages: list[dict[str, Any]] = []
        if effectful_pre_execution:
            required_goal_ids = set(plan.goal_ids)
            immediate_item = (
                ("immediate", response_plan.immediate)
                if response_plan.immediate is not None
                else None
            )
            pre_action_item = (
                ("pre_action", response_plan.pre_action)
                if response_plan.pre_action is not None
                else None
            )
            available_pre_execution = [
                item for item in (immediate_item, pre_action_item) if item is not None
            ]
            covered_pre_execution = {
                goal_id for _, stage in available_pre_execution for goal_id in stage.covers_goal_ids
            }

            # A safe, read-only lookup may start immediately without any spoken
            # acknowledgement. If the response model supplied a tiny natural
            # acknowledgement, it is optional and runs in parallel with the lookup.
            # Effectful or confirmation-gated work retains the delivery barrier.
            if safe_read_parallel:
                if not safe_read_speech_optional and not available_pre_execution:
                    raise ValueError(
                        "mixed safe-read execution requires response speech for "
                        "its non-executing goals"
                    )
                if available_pre_execution and not required_goal_ids.issubset(
                    covered_pre_execution
                ):
                    raise ValueError(
                        "safe-read pre-execution speech, when present, must cover "
                        "all canonical goals"
                    )
                if pre_action_item is not None and required_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    stage_items = [pre_action_item]
                elif immediate_item is not None and required_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    stage_items = [immediate_item]
                else:
                    stage_items = []
            else:
                if not available_pre_execution or not required_goal_ids.issubset(
                    covered_pre_execution
                ):
                    raise ValueError(
                        "effectful pre-execution response requires immediate and/or "
                        "pre_action stages covering all canonical goals"
                    )

                if pre_action_item is not None and required_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    stage_items = [pre_action_item]
                elif immediate_item is not None and required_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    stage_items = [immediate_item]
                else:
                    stage_items = list(available_pre_execution)

            selected_keys = {(phase, id(stage)) for phase, stage in stage_items}
            omitted_pre_execution_speech_phases = [
                phase
                for phase, stage in (
                    ("immediate", response_plan.immediate),
                    ("pre_action", response_plan.pre_action),
                    *[("progress", item) for item in response_plan.progress],
                    ("final", response_plan.final),
                )
                if stage is not None and (phase, id(stage)) not in selected_keys
            ]

            model_pre_execution = next(
                (
                    (phase, stage)
                    for phase, stage in stage_items
                    if stage is not None and required_goal_ids.issubset(set(stage.covers_goal_ids))
                ),
                None,
            )

            confirmation_stages = [
                stage
                for _, stage in stage_items
                if stage is not None
                and stage.speech_act.casefold() == "ask_confirmation"
                and stage.commitment_state == "waiting_for_user"
            ]
            confirmation_stage_goal_ids = {
                goal_id for stage in confirmation_stages for goal_id in stage.covers_goal_ids
            }
            if confirmation_goal_ids and not confirmation_goal_ids.issubset(
                confirmation_stage_goal_ids
            ):
                raise ValueError(
                    "confirmation-bound execution requires model-authored "
                    "ask_confirmation speech covering every confirmation goal"
                )
            if (
                not confirmation_goal_ids
                and plan.disposition == "execute"
                and any(
                    stage is not None
                    and (
                        stage.speech_act.casefold() == "ask_confirmation"
                        or stage.commitment_state == "waiting_for_user"
                    )
                    for _, stage in stage_items
                )
            ):
                raise ValueError(
                    "execution response requests confirmation without a runtime "
                    "confirmation requirement"
                )

            if safe_read_parallel:
                if model_pre_execution is not None:
                    phase, stage = model_pre_execution
                    projected_speech_stages = [
                        {
                            "phase": phase,
                            "text": stage.text,
                            "speech_act": stage.speech_act,
                            "commitment_state": stage.commitment_state,
                            "must_not_claim_completion": True,
                            "covers_goal_ids": list(stage.covers_goal_ids),
                            "claims": stage.claims,
                            "source": "goal_driven_response_composer",
                            "operational_text_source": "llm_wording_runtime_validated",
                            "runtime_confirmation_required": False,
                            "safe_read_micro_ack": safe_read_speech_optional,
                            "coordination_id": stage.coordination_id,
                            "delivery_role": stage.delivery_role,
                            "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                            "reused_speech_event_id": stage.reused_speech_event_id,
                        }
                    ]
                else:
                    projected_speech_stages = []
            else:
                projected_speech_stages = [
                    {
                        "phase": phase,
                        "text": stage.text,
                        "speech_act": stage.speech_act,
                        "commitment_state": stage.commitment_state,
                        "must_not_claim_completion": (stage.must_not_claim_completion),
                        "covers_goal_ids": list(stage.covers_goal_ids),
                        "claims": list(stage.claims),
                        "source": "goal_driven_response_composer",
                        "operational_text_source": ("llm_wording_runtime_validated"),
                        "runtime_confirmation_required": (
                            bool(confirmation_goal_ids) and stage in confirmation_stages
                        ),
                        "coordination_id": stage.coordination_id,
                        "delivery_role": stage.delivery_role,
                        "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                        "reused_speech_event_id": stage.reused_speech_event_id,
                    }
                    for phase, stage in stage_items
                    if stage is not None
                ]
        else:
            projected_speech_stages = [
                {
                    "phase": phase,
                    "text": stage.text,
                    "speech_act": stage.speech_act,
                    "commitment_state": stage.commitment_state,
                    "must_not_claim_completion": stage.must_not_claim_completion,
                    "covers_goal_ids": stage.covers_goal_ids,
                    "claims": stage.claims,
                    "source": "goal_driven_response_composer",
                    "coordination_id": stage.coordination_id,
                    "delivery_role": stage.delivery_role,
                    "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                    "reused_speech_event_id": stage.reused_speech_event_id,
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        speech: list[InteractionSpeech] = []
        for projected in projected_speech_stages:
            phase = str(projected["phase"])
            coordination_id = str(projected.get("coordination_id") or "").strip()
            coordination = lane_coordination_by_id.get(coordination_id)
            coordinated_speech = bool(coordination is not None and "vocal" in coordination.lanes)
            playback_barrier = (
                projected.get("reuse_current_turn_speech") is True
                or (not safe_read_parallel and not coordinated_speech)
            )
            speech_metadata = {
                "source": projected["source"],
                "turn_id": turn_id,
                "phase": phase,
                "speech_act": projected["speech_act"],
                "commitment_state": projected["commitment_state"],
                "must_not_claim_completion": projected["must_not_claim_completion"],
                "covers_goal_ids": projected["covers_goal_ids"],
                "source_goal_ids": projected["covers_goal_ids"],
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "claims": projected["claims"],
                "execution_lane": "vocal",
                "delivery_role": projected.get("delivery_role", "response"),
                "wait_for_playback_start": playback_barrier,
                "playback_start_required_for_delivery": playback_barrier,
            }
            if projected.get("reuse_current_turn_speech") is True:
                reused_event_id = " ".join(
                    str(projected.get("reused_speech_event_id") or "").strip().split()
                )
                reused = reusable_turn_speech.get(reused_event_id)
                if reused is None:
                    raise ValueError(
                        "response stage requested current-turn speech reuse but "
                        "no exact scheduled or delivered speech event exists"
                    )
                normalized_text = " ".join(str(projected.get("text") or "").strip().split())
                reused_text = " ".join(str(reused.get("text") or "").strip().split())
                if normalized_text != reused_text:
                    raise ValueError(
                        "response stage text does not match the referenced "
                        "current-turn speech event"
                    )
                reused_goal_ids = {
                    normalized
                    for item in reused.get("source_goal_ids") or []
                    if (normalized := " ".join(str(item or "").strip().split()))
                }
                reassigned_goal_ids = (
                    set(projected.get("covers_goal_ids") or []) - reused_goal_ids
                )
                if reused_goal_ids and reassigned_goal_ids:
                    raise ValueError(
                        "Goal-bound current-turn speech cannot be reassigned to "
                        "unrelated canonical Goals: "
                        + ", ".join(sorted(reassigned_goal_ids))
                    )
                reused_plan_id = " ".join(
                    str(reused.get("canonical_plan_id") or "").strip().split()
                )
                if reused_plan_id and reused_plan_id != plan.plan_id:
                    raise ValueError(
                        "reused current-turn speech references a different "
                        "canonical plan"
                    )
                reused_plan_fingerprint = " ".join(
                    str(reused.get("canonical_plan_fingerprint") or "")
                    .strip()
                    .split()
                )
                if reused_plan_fingerprint and reused_plan_fingerprint != fingerprint:
                    raise ValueError(
                        "reused current-turn speech canonical-plan fingerprint "
                        "mismatch"
                    )
                raw_orders = reused.get("orders")
                if not isinstance(raw_orders, list):
                    raw_orders = []
                speech_metadata.update(
                    {
                        "reuse_current_turn_speech": True,
                        "reused_speech_event_id": reused_event_id,
                        "reused_speech_status": reused.get("status"),
                        "reused_speech_generation": reused.get("generation"),
                        "reused_speech_orders": [
                            int(item) for item in raw_orders if isinstance(item, int)
                        ],
                    }
                )
            if coordinated_speech and coordination is not None:
                speech_metadata.update(
                    {
                        "coordination_id": coordination.coordination_id,
                        "lane_coordination_relation": coordination.relation,
                        "lane_start_policy": coordination.start_policy,
                        "lane_failure_policy": coordination.failure_policy,
                        "parallel_with_activity": "activity" in coordination.lanes,
                        "playback_start_required_for_effects": False,
                    }
                )
                mixer_contract = media_mixer_by_coordination_id.get(coordination.coordination_id)
                if mixer_contract is not None:
                    speech_metadata.update(mixer_contract)
            elif safe_read_parallel:
                speech_metadata.update(
                    {
                        "safe_read_micro_ack": safe_read_speech_optional,
                        "parallel_with_safe_read": True,
                        "playback_start_required_for_effects": False,
                    }
                )
            elif effectful_pre_execution:
                speech_metadata["playback_start_required_for_effects"] = True
            for key in (
                "operational_text_source",
                "runtime_confirmation_required",
            ):
                if key in projected:
                    speech_metadata[key] = projected[key]
            speech.append(
                InteractionSpeech(
                    text=str(projected["text"]),
                    timing=(
                        "parallel"
                        if safe_read_parallel or coordinated_speech
                        else "immediate"
                        if phase == "immediate"
                        else "sequential"
                    ),
                    style="brief",
                    metadata=speech_metadata,
                )
            )

        skills: list[SkillRequest] = []
        for step in plan.steps:
            definition = self.interaction_runtime.skill_definition(step.skill_id)
            execution_lane = str(definition.metadata.get("execution_lane") or "activity").strip()
            if execution_lane not in {"vocal", "activity"}:
                raise ValueError(
                    "canonical plan capability has unsupported execution lane: "
                    f"{step.skill_id}={execution_lane!r}"
                )
            if (
                step.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
                and execution_lane != "vocal"
            ):
                raise ValueError(
                    "exact vocal performance capability must remain in the vocal lane"
                )
            if step.capability_id in MEDIA_CAPABILITY_IDS.values() and execution_lane != "activity":
                raise ValueError(
                    "exact media playback capabilities must remain in the activity lane"
                )
            coordination = (
                vocal_coordination_by_step_id.get(step.step_id)
                if execution_lane == "vocal"
                else activity_coordination_by_step_id.get(step.step_id)
            )
            wrong_lane_coordination = (
                activity_coordination_by_step_id.get(step.step_id)
                if execution_lane == "vocal"
                else vocal_coordination_by_step_id.get(step.step_id)
            )
            if wrong_lane_coordination is not None:
                raise ValueError(
                    "lane coordination step membership contradicts trusted "
                    f"capability execution_lane={execution_lane}: {step.step_id}"
                )
            if coordination is not None:
                if not definition.can_run_parallel:
                    raise ValueError("cross-lane capability is not parallel-safe: " + step.skill_id)
                if definition.metadata.get("parallel_metadata_declared") is not True:
                    raise ValueError(
                        "cross-lane capability lacks explicit parallel metadata: " + step.skill_id
                    )
            coordination_metadata = (
                {
                    "coordination_id": coordination.coordination_id,
                    "lane_coordination_relation": coordination.relation,
                    "lane_start_policy": coordination.start_policy,
                    "lane_failure_policy": coordination.failure_policy,
                    "parallel_with_vocal": (
                        execution_lane != "vocal" and "vocal" in coordination.lanes
                    ),
                    "parallel_with_activity": (
                        execution_lane != "activity" and "activity" in coordination.lanes
                    ),
                }
                if coordination is not None
                else {}
            )
            media_mixer_metadata: dict[str, Any] = {}
            if (
                coordination is not None
                and step.capability_id in MEDIA_CAPABILITY_IDS.values()
                and "vocal" in coordination.lanes
            ):
                media_mixer_metadata = dict(
                    media_mixer_by_coordination_id[coordination.coordination_id]
                )
            digest = hashlib.sha256(f"{fingerprint}|{step.step_id}".encode("utf-8")).hexdigest()[
                :20
            ]
            skills.append(
                SkillRequest(
                    request_id=f"cogreq_{digest}",
                    skill_id=step.skill_id,
                    skill_version=definition.version,
                    args=step.args,
                    timing="parallel" if safe_read_parallel else step.timing,
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=(bool(definition.requires_confirmation) or alternative),
                    idempotency_key=f"{plan.plan_id}:{step.step_id}:{fingerprint[:16]}",
                    committed_output_schema_sha256=output_schema_sha256(definition.output_schema),
                    metadata={
                        **step.metadata,
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                        "planner_tier": plan.planner_tier,
                        "step_id": step.step_id,
                        "source_goal_ids": step.source_goal_ids,
                        "reason_summary": step.reason_summary,
                        "language": language,
                        "effects": list(definition.metadata.get("effects") or []),
                        "safety_class": str(definition.metadata.get("safety_class") or ""),
                        "effectful": str(definition.metadata.get("safety_class") or "")
                        not in {"safe_read", "planning_only"},
                        "retryable_safe_read": safe_read_parallel,
                        "execution_lane": execution_lane,
                        "parallel_with_vocal": (
                            safe_read_parallel
                            or bool(coordination_metadata.get("parallel_with_vocal"))
                        ),
                        **coordination_metadata,
                        **media_mixer_metadata,
                        "canonical_timing": step.timing,
                        "effective_timing": ("parallel" if safe_read_parallel else step.timing),
                        "runtime_timing_adjustment": (
                            "safe_read_parallel"
                            if safe_read_parallel and step.timing != "parallel"
                            else "none"
                        ),
                    },
                )
            )

        status_map = {
            "respond": "ok",
            "execute": "ok",
            "mixed": "ok",
            "clarify": "clarify",
            "unavailable": "refused",
            "refused": "refused",
        }
        primary_effectful_count = sum(
            1 for request in skills if request.metadata.get("effectful") is True
        )
        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
            "response_composition": composition.model_dump(mode="json", exclude_none=True),
            "execution_lanes": {
                "vocal": (
                    "response_delivery_and_provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "vocal" for request in skills
                    )
                    else "response_delivery"
                ),
                "activity": (
                    "provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "activity"
                        for request in skills
                    )
                    else "idle"
                ),
            },
            "lane_coordination_groups": [
                item.model_dump(mode="json", exclude_none=True)
                for item in composition.lane_coordination
            ],
            "planning_result": (
                "composed_plan" if plan.disposition in {"execute", "mixed"} else plan.disposition
            ),
            "capability_decision": plan.disposition,
            "goal_ids": plan.goal_ids,
            "planner_tier": plan.planner_tier,
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
            "omitted_pre_execution_speech_phases": (omitted_pre_execution_speech_phases),
            "operational_speech_authority": (
                "llm_optional_micro_ack"
                if safe_read_speech_optional
                else "llm_parallel_speech"
                if safe_read_parallel
                else "llm_wording_runtime_validated"
                if effectful_pre_execution
                else "not_applicable"
            ),
            "safe_read_parallel_execution": safe_read_parallel,
            "safe_read_speech_optional": safe_read_speech_optional,
            "deepthinking_proposed_effect_task_count": primary_effectful_count,
            "deepthinking_valid_effect_task_count": primary_effectful_count,
            "deepthinking_proposed_action_count": primary_effectful_count,
            "deepthinking_valid_action_count": primary_effectful_count,
        }
        runtime_context = context if isinstance(context, dict) else {}
        if isinstance(runtime_context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = runtime_context["user_turn_envelope"]
        mind_context = runtime_context.get("mind")
        if isinstance(mind_context, dict) and isinstance(
            mind_context.get("personality_expression"), dict
        ):
            metadata["personality_expression"] = mind_context["personality_expression"]
        if alternative:
            metadata["material_plan_change_requires_confirmation"] = True
        confirmation_prompt = next(
            (
                item.text
                for item in speech
                if item.metadata.get("runtime_confirmation_required") is True
            ),
            "",
        )
        if confirmation_prompt:
            metadata["confirmation_prompt"] = confirmation_prompt
            metadata["confirmation_prompt_source"] = "llm_wording_runtime_validated"
        response = InteractionResponse(
            status=status_map.get(plan.disposition, "error"),
            speech=speech,
            skills=skills,
            requires_confirmation=any(item.requires_confirmation for item in skills),
            reason=(
                plan.escalation_reason if plan.disposition in {"unavailable", "refused"} else None
            ),
            metadata=metadata,
        )
        return response


class GoalDrivenRuntimeCoordinator:
    """Advance one Core-owned interaction as independent work becomes ready."""

    TRACE_MODULE = TraceModule(
        name="orchestrator.cognitive_runtime",
        component_type="interaction_coordinator",
        implementation="GoalDrivenRuntimeCoordinator",
        schema_version=1,
    )

    def __init__(
        self,
        *,
        agent_client: CognitiveAgentClient,
        adapter: CanonicalPlanRuntimeAdapter,
        policy: CognitiveRuntimePolicy,
        goal_state_apply: Callable[..., list[dict[str, Any]]] | None = None,
        context_refresh: Callable[[str | None], dict[str, Any]] | None = None,
        delivered_turn_speech_provider: (Callable[[str], list[dict[str, Any]]] | None) = None,
        interaction_ledger: Any | None = None,
        workflow_stage_sink: Callable[..., None] | None = None,
    ) -> None:
        self.agent_client = agent_client
        self.adapter = adapter
        self.policy = policy
        self.goal_state_apply = goal_state_apply
        self.context_refresh = context_refresh
        self._goal_association_locks: dict[str, asyncio.Lock] = {}
        self.delivered_turn_speech_provider = delivered_turn_speech_provider
        self.workflow_stage_sink = workflow_stage_sink
        self.interaction_ledger = interaction_ledger or getattr(
            getattr(adapter, "interaction_runtime", None),
            "interaction_ledger",
            None,
        )
        self._auxiliary_tasks: set[asyncio.Task[Any]] = set()
        self._social_attention_pending: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        self._social_attention_workers: dict[
            tuple[str, str], asyncio.Task[Any]
        ] = {}

    def _track_auxiliary_task(self, task: asyncio.Task[Any]) -> None:
        """Keep background social decoration alive without making it a turn-response barrier."""

        self._auxiliary_tasks.add(task)

        def _done(completed: asyncio.Task[Any]) -> None:
            self._auxiliary_tasks.discard(completed)
            if completed.cancelled():
                return
            exc = completed.exception()
            if exc is not None:  # pragma: no cover - background-loop bug visibility guard
                logger.warning(
                    "auxiliary cognitive task failed task=%s error_type=%s error=%s",
                    completed.get_name(),
                    type(exc).__name__,
                    exc,
                )

        task.add_done_callback(_done)

    @staticmethod
    def _scheduled_speech_social_activity(
        context: dict[str, Any],
        *,
        turn_id: str,
    ) -> SocialAttentionActivityAnchor | None:
        """Project an actually scheduled fast utterance into an Activity anchor."""

        rows = context.get("scheduled_turn_speech")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get("text") or "").strip().split())
            if not text:
                continue
            raw_id = " ".join(str(row.get("speech_event_id") or "").strip().split())
            if not raw_id:
                digest = hashlib.sha256(
                    f"{turn_id}|scheduled_speech|{text}".encode("utf-8")
                ).hexdigest()[:20]
                raw_id = f"speech_{digest}"
            return SocialAttentionActivityAnchor(
                activity_id=raw_id,
                kind="speech",
                phase="ready",
                summary=text,
            )
        return None

    @staticmethod
    def _resolution_social_activity(
        resolution: CognitiveRuntimeResolution,
        *,
        turn_id: str,
    ) -> SocialAttentionActivityAnchor | None:
        """Return the primary human-observable Activity prepared by this resolution."""

        interaction = resolution.interaction_response
        if interaction is None:
            return None
        speech_texts = [
            " ".join(str(item.text or "").strip().split())
            for item in interaction.speech
            if " ".join(str(item.text or "").strip().split())
        ]
        capability_ids = [
            str(item.capability_id or "").strip()
            for item in interaction.skills
            if str(item.capability_id or "").strip()
        ]
        observable_capability_ids = [
            capability_id
            for capability_id in capability_ids
            if capability_id.startswith("soridormi.")
            or capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
            or capability_id.startswith("chromie.media.")
        ]
        if not speech_texts and not observable_capability_ids:
            return None
        if speech_texts and observable_capability_ids:
            kind = "mixed"
        elif speech_texts:
            kind = "speech"
        elif all(
            capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
            for capability_id in observable_capability_ids
        ):
            kind = "vocal_performance"
        elif all(
            capability_id.startswith("chromie.media.")
            for capability_id in observable_capability_ids
        ):
            kind = "media_playback"
        else:
            kind = "body_action"
        summary = speech_texts[0] if speech_texts else ", ".join(observable_capability_ids)
        goal_ids = list(resolution.terminal_plan.goal_ids) if resolution.terminal_plan else []
        return SocialAttentionActivityAnchor(
            activity_id=interaction.interaction_id,
            kind=kind,
            phase="ready",
            summary=summary,
            goal_ids=goal_ids,
            capability_ids=observable_capability_ids,
        )

    def _queue_social_attention_for_activity(
        self,
        session: Any,
        *,
        activity: SocialAttentionActivityAnchor | None,
        text: str,
        sid: str,
        turn_id: str,
        language: str,
        intent: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        if activity is None:
            return
        event = (
            "primary_activity_ready"
            if activity.phase == "ready"
            else "primary_activity_started"
        )
        self._queue_social_attention_event(
            session,
            event=event,
            text=text,
            sid=sid,
            turn_id=turn_id,
            language=language,
            intent=intent,
            context={
                **context,
                "social_attention_primary_activity": activity.model_dump(
                    mode="json", exclude_none=True
                ),
            },
            history=history,
        )

    def _queue_social_attention_event(
        self,
        session: Any,
        *,
        event: str,
        text: str,
        sid: str,
        turn_id: str,
        language: str,
        intent: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        """Coalesce background social-decoration state without blocking primary cognition."""

        if self.policy.mode != "apply" or self.adapter.social_attention_mode == "off":
            return
        raw_activity = context.get("social_attention_primary_activity")
        if not isinstance(raw_activity, dict):
            return
        activity_id = str(raw_activity.get("activity_id") or "").strip()
        if not activity_id:
            return
        key = (sid, activity_id)
        # Coalesce only duplicate updates for the same primary Activity. Different
        # observable Activities in one turn remain independently eligible for optional
        # Social Attention.
        self._social_attention_pending[key] = {
            "session": session,
            "event": event,
            "text": text,
            "sid": sid,
            "turn_id": turn_id,
            "language": language,
            "intent": intent,
            "context": dict(context),
            "history": [dict(item) for item in history if isinstance(item, dict)],
        }
        existing = self._social_attention_workers.get(key)
        if existing is not None and not existing.done():
            return
        worker = asyncio.create_task(
            self._drain_social_attention_events(key),
            name=f"social-attention:{sid}:{turn_id}",
        )
        self._social_attention_workers[key] = worker
        self._track_auxiliary_task(worker)

    async def _drain_social_attention_events(self, key: tuple[str, str]) -> None:
        try:
            while True:
                payload = self._social_attention_pending.pop(key, None)
                if payload is None:
                    return
                await self._run_social_attention_event(**payload)
        finally:
            self._social_attention_workers.pop(key, None)
            self._social_attention_pending.pop(key, None)

    _CONTINUITY_REFRESH_KEYS = frozenset(
        {
            "conversation",
            "session_memory",
            "memory_summary",
            "extracted_memory",
            "history",
            "pending_tasks",
            "active_pending_tasks",
            "task_contexts",
            "active_task_contexts",
            "active_task_snapshots",
            "active_goal_snapshots",
            "recent_goal_snapshots",
            "current_task_context",
            "discourse_referents",
            "discourse_focus",
            "verified_tool_memory_index",
            "recent_tool_evidence",
            "interaction_engagement",
        }
    )

    @staticmethod
    def _goal_association_lock_key(
        context: dict[str, Any],
        sid: str,
    ) -> str:
        return " ".join(
            str(context.get("conversation_id") or sid or "local_default")
            .strip()
            .split()
        ) or "local_default"

    def _goal_association_lock(
        self,
        *,
        context: dict[str, Any],
        sid: str,
    ) -> asyncio.Lock:
        key = self._goal_association_lock_key(context, sid)
        lock = self._goal_association_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._goal_association_locks[key] = lock
        return lock

    def _refresh_continuity_context(
        self,
        *,
        context: dict[str, Any],
        sid: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if self.context_refresh is None:
            refreshed = dict(context)
        else:
            live = self.context_refresh(sid)
            refreshed = dict(context)
            for key in self._CONTINUITY_REFRESH_KEYS:
                if key in live:
                    refreshed[key] = live[key]

        # The admitted current turn may already be published as conversation
        # evidence. Goal Association receives it separately as authoritative
        # request.text, so history must contain only prior dialogue.
        raw_history = refreshed.get("history")
        if isinstance(raw_history, list):
            normalized_sid = str(sid or "").strip()
            current_index = next(
                (
                    index
                    for index, item in enumerate(raw_history)
                    if isinstance(item, dict)
                    and str(item.get("sid") or "").strip() == normalized_sid
                ),
                None,
            )
            causal_history = (
                raw_history[:current_index]
                if current_index is not None
                else raw_history
            )
            history = [
                dict(item)
                for item in causal_history
                if isinstance(item, dict)
                and str(item.get("sid") or "").strip() != normalized_sid
            ]
        else:
            history = []
        refreshed["history"] = history
        return refreshed, history

    @staticmethod
    def _workflow_output_status(output: Any) -> str:
        metadata = getattr(output, "metadata", None)
        if isinstance(metadata, dict):
            metadata_status = str(metadata.get("status") or "").strip()
            if metadata_status:
                return metadata_status
            if metadata.get("failure_class"):
                return "failed"
        status = str(getattr(output, "status", "") or "").strip()
        if status:
            return status
        disposition = str(getattr(output, "disposition", "") or "").strip()
        if disposition == "escalate":
            return "escalated"
        return "accepted"

    @staticmethod
    def _workflow_output_errors(output: Any) -> list[Any]:
        metadata = getattr(output, "metadata", None)
        if not isinstance(metadata, dict):
            return []
        errors: list[Any] = []
        for key in (
            "error",
            "initial_validation_errors",
            "validation_feedback",
            "stage_diagnostics",
        ):
            value = metadata.get(key)
            if value not in (None, "", [], {}):
                errors.append({key: value})
        return errors

    def _record_workflow_stage(
        self,
        *,
        sid: str,
        stage: str,
        started_monotonic_ms: float,
        finished_monotonic_ms: float,
        status: str,
        input_payload: Any,
        output_payload: Any,
        errors: list[Any],
        attempt: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.workflow_stage_sink is None:
            return
        try:
            self.workflow_stage_sink(
                sid,
                stage=stage,
                started_monotonic_ms=started_monotonic_ms,
                finished_monotonic_ms=finished_monotonic_ms,
                status=status,
                input_payload=input_payload,
                output_payload=output_payload,
                errors=errors,
                attempt=attempt,
                metadata=metadata,
            )
        except Exception as exc:
            # Evidence capture must never change cognitive execution semantics.
            logger.warning(
                "Could not retain cognitive workflow stage %s: %s",
                stage,
                exc,
            )
            return

    async def _observe_workflow_stage(
        self,
        *,
        sid: str,
        stage: str,
        input_payload: Any,
        operation: Awaitable[Any],
        attempt: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        started_monotonic_ms = time.perf_counter() * 1000.0
        try:
            output = await operation
        except asyncio.CancelledError:
            self._record_workflow_stage(
                sid=sid,
                stage=stage,
                started_monotonic_ms=started_monotonic_ms,
                finished_monotonic_ms=time.perf_counter() * 1000.0,
                status="cancelled",
                input_payload=input_payload,
                output_payload=None,
                errors=[{"reason": "operation_cancelled"}],
                attempt=attempt,
                metadata=metadata,
            )
            raise
        except Exception as exc:
            self._record_workflow_stage(
                sid=sid,
                stage=stage,
                started_monotonic_ms=started_monotonic_ms,
                finished_monotonic_ms=time.perf_counter() * 1000.0,
                status="failed",
                input_payload=input_payload,
                output_payload=None,
                errors=[
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                ],
                attempt=attempt,
                metadata=metadata,
            )
            raise
        self._record_workflow_stage(
            sid=sid,
            stage=stage,
            started_monotonic_ms=started_monotonic_ms,
            finished_monotonic_ms=time.perf_counter() * 1000.0,
            status=self._workflow_output_status(output),
            input_payload=input_payload,
            output_payload=output,
            errors=self._workflow_output_errors(output),
            attempt=attempt,
            metadata=metadata,
        )
        return output

    @staticmethod
    def _context_turn_id(context: dict[str, Any], sid: str) -> str:
        envelope = context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            turn_id = " ".join(
                str(envelope.get("turn_id") or "").strip().split()
            )
            if turn_id:
                return turn_id
        return sid

    def _interaction_context(
        self,
        *,
        sid: str,
        context: dict[str, Any],
        goal_ids: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if self.interaction_ledger is None:
            return {}
        projection = self.interaction_ledger.context(
            sid,
            goal_ids=goal_ids,
            turn_id=self._context_turn_id(context, sid),
        )
        return projection.model_dump(mode="json")


    @staticmethod
    def _association_goal_ids(association: GoalAssociationResolution) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            text = " ".join(str(value or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)

        for item in association.associations:
            for goal_id in item.target_goal_ids:
                add(goal_id)
        for goal in association.new_goals:
            add(goal.goal_id)
        return ordered

    @staticmethod
    def _is_direct_spoken_association(
        association: GoalAssociationResolution,
    ) -> bool:
        return (
            not association.clarification
            and not association.associations
            and bool(association.new_goals)
            and all(
                str((goal.metadata or {}).get("responsibility_kind") or "") == "vocal_output"
                and not bool((goal.metadata or {}).get("provider_required"))
                and bool(str(goal.goal_id or "").strip())
                for goal in association.new_goals
            )
        )

    @staticmethod
    def _transient_native_responsibility_ids(
        association: GoalAssociationResolution,
        candidates: dict[str, CognitiveProgressCandidate],
    ) -> list[str]:
        """Return immediately dischargeable conversational responsibility IDs.

        Goal Association still provides bounded semantic coverage so the ready
        native response can be checked against the exact understood outcome, but
        no durable Goal is needed when every new responsibility is ordinary
        provider-free speech and every one is completely covered by a supplied
        native response candidate. This is a materialization decision, not a
        second interpretation pass.
        """

        if (
            association.clarification
            or association.associations
            or not association.new_goals
        ):
            return []
        goal_by_id = {
            str(goal.goal_id or "").strip(): goal
            for goal in association.new_goals
            if str(goal.goal_id or "").strip()
        }
        if len(goal_by_id) != len(association.new_goals):
            return []
        if any(
            str((goal.metadata or {}).get("output_mode") or "") != "speech"
            or bool((goal.metadata or {}).get("provider_required"))
            for goal in goal_by_id.values()
        ):
            return []
        covered: set[str] = set()
        for binding in association.progress_bindings:
            candidate = candidates.get(binding.candidate_id)
            if candidate is None or candidate.kind != "native_response":
                return []
            if not binding.goal_ids or any(goal_id not in goal_by_id for goal_id in binding.goal_ids):
                return []
            if covered.intersection(binding.goal_ids):
                return []
            covered.update(binding.goal_ids)
        if covered != set(goal_by_id):
            return []
        return list(goal_by_id)

    @staticmethod
    def _progress_candidates_from_context(
        context: dict[str, Any],
    ) -> dict[str, CognitiveProgressCandidate]:
        candidates: dict[str, CognitiveProgressCandidate] = {}
        for item in context.get("progress_candidates") or []:
            try:
                candidate = CognitiveProgressCandidate.model_validate(item)
            except ValidationError:
                continue
            candidates[candidate.candidate_id] = candidate
        return candidates

    async def _start_ready_progress(
        self,
        *,
        candidates: dict[str, CognitiveProgressCandidate],
        sid: str,
        turn_id: str,
        language: str,
    ) -> dict[str, Any]:
        """Start independently-ready native speech without changing its meaning."""

        runtime = self.adapter.interaction_runtime

        async def start(candidate: CognitiveProgressCandidate) -> Any:
            return await runtime.start_ready_native_response(
                candidate,
                session_id=sid,
                turn_id=turn_id,
                language=language,
            )

        starts = {
            candidate_id: asyncio.create_task(start(candidate))
            for candidate_id, candidate in candidates.items()
        }
        handles: dict[str, Any] = {}
        if not starts:
            return handles
        outcomes = await asyncio.gather(*starts.values(), return_exceptions=True)
        for candidate_id, outcome in zip(starts, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "ready progress start failed candidate_id=%s error_type=%s error=%s",
                    candidate_id,
                    type(outcome).__name__,
                    outcome,
                )
                continue
            if outcome is not None:
                handles[candidate_id] = outcome
        return handles

    async def _cancel_ready_progress(self, handles: dict[str, Any]) -> None:
        if not handles:
            return
        runtime = self.adapter.interaction_runtime

        async def cancel(candidate_id: str, handle: Any) -> None:
            del candidate_id
            await runtime.cancel_ready_native_response(handle)

        await asyncio.gather(
            *(cancel(candidate_id, handle) for candidate_id, handle in list(handles.items())),
            return_exceptions=True,
        )
        handles.clear()

    async def _run_social_attention_event(
        self,
        session: Any,
        *,
        event: str,
        text: str,
        sid: str,
        turn_id: str,
        language: str,
        intent: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolver = getattr(self.agent_client, "resolve_social_attention", None)
        if not callable(resolver) or self.adapter.social_attention_mode == "off":
            return {"status": "not_available", "event": event}

        social_context = dict(context)
        raw_activity = social_context.get("social_attention_primary_activity")
        try:
            primary_activity = SocialAttentionActivityAnchor.model_validate(raw_activity)
        except (ValidationError, TypeError, ValueError):
            return {
                "status": "suppressed",
                "event": event,
                "decision": "none",
                "materialized_count": 0,
                "reasons": ["missing_or_invalid_primary_activity_anchor"],
            }

        # Throttle per primary Activity, never per cognition turn. A fast acknowledgement
        # and a later walk/final response are different observable Activities and may each
        # independently receive optional Social Attention.
        recent = getattr(self.adapter, "recent_auxiliary_behavior_evidence", None)
        recent_evidence = recent(sid) if callable(recent) else []
        if any(
            str(item.get("primary_activity_id") or "").strip()
            == primary_activity.activity_id
            for item in recent_evidence
            if isinstance(item, dict)
        ):
            return {
                "status": "suppressed",
                "event": event,
                "decision": "none",
                "materialized_count": 0,
                "reasons": ["same_primary_activity_auxiliary_cooldown"],
            }

        social_context["social_attention_event"] = event
        primary_progress: list[dict[str, Any]] = []
        primary_capability_ids: list[str] = list(primary_activity.capability_ids)
        seen_primary_ids: set[str] = set(primary_capability_ids)

        def retain_primary_progress(rows: Any) -> None:
            if not isinstance(rows, list):
                return
            for row in rows[:12]:
                if not isinstance(row, dict):
                    continue
                capability_id = str(
                    row.get("capability_id") or row.get("skill_id") or ""
                ).strip()
                if not capability_id:
                    continue
                if capability_id not in seen_primary_ids:
                    seen_primary_ids.add(capability_id)
                    primary_capability_ids.append(capability_id)
                projection = {
                    key: row[key]
                    for key in (
                        "candidate_id",
                        "step_id",
                        "capability_id",
                        "skill_id",
                        "intent",
                        "args",
                    )
                    if key in row
                }
                primary_progress.append(projection)

        retain_primary_progress(social_context.get("progress_candidates"))
        retain_primary_progress(social_context.get("execution_capabilities"))
        canonical_plan = social_context.get("canonical_plan_resolution")
        if isinstance(canonical_plan, dict):
            retain_primary_progress(canonical_plan.get("steps"))
        social_context["social_attention_interaction_state"] = {
            "event": event,
            "primary_activity": primary_activity.model_dump(mode="json", exclude_none=True),
            "primary_capability_ids": primary_capability_ids,
            "primary_progress": primary_progress,
            "primary_work_known": bool(primary_activity.summary or primary_capability_ids),
        }
        social_context["recent_auxiliary_behavior_evidence"] = recent_evidence
        request = SocialAttentionRequest(
            session_id=sid,
            turn_id=turn_id,
            event=event,
            primary_activity=primary_activity,
            text=text,
            language=language,
            intent=intent or "unknown",
            context=social_context,
            history=[dict(item) for item in history[-6:] if isinstance(item, dict)],
        )
        planner_outcome = (
            await asyncio.gather(
                resolver(session, request=request),
                return_exceptions=True,
            )
        )[0]
        if isinstance(planner_outcome, asyncio.CancelledError):
            raise planner_outcome
        if isinstance(planner_outcome, BaseException):
            return {
                "status": "planner_failed",
                "event": event,
                "error_type": type(planner_outcome).__name__,
                "error": str(planner_outcome)[:240],
            }
        plan = planner_outcome
        execution_outcome = (
            await asyncio.gather(
                self.adapter.execute_social_attention_event(
                    plan=plan,
                    session_id=sid,
                    turn_id=turn_id,
                    event=event,
                    context=social_context,
                ),
                return_exceptions=True,
            )
        )[0]
        if isinstance(execution_outcome, asyncio.CancelledError):
            raise execution_outcome
        if isinstance(execution_outcome, BaseException):
            return {
                "status": "execution_failed",
                "event": event,
                "decision": plan.decision,
                "error_type": type(execution_outcome).__name__,
                "error": str(execution_outcome)[:240],
            }
        logger.info(
            "continuous_social_attention_event_done sid=%s turn_id=%s event=%s "
            "status=%s decision=%s materialized_count=%d request_ids=%s reasons=%s",
            sid,
            turn_id,
            event,
            str(execution_outcome.get("status") or "unknown"),
            plan.decision,
            int(execution_outcome.get("materialized_count") or 0),
            ",".join(
                str(item)
                for item in execution_outcome.get("request_ids", [])
                if str(item)
            ),
            ",".join(
                str(item)
                for item in execution_outcome.get("reasons", [])
                if str(item)
            ),
        )
        return execution_outcome

    @staticmethod
    def _is_terminal_missing_ability_decision(route_decision: Any) -> bool:
        return bool(
            str(getattr(route_decision, "route", "") or "").strip() == "clarify"
            and str(getattr(route_decision, "intent", "") or "").strip()
            == "missing_or_unsupported_ability"
        )

    @staticmethod
    def _terminal_missing_ability_interaction(
        route_decision: Any,
        *,
        sid: str,
        language: str,
        context: dict[str, Any],
    ) -> InteractionResponse:
        text = " ".join(str(getattr(route_decision, "speak_first", "") or "").strip().split())
        if not text:
            raise ValueError(
                "terminal missing-ability decision requires model-authored speak_first"
            )
        route_metadata = getattr(route_decision, "metadata", {})
        if not isinstance(route_metadata, dict):
            route_metadata = {}
        desired_abilities = route_metadata.get("desired_abilities")
        task_proposals = route_metadata.get("task_proposals")
        metadata: dict[str, Any] = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "planning_result": "terminal_missing_ability",
            "capability_decision": "unavailable",
            "goal_understood": True,
            "capability_state": "unavailable",
            "execution_state": "not_attempted",
            "result_state": "not_observed",
            "execution_attempted": False,
            "operational_speech_authority": "goal_interpreter_model",
            "missing_ability_terminal": True,
            "desired_abilities": (
                list(desired_abilities) if isinstance(desired_abilities, list) else []
            ),
            "task_proposals": (list(task_proposals) if isinstance(task_proposals, list) else []),
        }
        if isinstance(context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = context["user_turn_envelope"]
        return InteractionResponse(
            interaction_id=f"cognitive_{sid}",
            status="clarify",
            reason="missing_or_unsupported_ability",
            speech=[
                InteractionSpeech(
                    text=text,
                    timing="immediate",
                    style="brief",
                    metadata={
                        "source": "goal_interpreter_missing_ability",
                        "phase": "final",
                        "speech_act": "capability_limitation",
                        "commitment_state": "completed",
                        "must_not_claim_completion": True,
                        "claims": [
                            "goal_understood",
                            "capability_unavailable",
                            "execution_not_attempted",
                            "result_not_observed",
                        ],
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                    },
                )
            ],
            skills=[],
            requires_confirmation=False,
            metadata=metadata,
        )

    @staticmethod
    def _fast_plan_path(plan: CanonicalPlan | None) -> str:
        if plan is None:
            return ""
        value = str(plan.metadata.get("path_classification") or "").strip()
        if value in {"terminal", "semantic_escalation", "contract_failure"}:
            return value
        if plan.metadata.get("failure_class"):
            return "contract_failure"
        if plan.disposition == "escalate":
            return "semantic_escalation"
        return "terminal"

    @staticmethod
    def _fast_plan_context_for_deep(plan: CanonicalPlan) -> dict[str, Any]:
        """Project only a genuine semantic Fast escalation into Deep cognition."""

        return plan.prompt_projection()

    async def resolve(
        self,
        session: Any,
        *,
        text: str,
        sid: str,
        route_decision: Any | None = None,
        core_interpretation: CoreInterpretationResult | None = None,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        language: str,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> CognitiveRuntimeResolution:
        if core_interpretation is not None:
            if turn_envelope is None:
                raise ValueError("Core interpretation requires its admitted UserTurnEnvelope")
            if core_interpretation.turn_id != turn_envelope.turn_id:
                raise ValueError("Core interpretation turn does not match UserTurnEnvelope")
            if core_interpretation.session_id != turn_envelope.session_id:
                raise ValueError("Core interpretation session does not match UserTurnEnvelope")
            route_decision = CompatibilityRouteDecision.model_validate(
                core_interpretation.route_decision_projection().model_dump(mode="json")
            )
            context = {
                **context,
                "core_interpretation": core_interpretation.model_dump(
                    mode="json",
                    exclude={"compatibility_projection"},
                ),
                "core_interpretation_projection_digest": (core_interpretation.projection_digest),
                "responsibility_proposals": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in core_interpretation.responsibilities
                ],
                "progress_candidates": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in core_interpretation.progress_candidates
                ],
            }
        if route_decision is None:
            raise ValueError(
                "Goal-driven Runtime requires a Core interpretation or explicit "
                "compatibility RouteDecision"
            )

        if turn_envelope is not None:
            if turn_envelope.admission not in {"admit", "reflex_and_admit"}:
                raise ValueError(
                    "Goal-driven Runtime accepts only admitted UserTurnEnvelope "
                    f"records, got {turn_envelope.admission}"
                )
            if str(sid or "").strip() != turn_envelope.session_id:
                raise ValueError("Goal-driven Runtime session does not match UserTurnEnvelope")
            if " ".join((text or "").strip().split()) != (turn_envelope.normalized_input.text):
                raise ValueError("Goal-driven Runtime text does not match UserTurnEnvelope")
            text = turn_envelope.normalized_input.text
            sid = turn_envelope.session_id
            language = turn_envelope.normalized_input.language
            context = {
                **context,
                "user_turn_envelope": turn_envelope.model_dump(mode="json"),
                "turn_id": turn_envelope.turn_id,
                "user_turn_schema_version": turn_envelope.schema_version,
            }
            envelope_history = context.get("history")
            if isinstance(envelope_history, list):
                history = list(envelope_history)

        experience = context.get("experience_context")
        if not isinstance(experience, dict):
            experience = {}
        conversation_id = str(
            context.get("conversation_id") or experience.get("conversation_id") or ""
        )
        interaction_id = str(
            context.get("interaction_id") or experience.get("interaction_id") or sid
        )
        turn_index = context.get("turn_index") or experience.get("turn_index")
        route = str(getattr(route_decision, "route", "") or "")
        intent = str(getattr(route_decision, "intent", "") or "")

        def attach_core_identity(
            resolution: CognitiveRuntimeResolution,
        ) -> CognitiveRuntimeResolution:
            if core_interpretation is None:
                return resolution
            metadata = dict(resolution.metadata)
            metadata["core_interpretation"] = core_interpretation.model_dump(
                mode="json",
                exclude={"compatibility_projection"},
            )
            metadata["core_interpretation_projection_digest"] = (
                core_interpretation.projection_digest
            )
            return resolution.model_copy(update={"metadata": metadata})

        def queue_resolution_social_attention(
            resolution: CognitiveRuntimeResolution,
        ) -> None:
            resolved_turn_id = (
                turn_envelope.turn_id
                if turn_envelope is not None
                else self._context_turn_id(context, sid)
            )
            activity = self._resolution_social_activity(
                resolution, turn_id=resolved_turn_id
            )
            social_context = dict(context)
            if resolution.goal_association is not None:
                social_context["goal_association"] = (
                    resolution.goal_association.prompt_projection()
                )
            if resolution.terminal_plan is not None:
                social_context["canonical_plan_resolution"] = (
                    resolution.terminal_plan.prompt_projection()
                )
            self._queue_social_attention_for_activity(
                session,
                activity=activity,
                text=text,
                sid=sid,
                turn_id=resolved_turn_id,
                language=language,
                intent=intent or "unknown",
                context=social_context,
                history=history,
            )

        trace_scope = runtime_tracer.start_trace(
            correlations={
                "session_id": sid,
                "conversation_id": conversation_id,
                "interaction_id": interaction_id,
                "turn_index": turn_index,
            },
            attributes={
                "runtime_mode": self.policy.mode,
                "route": route,
                "intent": intent,
                "language": language,
                "text_chars": len(text or ""),
            },
            sampling_reason="goal_driven_interaction",
        )
        if not trace_scope.enabled:
            resolution = await self._resolve(
                session,
                text=text,
                sid=sid,
                route_decision=route_decision,
                context=context,
                history=history,
                language=language,
            )
            if turn_envelope is not None:
                resolution = resolution.model_copy(update={"turn_envelope": turn_envelope})
            resolution = attach_core_identity(resolution)
            queue_resolution_social_attention(resolution)
            return resolution
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    kind="interaction",
                    attributes={"policy_mode": self.policy.mode},
                ) as span:
                    resolution = await self._resolve(
                        session,
                        text=text,
                        sid=sid,
                        route_decision=route_decision,
                        context=context,
                        history=history,
                        language=language,
                    )
                    if turn_envelope is not None:
                        resolution = resolution.model_copy(update={"turn_envelope": turn_envelope})
                    resolution = attach_core_identity(resolution)
                    queue_resolution_social_attention(resolution)
                    span.set_attribute("result_status", resolution.status)
                    span.set_attribute("lane", resolution.lane)
                    if resolution.status == "error":
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise

        snapshot = trace_scope.finish(state="complete")
        if snapshot is None:
            return resolution
        metadata = dict(resolution.metadata)
        metadata["runtime_trace"] = snapshot.reference()
        metadata["runtime_trace_summary"] = snapshot.summary
        retention = trace_scope.policy.retention_decision(snapshot)
        metadata["runtime_trace_retention"] = retention.as_dict()
        if retention.emit:
            metadata["runtime_trace_event"] = runtime_tracer.persist_snapshot(
                snapshot,
                event_subtype="goal_driven_interaction",
                producer="chromie.orchestrator.cognitive_runtime",
                severity=("warning" if resolution.status == "error" else retention.severity),
                retention_reason=retention.reason,
            )
        return resolution.model_copy(update={"metadata": metadata})

    async def _resolve(
        self,
        session: Any,
        *,
        text: str,
        sid: str,
        route_decision: Any,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        language: str,
    ) -> CognitiveRuntimeResolution:
        started = time.perf_counter()
        context = dict(context)
        context["interaction_context"] = self._interaction_context(
            sid=sid,
            context=context,
        )
        timings: dict[str, float] = {}
        association: GoalAssociationResolution | None = None
        fast_plan: CanonicalPlan | None = None
        terminal_plan: CanonicalPlan | None = None
        composition_resolution: ResponseCompositionResolution | None = None
        interaction: InteractionResponse | None = None
        goal_state_results: list[dict[str, Any]] = []
        goal_state_commit_stage = ""
        stage_diagnostics: list[dict[str, Any]] = []
        fast_planner_path = ""
        deep_planner_invocation_reasons: list[str] = []
        source_lane = str(getattr(route_decision, "route", "") or "")
        lane: CognitiveLane = (
            source_lane
            if source_lane in {"chat", "robot_action", "tool", "memory"}
            else "unsupported"
        )
        progress_candidates = self._progress_candidates_from_context(context)
        ready_handles: dict[str, Any] = {}
        ready_start_task: asyncio.Task[dict[str, Any]] | None = None
        ready_bound_count = 0
        transient_responsibility_ids: list[str] = []

        def path_metadata() -> dict[str, Any]:
            first_deep_reason = (
                deep_planner_invocation_reasons[0] if deep_planner_invocation_reasons else ""
            )
            return {
                "fast_planner_path": fast_planner_path,
                "deep_planner_invoked": bool(deep_planner_invocation_reasons),
                "deep_planner_invocation_reason": first_deep_reason,
                "deep_planner_invocation_reasons": list(deep_planner_invocation_reasons),
                "deep_planner_avoided": bool(
                    fast_planner_path
                    in {
                        "terminal",
                        "direct_vocal_output",
                        "native_response_readiness_adoption",
                        "terminal_missing_ability",
                        "contract_failure",
                    }
                    and not deep_planner_invocation_reasons
                ),
                "fast_plan_committed_without_deep": bool(
                    fast_plan is not None
                    and fast_plan.planner_tier == "fast"
                    and fast_plan.disposition != "escalate"
                    and fast_planner_path
                    in {
                        "terminal",
                        "direct_vocal_output",
                        "native_response_readiness_adoption",
                    }
                    and not deep_planner_invocation_reasons
                ),
                "terminal_planner_tier": (
                    terminal_plan.planner_tier if terminal_plan is not None else ""
                ),
                "authoritative_goal_count": (
                    0
                    if transient_responsibility_ids
                    else (
                        len(self._association_goal_ids(association))
                        if association is not None
                        else 0
                    )
                ),
                "transient_responsibility_count": len(transient_responsibility_ids),
                "transient_responsibility_ids": list(transient_responsibility_ids),
                "fast_goal_outcome_count": (
                    len(fast_plan.goal_outcomes) if fast_plan is not None else 0
                ),
                "fast_executable_step_count": (
                    len(fast_plan.steps) if fast_plan is not None else 0
                ),
                "goal_state_commit_stage": goal_state_commit_stage,
                "progress_candidate_count": len(progress_candidates),
                "ready_result_bound_count": ready_bound_count,
            }

        if self._is_terminal_missing_ability_decision(route_decision):
            lane = "chat"
            fast_planner_path = "terminal_missing_ability"
            terminal_metadata = {
                "stage_diagnostics": stage_diagnostics,
                "architecture_attribution": "not_evaluated",
                "terminal_goal_interpretation": True,
                **path_metadata(),
            }
            if self.policy.mode == "apply":
                if not self.policy.lane_enabled(lane):
                    return self._finish(
                        mode="apply",
                        status="error",
                        lane=lane,
                        association=None,
                        fast_plan=None,
                        terminal_plan=None,
                        composition=None,
                        timings=timings,
                        started=started,
                        fallback_reason="missing_ability_lane_not_enabled_for_apply",
                        metadata={
                            **terminal_metadata,
                            "failure_stage": "authority_boundary",
                            "failure_class": "terminal_missing_ability_lane_mismatch",
                            "failure_domain": "cognitive_runtime",
                            "retryable": False,
                        },
                    )
                interaction = self._terminal_missing_ability_interaction(
                    route_decision,
                    sid=sid,
                    language=language,
                    context=context,
                )
                return self._finish(
                    mode="apply",
                    status="applied",
                    lane=lane,
                    association=None,
                    fast_plan=None,
                    terminal_plan=None,
                    composition=None,
                    interaction=interaction,
                    timings=timings,
                    started=started,
                    metadata=terminal_metadata,
                )
            return self._finish(
                mode="report_only",
                status="report_only",
                lane=lane,
                association=None,
                fast_plan=None,
                terminal_plan=None,
                composition=None,
                timings=timings,
                started=started,
                metadata=terminal_metadata,
            )

        try:
            turn_id = self._context_turn_id(context, sid)
            if (
                self.policy.mode == "apply"
                and self.policy.lane_enabled(lane)
                and progress_candidates
            ):
                ready_start_task = asyncio.create_task(
                    self._start_ready_progress(
                        candidates=progress_candidates,
                        sid=sid,
                        turn_id=turn_id,
                        language=language,
                    )
                )
            self._queue_social_attention_for_activity(
                session,
                activity=self._scheduled_speech_social_activity(
                    context, turn_id=turn_id
                ),
                text=text,
                sid=sid,
                turn_id=turn_id,
                language=language,
                intent=str(getattr(route_decision, "intent", "") or "unknown"),
                context=context,
                history=history,
            )
            association_lock = self._goal_association_lock(
                context=context,
                sid=sid,
            )
            async with association_lock:
                context, history = self._refresh_continuity_context(
                    context=context,
                    sid=sid,
                )
                situation = build_situation_projection(
                    context=context,
                    turn_id=turn_id,
                    lane=str(getattr(route_decision, "route", "") or "unknown"),
                    intent=str(getattr(route_decision, "intent", "") or "unknown"),
                    progress_candidate_ids=[
                        item.candidate_id for item in progress_candidates.values()
                    ],
                    revision=1,
                )
                context = {**context, "situation": situation.prompt_projection()}
                stage = time.perf_counter()
                association = await self._observe_workflow_stage(
                    sid=sid,
                    stage="goal_association",
                    input_payload={
                        "user_text": text,
                        "route_decision": route_decision,
                        "active_goal_snapshots": context.get("active_goal_snapshots", []),
                        "situation_digest": situation.digest,
                        "history_turn_count": len(history),
                    },
                    operation=self.agent_client.resolve_goal_association(
                        session,
                        text=text,
                        route_decision=route_decision,
                        sid=sid,
                        context=context,
                        history=history,
                        timeout_ms=self.policy.goal_association_timeout_ms,
                    ),
                )
                timings["goal_association"] = (time.perf_counter() - stage) * 1000.0
                # Terminal semantics are part of the validated contract.  Diagnostic
                # metadata may explain a failure but must never decide whether Goal
                # state is writable.
                association_status = association.resolution_status
                planning_context = dict(context)
                planning_context["goal_association_resolution"] = association.prompt_projection()

                if association_status not in {"resolved", "needs_clarification"}:
                    raise CognitiveStageFailure(
                        "goal_association",
                        self._stage_failure_metadata(
                            "goal_association",
                            association.metadata,
                            default_failure_class=association_status or "stage_failure",
                        ),
                    )

                transient_responsibility_ids = (
                    self._transient_native_responsibility_ids(
                        association,
                        progress_candidates,
                    )
                    if association_status == "resolved"
                    else []
                )
                if transient_responsibility_ids:
                    planning_context["transient_responsibility_ids"] = list(
                        transient_responsibility_ids
                    )

                # Goal Association is the model-owned semantic interpretation of the
                # user's responsibility.  Publish that validated semantic state as
                # soon as the stage completes so a concurrent follow-up can reason
                # over the in-flight Goal while planning/composition continue.  The
                # host is only transporting and versioning the model result here; it
                # does not infer continuity, entities, or bindings itself.
                #
                # Named cancellation remains deferred to the trusted runtime closure
                # because execution-bound cancellation requires provider receipts.
                has_named_goal_cancellation = any(
                    item.relationship == "cancel" for item in association.associations
                )
                has_goal_replacement = any(
                    goal.supersedes_goal_ids for goal in association.new_goals
                )
                if (
                    self.policy.mode == "apply"
                    and self.goal_state_apply is not None
                    and association_status == "resolved"
                    and not association.clarification
                ):
                    if transient_responsibility_ids:
                        goal_state_commit_stage = "transient_native_responsibility"
                    elif has_named_goal_cancellation:
                        goal_state_commit_stage = "deferred_named_goal_cancellation"
                    elif has_goal_replacement:
                        goal_state_commit_stage = "deferred_goal_replacement"
                    else:
                        commit_started_ms = time.perf_counter() * 1000.0
                        try:
                            goal_state_results = self.goal_state_apply(
                                association,
                                sid=sid,
                                user_text=text,
                                route=route_decision.route,
                                intent=route_decision.intent,
                                source=("goal_driven_cognitive_runtime_goal_association"),
                            )
                        except Exception as exc:
                            self._record_workflow_stage(
                                sid=sid,
                                stage="goal_state_commit",
                                started_monotonic_ms=commit_started_ms,
                                finished_monotonic_ms=time.perf_counter() * 1000.0,
                                status="failed",
                                input_payload={"goal_association": association},
                                output_payload=None,
                                errors=[
                                    {
                                        "error_type": type(exc).__name__,
                                        "error": str(exc),
                                    }
                                ],
                                attempt=1,
                            )
                            raise CognitiveStageFailure(
                                "goal_association_commit",
                                {
                                    "failure_class": type(exc).__name__,
                                    "failure_domain": "semantic_state",
                                    "architecture_attribution": "host_runtime",
                                    "retryable": False,
                                    "error_type": type(exc).__name__,
                                    "error": str(exc)[:300],
                                },
                            ) from exc
                        self._record_workflow_stage(
                            sid=sid,
                            stage="goal_state_commit",
                            started_monotonic_ms=commit_started_ms,
                            finished_monotonic_ms=time.perf_counter() * 1000.0,
                            status="accepted",
                            input_payload={"goal_association": association},
                            output_payload={"goal_state_results": goal_state_results},
                            errors=[],
                            attempt=1,
                        )
                        rejected = [
                            item
                            for item in goal_state_results
                            if item.get("applied") is False
                            and item.get("reason")
                            not in {
                                "operation_already_applied",
                            }
                        ]
                        if rejected:
                            raise CognitiveStageFailure(
                                "goal_association_commit",
                                {
                                    "failure_class": "goal_state_application_rejected",
                                    "failure_domain": "semantic_state",
                                    "architecture_attribution": "host_runtime",
                                    "retryable": False,
                                    "error": json.dumps(
                                        rejected,
                                        ensure_ascii=False,
                                    )[:300],
                                },
                            )
                        goal_state_commit_stage = "goal_association"

            if ready_start_task is not None:
                ready_handles = await ready_start_task
                ready_start_task = None

            association_goal_ids = self._association_goal_ids(association)
            planning_situation = build_situation_projection(
                context=context,
                turn_id=turn_id,
                lane=str(getattr(route_decision, "route", "") or "unknown"),
                intent=str(getattr(route_decision, "intent", "") or "unknown"),
                progress_candidate_ids=[item.candidate_id for item in progress_candidates.values()],
                focus_goal_ids=association_goal_ids or situation.focus_goal_ids,
                revision=situation.revision + 1,
            )
            planning_context["situation"] = planning_situation.prompt_projection()
            if self.policy.mode == "apply" and self.interaction_ledger is not None:
                self.interaction_ledger.record_goal_association(
                    session_id=sid,
                    turn_id=association.turn_id,
                    interaction_id="",
                    association_id=goal_association_fingerprint(association),
                    goal_ids=([] if transient_responsibility_ids else association_goal_ids),
                    relationships=[
                        *[item.relationship for item in association.associations],
                        *(["transient"] if transient_responsibility_ids else []),
                        *(["new"] if association.new_goals and not transient_responsibility_ids else []),
                        *(["clarify"] if association.clarification else []),
                    ],
                )
            planning_context["interaction_context"] = self._interaction_context(
                sid=sid,
                context=planning_context,
                goal_ids=association_goal_ids,
            )
            if association_status == "needs_clarification" or association.clarification:
                terminal_plan = CanonicalPlan(
                    plan_id=f"plan_goal_association_{sid}",
                    planner_tier="deep",
                    disposition="clarify",
                    coverage="uncertain",
                    confidence=association.confidence,
                    goal_ids=association_goal_ids,
                    goal_summary=text,
                    response_text=(
                        association.clarification
                        or (
                            "请补充你想继续或开始的具体事情。"
                            if language.startswith("zh")
                            else "Please clarify which goal you want to continue or start."
                        )
                    ),
                    steps=[],
                    unresolved=["goal_association_clarification"],
                    metadata={
                        "resolver": "goal_association",
                        "status": "clarify",
                        "authority": "advisory",
                        "association_status": association_status,
                    },
                )
            else:
                if not association_goal_ids:
                    raise CognitiveStageFailure(
                        "goal_association",
                        {
                            "failure_class": "empty_canonical_goal_set",
                            "failure_domain": "model_contract",
                            "architecture_attribution": "not_evaluated",
                            "retryable": True,
                            "reason": "resolved Goal Association produced no canonical goals",
                            "status": association_status,
                        },
                    )

                if self._is_direct_spoken_association(association):
                    lane = "chat"
                    adoption_stage = time.perf_counter()
                    adopted_native = self.adapter.build_adopted_native_response(
                        association=association,
                        candidates=progress_candidates,
                        session_id=sid,
                        language=language,
                        context=planning_context,
                    )
                    timings["native_response_adoption"] = (
                        time.perf_counter() - adoption_stage
                    ) * 1000.0
                    if adopted_native is not None:
                        fast_planner_path = "native_response_readiness_adoption"
                        timings["fast_planner"] = 0.0
                        timings["response_composer"] = 0.0
                        if self.policy.mode == "apply":
                            if not self.policy.lane_enabled(lane):
                                return self._finish(
                                    mode="apply",
                                    status="error",
                                    lane=lane,
                                    association=association,
                                    fast_plan=None,
                                    terminal_plan=None,
                                    composition=None,
                                    timings=timings,
                                    started=started,
                                    fallback_reason=(
                                        "native_response_lane_not_enabled_for_apply"
                                    ),
                                    metadata={
                                        "failure_stage": "authority_boundary",
                                        "failure_class": (
                                            "native_response_lane_mismatch"
                                        ),
                                        "failure_domain": "cognitive_runtime",
                                        "retryable": False,
                                        **path_metadata(),
                                    },
                                )
                            runtime = self.adapter.interaction_runtime
                            for speech_item in adopted_native.speech:
                                candidate_id = str(
                                    speech_item.metadata.get("progress_candidate_id")
                                    or ""
                                ).strip()
                                handle = ready_handles.get(candidate_id)
                                if handle is None:
                                    continue
                                if await runtime.bind_ready_native_response(
                                    handle,
                                    canonical_interaction_id=(
                                        adopted_native.interaction_id
                                    ),
                                    canonical_speech=speech_item,
                                ):
                                    ready_bound_count += 1
                                    ready_handles.pop(candidate_id, None)
                            if goal_state_commit_stage == "goal_association":
                                adopted_native.metadata["goal_state_results"] = (
                                    goal_state_results
                                )
                            return self._finish(
                                mode="apply",
                                status="applied",
                                lane=lane,
                                association=association,
                                fast_plan=None,
                                terminal_plan=None,
                                composition=None,
                                interaction=adopted_native,
                                goal_state_results=goal_state_results,
                                timings=timings,
                                started=started,
                                metadata={
                                    "planless_direct_response": True,
                                    "native_response_readiness_adoption": True,
                                    "stage_diagnostics": stage_diagnostics,
                                    **path_metadata(),
                                },
                            )
                        return self._finish(
                            mode="report_only",
                            status="report_only",
                            lane=lane,
                            association=association,
                            fast_plan=None,
                            terminal_plan=None,
                            composition=None,
                            interaction=adopted_native,
                            timings=timings,
                            started=started,
                            metadata={
                                "planless_direct_response": True,
                                "native_response_readiness_adoption": True,
                                "stage_diagnostics": stage_diagnostics,
                                **path_metadata(),
                            },
                        )

                    fast_planner_path = "direct_vocal_output"
                    composition_context = dict(planning_context)
                    composition_context["direct_goal_association_resolution"] = (
                        association.prompt_projection()
                    )
                    composition_context["execution_capabilities"] = []
                    recent_auxiliary_evidence = getattr(
                        self.adapter,
                        "recent_auxiliary_behavior_evidence",
                        None,
                    )
                    composition_context["recent_auxiliary_behavior_evidence"] = (
                        recent_auxiliary_evidence(sid)
                        if callable(recent_auxiliary_evidence)
                        else []
                    )
                    delivered_turn_speech = (
                        self.delivered_turn_speech_provider(sid)
                        if callable(self.delivered_turn_speech_provider)
                        else []
                    )
                    composition_context["delivered_turn_speech"] = [
                        dict(item) for item in delivered_turn_speech if isinstance(item, dict)
                    ]
                    stage = time.perf_counter()
                    composition_resolution = await self._observe_workflow_stage(
                        sid=sid,
                        stage="response_composer",
                        input_payload={
                            "user_text": text,
                            "goal_association": association,
                            "direct_response": True,
                            "delivered_turn_speech": delivered_turn_speech,
                        },
                        operation=self.agent_client.compose_response_plan(
                            session,
                            text=text,
                            route_decision=route_decision,
                            sid=sid,
                            context=composition_context,
                            history=history,
                            timeout_ms=(self.policy.response_composer_timeout_ms),
                        ),
                    )
                    timings["response_composer"] = (time.perf_counter() - stage) * 1000.0
                    if composition_resolution.status != "resolved" or not isinstance(
                        composition_resolution.composition,
                        DirectResponseComposition,
                    ):
                        raise CognitiveStageFailure(
                            "response_composer",
                            self._stage_failure_metadata(
                                "response_composer",
                                composition_resolution.metadata,
                                default_failure_class=(composition_resolution.status),
                            ),
                        )
                    if self.policy.mode == "apply":
                        if not self.policy.lane_enabled(lane):
                            return self._finish(
                                mode="apply",
                                status="error",
                                lane=lane,
                                association=association,
                                fast_plan=None,
                                terminal_plan=None,
                                composition=composition_resolution,
                                timings=timings,
                                started=started,
                                fallback_reason=("direct_response_lane_not_enabled_for_apply"),
                                metadata={
                                    "failure_stage": "authority_boundary",
                                    "failure_class": ("direct_response_lane_mismatch"),
                                    "failure_domain": "cognitive_runtime",
                                    "retryable": False,
                                    **path_metadata(),
                                },
                            )
                        stage = time.perf_counter()
                        interaction = await self._observe_workflow_stage(
                            sid=sid,
                            stage="runtime_adapter",
                            input_payload={
                                "goal_association": association,
                                "response_composition": composition_resolution,
                            },
                            operation=self.adapter.build_direct_response(
                                composition=(composition_resolution.composition),
                                session_id=sid,
                                language=language,
                                context=composition_context,
                            ),
                        )
                        timings["runtime_adapter"] = (time.perf_counter() - stage) * 1000.0
                        if goal_state_commit_stage == "goal_association":
                            interaction.metadata["goal_state_results"] = goal_state_results
                        return self._finish(
                            mode="apply",
                            status="applied",
                            lane=lane,
                            association=association,
                            fast_plan=None,
                            terminal_plan=None,
                            composition=composition_resolution,
                            interaction=interaction,
                            goal_state_results=goal_state_results,
                            timings=timings,
                            started=started,
                            metadata={
                                "planless_direct_response": True,
                                "stage_diagnostics": stage_diagnostics,
                                **path_metadata(),
                            },
                        )
                    return self._finish(
                        mode="report_only",
                        status="report_only",
                        lane=lane,
                        association=association,
                        fast_plan=None,
                        terminal_plan=None,
                        composition=composition_resolution,
                        timings=timings,
                        started=started,
                        metadata={
                            "planless_direct_response": True,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )

                stage = time.perf_counter()
                fast_plan = await self._observe_workflow_stage(
                    sid=sid,
                    stage="fast_planner",
                    input_payload={
                        "user_text": text,
                        "route_decision": route_decision,
                        "goal_association": association,
                        "interaction_context": planning_context.get(
                            "interaction_context", {}
                        ),
                    },
                    operation=self.agent_client.resolve_fast_plan(
                        session,
                        text=text,
                        route_decision=route_decision,
                        sid=sid,
                        context=planning_context,
                        history=history,
                        timeout_ms=self.policy.fast_planner_timeout_ms,
                    ),
                )
                timings["fast_planner"] = (time.perf_counter() - stage) * 1000.0
                fast_failure = self._optional_stage_failure_metadata(
                    "fast_planner", fast_plan.metadata
                )
                if fast_failure is not None:
                    stage_diagnostics.append(fast_failure)
                terminal_plan = fast_plan
                fast_planner_path = self._fast_plan_path(fast_plan)
                if fast_plan.disposition == "escalate":
                    if fast_planner_path == "contract_failure":
                        # A malformed or grounding-invalid Fast plan is not evidence
                        # that the user's problem needs deeper cognition. Deep Planner
                        # must not become an online repair service for a Fast output
                        # that failed the authoritative contract. Preserve the failure
                        # and stop before dispatch; a later user turn or Reflection may
                        # reconsider from new meaning/evidence.
                        fast_failure = self._optional_stage_failure_metadata(
                            "fast_planner", fast_plan.metadata
                        ) or self._stage_failure_metadata(
                            "fast_planner",
                            fast_plan.metadata,
                            default_failure_class=(
                                fast_plan.escalation_reason
                                or "fast_planner_contract_failure"
                            ),
                        )
                        raise CognitiveStageFailure("fast_planner", fast_failure)

                    deep_reason = "semantic_escalation"
                    deep_planner_invocation_reasons.append(deep_reason)
                    deep_context = dict(planning_context)
                    deep_context["fast_plan_resolution"] = self._fast_plan_context_for_deep(
                        fast_plan
                    )
                    fast_validation_feedback = fast_plan.metadata.get(
                        "validation_feedback"
                    )
                    if isinstance(fast_validation_feedback, list):
                        deep_context["runtime_validator_feedback"] = [
                            dict(item)
                            for item in fast_validation_feedback
                            if isinstance(item, dict)
                        ]
                    deep_context["deep_planner_invocation_reason"] = deep_reason
                    stage = time.perf_counter()
                    terminal_plan = await self._observe_workflow_stage(
                        sid=sid,
                        stage="deep_planner",
                        input_payload={
                            "user_text": text,
                            "goal_association": association,
                            "fast_plan": fast_plan,
                            "validation_feedback": deep_context.get(
                                "runtime_validator_feedback", []
                            ),
                            "invocation_reason": deep_reason,
                        },
                        operation=self.agent_client.resolve_deep_plan(
                            session,
                            text=text,
                            route_decision=route_decision,
                            sid=sid,
                            context=deep_context,
                            history=history,
                            timeout_ms=self.policy.deep_planner_timeout_ms,
                        ),
                    )
                    timings["deep_planner"] = (time.perf_counter() - stage) * 1000.0
                    deep_failure = self._optional_stage_failure_metadata(
                        "deep_planner", terminal_plan.metadata
                    )
                    if deep_failure is not None:
                        raise CognitiveStageFailure("deep_planner", deep_failure)

            lane = self.adapter.lane_for_plan(terminal_plan)
            source_route = str(getattr(route_decision, "route", "") or "")
            if lane == "robot_action" and source_route != "robot_action":
                return self._finish(
                    mode=self.policy.mode,
                    status="error",
                    lane=lane,
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    composition=None,
                    timings=timings,
                    started=started,
                    fallback_reason=("terminal_plan_exceeds_source_route_effect_envelope"),
                    metadata={
                        "failure_stage": "authority_boundary",
                        "failure_class": "route_effect_escalation",
                        "failure_domain": "cognitive_runtime",
                        "architecture_attribution": "not_evaluated",
                        "retryable": False,
                        "source_route": source_route,
                        "terminal_lane": lane,
                        "stage_diagnostics": stage_diagnostics,
                        **path_metadata(),
                    },
                )
            runtime_errors = await self._observe_workflow_stage(
                sid=sid,
                stage="canonical_plan_validation",
                input_payload={"canonical_plan": terminal_plan},
                operation=self.adapter.validation_errors(terminal_plan),
                metadata={"phase": "pre_dispatch"},
            )
            if runtime_errors:
                self._record_workflow_stage(
                    sid=sid,
                    stage="canonical_plan_rejection",
                    started_monotonic_ms=time.perf_counter() * 1000.0,
                    finished_monotonic_ms=time.perf_counter() * 1000.0,
                    status="rejected",
                    input_payload={"canonical_plan": terminal_plan},
                    output_payload={"validation_errors": runtime_errors},
                    errors=list(runtime_errors),
                    attempt=1,
                    metadata={"dispatch_allowed": False},
                )
            if runtime_errors:
                # Fast Planner already escalated to Deep Planner when needed, and
                # Deep Planner owns its one bounded same-tier revision.  The Host
                # validates authority and runtime contracts; it must not become a
                # third semantic planner after rejecting the terminal plan.
                raise ValueError(
                    "runtime validation rejected terminal canonical plan: "
                    + json.dumps(runtime_errors, ensure_ascii=False)
                )

            if self.policy.mode == "apply" and self.interaction_ledger is not None:
                self.interaction_ledger.record_plan(
                    session_id=sid,
                    turn_id=self._context_turn_id(planning_context, sid),
                    interaction_id="",
                    plan=terminal_plan,
                )
            planning_context["interaction_context"] = self._interaction_context(
                sid=sid,
                context=planning_context,
                goal_ids=terminal_plan.goal_ids,
            )

            if self.adapter.is_pure_safe_read_plan(terminal_plan):
                lane = "tool"
                if self.policy.mode == "apply":
                    if not self.policy.lane_enabled(lane):
                        return self._finish(
                            mode="apply",
                            status="error",
                            lane=lane,
                            association=association,
                            fast_plan=fast_plan,
                            terminal_plan=terminal_plan,
                            composition=None,
                            timings=timings,
                            started=started,
                            fallback_reason="safe_read_lane_not_enabled_for_apply",
                            metadata={
                                "failure_stage": "authority_boundary",
                                "failure_class": "safe_read_lane_mismatch",
                                "failure_domain": "cognitive_runtime",
                                "retryable": False,
                                **path_metadata(),
                            },
                        )
                    stage = time.perf_counter()
                    interaction = await self._observe_workflow_stage(
                        sid=sid,
                        stage="runtime_adapter",
                        input_payload={
                            "canonical_plan": terminal_plan,
                            "execution_only_safe_read": True,
                        },
                        operation=self.adapter.build_execution_only_response(
                            plan=terminal_plan,
                            session_id=sid,
                            language=language,
                            context=planning_context,
                        ),
                    )
                    timings["runtime_adapter"] = (time.perf_counter() - stage) * 1000.0
                    timings["response_composer"] = 0.0
                    interaction.metadata["goal_association"] = association.model_dump(
                        mode="json", exclude_none=True
                    )
                    if goal_state_commit_stage == "goal_association":
                        interaction.metadata["goal_state_results"] = goal_state_results
                    interaction.metadata["continuous_cognition"] = {
                        "native_response_progress_started_before_goal_association_completed": bool(
                            progress_candidates
                        ),
                        "provider_work_started_before_goal_association_completed": False,
                        "response_composer_llm_avoided": True,
                        "ready_result_bound_count": ready_bound_count,
                    }
                    return self._finish(
                        mode="apply",
                        status="applied",
                        lane=lane,
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
                        composition=None,
                        interaction=interaction,
                        goal_state_results=goal_state_results,
                        timings=timings,
                        started=started,
                        metadata={
                            "execution_only_safe_read": True,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )
                timings["response_composer"] = 0.0
                return self._finish(
                    mode="report_only",
                    status="report_only",
                    lane=lane,
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    composition=None,
                    timings=timings,
                    started=started,
                    metadata={
                        "execution_only_safe_read": True,
                        "stage_diagnostics": stage_diagnostics,
                        **path_metadata(),
                    },
                )

            composition_context = dict(planning_context)
            composition_context["canonical_plan_resolution"] = terminal_plan.prompt_projection()
            composition_context["execution_capabilities"] = [
                {
                    "capability_id": step.capability_id,
                    "step_id": step.step_id,
                    "execution_lane": str(
                        self.adapter.interaction_runtime.skill_definition(
                            step.skill_id
                        ).metadata.get("execution_lane")
                        or "activity"
                    ),
                    "effects": list(
                        self.adapter.interaction_runtime.skill_definition(
                            step.skill_id
                        ).metadata.get("effects")
                        or []
                    ),
                    "safety_class": str(
                        self.adapter.interaction_runtime.skill_definition(
                            step.skill_id
                        ).metadata.get("safety_class")
                        or ""
                    ),
                    "requires_confirmation": bool(
                        self.adapter.interaction_runtime.skill_definition(
                            step.skill_id
                        ).requires_confirmation
                    ),
                }
                for step in terminal_plan.steps
            ]
            recent_auxiliary_evidence = getattr(
                self.adapter,
                "recent_auxiliary_behavior_evidence",
                None,
            )
            composition_context["recent_auxiliary_behavior_evidence"] = (
                recent_auxiliary_evidence(sid) if callable(recent_auxiliary_evidence) else []
            )
            delivered_turn_speech = (
                self.delivered_turn_speech_provider(sid)
                if callable(self.delivered_turn_speech_provider)
                else []
            )
            composition_context["delivered_turn_speech"] = [
                dict(item) for item in delivered_turn_speech if isinstance(item, dict)
            ]
            stage = time.perf_counter()
            composition_resolution = await self._observe_workflow_stage(
                sid=sid,
                stage="response_composer",
                input_payload={
                    "user_text": text,
                    "canonical_plan": terminal_plan,
                    "execution_capabilities": composition_context.get(
                        "execution_capabilities", []
                    ),
                    "delivered_turn_speech": delivered_turn_speech,
                },
                operation=self.agent_client.compose_response_plan(
                    session,
                    text=text,
                    route_decision=route_decision,
                    sid=sid,
                    context=composition_context,
                    history=history,
                    timeout_ms=self.policy.response_composer_timeout_ms,
                ),
            )
            timings["response_composer"] = (time.perf_counter() - stage) * 1000.0
            if (
                composition_resolution.status != "resolved"
                or composition_resolution.composition is None
            ):
                raise CognitiveStageFailure(
                    "response_composer",
                    self._stage_failure_metadata(
                        "response_composer",
                        composition_resolution.metadata,
                        default_failure_class=composition_resolution.status,
                    ),
                )

            if self.policy.mode == "apply":
                if not self.policy.lane_enabled(lane):
                    return self._finish(
                        mode="apply",
                        status="error",
                        lane=lane,
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
                        composition=composition_resolution,
                        timings=timings,
                        started=started,
                        fallback_reason="terminal_plan_lane_not_enabled_for_apply",
                        metadata={
                            "failure_stage": "authority_boundary",
                            "failure_class": "terminal_plan_lane_mismatch",
                            "failure_domain": "cognitive_runtime",
                            "architecture_attribution": "not_evaluated",
                            "retryable": False,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )
                stage = time.perf_counter()
                interaction = await self._observe_workflow_stage(
                    sid=sid,
                    stage="runtime_adapter",
                    input_payload={
                        "canonical_plan": terminal_plan,
                        "response_composition": composition_resolution,
                    },
                    operation=self.adapter.build_response(
                        plan=terminal_plan,
                        composition=composition_resolution.composition,
                        session_id=sid,
                        language=language,
                        context=composition_context,
                    ),
                )
                timings["runtime_adapter"] = (time.perf_counter() - stage) * 1000.0
                if goal_state_commit_stage == "goal_association":
                    interaction.metadata["goal_association"] = association.model_dump(
                        mode="json", exclude_none=True
                    )
                    interaction.metadata["goal_state_results"] = goal_state_results
                return self._finish(
                    mode="apply",
                    status="applied",
                    lane=lane,
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    composition=composition_resolution,
                    interaction=interaction,
                    goal_state_results=goal_state_results,
                    timings=timings,
                    started=started,
                    metadata={
                        "stage_diagnostics": stage_diagnostics,
                        "architecture_attribution": (
                            "not_evaluated" if stage_diagnostics else "not_evaluated"
                        ),
                        **path_metadata(),
                    },
                )

            return self._finish(
                mode="report_only",
                status="report_only",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                timings=timings,
                started=started,
                metadata={
                    "stage_diagnostics": stage_diagnostics,
                    "architecture_attribution": (
                        "not_evaluated" if stage_diagnostics else "not_evaluated"
                    ),
                    **path_metadata(),
                },
            )
        except CognitiveStageFailure as exc:
            failure_metadata = {
                **exc.failure_metadata,
                "failure_stage": exc.stage,
                "stage_diagnostics": stage_diagnostics,
                **path_metadata(),
            }
            return self._finish(
                mode=self.policy.mode,
                status="error",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                interaction=interaction,
                goal_state_results=goal_state_results,
                timings=timings,
                started=started,
                fallback_reason=str(exc)[:500],
                metadata=failure_metadata,
            )
        except Exception as exc:
            return self._finish(
                mode=self.policy.mode,
                status="error",
                lane=lane,
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                composition=composition_resolution,
                interaction=interaction,
                goal_state_results=goal_state_results,
                timings=timings,
                started=started,
                fallback_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
                metadata={
                    "failure_stage": "runtime",
                    "failure_class": type(exc).__name__,
                    "failure_domain": "cognitive_runtime",
                    "architecture_attribution": "not_evaluated",
                    "retryable": False,
                    "stage_diagnostics": stage_diagnostics,
                    **path_metadata(),
                },
            )
        finally:
            if ready_start_task is not None:
                pending_outcome = (
                    await asyncio.gather(ready_start_task, return_exceptions=True)
                )[0]
                if isinstance(pending_outcome, dict):
                    ready_handles.update(pending_outcome)
                elif isinstance(pending_outcome, BaseException):
                    logger.warning(
                        "ready progress cleanup observed failure error_type=%s error=%s",
                        type(pending_outcome).__name__,
                        pending_outcome,
                    )
            await self._cancel_ready_progress(ready_handles)

    @staticmethod
    def _optional_stage_failure_metadata(
        stage: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        values = dict(metadata or {})
        if not values.get("failure_class"):
            return None
        return GoalDrivenRuntimeCoordinator._stage_failure_metadata(
            stage,
            values,
            default_failure_class=str(values.get("failure_class")),
        )

    @staticmethod
    def _stage_failure_metadata(
        stage: str,
        metadata: dict[str, Any] | None,
        *,
        default_failure_class: str,
    ) -> dict[str, Any]:
        values = dict(metadata or {})
        result = {
            "stage": stage,
            "failure_class": str(
                values.get("failure_class") or default_failure_class or "stage_failure"
            ),
            "failure_domain": str(values.get("failure_domain") or "model_or_runtime"),
            "architecture_attribution": str(
                values.get("architecture_attribution") or "not_evaluated"
            ),
            "retryable": bool(values.get("retryable", False)),
            "error_type": str(values.get("error_type") or ""),
            "error": str(values.get("error") or values.get("reason_summary") or "")[:300],
        }
        for key in (
            "purpose",
            "model",
            "timeout_ms",
            "elapsed_ms",
            "num_ctx",
            "num_predict",
            "done_reason",
            "prompt_eval_count",
            "eval_count",
            "suggestion",
            "reason",
        ):
            if key in values and values[key] not in {None, ""}:
                result[key] = values[key]
        return result

    @staticmethod
    def _finish(
        *,
        mode: CognitiveRuntimeMode,
        status: CognitiveRuntimeStatus,
        lane: CognitiveLane,
        association: GoalAssociationResolution | None,
        fast_plan: CanonicalPlan | None,
        terminal_plan: CanonicalPlan | None,
        composition: ResponseCompositionResolution | None,
        timings: dict[str, float],
        started: float,
        interaction: InteractionResponse | None = None,
        goal_state_results: list[dict[str, Any]] | None = None,
        fallback_reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CognitiveRuntimeResolution:
        final_timings = dict(timings)
        final_timings["total"] = (time.perf_counter() - started) * 1000.0
        return CognitiveRuntimeResolution(
            mode=mode,
            status=status,
            lane=lane,
            goal_association=association,
            fast_plan=fast_plan,
            terminal_plan=terminal_plan,
            response_composition=composition,
            interaction_response=interaction,
            goal_state_results=list(goal_state_results or []),
            timings_ms={key: round(value, 1) for key, value in final_timings.items()},
            fallback_reason=fallback_reason,
            metadata=dict(metadata or {}),
        )
