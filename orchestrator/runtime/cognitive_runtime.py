from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from agent.app.capabilities.validator import validate_args_for_schema
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.schemas.route import RouteDecision as CompatibilityRouteDecision
from shared.chromie_contracts.core_interpretation import CoreInterpretationResult
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
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    DirectResponseComposition,
    ResponseCompositionResolution,
    canonical_plan_fingerprint,
    goal_association_fingerprint,
)
from shared.chromie_contracts.social_attention import normalize_social_attention_mode
from shared.chromie_contracts.user_turn import (
    AttentionReviewResult,
    GatewayContextSnapshot,
    UserTurnEnvelope,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

from orchestrator.runtime.evidence_identity import runtime_identity_reference

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
    host_replan_budget: int = 1
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
            "social_attention": (
                composition.social_attention_plan.decision
                if composition and composition.social_attention_plan
                else None
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
            "safe_read_semantic_review": (
                dict(composition.metadata.get("safe_read_semantic_review") or {})
                if composition
                and isinstance(composition.metadata, dict)
                and isinstance(composition.metadata.get("safe_read_semantic_review"), dict)
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

    def _effective_social_attention_mode(
        self,
        composition: CoordinatedResponsePlan,
    ) -> str:
        policy_payload = composition.metadata.get("social_attention_policy")
        agent_mode = normalize_social_attention_mode(
            policy_payload.get("mode") if isinstance(policy_payload, dict) else "off",
            default="off",
        )
        # Both the Agent-side policy and the Host-side launch policy must allow
        # the behavior. The more restrictive mode wins; a compromised/stale
        # composition cannot widen the local runtime policy.
        if "off" in {self.social_attention_mode, agent_mode}:
            return "off"
        if "report_only" in {self.social_attention_mode, agent_mode}:
            return "report_only"
        return "on"

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
        speech = [
            InteractionSpeech(
                text=final.text,
                timing="immediate",
                style="brief",
                metadata={
                    "source": "goal_driven_response_composer",
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
                    "execution_lane": "speaking",
                    "delivery_role": "response",
                },
            )
        ]

        runtime_context = context if isinstance(context, dict) else {}
        attention = composition.social_attention_plan
        policy_mode = self._effective_social_attention_mode(composition)
        omitted_attention: list[str] = []
        skills: list[SkillRequest] = []
        if attention is not None and attention.decision == "express":
            if policy_mode == "off":
                omitted_attention.append("policy_off")
            elif policy_mode == "report_only":
                omitted_attention.append("policy_report_only")
            else:
                target_error = self._attention_target_error(attention, runtime_context)
                if target_error:
                    omitted_attention.append(target_error)
                else:
                    seen: set[str] = set()
                    for index, behavior in enumerate(attention.behaviors):
                        try:
                            await self.interaction_runtime.ensure_skill_definitions(
                                [behavior.skill_id]
                            )
                            definition = self.interaction_runtime.skill_definition(
                                behavior.skill_id
                            )
                            if behavior.skill_id in seen:
                                omitted_attention.append(
                                    f"duplicate_social_skill:{behavior.skill_id}"
                                )
                                continue
                            if not definition.available:
                                omitted_attention.append(f"unavailable:{behavior.skill_id}")
                                continue
                            if definition.requires_confirmation:
                                omitted_attention.append(
                                    f"confirmation_required:{behavior.skill_id}"
                                )
                                continue
                            if behavior.timing != "parallel":
                                omitted_attention.append(
                                    f"auxiliary_must_be_parallel:{behavior.skill_id}"
                                )
                                continue
                            schema_errors = validate_args_for_schema(
                                behavior.args, definition.input_schema
                            )
                            if schema_errors:
                                omitted_attention.append(f"invalid_args:{behavior.skill_id}")
                                continue
                            target_args_error = self._attention_target_args_error(
                                behavior.args,
                                definition.input_schema,
                                runtime_context,
                            )
                            if target_args_error:
                                omitted_attention.append(
                                    f"target_error:{behavior.skill_id}:{target_args_error}"
                                )
                                continue
                            digest = hashlib.sha256(
                                (f"{fingerprint}|direct-social|{index}|{behavior.skill_id}").encode(
                                    "utf-8"
                                )
                            ).hexdigest()[:20]
                            request = SkillRequest(
                                request_id=f"social_{digest}",
                                skill_id=behavior.skill_id,
                                skill_version=definition.version,
                                args=behavior.args,
                                timing="parallel",
                                timeout_ms=definition.timeout_ms,
                                cancellable=definition.interruptible,
                                requires_confirmation=False,
                                idempotency_key=(f"direct:{fingerprint[:16]}:social:{index}"),
                                metadata={
                                    "source": "social_attention_plan",
                                    "auxiliary_social_attention": True,
                                    "behavior_domain": attention.behavior_domain,
                                    "interaction_role": attention.interaction_role,
                                    "social_attention_purpose": attention.purpose,
                                    "social_function": behavior.social_function,
                                    "goal_association_fingerprint": fingerprint,
                                    "target": attention.target.model_dump(
                                        mode="json", exclude_none=True
                                    ),
                                    "reason": behavior.reason,
                                    "social_attention_policy_mode": policy_mode,
                                    "execution_lane": "social_attention",
                                },
                            )
                            skills.append(request)
                            self._record_auxiliary_behavior_request(request, session_id=session_id)
                            seen.add(behavior.skill_id)
                        except Exception as exc:
                            omitted_attention.append(
                                f"invalid:{behavior.skill_id}:{type(exc).__name__}"
                            )

        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "planless_direct_response": True,
            "goal_association": association.model_dump(mode="json", exclude_none=True),
            "goal_association_fingerprint": fingerprint,
            "response_composition": composition.model_dump(mode="json", exclude_none=True),
            "execution_lanes": {
                "social_attention": "proposal_and_auxiliary_execution",
                "speaking": "response_delivery",
                "activity": "idle",
            },
            "lane_coordination_groups": [],
            "planning_result": "direct_response",
            "capability_decision": "respond",
            "goal_ids": goal_ids,
            "planner_tier": "none",
            "omitted_social_attention": omitted_attention,
            "social_attention_policy_mode": policy_mode,
            "operational_speech_authority": "llm_direct_response",
        }
        if isinstance(runtime_context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = runtime_context["user_turn_envelope"]
        return InteractionResponse(
            interaction_id=f"cognitive_{session_id}",
            status="ok",
            speech=speech,
            skills=skills,
            metadata=metadata,
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
        speaking_coordination_by_step_id = {
            step_id: item
            for item in composition.lane_coordination
            for step_id in item.speaking_step_ids
        }
        plan_steps_by_id = {step.step_id: step for step in plan.steps}
        media_mixer_by_coordination_id: dict[str, dict[str, Any]] = {}
        for coordination in composition.lane_coordination:
            if "speaking" not in coordination.lanes:
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
                if definition.metadata.get("mixer_policy") != ("duck_media_during_speaking"):
                    raise ValueError(
                        "speech-over-media coordination requires the declared "
                        "duck_media_during_speaking mixer policy: " + step_id
                    )
                try:
                    mixer_contracts.append(
                        {
                            "media_mixer_policy": "duck_media_during_speaking",
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
            for key in ("delivered_turn_speech", "scheduled_turn_speech"):
                values = context.get(key)
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    text = " ".join(str(item.get("text") or "").strip().split())
                    status = str(item.get("status") or "").strip()
                    if text and status in {
                        "scheduled",
                        "playback_started",
                        "playback_completed",
                    }:
                        reusable_turn_speech[text] = dict(item)
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
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        speech: list[InteractionSpeech] = []
        for projected in projected_speech_stages:
            phase = str(projected["phase"])
            coordination_id = str(projected.get("coordination_id") or "").strip()
            coordination = lane_coordination_by_id.get(coordination_id)
            coordinated_speech = bool(coordination is not None and "speaking" in coordination.lanes)
            playback_barrier = not safe_read_parallel and not coordinated_speech
            speech_metadata = {
                "source": projected["source"],
                "phase": phase,
                "speech_act": projected["speech_act"],
                "commitment_state": projected["commitment_state"],
                "must_not_claim_completion": projected["must_not_claim_completion"],
                "covers_goal_ids": projected["covers_goal_ids"],
                "source_goal_ids": projected["covers_goal_ids"],
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "claims": projected["claims"],
                "execution_lane": "speaking",
                "delivery_role": projected.get("delivery_role", "response"),
                "wait_for_playback_start": playback_barrier,
                "playback_start_required_for_delivery": playback_barrier,
            }
            if projected.get("reuse_current_turn_speech") is True:
                normalized_text = " ".join(str(projected.get("text") or "").strip().split())
                reused = reusable_turn_speech.get(normalized_text)
                if reused is None:
                    raise ValueError(
                        "response stage requested current-turn speech reuse but "
                        "no exact scheduled or delivered utterance exists"
                    )
                raw_orders = reused.get("orders")
                if not isinstance(raw_orders, list):
                    raw_orders = []
                speech_metadata.update(
                    {
                        "reuse_current_turn_speech": True,
                        "reused_speech_event_id": reused.get("event_id")
                        or reused.get("speech_event_id"),
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
                        "parallel_with_social_attention": (
                            "social_attention" in coordination.lanes
                        ),
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
            if execution_lane not in {"speaking", "activity"}:
                raise ValueError(
                    "canonical plan capability has unsupported execution lane: "
                    f"{step.skill_id}={execution_lane!r}"
                )
            if (
                step.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
                and execution_lane != "speaking"
            ):
                raise ValueError(
                    "exact vocal performance capability must remain in the speaking lane"
                )
            if step.capability_id in MEDIA_CAPABILITY_IDS.values() and execution_lane != "activity":
                raise ValueError(
                    "exact media playback capabilities must remain in the activity lane"
                )
            coordination = (
                speaking_coordination_by_step_id.get(step.step_id)
                if execution_lane == "speaking"
                else activity_coordination_by_step_id.get(step.step_id)
            )
            wrong_lane_coordination = (
                activity_coordination_by_step_id.get(step.step_id)
                if execution_lane == "speaking"
                else speaking_coordination_by_step_id.get(step.step_id)
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
                    "parallel_with_speech": (
                        execution_lane != "speaking" and "speaking" in coordination.lanes
                    ),
                    "parallel_with_activity": (
                        execution_lane != "activity" and "activity" in coordination.lanes
                    ),
                    "parallel_with_social_attention": ("social_attention" in coordination.lanes),
                }
                if coordination is not None
                else {}
            )
            media_mixer_metadata: dict[str, Any] = {}
            if (
                coordination is not None
                and step.capability_id in MEDIA_CAPABILITY_IDS.values()
                and "speaking" in coordination.lanes
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
                        "parallel_with_speech": (
                            safe_read_parallel
                            or bool(coordination_metadata.get("parallel_with_speech"))
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

        omitted_attention: list[str] = []
        attention = composition.social_attention_plan
        runtime_context = context if isinstance(context, dict) else {}
        policy_mode = self._effective_social_attention_mode(composition)
        if attention is not None and attention.decision == "express" and policy_mode == "off":
            omitted_attention.append("policy_off")
        elif (
            attention is not None
            and attention.decision == "express"
            and policy_mode == "report_only"
        ):
            omitted_attention.append("policy_report_only")
        elif attention is not None and attention.decision == "express":
            target_error = self._attention_target_error(attention, runtime_context)
            if target_error:
                omitted_attention.append(target_error)
            else:
                primary_definitions = {
                    step.skill_id: self.interaction_runtime.skill_definition(step.skill_id)
                    for step in plan.steps
                }
                seen_social: set[str] = set()
                for index, behavior in enumerate(attention.behaviors):
                    try:
                        await self.interaction_runtime.ensure_skill_definitions([behavior.skill_id])
                        definition = self.interaction_runtime.skill_definition(behavior.skill_id)
                        if (
                            behavior.skill_id in primary_definitions
                            or behavior.skill_id in seen_social
                        ):
                            omitted_attention.append(
                                f"duplicate_or_primary_skill:{behavior.skill_id}"
                            )
                            continue
                        if not definition.available:
                            omitted_attention.append(f"unavailable:{behavior.skill_id}")
                            continue
                        if definition.requires_confirmation:
                            omitted_attention.append(f"confirmation_required:{behavior.skill_id}")
                            continue
                        if behavior.timing != "parallel":
                            omitted_attention.append(
                                f"auxiliary_must_be_parallel:{behavior.skill_id}"
                            )
                            continue
                        schema_errors = validate_args_for_schema(
                            behavior.args, definition.input_schema
                        )
                        if schema_errors:
                            omitted_attention.append(f"invalid_args:{behavior.skill_id}")
                            continue
                        target_args_error = self._attention_target_args_error(
                            behavior.args,
                            definition.input_schema,
                            runtime_context,
                        )
                        if target_args_error:
                            omitted_attention.append(
                                f"target_error:{behavior.skill_id}:{target_args_error}"
                            )
                            continue
                        if self._attention_conflicts_with_primary(
                            definition,
                            behavior.timing,
                            primary_definitions,
                        ):
                            omitted_attention.append(f"resource_conflict:{behavior.skill_id}")
                            continue
                        coordination_id = str(behavior.coordination_id or "").strip()
                        coordination = lane_coordination_by_id.get(coordination_id)
                        coordination_metadata = (
                            {
                                "coordination_id": coordination.coordination_id,
                                "lane_coordination_relation": coordination.relation,
                                "lane_start_policy": coordination.start_policy,
                                "lane_failure_policy": coordination.failure_policy,
                                "parallel_with_speech": ("speaking" in coordination.lanes),
                                "parallel_with_activity": ("activity" in coordination.lanes),
                            }
                            if coordination is not None
                            else {}
                        )
                        digest = hashlib.sha256(
                            f"{fingerprint}|social|{index}|{behavior.skill_id}".encode("utf-8")
                        ).hexdigest()[:20]
                        skills.append(
                            SkillRequest(
                                request_id=f"social_{digest}",
                                skill_id=behavior.skill_id,
                                skill_version=definition.version,
                                args=behavior.args,
                                timing=behavior.timing,
                                timeout_ms=definition.timeout_ms,
                                cancellable=definition.interruptible,
                                requires_confirmation=False,
                                idempotency_key=(
                                    f"{plan.plan_id}:social:{index}:{fingerprint[:16]}"
                                ),
                                metadata={
                                    "source": "social_attention_plan",
                                    "auxiliary_social_attention": True,
                                    "behavior_domain": attention.behavior_domain,
                                    "interaction_role": attention.interaction_role,
                                    "social_attention_purpose": attention.purpose,
                                    "speech_expression": attention.speech_expression.model_dump(
                                        mode="json", exclude_none=True
                                    ),
                                    "social_function": behavior.social_function,
                                    "canonical_plan_id": plan.plan_id,
                                    "target": attention.target.model_dump(
                                        mode="json", exclude_none=True
                                    ),
                                    "reason": behavior.reason,
                                    "social_attention_policy_mode": policy_mode,
                                    "execution_lane": "social_attention",
                                    **coordination_metadata,
                                },
                            )
                        )
                        seen_social.add(behavior.skill_id)
                    except Exception as exc:
                        omitted_attention.append(
                            f"invalid:{behavior.skill_id}:{type(exc).__name__}"
                        )

        proposed_social_capability_ids = (
            [behavior.skill_id for behavior in attention.behaviors]
            if attention is not None and attention.decision == "express"
            else []
        )
        materialized_social_capability_ids = [
            request.skill_id
            for request in skills
            if request.metadata.get("auxiliary_social_attention") is True
        ]
        for request in skills:
            self._record_auxiliary_behavior_request(
                request,
                session_id=session_id,
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
            1
            for request in skills
            if request.metadata.get("auxiliary_social_attention") is not True
            and request.metadata.get("effectful") is True
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
                "social_attention": "proposal_and_auxiliary_execution",
                "speaking": (
                    "response_delivery_and_provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "speaking" for request in skills
                    )
                    else "response_delivery"
                ),
                "activity": (
                    "provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "activity"
                        and request.metadata.get("auxiliary_social_attention") is not True
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
            "omitted_social_attention": omitted_attention,
            "social_attention_policy_mode": policy_mode,
            "social_attention_model_decision": (
                attention.decision if attention is not None else "missing"
            ),
            "social_attention_proposed_capability_ids": proposed_social_capability_ids,
            "social_attention_materialized_capability_ids": (materialized_social_capability_ids),
            "social_attention_materialized_count": len(materialized_social_capability_ids),
            "recent_auxiliary_behavior_evidence": (
                self.recent_auxiliary_behavior_evidence(session_id)
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
        return InteractionResponse(
            status=status_map.get(plan.disposition, "error"),
            speech=speech,
            skills=skills,
            requires_confirmation=any(item.requires_confirmation for item in skills),
            reason=(
                plan.escalation_reason if plan.disposition in {"unavailable", "refused"} else None
            ),
            metadata=metadata,
        )


class GoalDrivenRuntimeCoordinator:
    """Single-direction goal association → fast/deep plan → composition pipeline."""

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
        context_refresh: Callable[[], dict[str, Any]] | None = None,
        delivered_turn_speech_provider: (Callable[[str], list[dict[str, Any]]] | None) = None,
    ) -> None:
        self.agent_client = agent_client
        self.adapter = adapter
        self.policy = policy
        self.goal_state_apply = goal_state_apply
        self.context_refresh = context_refresh
        self.delivered_turn_speech_provider = delivered_turn_speech_provider

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
                str((goal.metadata or {}).get("responsibility_kind") or "") == "spoken_response"
                and not bool((goal.metadata or {}).get("provider_required"))
                and bool(str(goal.goal_id or "").strip())
                for goal in association.new_goals
            )
        )

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
    def _fast_plan_context_for_deep(
        plan: CanonicalPlan,
        *,
        path_classification: str,
    ) -> dict[str, Any]:
        payload = plan.prompt_projection()
        if path_classification != "contract_failure":
            return payload
        metadata = dict(payload.get("metadata") or {})
        payload["metadata"] = {
            key: metadata[key]
            for key in (
                "resolver",
                "status",
                "authority",
                "path_classification",
                "failure_class",
                "failure_domain",
                "architecture_attribution",
                "retryable",
                "error_type",
            )
            if key in metadata
        }
        return payload

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
            return attach_core_identity(resolution)
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
                    span.set_attribute("result_status", resolution.status)
                    span.set_attribute("lane", resolution.lane)
                    span.set_attribute(
                        "runtime_replan_count",
                        resolution.metadata.get("runtime_replan_count", 0),
                    )
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
        lane: CognitiveLane = "unsupported"

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
                        "direct_spoken_response",
                        "terminal_missing_ability",
                    }
                    and not deep_planner_invocation_reasons
                ),
                "terminal_planner_tier": (
                    terminal_plan.planner_tier if terminal_plan is not None else ""
                ),
                "authoritative_goal_count": (
                    len(self._association_goal_ids(association)) if association is not None else 0
                ),
                "fast_goal_outcome_count": (
                    len(fast_plan.goal_outcomes) if fast_plan is not None else 0
                ),
                "fast_executable_step_count": (
                    len(fast_plan.steps) if fast_plan is not None else 0
                ),
                "goal_state_commit_stage": goal_state_commit_stage,
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
            stage = time.perf_counter()
            association = await self.agent_client.resolve_goal_association(
                session,
                text=text,
                route_decision=route_decision,
                sid=sid,
                context=context,
                history=history,
                timeout_ms=self.policy.goal_association_timeout_ms,
            )
            timings["goal_association"] = (time.perf_counter() - stage) * 1000.0
            association_status = str((association.metadata or {}).get("status") or "resolved")
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
            if (
                self.policy.mode == "apply"
                and self.goal_state_apply is not None
                and association_status == "resolved"
                and not association.clarification
            ):
                if has_named_goal_cancellation:
                    goal_state_commit_stage = "deferred_named_goal_cancellation"
                else:
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

            association_goal_ids = self._association_goal_ids(association)
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
                    fast_planner_path = "direct_spoken_response"
                    lane = "chat"
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
                    composition_resolution = await self.agent_client.compose_response_plan(
                        session,
                        text=text,
                        route_decision=route_decision,
                        sid=sid,
                        context=composition_context,
                        history=history,
                        timeout_ms=(self.policy.response_composer_timeout_ms),
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
                        interaction = await self.adapter.build_direct_response(
                            composition=(composition_resolution.composition),
                            session_id=sid,
                            language=language,
                            context=composition_context,
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
                                "runtime_replan_count": 0,
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
                            "runtime_replan_count": 0,
                            "planless_direct_response": True,
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )

                stage = time.perf_counter()
                fast_plan = await self.agent_client.resolve_fast_plan(
                    session,
                    text=text,
                    route_decision=route_decision,
                    sid=sid,
                    context=planning_context,
                    history=history,
                    timeout_ms=self.policy.fast_planner_timeout_ms,
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
                    deep_reason = (
                        "fast_contract_failure"
                        if fast_planner_path == "contract_failure"
                        else "semantic_escalation"
                    )
                    deep_planner_invocation_reasons.append(deep_reason)
                    deep_context = dict(planning_context)
                    deep_context["fast_plan_resolution"] = self._fast_plan_context_for_deep(
                        fast_plan,
                        path_classification=fast_planner_path,
                    )
                    deep_context["deep_planner_invocation_reason"] = deep_reason
                    stage = time.perf_counter()
                    terminal_plan = await self.agent_client.resolve_deep_plan(
                        session,
                        text=text,
                        route_decision=route_decision,
                        sid=sid,
                        context=deep_context,
                        history=history,
                        timeout_ms=self.policy.deep_planner_timeout_ms,
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
            runtime_errors = await self.adapter.validation_errors(terminal_plan)
            replan_count = 0
            while runtime_errors and replan_count < self.policy.host_replan_budget:
                replan_count += 1
                if fast_plan is None:
                    raise ValueError("runtime replan requires an existing fast plan")
                deep_context = dict(planning_context)
                deep_context["fast_plan_resolution"] = self._fast_plan_context_for_deep(
                    fast_plan,
                    path_classification=fast_planner_path,
                )
                deep_context["runtime_validator_feedback"] = runtime_errors
                deep_context["deep_planner_invocation_reason"] = "host_replan"
                deep_planner_invocation_reasons.append("host_replan")
                stage = time.perf_counter()
                terminal_plan = await self.agent_client.resolve_deep_plan(
                    session,
                    text=text,
                    route_decision=route_decision,
                    sid=sid,
                    context=deep_context,
                    history=history,
                    timeout_ms=self.policy.deep_planner_timeout_ms,
                )
                timings[f"runtime_replan_{replan_count}"] = (time.perf_counter() - stage) * 1000.0
                deep_failure = self._optional_stage_failure_metadata(
                    "deep_planner", terminal_plan.metadata
                )
                if deep_failure is not None:
                    raise CognitiveStageFailure("deep_planner", deep_failure)
                lane = self.adapter.lane_for_plan(terminal_plan)
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
                runtime_errors = await self.adapter.validation_errors(terminal_plan)
            if runtime_errors:
                raise ValueError(
                    "runtime validation rejected canonical plan: "
                    + json.dumps(runtime_errors, ensure_ascii=False)
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
            composition_resolution = await self.agent_client.compose_response_plan(
                session,
                text=text,
                route_decision=route_decision,
                sid=sid,
                context=composition_context,
                history=history,
                timeout_ms=self.policy.response_composer_timeout_ms,
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
                interaction = await self.adapter.build_response(
                    plan=terminal_plan,
                    composition=composition_resolution.composition,
                    session_id=sid,
                    language=language,
                    context=composition_context,
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
                        "runtime_replan_count": replan_count,
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
                    "runtime_replan_count": replan_count,
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
