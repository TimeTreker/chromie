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

import aiohttp
from agent.app.capabilities.validator import validate_args_for_schema
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.chromie_contracts.core_interpretation import (
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    claim_qualification_policy_sha256,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
    goal_association_fingerprint,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    MEDIA_CAPABILITY_IDS,
    CapabilityRequest,
    VOCAL_MODES,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    ClarifyGoalPlanOutcome,
    ExecuteGoalPlanOutcome,
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerCommunicativeAct,
    FastPlannerFirstResponse,
    GoalSatisfactionAssessment,
    PlannerInformationGap,
    PlannedCommunicativeAct,
    RespondGoalPlanOutcome,
    fast_planner_activity_request_id,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.social_attention import (
    SocialAttentionActivityAnchor,
    SocialAttentionActivityRealization,
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
    turn_envelope: UserTurnEnvelope | None = None
    goal_association: GoalAssociationResolution | None = None
    fast_advance: FastPlannerAdvance | None = None
    fast_plan: CanonicalPlan | None = None
    terminal_plan: CanonicalPlan | None = None
    interaction_response: InteractionResponse | None = None
    goal_state_results: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    fallback_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class CognitiveRuntimePolicy:
    mode: CognitiveRuntimeMode = "off"
    goal_association_timeout_ms: int = 3500
    fast_planner_timeout_ms: int = 3000
    deep_planner_timeout_ms: int = 10000


@dataclass(frozen=True)
class _GoalAssociationStageResult:
    """Mechanical lifecycle result for the existing Goal Association owner."""

    association: GoalAssociationResolution
    context: dict[str, Any]
    history: list[dict[str, Any]]
    planning_context: dict[str, Any]
    situation: Any
    goal_state_results: list[dict[str, Any]]
    goal_state_commit_stage: str
    has_named_goal_cancellation: bool
    has_goal_replacement: bool


@dataclass
class _FastAdvanceProgress:
    """Transient early-execution handle visible to cancellation while Fast advance runs."""

    ready_capability_execution: Any | None = None
    ready_capability_status: str = "not_started"


@dataclass(frozen=True)
class _FastAdvanceStageResult:
    """Mechanical result of the Fast Planner advance phase and safe early realization."""

    advance: FastPlannerAdvance
    activity_plan_elapsed_ms: float
    ready_capability_execution: Any | None
    ready_capability_status: str
    communicative_realization_status: str
    social_attention_opportunity_delta: int
    ready_communicative_executions: tuple[Any, ...]
    vocal_activity_ids: tuple[str, ...]


class CognitiveAgentClient(Protocol):
    async def resolve_goal_association(
        self, session: Any, **kwargs: Any
    ) -> GoalAssociationResolution: ...

    async def resolve_fast_advance(
        self, session: Any, **kwargs: Any
    ) -> FastPlannerAdvance: ...

    async def resolve_fast_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_deep_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_reflection(
        self, session: Any, **kwargs: Any
    ) -> ReflectionResolution: ...

    async def resolve_social_attention(
        self, session: Any, **kwargs: Any
    ) -> SocialAttentionPlan: ...


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
            "fast_advance": (
                resolution.fast_advance.model_dump(mode="json", exclude_none=True)
                if resolution.fast_advance is not None
                else None
            ),
            "fast_plan": self._plan_summary(resolution.fast_plan),
            "terminal_plan": self._plan_summary(resolution.terminal_plan),
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
    def _interaction_summary(response: InteractionResponse | None) -> dict[str, Any] | None:
        if response is None:
            return None
        return {
            "interaction_id": response.interaction_id,
            "status": response.status,
            "speech_count": len(response.speech),
            "capability_ids": [item.capability_id for item in response.capabilities],
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
        request: CapabilityRequest,
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
                "primary_activity_goal_ids": list(
                    request.metadata.get("primary_activity_goal_ids") or []
                ),
                "primary_activity_execution_lanes": list(
                    request.metadata.get("primary_activity_execution_lanes") or []
                ),
                "primary_activity_vocal_modes": list(
                    request.metadata.get("primary_activity_vocal_modes") or []
                ),
                "canonical_plan_id": request.metadata.get("canonical_plan_id"),
                "policy_mode": request.metadata.get("social_attention_policy_mode"),
            }
        )


    def is_pure_safe_read_plan(self, plan: CanonicalPlan) -> bool:
        if plan.disposition != "execute" or not plan.steps:
            return False
        try:
            definitions = [
                self.interaction_runtime.capability_definition(step.capability_id)
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
        capability_ids = [step.capability_id for step in plan.steps]
        try:
            await self.interaction_runtime.ensure_capability_definitions(capability_ids)
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
                definition = self.interaction_runtime.capability_definition(step.capability_id)
            except Exception as exc:
                errors.append(
                    {
                        "type": "unknown_runtime_capability",
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
                        "type": "runtime_capability_unavailable",
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

        requests: list[CapabilityRequest] = []
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
        primary_capability_ids.update(primary_activity.realization.capability_ids)
        primary_definitions: dict[str, Any] = {}
        unresolved_embodied_primary_ids: set[str] = set()
        for capability_id in sorted(primary_capability_ids):
            try:
                await self.interaction_runtime.ensure_capability_definitions([capability_id])
                primary_definition = self.interaction_runtime.capability_definition(capability_id)
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
                if behavior.capability_id in primary_capability_ids:
                    reasons.append(
                        f"duplicates_primary_activity:{behavior.capability_id}"
                    )
                    continue
                if unresolved_embodied_primary_ids:
                    reasons.extend(
                        f"primary_definition_unavailable:{capability_id}"
                        for capability_id in sorted(unresolved_embodied_primary_ids)
                    )
                    continue
                await self.interaction_runtime.ensure_capability_definitions([behavior.capability_id])
                definition = self.interaction_runtime.capability_definition(behavior.capability_id)
                metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
                domains = {
                    str(item).strip().lower()
                    for item in metadata.get("behavior_domains", [])
                    if str(item).strip()
                }
                if "social_attention" not in domains:
                    reasons.append(f"not_social_attention:{behavior.capability_id}")
                    continue
                if behavior.capability_id in seen:
                    reasons.append(f"duplicate_social_skill:{behavior.capability_id}")
                    continue
                if not definition.available:
                    reasons.append(f"unavailable:{behavior.capability_id}")
                    continue
                if definition.requires_confirmation:
                    reasons.append(f"confirmation_required:{behavior.capability_id}")
                    continue
                if behavior.timing != "parallel":
                    reasons.append(f"auxiliary_must_be_parallel:{behavior.capability_id}")
                    continue
                if not definition.can_run_parallel:
                    reasons.append(f"parallel_not_supported:{behavior.capability_id}")
                    continue
                if (
                    behavior.capability_id.startswith("soridormi.")
                    and metadata.get("parallel_metadata_declared") is not True
                ):
                    reasons.append(f"parallel_metadata_missing:{behavior.capability_id}")
                    continue
                if self._attention_conflicts_with_primary(
                    definition,
                    behavior.timing,
                    primary_definitions,
                ):
                    reasons.append(f"resource_conflict:{behavior.capability_id}")
                    continue
                schema_errors = validate_args_for_schema(behavior.args, definition.input_schema)
                if schema_errors:
                    reasons.append(f"invalid_args:{behavior.capability_id}")
                    continue
                target_args_error = self._attention_target_args_error(
                    behavior.args,
                    definition.input_schema,
                    runtime_context,
                )
                if target_args_error:
                    reasons.append(
                        f"target_error:{behavior.capability_id}:{target_args_error}"
                    )
                    continue
                schema_digest = output_schema_sha256(definition.output_schema)
                digest = hashlib.sha256(
                    f"{turn_id}|{primary_activity.activity_id}|{event}|{index}|{behavior.capability_id}".encode("utf-8")
                ).hexdigest()[:20]
                request = CapabilityRequest(
                    request_id=f"social_{digest}",
                    capability_id=behavior.capability_id,
                    capability_version=definition.version,
                    args=dict(behavior.args),
                    timing="parallel",
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=False,
                    idempotency_key=(
                        f"{turn_id}:social:{primary_activity.activity_id}:{event}:{index}"
                    ),
                    committed_output_schema_sha256=schema_digest,
                    committed_completion_evidence_sha256=(
                        claim_qualification_policy_sha256(
                            definition.completion_evidence_policy
                        )
                        if definition.completion_evidence_policy is not None
                        else None
                    ),
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
                        "primary_activity_goal_ids": list(primary_activity.goal_ids),
                        "primary_activity_execution_lanes": list(
                            primary_activity.realization.execution_lanes
                        ),
                        "primary_activity_vocal_modes": list(
                            primary_activity.realization.vocal_modes
                        ),
                    },
                )
                requests.append(request)
                self._record_auxiliary_behavior_request(request, session_id=session_id)
                seen.add(behavior.capability_id)
            except (TypeError, ValueError, ValidationError, RuntimeError) as exc:
                reasons.append(f"invalid:{behavior.capability_id}:{type(exc).__name__}")

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
            "primary_activity_goal_ids": list(primary_activity.goal_ids),
            "primary_activity_execution_lanes": list(
                primary_activity.realization.execution_lanes
            ),
            "primary_activity_vocal_modes": list(
                primary_activity.realization.vocal_modes
            ),
        }
        envelope = runtime_context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            response_metadata["user_turn_envelope"] = dict(envelope)
        response = InteractionResponse(
            interaction_id=interaction_id,
            status="ok",
            capabilities=requests,
            metadata=response_metadata,
        )
        dispatch = await self.interaction_runtime.submit_response(
            response,
            session_id=session_id,
        )
        execution = await self.interaction_runtime.wait_dispatch(dispatch)
        return {
            "status": execution.status,
            "decision": plan.decision,
            "event": event,
            "materialized_count": len(requests),
            "request_ids": [item.request_id for item in requests],
            "reasons": reasons,
        }

    def build_fast_advance_response(
        self,
        *,
        advance: FastPlannerAdvance,
        plan: CanonicalPlan,
        session_id: str,
        language: str,
        preexecuted_activity_ids: set[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Compile Planner-owned Communicative Activities after GA Goal binding."""

        if plan.steps or plan.disposition not in {"respond", "clarify"}:
            raise ValueError("Fast Planner vocal response requires a non-executable Plan")
        runtime_context = context if isinstance(context, dict) else {}
        preexecuted = set(preexecuted_activity_ids or ())
        refs_to_goals = plan.metadata.get("goal_ids_by_responsibility")
        if not isinstance(refs_to_goals, dict):
            refs_to_goals = {}
        speech: list[InteractionSpeech] = []
        for activity in advance.activities:
            if activity.role == "capability" or activity.activity_id in preexecuted:
                continue
            source_goal_ids: list[str] = []
            for responsibility_ref in activity.source_responsibility_refs:
                raw_goal_ids = refs_to_goals.get(responsibility_ref)
                if not isinstance(raw_goal_ids, list):
                    continue
                for goal_id in raw_goal_ids:
                    if goal_id not in source_goal_ids:
                        source_goal_ids.append(goal_id)
            speech.append(
                InteractionSpeech(
                    id=f"fast_activity_speech_{activity.activity_id}",
                    text=activity.text,
                    timing=activity.timing,
                    style="brief",
                    priority="normal",
                    interruptible=True,
                    metadata={
                        "source": "fast_planner_advance",
                        "wording_owner": "planner",
                        "truth_stage": activity.truth_stage,
                        "evidence_refs": list(activity.evidence_refs),
                        "phase": "fast_planner_activity",
                        "speech_act": activity.speech_act,
                        "turn_id": advance.turn_id,
                        "session_id": session_id,
                        "language": language,
                        "fast_activity_id": activity.activity_id,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "source_goal_ids": source_goal_ids,
                        "canonical_plan_id": plan.plan_id,
                        "canonical_goal_binding_pending": False,
                        "goal_completion_authority": activity.role
                        == "complete_response",
                        "execution_lane": "vocal",
                        "delivery_role": activity.role,
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                    },
                )
            )
        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "turn_id": advance.turn_id,
            "session_id": session_id,
            "language": language,
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
            "canonical_plan_id": plan.plan_id,
            "goal_ids": list(plan.goal_ids),
            "planner_tier": "fast",
            "fast_activity_ids": [item.activity_id for item in advance.activities],
            "preexecuted_fast_activity_ids": sorted(preexecuted),
            "goal_grouped_task_list": True,
        }
        envelope = runtime_context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            metadata["user_turn_envelope"] = dict(envelope)
        return InteractionResponse(
            interaction_id=f"cognitive_{session_id}",
            status="clarify" if plan.disposition == "clarify" else "ok",
            speech=speech,
            metadata=metadata,
        )

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
        planner_response = PlannerResponseProjection(
            projection_id=f"execution_only_{fingerprint[:20]}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan,
            response_plan=ResponsePlan(),
            lane_coordination=[],
            confidence=1.0,
            rationale="Pure safe-read execution does not require pre-evidence planner response projection.",
            metadata={
                "authority": "advisory",
                "resolver": "readiness_execution",
                "task_plan_immutable": True,
                "safe_read_speech_optional": True,
            },
        )
        return await self.build_response(
            plan=plan,
            planner_response=planner_response,
            session_id=session_id,
            language=language,
            context=context,
        )

    async def build_planner_owned_response(
        self,
        *,
        plan: CanonicalPlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Mechanically realize exact Planner wording without another model owner."""

        delivered_by_fast_activity_id: dict[str, dict[str, Any]] = {}
        ambiguous_fast_activity_ids: set[str] = set()
        if isinstance(context, dict):
            delivered_rows = context.get("delivered_turn_speech")
            if isinstance(delivered_rows, list):
                for row in delivered_rows:
                    if not isinstance(row, dict):
                        continue
                    activity_id = " ".join(
                        str(row.get("fast_activity_id") or "").strip().split()
                    )
                    event_id = " ".join(
                        str(row.get("event_id") or row.get("speech_event_id") or "")
                        .strip()
                        .split()
                    )
                    if not activity_id or not event_id:
                        continue
                    previous = delivered_by_fast_activity_id.get(activity_id)
                    if previous is not None and str(previous.get("event_id")) != event_id:
                        ambiguous_fast_activity_ids.add(activity_id)
                        continue
                    delivered_by_fast_activity_id[activity_id] = dict(row)
        for activity_id in ambiguous_fast_activity_ids:
            delivered_by_fast_activity_id.pop(activity_id, None)

        confirmation_required = any(
            self.interaction_runtime.capability_definition(step.capability_id)
            .requires_confirmation
            for step in plan.steps
        )

        if plan.communicative_acts:
            executable_goal_ids = set(plan.executable_goal_ids())
            clarification_acts = [
                act for act in plan.communicative_acts if act.role == "clarification"
            ]
            execution_acts = [
                act
                for act in plan.communicative_acts
                if act.role != "clarification"
                and set(act.source_goal_ids).intersection(executable_goal_ids)
            ]
            other_acts = [
                act
                for act in plan.communicative_acts
                if act.role != "clarification" and act not in execution_acts
            ]

            def stage_for_acts(
                acts: list[Any],
                *,
                speech_act: str,
                commitment_state: str,
                must_not_claim_completion: bool,
            ) -> ResponseStage | None:
                if not acts:
                    return None
                text = " ".join(dict.fromkeys(act.text for act in acts))
                covered = [
                    goal_id
                    for goal_id in plan.goal_ids
                    if any(goal_id in act.source_goal_ids for act in acts)
                ]
                reused_event_id = ""
                if len(acts) == 1:
                    reused_event = delivered_by_fast_activity_id.get(
                        str(acts[0].activity_id)
                    )
                    if reused_event is not None:
                        reused_event_id = " ".join(
                            str(reused_event.get("event_id") or "").strip().split()
                        )
                return ResponseStage(
                    text=text,
                    speech_act=speech_act,
                    commitment_state=commitment_state,
                    must_not_claim_completion=must_not_claim_completion,
                    covers_goal_ids=covered,
                    reuse_current_turn_speech=bool(reused_event_id),
                    reused_speech_event_id=reused_event_id or None,
                    metadata={
                        "wording_owner": "planner",
                        "canonical_plan_id": plan.plan_id,
                        "communicative_activity_ids": [
                            act.activity_id for act in acts
                        ],
                        "truth_stages": list(
                            dict.fromkeys(act.truth_stage for act in acts)
                        ),
                        "evidence_refs": list(
                            dict.fromkeys(
                                evidence_ref
                                for act in acts
                                for evidence_ref in act.evidence_refs
                            )
                        ),
                    },
                )

            # ResponsePlan is a transport projection only. It combines exact
            # Planner-owned Activities that share a delivery phase; it never
            # invents or rewrites their wording.
            immediate_acts = [*other_acts, *clarification_acts]
            immediate = stage_for_acts(
                immediate_acts,
                speech_act=(
                    "ask_clarification"
                    if clarification_acts
                    else (other_acts[0].speech_act if other_acts else "inform")
                ),
                commitment_state=(
                    "waiting_for_user"
                    if clarification_acts
                    else (
                        "completed"
                        if plan.disposition == "respond"
                        else "none"
                    )
                ),
                must_not_claim_completion=(
                    bool(clarification_acts) or plan.disposition != "respond"
                ),
            )
            pre_action = stage_for_acts(
                execution_acts,
                speech_act=("ask_confirmation" if confirmation_required else "inform"),
                commitment_state=(
                    "waiting_for_user" if confirmation_required else "evaluating"
                ),
                must_not_claim_completion=True,
            )
            response_plan = ResponsePlan(
                immediate=immediate,
                pre_action=pre_action,
            )
            fingerprint = canonical_plan_fingerprint(plan)
            planner_response = PlannerResponseProjection(
                projection_id=f"planner_owned_{fingerprint[:20]}",
                canonical_plan_id=plan.plan_id,
                canonical_plan_fingerprint=fingerprint,
                canonical_plan=plan,
                response_plan=response_plan,
                lane_coordination=[],
                confidence=plan.confidence,
                rationale="Planner owns exact Communicative Activity wording.",
                metadata={
                    "authority": "planner",
                    "resolver": "planner_owned_communication",
                    "task_plan_immutable": True,
                },
            )
            return await self.build_response(
                plan=plan,
                planner_response=planner_response,
                session_id=session_id,
                language=language,
                context=context,
            )

        text = " ".join(str(plan.response_text or "").strip().split())
        if not text:
            texts = [
                " ".join(str(item.response_text or "").strip().split())
                for item in plan.goal_outcomes
                if " ".join(str(item.response_text or "").strip().split())
            ]
            text = " ".join(dict.fromkeys(texts))
        if not text and plan.communicative_acts:
            text = " ".join(
                dict.fromkeys(
                    item.text for item in plan.communicative_acts if item.text
                )
            )
        pure_silent_execution = (
            not text
            and plan.disposition == "execute"
            and bool(plan.steps)
            and set(plan.executable_goal_ids()) == set(plan.goal_ids)
            and not confirmation_required
        )
        if pure_silent_execution:
            fingerprint = canonical_plan_fingerprint(plan)
            planner_response = PlannerResponseProjection(
                projection_id=f"planner_owned_{fingerprint[:20]}",
                canonical_plan_id=plan.plan_id,
                canonical_plan_fingerprint=fingerprint,
                canonical_plan=plan,
                response_plan=ResponsePlan(),
                lane_coordination=[],
                confidence=plan.confidence,
                rationale=(
                    "Planner selected complete execution without a communicative act."
                ),
                metadata={
                    "authority": "planner",
                    "resolver": "planner_owned_communication",
                    "task_plan_immutable": True,
                },
            )
            return await self.build_response(
                plan=plan,
                planner_response=planner_response,
                session_id=session_id,
                language=language,
                context=context,
            )
        if not text:
            raise ValueError(
                "Planner-owned communicative response requires exact text"
            )

        if plan.disposition == "clarify":
            speech_act = "ask_clarification"
            commitment_state = "waiting_for_user"
            must_not_claim_completion = True
        elif confirmation_required:
            speech_act = "ask_confirmation"
            commitment_state = "waiting_for_user"
            must_not_claim_completion = True
        elif plan.disposition in {"execute", "mixed"}:
            speech_act = "inform"
            commitment_state = "evaluating"
            must_not_claim_completion = True
        elif plan.disposition == "respond":
            speech_act = "respond"
            commitment_state = "completed"
            must_not_claim_completion = False
        elif plan.disposition == "refused":
            speech_act = "refuse"
            commitment_state = "none"
            must_not_claim_completion = True
        else:
            speech_act = "inform"
            commitment_state = "none"
            must_not_claim_completion = True

        stage = ResponseStage(
            text=text,
            speech_act=speech_act,
            commitment_state=commitment_state,
            must_not_claim_completion=must_not_claim_completion,
            covers_goal_ids=list(plan.goal_ids),
            metadata={
                "wording_owner": "planner",
                "canonical_plan_id": plan.plan_id,
            },
        )
        response_plan = (
            ResponsePlan(pre_action=stage)
            if plan.disposition in {"execute", "mixed"}
            else ResponsePlan(final=stage)
        )
        fingerprint = canonical_plan_fingerprint(plan)
        planner_response = PlannerResponseProjection(
            projection_id=f"planner_owned_{fingerprint[:20]}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan,
            response_plan=response_plan,
            lane_coordination=[],
            confidence=plan.confidence,
            rationale="Planner owns exact Communicative Activity wording.",
            metadata={
                "authority": "planner",
                "resolver": "planner_owned_communication",
                "task_plan_immutable": True,
            },
        )
        return await self.build_response(
            plan=plan,
            planner_response=planner_response,
            session_id=session_id,
            language=language,
            context=context,
        )

    async def build_response(
        self,
        *,
        plan: CanonicalPlan,
        planner_response: PlannerResponseProjection,
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
                        planner_response.response_plan.immediate,
                        planner_response.response_plan.pre_action,
                        planner_response.response_plan.final,
                    )
                    if item is not None
                )
                + len(planner_response.response_plan.progress),
            },
        ) as span:
            response = await self._build_response(
                plan=plan,
                planner_response=planner_response,
                session_id=session_id,
                language=language,
                context=context,
            )
            span.set_attribute("response_status", response.status)
            span.set_attribute("speech_count", len(response.speech))
            span.set_attribute("capability_count", len(response.capabilities))
            if response.status == "error":
                span.set_status("error")
            return response

    async def _build_response(
        self,
        *,
        plan: CanonicalPlan,
        planner_response: PlannerResponseProjection,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        if planner_response.canonical_plan_id != plan.plan_id:
            raise ValueError("planner response projection references a different canonical plan")
        if planner_response.canonical_plan_fingerprint != canonical_plan_fingerprint(plan):
            raise ValueError("planner response projection canonical-plan fingerprint mismatch")
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
        reflex = envelope.get("reflex") if isinstance(envelope, dict) else None
        deterministic_interrupt = bool(
            isinstance(envelope, dict)
            and envelope.get("admission") == "reflex_and_admit"
            and isinstance(reflex, dict)
            and reflex.get("action") == "interrupt"
        )
        speech_prohibited = bool(
            deterministic_interrupt and reflex.get("should_speak") is not True
        )
        residual_effects_permitted = bool(
            deterministic_interrupt
            and reflex.get("cancellation_scope") == "output_only"
            and isinstance(reflex.get("metadata"), dict)
            and reflex["metadata"].get("residual_semantic_input") is True
        )
        alternative = str(plan.metadata.get("plan_relation") or "") in {
            "alternative",
            "safe_adjustment",
        } or bool(plan.metadata.get("user_confirmation_required"))
        executable_goal_ids = set(plan.executable_goal_ids())
        confirmation_goal_ids = set(executable_goal_ids) if alternative else set()
        if not alternative:
            for step in plan.steps:
                definition = self.interaction_runtime.capability_definition(step.capability_id)
                if definition.requires_confirmation:
                    confirmation_goal_ids.update(step.source_goal_ids)

        response_plan = planner_response.response_plan
        lane_coordination_by_id = {
            item.coordination_id: item for item in planner_response.lane_coordination
        }
        activity_coordination_by_step_id = {
            step_id: item
            for item in planner_response.lane_coordination
            for step_id in item.activity_step_ids
        }
        vocal_coordination_by_step_id = {
            step_id: item
            for item in planner_response.lane_coordination
            for step_id in item.vocal_step_ids
        }
        plan_steps_by_id = {step.step_id: step for step in plan.steps}
        media_mixer_by_coordination_id: dict[str, dict[str, Any]] = {}
        for coordination in planner_response.lane_coordination:
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
                definition = self.interaction_runtime.capability_definition(
                    plan_steps_by_id[step_id].capability_id
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
            [self.interaction_runtime.capability_definition(step.capability_id) for step in plan.steps]
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
        pure_execution_speech_optional = (
            effectful_pre_execution
            and plan.disposition == "execute"
            and executable_goal_ids == set(plan.goal_ids)
            and not confirmation_goal_ids
            and response_plan.immediate is None
            and response_plan.pre_action is None
        )
        reusable_turn_speech: dict[str, dict[str, Any]] = {}
        if isinstance(context, dict):
            # A speech-event identity selects the Communicative Act. Text is
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
                if pure_execution_speech_optional:
                    stage_items = []
                elif not available_pre_execution or not required_goal_ids.issubset(
                    covered_pre_execution
                ):
                    raise ValueError(
                        "effectful pre-execution response requires immediate and/or "
                        "pre_action stages covering all canonical goals"
                    )
                elif pre_action_item is not None and required_goal_ids.issubset(
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
                            "source": "planner_communicative_activity",
                            "operational_text_source": "planner_wording_runtime_validated",
                            "runtime_confirmation_required": False,
                            "safe_read_micro_ack": safe_read_speech_optional,
                            "coordination_id": stage.coordination_id,
                            "delivery_role": stage.delivery_role,
                            "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                            "reused_speech_event_id": stage.reused_speech_event_id,
                            "communicative_activity_ids": list(
                                (stage.metadata or {}).get("communicative_activity_ids") or []
                            ),
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
                        "source": "planner_communicative_activity",
                        "operational_text_source": ("planner_wording_runtime_validated"),
                        "runtime_confirmation_required": (
                            bool(confirmation_goal_ids) and stage in confirmation_stages
                        ),
                        "coordination_id": stage.coordination_id,
                        "delivery_role": stage.delivery_role,
                        "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                        "reused_speech_event_id": stage.reused_speech_event_id,
                        "communicative_activity_ids": list(
                            (stage.metadata or {}).get("communicative_activity_ids") or []
                        ),
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
                    "source": "planner_communicative_activity",
                    "coordination_id": stage.coordination_id,
                    "delivery_role": stage.delivery_role,
                    "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                    "reused_speech_event_id": stage.reused_speech_event_id,
                    "communicative_activity_ids": list(
                        (stage.metadata or {}).get("communicative_activity_ids") or []
                    ),
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        if speech_prohibited:
            projected_speech_stages = []

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
                "session_id": session_id,
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
                "communicative_activity_ids": list(
                    projected.get("communicative_activity_ids") or []
                ),
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

        capabilities: list[CapabilityRequest] = []
        for step in plan.steps:
            if deterministic_interrupt and not residual_effects_permitted:
                # The control itself is already applied by the Gateway. Semantic
                # admission exists only to reconcile retained Goal state; it may
                # never materialize replacement work for the interrupting turn.
                continue
            if (step.metadata or {}).get("retained_work_reused") is True:
                # The exact live request remains owned by its original Runtime
                # submission. Planner selected it explicitly and Host validated
                # its identity above, so this canonical revision must not
                # dispatch a duplicate request.
                continue
            definition = self.interaction_runtime.capability_definition(step.capability_id)
            execution_lane = str(definition.metadata.get("execution_lane") or "activity").strip()
            if execution_lane not in {"vocal", "activity"}:
                raise ValueError(
                    "canonical plan capability has unsupported execution lane: "
                    f"{step.capability_id}={execution_lane!r}"
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
                    raise ValueError("cross-lane capability is not parallel-safe: " + step.capability_id)
                if definition.metadata.get("parallel_metadata_declared") is not True:
                    raise ValueError(
                        "cross-lane capability lacks explicit parallel metadata: " + step.capability_id
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
            fast_activity_id = str(
                (step.metadata or {}).get("fast_activity_id") or ""
            ).strip()
            digest = hashlib.sha256(f"{fingerprint}|{step.step_id}".encode("utf-8")).hexdigest()[
                :20
            ]
            request_id = (
                fast_planner_activity_request_id(turn_id, fast_activity_id)
                if fast_activity_id
                else f"cogreq_{digest}"
            )
            capabilities.append(
                CapabilityRequest(
                    request_id=request_id,
                    capability_id=step.capability_id,
                    capability_version=definition.version,
                    args=step.args,
                    timing="parallel" if safe_read_parallel else step.timing,
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=(bool(definition.requires_confirmation) or alternative),
                    idempotency_key=f"{plan.plan_id}:{step.step_id}:{fingerprint[:16]}",
                    committed_output_schema_sha256=output_schema_sha256(definition.output_schema),
                    committed_completion_evidence_sha256=(
                        claim_qualification_policy_sha256(
                            definition.completion_evidence_policy
                        )
                        if definition.completion_evidence_policy is not None
                        else None
                    ),
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
                        "task_list_revision": int(
                            plan.metadata.get("task_list_revision") or 1
                        ),
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
            1 for request in capabilities if request.metadata.get("effectful") is True
        )
        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
            "planner_response_projection": planner_response.model_dump(mode="json", exclude_none=True),
            "execution_lanes": {
                "vocal": (
                    "response_delivery_and_provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "vocal" for request in capabilities
                    )
                    else "response_delivery"
                ),
                "activity": (
                    "provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "activity"
                        for request in capabilities
                    )
                    else "idle"
                ),
            },
            "lane_coordination_groups": [
                item.model_dump(mode="json", exclude_none=True)
                for item in planner_response.lane_coordination
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
                else "planner_selected_silence"
                if pure_execution_speech_optional
                else "llm_parallel_speech"
                if safe_read_parallel
                else "planner_wording_runtime_validated"
                if effectful_pre_execution
                else "not_applicable"
            ),
            "safe_read_parallel_execution": safe_read_parallel,
            "safe_read_speech_optional": safe_read_speech_optional,
            "retained_work_reconciliation_only": (
                plan.metadata.get("retained_work_reconciliation_only") is True
            ),
            "deterministic_interrupt_speech_prohibited": speech_prohibited,
            "deterministic_interrupt_residual_effects_permitted": (
                residual_effects_permitted
            ),
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
            metadata["confirmation_prompt_source"] = (
                "planner_wording_runtime_validated"
            )
        response = InteractionResponse(
            status=status_map.get(plan.disposition, "error"),
            speech=speech,
            capabilities=capabilities,
            requires_confirmation=any(item.requires_confirmation for item in capabilities),
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
        planner_gap_apply: Callable[..., list[dict[str, Any]]] | None = None,
        context_refresh: Callable[[str | None], dict[str, Any]] | None = None,
        delivered_turn_speech_provider: (Callable[[str], list[dict[str, Any]]] | None) = None,
        interaction_ledger: Any | None = None,
        workflow_stage_sink: Callable[..., None] | None = None,
    ) -> None:
        self.agent_client = agent_client
        self.adapter = adapter
        self.policy = policy
        self.goal_state_apply = goal_state_apply
        self.planner_gap_apply = planner_gap_apply
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
    def _fast_planner_communicative_social_activity(
        activity: FastPlannerCommunicativeAct,
        *,
        ready_execution: Any | None = None,
    ) -> SocialAttentionActivityAnchor:
        """Use the Planner-authored Communicative Act as its own SA anchor.

        Fast Planner already owns semantic Activity identity here. Do not wait for
        a later context projection to rediscover scheduled speech, and do not
        promote the underlying cognition milestone into a social Activity.
        """

        speech = getattr(ready_execution, "speech", None)
        execution_item_id = str(getattr(speech, "id", "") or "").strip()
        if not execution_item_id:
            execution_item_id = f"fast_activity_speech_{activity.activity_id}"
        return SocialAttentionActivityAnchor(
            activity_id=activity.activity_id,
            phase="ready",
            summary=" ".join(activity.text.strip().split())[:500],
            realization=SocialAttentionActivityRealization(
                execution_lanes=["vocal"],
                vocal_modes=["speech"],
                execution_item_ids=[execution_item_id],
            ),
        )

    @staticmethod
    def _scheduled_speech_social_activity(
        context: dict[str, Any],
        *,
        turn_id: str,
    ) -> SocialAttentionActivityAnchor | None:
        """Project one scheduled Fast-Planner Communicative Act as a semantic Activity.

        The act is not called a ``speech Activity``.  Speaking is only its Vocal
        Expression realization; the text/purpose carries the outward semantic act.
        """

        rows = context.get("scheduled_turn_speech")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get("text") or "").strip().split())
            if not text:
                continue
            execution_item_id = " ".join(
                str(row.get("speech_event_id") or "").strip().split()
            )
            purpose = " ".join(str(row.get("purpose") or "").strip().split())
            commitment = " ".join(str(row.get("commitment") or "").strip().split())
            identity_digest = hashlib.sha256(
                "|".join(
                    [turn_id, "scheduled_communicative_act", purpose, commitment, text]
                ).encode("utf-8")
            ).hexdigest()[:20]
            if not execution_item_id:
                execution_item_id = f"speech_{identity_digest}"
            return SocialAttentionActivityAnchor(
                activity_id=f"activity_{identity_digest}",
                phase="ready",
                summary=(f"{purpose}: {text}" if purpose else text),
                realization=SocialAttentionActivityRealization(
                    execution_lanes=["vocal"],
                    vocal_modes=["speech"],
                    execution_item_ids=[execution_item_id],
                ),
            )
        return None

    @staticmethod
    def _resolution_social_activities(
        resolution: CognitiveRuntimeResolution,
        *,
        turn_id: str,
        context: dict[str, Any] | None = None,
    ) -> list[SocialAttentionActivityAnchor]:
        """Project prepared work into semantic primary Activities.

        The hierarchy is deliberately three-layered:

        Responsibility/Goal -> semantic Activity/Work -> execution realization.

        A Goal may own several Activities, while a sufficiently high-level provider
        capability may realize one whole Activity atomically.  Interaction speech is
        projected as a semantic Communicative Act; canonical Capability work is
        projected at Plan-step granularity.  Vocal modes, execution lanes, request IDs,
        and Capability IDs stay strictly below Activity identity as realization facts.
        """

        interaction = resolution.interaction_response
        if interaction is None:
            return []
        runtime_context = context if isinstance(context, dict) else {}

        goal_summary_by_id: dict[str, str] = {}

        def remember_goal(goal_id: Any, summary: Any) -> None:
            normalized_id = " ".join(str(goal_id or "").strip().split())
            normalized_summary = " ".join(str(summary or "").strip().split())
            if normalized_id and normalized_summary and normalized_id not in goal_summary_by_id:
                goal_summary_by_id[normalized_id] = normalized_summary

        for key in ("active_goal_snapshots", "recent_goal_snapshots"):
            rows = runtime_context.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                goal = row.get("goal") if isinstance(row.get("goal"), dict) else {}
                remember_goal(
                    row.get("goal_id") or goal.get("goal_id"),
                    goal.get("description") or row.get("last_user_update"),
                )

        if resolution.goal_association is not None:
            for goal in resolution.goal_association.new_goals:
                remember_goal(goal.goal_id, goal.description)

        association_payload = runtime_context.get("goal_association_resolution")
        if isinstance(association_payload, dict):
            for row in association_payload.get("new_goals") or []:
                if isinstance(row, dict):
                    remember_goal(row.get("goal_id"), row.get("description"))

        single_plan_goal_ids = (
            list(resolution.terminal_plan.goal_ids)
            if resolution.terminal_plan is not None
            and len(resolution.terminal_plan.goal_ids) == 1
            else []
        )
        fallback_goal_summary = (
            " ".join(str(resolution.terminal_plan.goal_summary or "").strip().split())
            if resolution.terminal_plan is not None
            else ""
        )

        def item_goal_ids(metadata: dict[str, Any]) -> list[str]:
            raw = metadata.get("source_goal_ids")
            if not isinstance(raw, list):
                raw = metadata.get("covers_goal_ids")
            if not isinstance(raw, list):
                return sorted(dict.fromkeys(single_plan_goal_ids))
            normalized = [
                text
                for item in raw
                if (text := " ".join(str(item or "").strip().split()))
            ]
            return sorted(dict.fromkeys(normalized)) or sorted(
                dict.fromkeys(single_plan_goal_ids)
            )

        def goal_context(goal_ids: list[str]) -> str:
            summaries = [
                goal_summary_by_id[item]
                for item in goal_ids
                if item in goal_summary_by_id
            ]
            if summaries:
                return "; ".join(dict.fromkeys(summaries))[:420]
            return fallback_goal_summary[:420]

        activities: dict[str, dict[str, Any]] = {}

        def get_activity(
            *,
            activity_id: str,
            summary: str,
            goal_ids: list[str],
        ) -> dict[str, Any] | None:
            normalized_summary = " ".join(str(summary or "").strip().split())[:500]
            if not normalized_summary:
                return None
            return activities.setdefault(
                activity_id,
                {
                    "activity_id": activity_id,
                    "summary": normalized_summary,
                    "goal_ids": list(goal_ids),
                    "execution_lanes": [],
                    "vocal_modes": [],
                    "execution_item_ids": [],
                    "capability_ids": [],
                },
            )

        def add_unique(row: dict[str, Any], field: str, value: str) -> None:
            if value and value not in row[field]:
                row[field].append(value)

        for speech in interaction.speech:
            text = " ".join(str(speech.text or "").strip().split())
            if not text:
                continue
            goal_ids = item_goal_ids(speech.metadata)
            speech_act = " ".join(
                str(speech.metadata.get("speech_act") or "conversational_act")
                .strip()
                .split()
            )
            delivery_role = " ".join(
                str(speech.metadata.get("delivery_role") or "response").strip().split()
            )
            phase = " ".join(str(speech.metadata.get("phase") or "").strip().split())
            goal_meaning = goal_context(goal_ids)
            summary = (
                f"{speech_act}: {goal_meaning}"
                if goal_meaning
                else text
            )
            digest = hashlib.sha256(
                "|".join(
                    [
                        turn_id,
                        "communicative_act",
                        *goal_ids,
                        speech_act,
                        delivery_role,
                        phase,
                        text,
                    ]
                ).encode("utf-8")
            ).hexdigest()[:20]
            row = get_activity(
                activity_id=f"activity_{digest}",
                summary=summary,
                goal_ids=goal_ids,
            )
            if row is None:
                continue
            add_unique(row, "execution_lanes", "vocal")
            add_unique(row, "vocal_modes", "speech")
            add_unique(row, "execution_item_ids", speech.id)

        for request in interaction.capabilities:
            capability_id = str(request.capability_id or "").strip()
            if not (
                capability_id.startswith("soridormi.")
                or capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
                or capability_id.startswith("chromie.media.")
            ):
                continue
            goal_ids = item_goal_ids(request.metadata)
            reason_summary = " ".join(
                str(request.metadata.get("reason_summary") or "").strip().split()
            )
            summary = reason_summary or goal_context(goal_ids)
            if not summary:
                # Activity meaning must come from semantic Goal/Plan evidence, never
                # by decoding the Capability identifier in Host code.
                continue
            plan_id = " ".join(
                str(request.metadata.get("canonical_plan_id") or "").strip().split()
            )
            step_id = " ".join(
                str(request.metadata.get("step_id") or "").strip().split()
            )
            identity_material = (
                f"plan_step|{plan_id}|{step_id}"
                if plan_id and step_id
                else "|".join(["semantic_work", *goal_ids, summary])
            )
            digest = hashlib.sha256(
                f"{turn_id}|{identity_material}".encode("utf-8")
            ).hexdigest()[:20]
            row = get_activity(
                activity_id=f"activity_{digest}",
                summary=summary,
                goal_ids=goal_ids,
            )
            if row is None:
                continue
            execution_lane = (
                "vocal"
                if capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
                else "activity"
            )
            add_unique(row, "execution_lanes", execution_lane)
            add_unique(row, "execution_item_ids", request.request_id)
            add_unique(row, "capability_ids", capability_id)
            if capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID:
                vocal_mode = " ".join(str(request.args.get("mode") or "").strip().split())
                if vocal_mode in VOCAL_MODES:
                    add_unique(row, "vocal_modes", vocal_mode)

        return [
            SocialAttentionActivityAnchor(
                activity_id=row["activity_id"],
                phase="ready",
                summary=row["summary"],
                goal_ids=row["goal_ids"],
                realization=SocialAttentionActivityRealization(
                    execution_lanes=row["execution_lanes"],
                    vocal_modes=row["vocal_modes"],
                    execution_item_ids=row["execution_item_ids"],
                    capability_ids=row["capability_ids"],
                ),
            )
            for row in activities.values()
        ]

    def queue_interaction_social_attention(
        self,
        session: Any,
        *,
        response: InteractionResponse,
        sid: str,
        context: dict[str, Any],
    ) -> None:
        """Offer one ready user-facing response to optional Social Attention.

        This is a presentation bridge only. It does not create speech, infer Goal
        meaning, or force an expression; Social Attention may still choose ``none``.
        """

        metadata = response.metadata if isinstance(response.metadata, dict) else {}
        bundle = metadata.get("execution_outcome_bundle")
        bundle_turn_id = (
            str(bundle.get("turn_id") or "").strip()
            if isinstance(bundle, dict)
            else ""
        )
        turn_id = (
            str(metadata.get("turn_id") or "").strip()
            or bundle_turn_id
            or str(sid or response.interaction_id or "response").strip()
        )
        language = str(metadata.get("language") or "auto").strip() or "auto"
        history = context.get("history")
        if not isinstance(history, list):
            history = []
        user_text = ""
        for item in reversed(history):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            user_text = str(item.get("text") or "").strip()
            if user_text:
                break
        projection = CognitiveRuntimeResolution(
            mode="apply",
            status="applied",
            interaction_response=response,
        )
        for activity in self._resolution_social_activities(
            projection, turn_id=turn_id, context=context
        ):
            self._queue_social_attention_for_activity(
                session,
                activity=activity,
                text=user_text,
                sid=sid,
                turn_id=turn_id,
                language=language,
                context=context,
                history=[dict(item) for item in history if isinstance(item, dict)],
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
            "context": dict(context),
            "history": [dict(item) for item in history if isinstance(item, dict)],
        }
        queued_ms = time.perf_counter() * 1000.0
        self._record_workflow_stage(
            sid=sid,
            stage="social_attention_opportunity",
            started_monotonic_ms=queued_ms,
            finished_monotonic_ms=queued_ms,
            status="queued",
            input_payload={
                "event": event,
                "primary_activity": raw_activity,
            },
            output_payload={"background": True, "blocks_main_activity": False},
            errors=[],
            attempt=1,
            metadata={
                "turn_id": turn_id,
                "primary_activity_id": activity_id,
                "attached_to_main_activity": True,
            },
        )
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
    def _goal_ids_by_responsibility(
        association: GoalAssociationResolution,
    ) -> dict[str, list[str]]:
        """Resolve the GA-owned Goal identity for every GI Responsibility.

        Fast Planner is allowed to plan before Goal Association finishes, so its
        Activities carry GI-local Responsibility references.  This is the single
        deterministic join from those references to GA's canonical Goal IDs.
        It never guesses a missing mapping.
        """

        mapped: dict[str, list[str]] = {}

        def bind(responsibility_ref: str, goal_ids: list[str]) -> None:
            ref = " ".join(str(responsibility_ref or "").strip().split())
            normalized = [
                goal_id
                for value in goal_ids
                if (goal_id := " ".join(str(value or "").strip().split()))
            ]
            if not ref or not normalized:
                return
            current = mapped.setdefault(ref, [])
            for goal_id in normalized:
                if goal_id not in current:
                    current.append(goal_id)

        for item in association.associations:
            for responsibility_ref in item.source_responsibility_refs:
                bind(responsibility_ref, item.target_goal_ids)
        for goal in association.new_goals:
            if not goal.goal_id:
                continue
            for responsibility_ref in goal.source_responsibility_refs:
                bind(responsibility_ref, [goal.goal_id])
        return mapped

    @classmethod
    def _planner_gaps_by_goal_id(
        cls,
        *,
        advance: FastPlannerAdvance,
        association: GoalAssociationResolution,
    ) -> dict[str, list[PlannerInformationGap]]:
        """Join Planner gap ownership to GA Goal identity without interpreting it."""

        refs_to_goals = cls._goal_ids_by_responsibility(association)
        by_goal: dict[str, list[PlannerInformationGap]] = {}
        seen_by_goal: dict[str, set[str]] = {}
        for activity in advance.activities:
            if activity.role != "clarification":
                continue
            target_goal_ids = [
                goal_id
                for ref in activity.source_responsibility_refs
                for goal_id in refs_to_goals.get(ref, [])
            ]
            for goal_id in target_goal_ids:
                seen = seen_by_goal.setdefault(goal_id, set())
                target = by_goal.setdefault(goal_id, [])
                for gap in activity.information_gaps:
                    if gap.gap_id in seen:
                        continue
                    seen.add(gap.gap_id)
                    target.append(gap)
        return by_goal

    @classmethod
    def _canonical_plan_from_fast_advance(
        cls,
        *,
        advance: FastPlannerAdvance,
        association: GoalAssociationResolution,
        user_text: str,
    ) -> CanonicalPlan:
        """Bind Fast Planner's first Activity Plan to GA's canonical Goals."""

        if advance.disposition in {"escalate", "unavailable", "refused"}:
            raise ValueError(
                "non-terminal Fast Planner advance cannot become a canonical Activity Plan"
            )
        refs_to_goals = cls._goal_ids_by_responsibility(association)
        missing_refs = sorted(
            set(advance.covered_responsibility_refs) - set(refs_to_goals)
        )
        if missing_refs:
            raise ValueError(
                "Goal Association omitted Fast Planner Responsibility mappings: "
                + ",".join(missing_refs)
            )

        goal_ids = cls._association_goal_ids(association)
        activities_by_goal: dict[str, list[Any]] = {
            goal_id: [] for goal_id in goal_ids
        }
        steps: list[CanonicalPlanStep] = []
        for activity in advance.activities:
            activity_goal_ids: list[str] = []
            for responsibility_ref in activity.source_responsibility_refs:
                for goal_id in refs_to_goals[responsibility_ref]:
                    if goal_id not in activity_goal_ids:
                        activity_goal_ids.append(goal_id)
            for goal_id in activity_goal_ids:
                activities_by_goal[goal_id].append(activity)
            if isinstance(activity, FastPlannerCapabilityActivity):
                steps.append(
                    CanonicalPlanStep(
                        step_id=activity.activity_id,
                        capability_id=activity.capability_id,
                        args=dict(activity.args),
                        timing=activity.timing,
                        source_goal_ids=activity_goal_ids,
                        reason_summary=activity.reason_summary,
                        metadata={
                            "fast_activity_id": activity.activity_id,
                            "source_responsibility_refs": list(
                                activity.source_responsibility_refs
                            ),
                            "task_list_revision": 1,
                        },
                    )
                )

        outcomes: list[Any] = []
        unresolved = list(advance.unresolved)
        communicative_acts: list[PlannedCommunicativeAct] = []
        for activity in advance.activities:
            if activity.role == "capability":
                continue
            activity_goal_ids: list[str] = []
            for responsibility_ref in activity.source_responsibility_refs:
                for goal_id in refs_to_goals[responsibility_ref]:
                    if goal_id not in activity_goal_ids:
                        activity_goal_ids.append(goal_id)
            communicative_acts.append(
                PlannedCommunicativeAct(
                    activity_id=activity.activity_id,
                    text=activity.text,
                    role=activity.role,
                    timing=activity.timing,
                    speech_act=activity.speech_act,
                    source_goal_ids=activity_goal_ids,
                    source_responsibility_refs=list(
                        activity.source_responsibility_refs
                    ),
                    truth_stage=activity.truth_stage,
                    evidence_refs=list(activity.evidence_refs),
                    information_gaps=list(
                        getattr(activity, "information_gaps", [])
                    ),
                    progress_kind=getattr(activity, "progress_kind", None),
                )
            )
        for goal_id in goal_ids:
            goal_activities = activities_by_goal.get(goal_id, [])
            goal_steps = [
                step.step_id for step in steps if goal_id in step.source_goal_ids
            ]
            clarifications = [
                activity
                for activity in goal_activities
                if activity.role == "clarification"
            ]
            responses = [
                activity
                for activity in goal_activities
                if activity.role == "complete_response"
            ]
            if goal_steps:
                satisfaction = GoalSatisfactionAssessment(
                    score=max(0.95, advance.confidence),
                    status="exact",
                    satisfied_goal_ids=[goal_id],
                    rationale="Fast Planner supplied executable Activities for this Goal.",
                )
                outcomes.append(
                    ExecuteGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="execute",
                        coverage="complete",
                        step_ids=goal_steps,
                        satisfaction=satisfaction,
                        rationale="Runtime execution and Evidence remain required.",
                    )
                )
            elif clarifications:
                outcomes.append(
                    ClarifyGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="clarify",
                        coverage="uncertain",
                        unresolved=(unresolved or ["user_clarification_required"]),
                        response_text=clarifications[0].text,
                        rationale=(
                            "A source-proven Planner InformationGap blocks this Goal's Work."
                        ),
                    )
                )
            elif responses:
                satisfaction = GoalSatisfactionAssessment(
                    score=max(0.95, advance.confidence),
                    status="exact",
                    satisfied_goal_ids=[goal_id],
                    rationale="Fast Planner supplied the complete Communicative Act.",
                )
                outcomes.append(
                    RespondGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="respond",
                        coverage="complete",
                        response_text=responses[0].text,
                        satisfaction=satisfaction,
                        rationale="No Capability Evidence is required for this Goal.",
                    )
                )
            else:
                raise ValueError(
                    f"Fast Planner supplied no terminal Activity for Goal {goal_id!r}"
                )

        dispositions = {item.disposition for item in outcomes}
        disposition = (
            next(iter(dispositions)) if len(dispositions) == 1 else "mixed"
        )
        top_coverage = (
            "uncertain" if disposition == "clarify" else "complete"
        )
        plan_seed = json.dumps(
            advance.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        global_satisfaction = None
        if "clarify" not in dispositions:
            global_satisfaction = GoalSatisfactionAssessment(
                score=max(0.95, advance.confidence),
                status="exact",
                satisfied_goal_ids=goal_ids,
                rationale="Every canonical Goal has a complete Fast Planner outcome.",
            )
        return CanonicalPlan(
            plan_id=(
                "fast_activity_plan_"
                + hashlib.sha256(plan_seed.encode("utf-8")).hexdigest()[:20]
            ),
            planner_tier="fast",
            disposition=disposition,
            coverage=top_coverage,
            confidence=advance.confidence,
            goal_ids=goal_ids,
            goal_summary=user_text,
            response_text=" ".join(
                dict.fromkeys(
                    activity.text
                    for activity in advance.activities
                    if activity.role in {"complete_response", "clarification"}
                )
            ),
            communicative_acts=communicative_acts,
            steps=steps,
            unresolved=(unresolved if disposition in {"clarify", "mixed"} else []),
            goal_outcomes=outcomes,
            goal_satisfaction=global_satisfaction,
            metadata={
                "resolver": "fast_planner_advance",
                "path_classification": "terminal",
                "plan_relation": "exact",
                "task_list_revision": 1,
                "goal_grouped_task_list": True,
                "goal_ids_by_responsibility": refs_to_goals,
            },
        )

    @classmethod
    def _canonical_plan_reusing_fast_capability_execution(
        cls,
        *,
        execution: Any,
        plan: CanonicalPlan,
        association: GoalAssociationResolution,
    ) -> CanonicalPlan | None:
        """Prove exact plan-level reuse without making a semantic judgment.

        Fast Planner owns whether the canonical Goal still needs the provisional
        Work by explicitly citing stable Activity IDs. The Host may reuse
        already-started safe Work only when every provisional Activity is selected
        exactly once and its Capability/argument/Goal/timing identity still matches.
        Extra newly planned steps are allowed. Ambiguous, partial, or changed
        selections return ``None`` and follow the normal cancel/replace path.
        """

        activities = list(getattr(execution, "activities", []) or [])
        if (
            plan.disposition not in {"execute", "mixed"}
            or not activities
        ):
            return None
        refs_to_goals = cls._goal_ids_by_responsibility(association)
        updated_steps = list(plan.steps)
        matched_step_indexes: set[int] = set()
        for activity in activities:
            activity_goal_ids = list(
                dict.fromkeys(
                    goal_id
                    for responsibility_ref in activity.source_responsibility_refs
                    for goal_id in refs_to_goals.get(responsibility_ref, [])
                )
            )
            if not activity_goal_ids:
                return None
            candidates = [
                index
                for index, step in enumerate(plan.steps)
                if index not in matched_step_indexes
                and step.reuse_activity_id == activity.activity_id
                and step.capability_id == activity.capability_id
                and step.args == activity.args
                and len(step.source_goal_ids) == len(activity_goal_ids)
                and set(step.source_goal_ids) == set(activity_goal_ids)
                and step.timing == activity.timing
            ]
            if len(candidates) != 1:
                return None
            index = candidates[0]
            matched_step_indexes.add(index)
            step = plan.steps[index]
            updated_steps[index] = step.model_copy(
                deep=True,
                update={
                    "metadata": {
                        **step.metadata,
                        "fast_activity_id": activity.activity_id,
                        "source_responsibility_refs": list(
                            activity.source_responsibility_refs
                        ),
                        "task_list_revision": int(
                            plan.metadata.get("task_list_revision") or 1
                        ),
                    }
                },
            )
        provisional_activity_ids = {
            activity.activity_id for activity in activities
        }
        cited_activity_ids = {
            step.reuse_activity_id
            for step in plan.steps
            if step.reuse_activity_id in provisional_activity_ids
        }
        if cited_activity_ids != provisional_activity_ids:
            return None
        return plan.model_copy(deep=True, update={"steps": updated_steps})

    @staticmethod
    def _retained_existing_work_activities(
        *,
        context: dict[str, Any],
        goal_ids: set[str],
    ) -> list[dict[str, Any]]:
        """Project still-owned retained Work for Planner comparison.

        Conversation State supplies the trusted bounded task snapshot. This
        projection adds no semantic judgment: it includes only request IDs still
        listed as remaining for the canonical Goals in scope.
        """

        by_activity_id: dict[str, dict[str, Any]] = {}
        snapshots = context.get("active_task_snapshots")
        if not isinstance(snapshots, list):
            return []
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            semantic_goal = snapshot.get("semantic_goal")
            if not isinstance(semantic_goal, dict):
                continue
            goal_id = str(semantic_goal.get("goal_id") or "").strip()
            if not goal_id or goal_id not in goal_ids:
                continue
            metadata = snapshot.get("metadata")
            binding = (
                metadata.get("execution_binding")
                if isinstance(metadata, dict)
                else None
            )
            if not isinstance(binding, dict):
                continue
            remaining = {
                str(item).strip()
                for item in binding.get("remaining_request_ids") or []
                if str(item).strip()
            }
            if not remaining:
                continue
            interaction_id = str(binding.get("interaction_id") or "").strip()
            plan_id = str(binding.get("canonical_plan_id") or "").strip()
            fingerprint = str(
                binding.get("canonical_plan_fingerprint") or ""
            ).strip()
            if not interaction_id or not plan_id or not fingerprint:
                continue
            for item in binding.get("planned_capabilities") or []:
                if not isinstance(item, dict):
                    continue
                request_id = str(item.get("request_id") or "").strip()
                capability_id = str(item.get("capability_id") or "").strip()
                if request_id not in remaining or not capability_id:
                    continue
                existing = by_activity_id.get(request_id)
                source_goal_ids = list(
                    dict.fromkeys(
                        [
                            *(
                                existing.get("source_goal_ids", [])
                                if existing is not None
                                else []
                            ),
                            *(
                                item.get("source_goal_ids")
                                if isinstance(item.get("source_goal_ids"), list)
                                else []
                            ),
                            goal_id,
                        ]
                    )
                )
                activity = {
                    "activity_id": request_id,
                    "origin": "retained_runtime",
                    "capability_id": capability_id,
                    "args": dict(item.get("args") or {}),
                    "timing": str(item.get("timing") or "sequential"),
                    "source_goal_ids": source_goal_ids,
                    "runtime_binding": {
                        "interaction_id": interaction_id,
                        "canonical_plan_id": plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                    },
                    "state": str(
                        (binding.get("request_statuses") or {}).get(request_id)
                        or snapshot.get("status")
                        or "scheduled"
                    ),
                }
                if existing is not None and any(
                    existing.get(key) != activity.get(key)
                    for key in ("capability_id", "args", "timing", "runtime_binding")
                ):
                    raise ValueError(
                        "retained Work identity conflicts across Goal snapshots: "
                        + request_id
                    )
                by_activity_id[request_id] = activity
        return list(by_activity_id.values())

    async def _apply_retained_work_reconciliation(
        self,
        *,
        plan: CanonicalPlan,
        activities: list[dict[str, Any]],
        turn_id: str,
    ) -> tuple[CanonicalPlan, str]:
        """Validate and apply Planner decisions for retained Runtime Work.

        The Planner's explicit ``reuse_activity_id`` is the only semantic
        selection. Runtime performs exact live-state validation, preserves every
        selected request without redispatch, or cancels the complete unselected
        retained set before replacement Work can start.
        """

        retained = [
            item
            for item in activities
            if item.get("origin") == "retained_runtime"
        ]
        if not retained:
            return plan, "not_applicable"
        retained_by_id = {
            str(item.get("activity_id") or ""): item for item in retained
        }
        selected_steps = {
            step.reuse_activity_id: step
            for step in plan.steps
            if step.reuse_activity_id in retained_by_id
        }
        if selected_steps and set(selected_steps) != set(retained_by_id):
            raise CognitiveStageFailure(
                "work_reconciliation",
                {
                    "failure_class": "partial_retained_work_reuse",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "planner",
                    "retryable": False,
                },
            )

        live_by_id: dict[str, dict[str, Any]] = {}
        for activity_id, activity in retained_by_id.items():
            runtime_binding = activity.get("runtime_binding")
            if not isinstance(runtime_binding, dict):
                raise ValueError("retained Work lacks trusted runtime binding")
            live = await self.adapter.interaction_runtime.reusable_request_snapshot(
                interaction_id=str(runtime_binding.get("interaction_id") or ""),
                request_id=activity_id,
            )
            if live is None:
                raise CognitiveStageFailure(
                    "work_reconciliation",
                    {
                        "failure_class": "retained_work_state_changed",
                        "failure_domain": "runtime_state",
                        "architecture_attribution": "capability_runtime",
                        "retryable": True,
                        "request_id": activity_id,
                    },
                )
            expected_goal_ids = set(activity.get("source_goal_ids") or [])
            if (
                live.get("capability_id") != activity.get("capability_id")
                or live.get("args") != activity.get("args")
                or live.get("timing") != activity.get("timing")
                or set(live.get("source_goal_ids") or []) != expected_goal_ids
                or live.get("canonical_plan_id")
                != runtime_binding.get("canonical_plan_id")
                or live.get("canonical_plan_fingerprint")
                != runtime_binding.get("canonical_plan_fingerprint")
            ):
                raise CognitiveStageFailure(
                    "work_reconciliation",
                    {
                        "failure_class": "retained_work_identity_changed",
                        "failure_domain": "runtime_state",
                        "architecture_attribution": "capability_runtime",
                        "retryable": True,
                        "request_id": activity_id,
                    },
                )
            live_by_id[activity_id] = live

        if selected_steps:
            if len(selected_steps) != len(plan.steps):
                raise CognitiveStageFailure(
                    "work_reconciliation",
                    {
                        "failure_class": "retained_reuse_with_additional_steps",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "planner",
                        "retryable": False,
                    },
                )
            updated_steps = list(plan.steps)
            for index, step in enumerate(plan.steps):
                activity = retained_by_id.get(step.reuse_activity_id)
                if activity is None:
                    continue
                if (
                    step.capability_id != activity.get("capability_id")
                    or step.args != activity.get("args")
                    or step.timing != activity.get("timing")
                    or set(step.source_goal_ids)
                    != set(activity.get("source_goal_ids") or [])
                ):
                    raise CognitiveStageFailure(
                        "work_reconciliation",
                        {
                            "failure_class": "planner_reuse_identity_mismatch",
                            "failure_domain": "model_contract",
                            "architecture_attribution": "planner",
                            "retryable": False,
                            "request_id": step.reuse_activity_id,
                        },
                    )
                updated_steps[index] = step.model_copy(
                    deep=True,
                    update={
                        "metadata": {
                            **step.metadata,
                            "retained_work_reused": True,
                            "retained_request_id": step.reuse_activity_id,
                            "retained_runtime_state": live_by_id[
                                step.reuse_activity_id
                            ]["state"],
                        }
                    },
                )
            return (
                plan.model_copy(
                    deep=True,
                    update={
                        "steps": updated_steps,
                        "metadata": {
                            **plan.metadata,
                            "retained_work_reconciliation_only": True,
                        },
                    },
                ),
                "retained_work_reused",
            )

        grouped: dict[tuple[str, str, str], dict[str, set[str]]] = {}
        for activity_id, activity in retained_by_id.items():
            runtime_binding = activity["runtime_binding"]
            key = (
                str(runtime_binding["interaction_id"]),
                str(runtime_binding["canonical_plan_id"]),
                str(runtime_binding["canonical_plan_fingerprint"]),
            )
            group = grouped.setdefault(
                key,
                {"goal_ids": set(), "request_ids": set()},
            )
            group["goal_ids"].update(activity.get("source_goal_ids") or [])
            group["request_ids"].add(activity_id)

        for (interaction_id, plan_id, fingerprint), group in grouped.items():
            receipt = await self.adapter.interaction_runtime.cancel_scope(
                CancellationDirective(
                    source_turn_id=turn_id,
                    requested_scope="specific_goal",
                    foreground_interaction_id=interaction_id,
                    target_goal_ids=tuple(sorted(group["goal_ids"])),
                    expected_plan_id=plan_id,
                    expected_plan_fingerprint=fingerprint,
                    reason="Fast Planner replaced retained Work",
                )
            )
            selected_request_ids = {
                item.request_id for item in receipt.selected_request_bindings
            }
            failure = bool(
                not group["request_ids"].issubset(selected_request_ids)
                or receipt.stale_binding_request_bindings
                or receipt.shared_owner_conflict_request_bindings
                or receipt.non_interruptible_request_bindings
                or receipt.provider_cancel_failure_evidence
                or receipt.dispatch_failures
            )
            if failure:
                raise CognitiveStageFailure(
                    "work_reconciliation",
                    {
                        "failure_class": "retained_work_cancellation_not_closed",
                        "failure_domain": "runtime_state",
                        "architecture_attribution": "capability_runtime",
                        "retryable": False,
                        "interaction_id": interaction_id,
                    },
                )
        return plan, "retained_work_cancelled_before_replacement"

    @staticmethod
    def _is_direct_spoken_association(
        association: GoalAssociationResolution,
    ) -> bool:
        return (
            not association.associations
            and bool(association.new_goals)
            and all(
                str((goal.metadata or {}).get("output_mode") or "") == "speech"
                and bool(str(goal.goal_id or "").strip())
                for goal in association.new_goals
            )
        )

    async def _run_social_attention_event(
        self,
        session: Any,
        *,
        event: str,
        text: str,
        sid: str,
        turn_id: str,
        language: str,
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

        # Throttle per semantic primary Activity, never per cognition turn or execution
        # modality/item. A Fast acknowledgement may be its own Communicative Act;
        # after planning, canonical conversational/Plan-step Work defines Activity identity.
        # Goal ownership is context above that identity, not the cooldown key.
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
        primary_capability_ids: list[str] = list(
            primary_activity.realization.capability_ids
        )
        seen_primary_ids: set[str] = set(primary_capability_ids)
        activity_goal_ids = set(primary_activity.goal_ids)

        def retain_primary_progress(rows: Any) -> None:
            if not isinstance(rows, list):
                return
            for row in rows[:12]:
                if not isinstance(row, dict):
                    continue
                row_goal_ids = {
                    text
                    for item in (row.get("source_goal_ids") or row.get("covers_goal_ids") or [])
                    if (text := " ".join(str(item or "").strip().split()))
                }
                if activity_goal_ids:
                    if not row_goal_ids.intersection(activity_goal_ids):
                        continue
                elif row_goal_ids:
                    # An unbound Communicative Act must not inherit unrelated later
                    # Goal/Plan implementation merely because it shares the turn.
                    continue
                capability_id = str(
                    row.get("capability_id") or ""
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
                        "args",
                        "source_goal_ids",
                        "covers_goal_ids",
                    )
                    if key in row
                }
                primary_progress.append(projection)

        retain_primary_progress(social_context.get("execution_capabilities"))
        canonical_plan = social_context.get("canonical_plan_resolution")
        if isinstance(canonical_plan, dict):
            retain_primary_progress(canonical_plan.get("steps"))
        social_context["social_attention_interaction_state"] = {
            "event": event,
            "primary_activity": primary_activity.model_dump(mode="json", exclude_none=True),
            "primary_capability_ids": primary_capability_ids,
            "primary_progress": primary_progress,
            "primary_work_known": bool(
                primary_activity.summary
                or primary_activity.realization.execution_item_ids
                or primary_capability_ids
            ),
        }
        social_context["recent_auxiliary_behavior_evidence"] = recent_evidence
        request = SocialAttentionRequest(
            session_id=sid,
            turn_id=turn_id,
            event=event,
            primary_activity=primary_activity,
            text=text,
            language=language,
            context=social_context,
            history=[dict(item) for item in history[-6:] if isinstance(item, dict)],
        )
        planner_started_ms = time.perf_counter() * 1000.0
        planner_outcome = (
            await asyncio.gather(
                resolver(session, request=request),
                return_exceptions=True,
            )
        )[0]
        if isinstance(planner_outcome, asyncio.CancelledError):
            raise planner_outcome
        if isinstance(planner_outcome, BaseException):
            self._record_workflow_stage(
                sid=sid,
                stage="social_attention_decision",
                started_monotonic_ms=planner_started_ms,
                finished_monotonic_ms=time.perf_counter() * 1000.0,
                status="failed",
                input_payload={"primary_activity": request.primary_activity},
                output_payload=None,
                errors=[{"error_type": type(planner_outcome).__name__}],
                attempt=1,
                metadata={"blocks_main_activity": False},
            )
            return {
                "status": "planner_failed",
                "event": event,
                "error_type": type(planner_outcome).__name__,
                "error": str(planner_outcome)[:240],
            }
        plan = planner_outcome
        self._record_workflow_stage(
            sid=sid,
            stage="social_attention_decision",
            started_monotonic_ms=planner_started_ms,
            finished_monotonic_ms=time.perf_counter() * 1000.0,
            status="accepted",
            input_payload={"primary_activity": request.primary_activity},
            output_payload={"decision": plan.decision, "plan": plan},
            errors=[],
            attempt=1,
            metadata={
                "blocks_main_activity": False,
                "attached_to_main_activity": True,
            },
        )
        execution_started_ms = time.perf_counter() * 1000.0
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
            self._record_workflow_stage(
                sid=sid,
                stage="social_attention_execution",
                started_monotonic_ms=execution_started_ms,
                finished_monotonic_ms=time.perf_counter() * 1000.0,
                status="failed",
                input_payload={"decision": plan.decision},
                output_payload=None,
                errors=[{"error_type": type(execution_outcome).__name__}],
                attempt=1,
                metadata={"blocks_main_activity": False},
            )
            return {
                "status": "execution_failed",
                "event": event,
                "decision": plan.decision,
                "error_type": type(execution_outcome).__name__,
                "error": str(execution_outcome)[:240],
            }
        self._record_workflow_stage(
            sid=sid,
            stage="social_attention_execution",
            started_monotonic_ms=execution_started_ms,
            finished_monotonic_ms=time.perf_counter() * 1000.0,
            status="completed",
            input_payload={"decision": plan.decision},
            output_payload=execution_outcome,
            errors=[],
            attempt=1,
            metadata={
                "blocks_main_activity": False,
                "attached_to_main_activity": True,
            },
        )
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

    async def _resolve_and_commit_goal_association(
        self,
        session: Any,
        *,
        work_request: CognitiveWorkRequest,
        sid: str,
        text: str,
        turn_id: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        timings: dict[str, float],
    ) -> _GoalAssociationStageResult:
        """Run GA and publish its validated canonical continuity mechanically.

        This is an extraction from ``_resolve`` inside the same CognitiveRuntime
        owner. It does not add a semantic stage: Goal Association still owns Goal
        meaning, while Host code only serializes, records, and applies that result.
        """

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
                revision=1,
            )
            context = {**context, "situation": situation.prompt_projection()}
            stage = time.perf_counter()
            association = await self._observe_workflow_stage(
                sid=sid,
                stage="goal_association",
                input_payload={
                    "user_text": text,
                    "responsibilities": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in work_request.responsibilities
                    ],
                    "active_goal_snapshots": context.get("active_goal_snapshots", []),
                    "situation_digest": situation.digest,
                    "history_turn_count": len(history),
                },
                operation=self.agent_client.resolve_goal_association(
                    session,
                    request=work_request.model_copy(
                        update={
                            "context": context,
                            "history": history,
                        }
                    ),
                    timeout_ms=self.policy.goal_association_timeout_ms,
                ),
            )
            timings["goal_association"] = (time.perf_counter() - stage) * 1000.0
            association_status = association.resolution_status
            planning_context = dict(context)
            planning_context["goal_association_resolution"] = (
                association.prompt_projection()
            )
            if association_status != "resolved":
                raise CognitiveStageFailure(
                    "goal_association",
                    self._stage_failure_metadata(
                        "goal_association",
                        association.metadata,
                        default_failure_class=association_status or "stage_failure",
                    ),
                )

            has_named_goal_cancellation = any(
                item.relationship == "cancel" for item in association.associations
            )
            has_goal_replacement = any(
                goal.supersedes_goal_ids for goal in association.new_goals
            )
            goal_state_results: list[dict[str, Any]] = []
            goal_state_commit_stage = ""
            if self.policy.mode == "apply" and self.goal_state_apply is not None:
                if has_named_goal_cancellation:
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
                            source="goal_driven_cognitive_runtime_goal_association",
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
                        and item.get("reason") != "operation_already_applied"
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

        return _GoalAssociationStageResult(
            association=association,
            context=context,
            history=history,
            planning_context=planning_context,
            situation=situation,
            goal_state_results=goal_state_results,
            goal_state_commit_stage=goal_state_commit_stage,
            has_named_goal_cancellation=has_named_goal_cancellation,
            has_goal_replacement=has_goal_replacement,
        )

    async def resolve(
        self,
        session: Any,
        *,
        text: str,
        sid: str,
        core_interpretation: CoreInterpretationResult,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        language: str,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> CognitiveRuntimeResolution:
        if turn_envelope is None:
            raise ValueError("Core interpretation requires its admitted UserTurnEnvelope")
        if core_interpretation.turn_id != turn_envelope.turn_id:
            raise ValueError("Core interpretation turn does not match UserTurnEnvelope")
        if core_interpretation.session_id != turn_envelope.session_id:
            raise ValueError("Core interpretation session does not match UserTurnEnvelope")
        context = {
            **context,
            "core_interpretation": core_interpretation.model_dump(mode="json"),
        }

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
        work_request = CognitiveWorkRequest(
            sid=sid,
            text=text,
            language=language,
            responsibilities=list(core_interpretation.responsibilities),
            interpretation_confidence=core_interpretation.confidence,
            interpretation_unresolved=list(core_interpretation.unresolved),
            context=context,
            history=history,
        )

        def attach_core_identity(
            resolution: CognitiveRuntimeResolution,
        ) -> CognitiveRuntimeResolution:
            if core_interpretation is None:
                return resolution
            metadata = dict(resolution.metadata)
            metadata["core_interpretation"] = core_interpretation.model_dump(
                mode="json"
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
            activities = self._resolution_social_activities(
                resolution,
                turn_id=resolved_turn_id,
                context=context,
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
            for activity in activities:
                self._queue_social_attention_for_activity(
                    session,
                    activity=activity,
                    text=text,
                    sid=sid,
                    turn_id=resolved_turn_id,
                    language=language,
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
                "responsibility_count": len(work_request.responsibilities),
                "interpretation_confidence": work_request.interpretation_confidence,
                "language": language,
                "text_chars": len(text or ""),
            },
            sampling_reason="goal_driven_interaction",
        )
        if not trace_scope.enabled:
            resolution = await self._resolve(
                session,
                work_request=work_request,
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
                        work_request=work_request,
                    )
                    if turn_envelope is not None:
                        resolution = resolution.model_copy(update={"turn_envelope": turn_envelope})
                    resolution = attach_core_identity(resolution)
                    queue_resolution_social_attention(resolution)
                    span.set_attribute("result_status", resolution.status)
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

    async def _resolve_fast_activity_plan_stage(
        self,
        session: Any,
        *,
        work_request: CognitiveWorkRequest,
        sid: str,
        turn_id: str,
        text: str,
        context: dict[str, Any],
        history: list[dict[str, Any]],
        responsibility_proposals: list[Any],
        committed_fast_activity_ids: set[str],
        fast_started: float,
        progress: _FastAdvanceProgress,
    ) -> _FastAdvanceStageResult:
        """Run Fast Planner advance and only its already-qualified early realizations.

        This extraction owns no new cognition or state. It is the former nested
        phase of ``_resolve`` expressed as a typed mechanical stage result so the
        main transaction remains reconstructable.
        """

        advance = await self._observe_workflow_stage(
            sid=sid,
            stage="fast_planner_advance",
            input_payload={
                "user_text": text,
                "responsibilities": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in responsibility_proposals
                ],
                "active_goal_snapshots": context.get("active_goal_snapshots", []),
                "interaction_context": context.get("interaction_context", {}),
            },
            operation=self.agent_client.resolve_fast_advance(
                session,
                request=work_request.model_copy(
                    update={
                        "sid": turn_id,
                        "context": context,
                        "history": history,
                    }
                ),
                timeout_ms=self.policy.fast_planner_timeout_ms,
            ),
        )
        ready_capability_execution: Any | None = progress.ready_capability_execution
        ready_capability_status = progress.ready_capability_status
        communicative_realization_status = "not_started"
        social_attention_opportunity_delta = 0
        ready_communicative_executions: list[Any] = []
        vocal_activity_ids: list[str] = []

        if self.policy.mode == "apply":
            capability_activities = [
                item
                for item in advance.activities
                if isinstance(item, FastPlannerCapabilityActivity)
            ]
            if capability_activities:
                try:
                    ready_capability_execution = (
                        await self.adapter.interaction_runtime.start_fast_planner_capability_activities(
                            capability_activities,
                            session_id=sid,
                            turn_id=turn_id,
                        )
                    )
                    ready_capability_status = (
                        "accepted_before_goal_association"
                        if ready_capability_execution is not None
                        else "not_started"
                    )
                    progress.ready_capability_execution = ready_capability_execution
                    progress.ready_capability_status = ready_capability_status
                except (
                    AttributeError,
                    TypeError,
                    ValueError,
                    ValidationError,
                    RuntimeError,
                ) as exc:
                    # Ineligible or invalid Work is not executed early. The
                    # canonical validation path still evaluates the Activity
                    # after GA; no semantic fallback is inferred.
                    ready_capability_status = (
                        "deferred_to_canonical_validation:" + type(exc).__name__
                    )
                    progress.ready_capability_status = ready_capability_status

        communicative_acts = [
            item for item in advance.activities if item.role != "capability"
        ]
        if communicative_acts:
            communicative_realization_status = "planner_owned"
        if self.policy.mode == "apply":
            has_capability = any(
                item.role == "capability" for item in advance.activities
            )
            for activity in advance.activities:
                if activity.role in {"capability", "clarification"}:
                    continue
                if activity.activity_id in committed_fast_activity_ids:
                    continue
                # Progress can accompany concurrent Goal work. Mixed complete
                # answer+Capability wording remains with final Plan coordination.
                if activity.role == "complete_response" and has_capability:
                    continue
                self._queue_social_attention_for_activity(
                    session,
                    activity=self._fast_planner_communicative_social_activity(activity),
                    text=text,
                    sid=sid,
                    turn_id=turn_id,
                    language=work_request.language or "auto",
                    context=context,
                    history=history,
                )
                if self.adapter.social_attention_mode != "off":
                    social_attention_opportunity_delta += 1
                ready_execution = (
                    await self.adapter.interaction_runtime.start_fast_planner_communicative_act(
                        activity,
                        session_id=sid,
                        turn_id=turn_id,
                        language=work_request.language or "auto",
                    )
                )
                if activity.role == "complete_response":
                    ready_communicative_executions.append(ready_execution)
                vocal_activity_ids.append(activity.activity_id)

        return _FastAdvanceStageResult(
            advance=advance,
            activity_plan_elapsed_ms=(time.perf_counter() - fast_started) * 1000.0,
            ready_capability_execution=ready_capability_execution,
            ready_capability_status=ready_capability_status,
            communicative_realization_status=communicative_realization_status,
            social_attention_opportunity_delta=social_attention_opportunity_delta,
            ready_communicative_executions=tuple(ready_communicative_executions),
            vocal_activity_ids=tuple(vocal_activity_ids),
        )

    async def _resolve(
        self,
        session: Any,
        *,
        work_request: CognitiveWorkRequest,
    ) -> CognitiveRuntimeResolution:
        started = time.perf_counter()
        text = work_request.text
        sid = str(work_request.sid or "")
        language = work_request.language or "auto"
        history = list(work_request.history)
        context = dict(work_request.context)
        context["interaction_context"] = self._interaction_context(
            sid=sid,
            context=context,
        )
        timings: dict[str, float] = {}
        association: GoalAssociationResolution | None = None
        fast_advance: FastPlannerAdvance | None = None
        fast_first_response: FastPlannerFirstResponse | None = None
        fast_plan: CanonicalPlan | None = None
        terminal_plan: CanonicalPlan | None = None
        interaction: InteractionResponse | None = None
        goal_state_results: list[dict[str, Any]] = []
        goal_state_commit_stage = ""
        stage_diagnostics: list[dict[str, Any]] = []
        fast_planner_path = ""
        deep_planner_invocation_reasons: list[str] = []
        needs_deep_planner = False
        fast_advance_task: asyncio.Task[_FastAdvanceStageResult] | None = None
        fast_vocal_activity_ids: list[str] = []
        ready_fast_communicative_executions: list[Any] = []
        fast_communicative_realization_status = "not_started"
        social_attention_opportunity_count = 0
        ready_fast_capability_execution: Any | None = None
        ready_fast_capability_status = "not_started"
        fast_advance_progress = _FastAdvanceProgress()
        retained_work_reconciliation_status = "not_applicable"
        work_reconciliation_required = False
        work_reconciliation_activity_count = 0

        def path_metadata() -> dict[str, Any]:
            first_deep_reason = (
                deep_planner_invocation_reasons[0] if deep_planner_invocation_reasons else ""
            )
            return {
                "fast_planner_advance": (
                    fast_advance.model_dump(mode="json", exclude_none=True)
                    if fast_advance is not None
                    else None
                ),
                "fast_planner_first_response": (
                    fast_first_response.model_dump(mode="json", exclude_none=True)
                    if fast_first_response is not None
                    else None
                ),
                "fast_planner_advance_continuations": (
                    list(fast_advance.continuations) if fast_advance is not None else []
                ),
                "fast_planner_path": fast_planner_path,
                "deep_planner_invoked": bool(deep_planner_invocation_reasons),
                "deep_planner_invocation_reason": first_deep_reason,
                "deep_planner_invocation_reasons": list(deep_planner_invocation_reasons),
                "deep_planner_avoided": bool(
                    fast_planner_path
                    in {
                        "terminal",
                        "direct_vocal_output",
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
                    }
                    and not deep_planner_invocation_reasons
                ),
                "terminal_planner_tier": (
                    terminal_plan.planner_tier if terminal_plan is not None else ""
                ),
                "authoritative_goal_count": (
                    len(self._association_goal_ids(association))
                    if association is not None
                    else 0
                ),
                "fast_goal_outcome_count": (
                    len(fast_plan.goal_outcomes) if fast_plan is not None else 0
                ),
                "fast_executable_step_count": (
                    len(fast_plan.steps) if fast_plan is not None else 0
                ),
                "goal_state_commit_stage": goal_state_commit_stage,
                "fast_vocal_activity_ids": list(fast_vocal_activity_ids),
                "fast_communicative_realization_status": (
                    fast_communicative_realization_status
                ),
                "social_attention_opportunity_count": (
                    social_attention_opportunity_count
                ),
                "fast_capability_activity_status": ready_fast_capability_status,
                "retained_work_reconciliation_status": (
                    retained_work_reconciliation_status
                ),
                "work_reconciliation_required": work_reconciliation_required,
                "work_reconciliation_activity_count": (
                    work_reconciliation_activity_count
                ),
                "gi_fanout_concurrent": True,
                "goal_grouped_task_list": True,
            }

        async def cancel_uncommitted_fast_work(reason: str) -> None:
            """Stop only Fast work that never received a canonical Plan binding."""

            nonlocal ready_fast_capability_status
            if fast_advance_task is not None and not fast_advance_task.done():
                fast_advance_task.cancel()
                await asyncio.gather(fast_advance_task, return_exceptions=True)
            execution = (
                ready_fast_capability_execution
                or fast_advance_progress.ready_capability_execution
            )
            execution_status = (
                ready_fast_capability_status
                if ready_fast_capability_execution is not None
                else fast_advance_progress.ready_capability_status
            )
            if (
                execution is None
                or execution_status.startswith("completed_before_canonical_dispatch")
                or execution_status == "cancelled_by_work_reconciliation"
            ):
                return
            try:
                await self.adapter.interaction_runtime.runtime.cancel_interaction(
                    execution.interaction_id
                )
                ready_fast_capability_status = "cancelled_before_goal_binding:" + reason
            except Exception as cleanup_exc:
                ready_fast_capability_status = (
                    "cancellation_failed_before_goal_binding:"
                    + type(cleanup_exc).__name__
                )
                logger.warning(
                    "fast_activity_cleanup_failed sid=%s reason=%s error_type=%s error=%s",
                    sid,
                    reason,
                    type(cleanup_exc).__name__,
                    cleanup_exc,
                )

        try:
            turn_id = self._context_turn_id(context, sid)

            responsibility_proposals = list(work_request.responsibilities)
            if responsibility_proposals:
                # Fast Planner first authors one tiny realizable Communicative
                # Activity. Once that latency-critical commitment is available,
                # its remaining Activity planning and GA fan out concurrently.
                # These are phases of one Fast Planner owner, not a response
                # composer followed by a planner.
                fast_started = time.perf_counter()
                fast_first_response = await self._observe_workflow_stage(
                    sid=sid,
                    stage="fast_planner_first_response",
                    input_payload={
                        "user_text": text,
                        "language": language,
                        "responsibilities": [
                            item.model_dump(mode="json", exclude_none=True)
                            for item in responsibility_proposals
                        ],
                        "interaction_context": context.get(
                            "interaction_context", {}
                        ),
                    },
                    operation=self.agent_client.resolve_fast_first_response(
                        session,
                        request=work_request.model_copy(
                            update={
                                "sid": turn_id,
                                "context": context,
                                "history": history,
                            }
                        ),
                        timeout_ms=self.policy.fast_planner_timeout_ms,
                    ),
                )
                timings["fast_planner_commit"] = (
                    time.perf_counter() - fast_started
                ) * 1000.0
                context = {
                    **context,
                    "fast_planner_first_response": (
                        fast_first_response.model_dump(
                            mode="json", exclude_none=True
                        )
                    ),
                }
                committed_fast_activity_ids: set[str] = set()
                first_activity = fast_first_response.activity
                if first_activity is not None:
                    committed_fast_activity_ids.add(first_activity.activity_id)
                    fast_communicative_realization_status = "planner_owned"
                    if (
                        self.policy.mode == "apply"
                    ):
                        self._queue_social_attention_for_activity(
                            session,
                            activity=self._fast_planner_communicative_social_activity(
                                first_activity,
                            ),
                            text=text,
                            sid=sid,
                            turn_id=turn_id,
                            language=language,
                            context=context,
                            history=history,
                        )
                        if self.adapter.social_attention_mode != "off":
                            social_attention_opportunity_count += 1
                        ready_execution = (
                            await self.adapter.interaction_runtime.start_fast_planner_communicative_act(
                                first_activity,
                                session_id=sid,
                                turn_id=turn_id,
                                language=language,
                            )
                        )
                        if first_activity.role == "complete_response":
                            ready_fast_communicative_executions.append(ready_execution)
                        fast_vocal_activity_ids.append(
                            first_activity.activity_id
                        )

                fast_advance_task = asyncio.create_task(
                    self._resolve_fast_activity_plan_stage(
                        session,
                        work_request=work_request,
                        sid=sid,
                        turn_id=turn_id,
                        text=text,
                        context=context,
                        history=history,
                        responsibility_proposals=responsibility_proposals,
                        committed_fast_activity_ids=committed_fast_activity_ids,
                        fast_started=fast_started,
                        progress=fast_advance_progress,
                    )
                )
                # Establish the GI fan-out before entering GA's serialized commit
                # section. A fail-fast GA result must not prevent Fast Planner from
                # receiving the same authoritative GI result.
                await asyncio.sleep(0)

            self._queue_social_attention_for_activity(
                session,
                activity=self._scheduled_speech_social_activity(
                    context, turn_id=turn_id
                ),
                text=text,
                sid=sid,
                turn_id=turn_id,
                language=language,
                context=context,
                history=history,
            )
            association_stage = await self._resolve_and_commit_goal_association(
                session,
                work_request=work_request,
                sid=sid,
                text=text,
                turn_id=turn_id,
                context=context,
                history=history,
                timings=timings,
            )
            association = association_stage.association
            context = association_stage.context
            history = association_stage.history
            planning_context = association_stage.planning_context
            situation = association_stage.situation
            goal_state_results = association_stage.goal_state_results
            goal_state_commit_stage = association_stage.goal_state_commit_stage
            has_named_goal_cancellation = (
                association_stage.has_named_goal_cancellation
            )
            has_goal_replacement = association_stage.has_goal_replacement

            if fast_advance_task is None:
                raise CognitiveStageFailure(
                    "fast_planner_advance",
                    {
                        "failure_class": "missing_responsibility_activity_plan",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "goal_interpretation",
                        "retryable": False,
                    },
                )
            fast_advance_stage = await fast_advance_task
            fast_advance = fast_advance_stage.advance
            timings["fast_planner_activity_plan"] = (
                fast_advance_stage.activity_plan_elapsed_ms
            )
            ready_fast_capability_execution = (
                fast_advance_stage.ready_capability_execution
            )
            ready_fast_capability_status = fast_advance_stage.ready_capability_status
            if fast_advance_stage.communicative_realization_status != "not_started":
                fast_communicative_realization_status = (
                    fast_advance_stage.communicative_realization_status
                )
            social_attention_opportunity_count += (
                fast_advance_stage.social_attention_opportunity_delta
            )
            ready_fast_communicative_executions.extend(
                fast_advance_stage.ready_communicative_executions
            )
            fast_vocal_activity_ids.extend(fast_advance_stage.vocal_activity_ids)
            timings["fast_planner_advance"] = (
                time.perf_counter() - fast_started
            ) * 1000.0
            needs_deep_planner = "deep_planner" in fast_advance.continuations

            if (
                self.policy.mode == "apply"
                and goal_state_commit_stage == "goal_association"
                and ready_fast_communicative_executions
            ):
                goal_ids_by_responsibility = self._goal_ids_by_responsibility(
                    association
                )
                for ready_execution in ready_fast_communicative_executions:
                    self.adapter.interaction_runtime.bind_fast_planner_communicative_execution(
                        ready_execution,
                        session_id=sid,
                        goal_ids_by_responsibility=goal_ids_by_responsibility,
                    )

            association_goal_ids = self._association_goal_ids(association)
            retained_reconciliation_goal_ids = {
                *association_goal_ids,
                *(
                    goal_id
                    for goal in association.new_goals
                    for goal_id in goal.supersedes_goal_ids
                ),
            }
            retained_work_activities = self._retained_existing_work_activities(
                context=planning_context,
                goal_ids=retained_reconciliation_goal_ids,
            )
            work_reconciliation_required = (
                not has_named_goal_cancellation
                and (
                    ready_fast_capability_execution is not None
                    or bool(retained_work_activities)
                )
            )
            goal_update_reconciliation_required = any(
                bool(item.goal_update) for item in association.associations
            )
            canonical_fast_revision_reason = ""
            if work_reconciliation_required:
                canonical_fast_revision_reason = (
                    "provisional_work_goal_reconciliation"
                    if ready_fast_capability_execution is not None
                    else "goal_replacement_work_reconciliation"
                    if has_goal_replacement
                    else "retained_goal_work_reconciliation"
                )
                provisional_work_activities = (
                    [
                        {
                            **item.model_dump(mode="json", exclude_none=True),
                            "origin": "provisional_fast",
                        }
                        for item in ready_fast_capability_execution.activities
                    ]
                    if ready_fast_capability_execution is not None
                    else []
                )
                planning_context["existing_work_activities"] = [
                    *retained_work_activities,
                    *provisional_work_activities,
                ]
                work_reconciliation_activity_count = len(
                    planning_context["existing_work_activities"]
                )
            elif goal_update_reconciliation_required:
                # Fast Advance and Goal Association share the GI result but run
                # concurrently. When GA authors an update to retained canonical
                # Goal meaning, only a new Fast Planner pass may decide whether
                # the provisional Activities or InformationGaps still apply.
                canonical_fast_revision_reason = (
                    "goal_association_update_reconciliation"
                )
            if canonical_fast_revision_reason:
                planning_context["canonical_fast_revision_reason"] = (
                    canonical_fast_revision_reason
                )
            planner_gaps_by_goal_id = (
                {}
                if canonical_fast_revision_reason
                else self._planner_gaps_by_goal_id(
                    advance=fast_advance,
                    association=association,
                )
            )
            if self.policy.mode == "apply" and planner_gaps_by_goal_id:
                if self.planner_gap_apply is None:
                    raise CognitiveStageFailure(
                        "planner_information_gap_commit",
                        {
                            "failure_class": "planner_gap_commit_boundary_unavailable",
                            "failure_domain": "semantic_state",
                            "architecture_attribution": "host_runtime",
                            "retryable": False,
                        },
                    )
                gap_commit_started_ms = time.perf_counter() * 1000.0
                try:
                    gap_results = self.planner_gap_apply(
                        planner_gaps_by_goal_id,
                        turn_id=turn_id,
                        sid=sid,
                        user_text=text,
                        source="goal_driven_cognitive_runtime_fast_planner",
                    )
                except Exception as exc:
                    self._record_workflow_stage(
                        sid=sid,
                        stage="planner_information_gap_commit",
                        started_monotonic_ms=gap_commit_started_ms,
                        finished_monotonic_ms=time.perf_counter() * 1000.0,
                        status="failed",
                        input_payload={
                            "planner_gaps_by_goal_id": planner_gaps_by_goal_id
                        },
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
                        "planner_information_gap_commit",
                        {
                            "failure_class": type(exc).__name__,
                            "failure_domain": "semantic_state",
                            "architecture_attribution": "host_runtime",
                            "retryable": False,
                            "error": str(exc)[:300],
                        },
                    ) from exc
                self._record_workflow_stage(
                    sid=sid,
                    stage="planner_information_gap_commit",
                    started_monotonic_ms=gap_commit_started_ms,
                    finished_monotonic_ms=time.perf_counter() * 1000.0,
                    status="accepted",
                    input_payload={
                        "planner_gaps_by_goal_id": planner_gaps_by_goal_id
                    },
                    output_payload={"goal_state_results": gap_results},
                    errors=[],
                    attempt=1,
                )
                rejected_gaps = [
                    item
                    for item in gap_results
                    if item.get("applied") is False
                    and item.get("reason") != "operation_already_applied"
                ]
                if rejected_gaps:
                    raise CognitiveStageFailure(
                        "planner_information_gap_commit",
                        {
                            "failure_class": "planner_gap_application_rejected",
                            "failure_domain": "semantic_state",
                            "architecture_attribution": "host_runtime",
                            "retryable": False,
                            "error": json.dumps(
                                rejected_gaps,
                                ensure_ascii=False,
                            )[:300],
                        },
                    )
                goal_state_results.extend(gap_results)
                goal_state_commit_stage = (
                    f"{goal_state_commit_stage}+planner_information_gap"
                    if goal_state_commit_stage
                    else "planner_information_gap"
                )
            planning_situation = build_situation_projection(
                context=context,
                turn_id=turn_id,
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
                    goal_ids=association_goal_ids,
                    relationships=[
                        *[item.relationship for item in association.associations],
                        *(["new"] if association.new_goals else []),
                    ],
                )
            planning_context["interaction_context"] = self._interaction_context(
                sid=sid,
                context=planning_context,
                goal_ids=association_goal_ids,
            )
            if not association_goal_ids:
                raise CognitiveStageFailure(
                    "goal_association",
                    {
                        "failure_class": "empty_canonical_goal_set",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "not_evaluated",
                        "retryable": True,
                        "reason": "resolved Goal Association produced no canonical goals",
                        "status": association.resolution_status,
                    },
                )

            if needs_deep_planner:
                deep_reason = "fast_planner_advance_complexity"
                deep_planner_invocation_reasons.append(deep_reason)
                deep_context = dict(planning_context)
                deep_context["deep_planner_invocation_reason"] = deep_reason
                deep_context["fast_planner_advance"] = fast_advance.model_dump(
                    mode="json", exclude_none=True
                )
                stage = time.perf_counter()
                terminal_plan = await self._observe_workflow_stage(
                    sid=sid,
                    stage="deep_planner",
                    input_payload={
                        "user_text": text,
                        "goal_association": association,
                        "fast_planner_advance": fast_advance,
                        "invocation_reason": deep_reason,
                    },
                    operation=self.agent_client.resolve_deep_plan(
                        session,
                        request=work_request.model_copy(
                            update={
                                "context": deep_context,
                                "history": history,
                            }
                        ),
                        timeout_ms=self.policy.deep_planner_timeout_ms,
                    ),
                )
                timings["deep_planner"] = (
                    time.perf_counter() - stage
                ) * 1000.0
                fast_planner_path = "deep_escalation"
                deep_failure = self._optional_stage_failure_metadata(
                    "deep_planner", terminal_plan.metadata
                )
                if deep_failure is not None:
                    raise CognitiveStageFailure("deep_planner", deep_failure)
            elif (
                fast_advance.disposition in {"unavailable", "refused"}
                or canonical_fast_revision_reason
            ):
                # A malformed/unavailable first Activity Plan, or a committed Goal
                # intersecting retained/provisional Work, receives one canonical Fast
                # Planner revision. GA supplies Goal continuity only; it never decides
                # Work compatibility. Provisional safe Work remains available until
                # Planner explicitly selects reuse or authors replacement Work.
                stage = time.perf_counter()
                fast_plan = await self._observe_workflow_stage(
                    sid=sid,
                    stage="fast_planner",
                    input_payload={
                        "user_text": text,
                        "goal_association": association,
                        "revision_reason": (
                            canonical_fast_revision_reason
                            if canonical_fast_revision_reason
                            else "fast_planner_advance_unavailable"
                        ),
                        "interaction_context": planning_context.get(
                            "interaction_context", {}
                        ),
                    },
                    operation=self.agent_client.resolve_fast_plan(
                        session,
                        request=work_request.model_copy(
                            update={
                                "context": planning_context,
                                "history": history,
                            }
                        ),
                        timeout_ms=self.policy.fast_planner_timeout_ms,
                    ),
                )
                timings["fast_planner"] = (
                    time.perf_counter() - stage
                ) * 1000.0
                fast_failure = self._optional_stage_failure_metadata(
                    "fast_planner", fast_plan.metadata
                )
                if fast_failure is not None:
                    stage_diagnostics.append(fast_failure)
                terminal_plan = fast_plan
                fast_planner_path = self._fast_plan_path(fast_plan)
                if fast_plan.disposition == "escalate":
                    if fast_planner_path == "contract_failure":
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
                    deep_context["fast_plan_resolution"] = (
                        self._fast_plan_context_for_deep(fast_plan)
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
                            request=work_request.model_copy(
                                update={
                                    "context": deep_context,
                                    "history": history,
                                }
                            ),
                            timeout_ms=self.policy.deep_planner_timeout_ms,
                        ),
                    )
                    timings["deep_planner"] = (
                        time.perf_counter() - stage
                    ) * 1000.0
                    deep_failure = self._optional_stage_failure_metadata(
                        "deep_planner", terminal_plan.metadata
                    )
                    if deep_failure is not None:
                        raise CognitiveStageFailure("deep_planner", deep_failure)
            else:
                fast_plan = self._canonical_plan_from_fast_advance(
                    advance=fast_advance,
                    association=association,
                    user_text=text,
                )
                terminal_plan = fast_plan
                fast_planner_path = "terminal"

            # Runtime authority starts from the validated canonical Plan and is
            # bounded by registered Capability, authorization, confirmation, resource,
            # and provider-safety contracts below. Goal Interpretation contributes WHAT only.
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

            if self.policy.mode == "apply" and retained_work_activities:
                terminal_plan, retained_work_reconciliation_status = (
                    await self._apply_retained_work_reconciliation(
                        plan=terminal_plan,
                        activities=retained_work_activities,
                        turn_id=turn_id,
                    )
                )

            if ready_fast_capability_execution is not None:
                refs_to_goals: dict[str, list[str]] | None = None
                if terminal_plan.metadata.get("resolver") == "fast_planner_advance":
                    raw_refs_to_goals = terminal_plan.metadata.get(
                        "goal_ids_by_responsibility"
                    )
                    if isinstance(raw_refs_to_goals, dict):
                        refs_to_goals = raw_refs_to_goals
                    else:
                        raise ValueError(
                            "Fast Activity Plan lacks canonical Goal grouping"
                        )
                elif work_reconciliation_required:
                    reusable_plan = (
                        self._canonical_plan_reusing_fast_capability_execution(
                            execution=ready_fast_capability_execution,
                            plan=terminal_plan,
                            association=association,
                        )
                    )
                    if reusable_plan is not None:
                        terminal_plan = reusable_plan
                        refs_to_goals = self._goal_ids_by_responsibility(
                            association
                        )
                if refs_to_goals is not None:
                    ready_result = await self.adapter.interaction_runtime.bind_fast_planner_capability_execution(
                        ready_fast_capability_execution,
                        target_interaction_id=f"cognitive_{sid}",
                        canonical_plan_id=terminal_plan.plan_id,
                        canonical_plan_fingerprint=canonical_plan_fingerprint(
                            terminal_plan
                        ),
                        goal_ids_by_responsibility=refs_to_goals,
                        task_list_revision=int(
                            terminal_plan.metadata.get("task_list_revision") or 1
                        ),
                    )
                    ready_fast_capability_status = (
                        "completed_before_canonical_dispatch:"
                        + ready_result.status
                    )
                else:
                    await self.adapter.interaction_runtime.runtime.cancel_interaction(
                        ready_fast_capability_execution.interaction_id
                    )
                    ready_fast_capability_status = (
                        "cancelled_by_work_reconciliation"
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

            if (
                terminal_plan.metadata.get("resolver") == "fast_planner_advance"
                and not terminal_plan.steps
                and terminal_plan.disposition in {"respond", "clarify"}
            ):
                timings["planner_communicative_activity_validation"] = 0.0
                if self.policy.mode == "apply":
                    interaction = self.adapter.build_fast_advance_response(
                        advance=fast_advance,
                        plan=terminal_plan,
                        session_id=sid,
                        language=language,
                        preexecuted_activity_ids=set(fast_vocal_activity_ids),
                        context=planning_context,
                    )
                    interaction.metadata["goal_association"] = association.model_dump(
                        mode="json", exclude_none=True
                    )
                    if goal_state_commit_stage.startswith("goal_association"):
                        interaction.metadata["goal_state_results"] = goal_state_results
                    return self._finish(
                        mode="apply",
                        status="applied",
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
                        interaction=interaction,
                        goal_state_results=goal_state_results,
                        timings=timings,
                        started=started,
                        metadata={
                            "fast_activity_response": True,
                            "fast_vocal_activity_ids": list(fast_vocal_activity_ids),
                            "stage_diagnostics": stage_diagnostics,
                            **path_metadata(),
                        },
                    )
                return self._finish(
                    mode="report_only",
                    status="report_only",
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    timings=timings,
                    started=started,
                    metadata={
                        "fast_activity_response": True,
                        "stage_diagnostics": stage_diagnostics,
                        **path_metadata(),
                    },
                )

            if self.adapter.is_pure_safe_read_plan(terminal_plan):
                if self.policy.mode == "apply":
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
                    timings["planner_communicative_activity_validation"] = 0.0
                    interaction.metadata["goal_association"] = association.model_dump(
                        mode="json", exclude_none=True
                    )
                    if goal_state_commit_stage == "goal_association":
                        interaction.metadata["goal_state_results"] = goal_state_results
                    interaction.metadata["continuous_cognition"] = {
                        "provider_work_started_before_goal_association_completed": (
                            ready_fast_capability_status.startswith(
                                "completed_before_canonical_dispatch"
                            )
                        ),
                        "duplicate_response_model_absent": True,
                    }
                    return self._finish(
                        mode="apply",
                        status="applied",
                        association=association,
                        fast_plan=fast_plan,
                        terminal_plan=terminal_plan,
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
                timings["planner_communicative_activity_validation"] = 0.0
                return self._finish(
                    mode="report_only",
                    status="report_only",
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
                    timings=timings,
                    started=started,
                    metadata={
                        "execution_only_safe_read": True,
                        "stage_diagnostics": stage_diagnostics,
                        **path_metadata(),
                    },
                )

            planner_response_context = dict(planning_context)
            planner_response_context["canonical_plan_resolution"] = terminal_plan.prompt_projection()
            delivered_turn_speech = (
                self.delivered_turn_speech_provider(sid)
                if callable(self.delivered_turn_speech_provider)
                else []
            )
            planner_response_context["delivered_turn_speech"] = [
                dict(item) for item in delivered_turn_speech if isinstance(item, dict)
            ]
            timings["planner_communicative_activity_validation"] = 0.0

            if self.policy.mode == "apply":
                stage = time.perf_counter()
                interaction = await self._observe_workflow_stage(
                    sid=sid,
                    stage="planner_communicative_activity_validation",
                    input_payload={
                        "canonical_plan": terminal_plan,
                        "wording_owner": "planner",
                    },
                    operation=self.adapter.build_planner_owned_response(
                        plan=terminal_plan,
                        session_id=sid,
                        language=language,
                        context=planner_response_context,
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
                    association=association,
                    fast_plan=fast_plan,
                    terminal_plan=terminal_plan,
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
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
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
        except asyncio.CancelledError:
            # The Host owns the outer foreground deadline. If it cancels this
            # pipeline, stop only Fast work that never reached canonical Goal/Plan
            # binding, then propagate cancellation so the Host records the timeout.
            await cancel_uncommitted_fast_work("foreground_deadline")
            raise
        except CognitiveStageFailure as exc:
            await cancel_uncommitted_fast_work(exc.stage)
            failure_metadata = {
                **exc.failure_metadata,
                "failure_stage": exc.stage,
                "stage_diagnostics": stage_diagnostics,
                **path_metadata(),
            }
            return self._finish(
                mode=self.policy.mode,
                status="error",
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
                interaction=interaction,
                goal_state_results=goal_state_results,
                timings=timings,
                started=started,
                fallback_reason=str(exc)[:500],
                metadata=failure_metadata,
            )
        except Exception as exc:
            await cancel_uncommitted_fast_work(type(exc).__name__)
            return self._finish(
                mode=self.policy.mode,
                status="error",
                association=association,
                fast_plan=fast_plan,
                terminal_plan=terminal_plan,
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
        association: GoalAssociationResolution | None,
        fast_plan: CanonicalPlan | None,
        terminal_plan: CanonicalPlan | None,
        timings: dict[str, float],
        started: float,
        interaction: InteractionResponse | None = None,
        goal_state_results: list[dict[str, Any]] | None = None,
        fallback_reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CognitiveRuntimeResolution:
        final_timings = dict(timings)
        final_timings["total"] = (time.perf_counter() - started) * 1000.0
        metadata_payload = dict(metadata or {})
        fast_advance = None
        raw_fast_advance = metadata_payload.get("fast_planner_advance")
        if isinstance(raw_fast_advance, dict):
            try:
                fast_advance = FastPlannerAdvance.model_validate(raw_fast_advance)
            except ValidationError:
                fast_advance = None
        return CognitiveRuntimeResolution(
            mode=mode,
            status=status,
            goal_association=association,
            fast_advance=fast_advance,
            fast_plan=fast_plan,
            terminal_plan=terminal_plan,
            interaction_response=interaction,
            goal_state_results=list(goal_state_results or []),
            timings_ms={key: round(value, 1) for key, value in final_timings.items()},
            fallback_reason=fallback_reason,
            metadata=metadata_payload,
        )
