from __future__ import annotations

from .cognitive_gateway_modules.context_assembly import ContextAssembly

import asyncio
import hashlib
import json
import logging
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, Literal, Protocol

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
    CapabilityTrace,
    MEDIA_CAPABILITY_IDS,
    CapabilityRequest,
    VOCAL_MODES,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.semantic_artifact import (
    SemanticArtifactKind,
    SemanticArtifactLineage,
    SemanticArtifactPacket,
    SemanticArtifactRef,
    merge_semantic_artifact_lineage,
    semantic_artifact_packet,
    semantic_artifact_ref,
)
from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialCognitionResolution
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.plan import (
    communication_need_id,
    AuxiliaryPlanActivity,
    SocialCommunicationNeed,
    CanonicalPlan,
    CanonicalPlanStep,
    PlanParameterResolution,
    ClarifyGoalPlanOutcome,
    ExecuteGoalPlanOutcome,
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerCommunicativeAct,
    FastPlannerStreamFailure,
    FastPlannerStreamFrame,
    FastPlannerStreamTerminal,
    GoalSatisfactionAssessment,
    PlannerInformationGap,
    PlannedCommunicativeAct,
    RespondGoalPlanOutcome,
    RefusedGoalPlanOutcome,
    UnavailableGoalPlanOutcome,
    fast_planner_activity_request_id,
    validate_communicative_activity_identity,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.user_turn import (
    AttentionReviewResult,
    GatewayContextSnapshot,
    UserTurnEnvelope,
    resolve_user_turn_source_span,
    user_turn_prohibits_speech,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

from orchestrator.runtime.evidence_identity import runtime_identity_reference

from orchestrator.runtime.situation import build_situation_projection
from orchestrator.runtime.response_plan import build_social_interaction_response

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


def _core_semantic_lineage(
    *,
    turn_envelope: UserTurnEnvelope,
    core_interpretation: CoreInterpretationResult,
) -> SemanticArtifactLineage:
    """Bind one admitted turn and accepted UMI output without copying semantics."""

    refs: list[SemanticArtifactRef] = [
        semantic_artifact_ref(
            turn_envelope, artifact_kind="user_turn", artifact_id=turn_envelope.turn_id,
        ),
        semantic_artifact_ref(
            core_interpretation, artifact_kind="user_meaning_interpretation",
            artifact_id=core_interpretation.turn_id,
        ),
    ]
    refs.extend(
        semantic_artifact_ref(
            item, artifact_kind="responsibility",
            artifact_id=f"{core_interpretation.turn_id}:{item.local_ref}",
        )
        for item in core_interpretation.responsibilities
    )
    return merge_semantic_artifact_lineage(refs)


def _association_semantic_lineage(
    base: SemanticArtifactLineage, association: GoalAssociationResolution,
) -> SemanticArtifactLineage:
    refs: list[SemanticArtifactRef] = [
        semantic_artifact_ref(
            association, artifact_kind="goal_association", artifact_id=association.turn_id,
        )
    ]
    refs.extend(
        semantic_artifact_ref(goal, artifact_kind="goal", artifact_id=goal.goal_id)
        for goal in association.new_goals
        if str(goal.goal_id or "").strip()
    )
    return merge_semantic_artifact_lineage(base, refs)


def _plan_semantic_lineage(
    base: SemanticArtifactLineage, plan: CanonicalPlan,
) -> SemanticArtifactLineage:
    return merge_semantic_artifact_lineage(
        base, semantic_artifact_ref(
            plan, artifact_kind="planner_plan", artifact_id=plan.plan_id,
        ),
    )


def _social_semantic_lineage(
    base: SemanticArtifactLineage, resolution: SocialCognitionResolution,
) -> SemanticArtifactLineage:
    refs: list[SemanticArtifactRef] = [
        semantic_artifact_ref(
            resolution, artifact_kind="social_cognition",
            artifact_id=resolution.request_id,
        )
    ]
    refs.extend(
        semantic_artifact_ref(
            act, artifact_kind="communicative_act", artifact_id=act.activity_id,
        )
        for act in resolution.activities
    )
    return merge_semantic_artifact_lineage(base, refs)


def _semantic_lineage_from_context(context: dict[str, Any] | None) -> SemanticArtifactLineage:
    raw = context.get("semantic_artifact_lineage") if isinstance(context, dict) else None
    if raw is None:
        return SemanticArtifactLineage()
    return SemanticArtifactLineage.model_validate(raw)


def _lineage_context(
    context: dict[str, Any], lineage: SemanticArtifactLineage,
) -> dict[str, Any]:
    updated = dict(context)
    updated["semantic_artifact_lineage"] = lineage.model_dump(mode="json")
    return updated


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
    planning_task: asyncio.Task[CanonicalPlan] | None = None
    planning_snapshot: dict[str, Any] | None = None


class CognitiveAgentClient(Protocol):
    async def resolve_social_cognition(
        self, session: Any, **kwargs: Any
    ) -> SocialCognitionResolution: ...

    async def resolve_goal_association(
        self, session: Any, **kwargs: Any
    ) -> GoalAssociationResolution: ...

    def stream_fast_advance(
        self, session: Any, **kwargs: Any
    ) -> AsyncIterator[FastPlannerStreamFrame]: ...

    async def resolve_fast_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_deep_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_reflection(
        self, session: Any, **kwargs: Any
    ) -> ReflectionResolution: ...

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

    @classmethod
    def semantic_artifact_packets(
        cls,
        resolution: "CognitiveRuntimeResolution",
        *,
        sid: str,
    ) -> list[SemanticArtifactPacket]:
        """Project accepted owner artifacts into immutable archival packets."""

        packets: list[SemanticArtifactPacket] = []
        seen: set[tuple[str, str, str]] = set()
        source = resolution.turn_envelope
        turn_id = source.turn_id if source is not None else str(sid or "")
        session_id = source.session_id if source is not None else str(sid or "")
        conversation_id = source.conversation_id if source is not None else ""

        def pack(
            payload: BaseModel | dict[str, Any],
            *,
            kind: SemanticArtifactKind,
            artifact_id: str,
            authority: str,
            parents: Iterable[SemanticArtifactRef] = (),
            artifact_session_id: str | None = None,
            artifact_turn_id: str | None = None,
        ) -> SemanticArtifactRef:
            packet = semantic_artifact_packet(
                payload,
                artifact_kind=kind,
                artifact_id=artifact_id,
                authority=authority,
                session_id=artifact_session_id or session_id,
                turn_id=artifact_turn_id if artifact_turn_id is not None else turn_id,
                conversation_id=conversation_id,
                parent_refs=parents,
            )
            key = (packet.ref.artifact_kind, packet.ref.artifact_id, packet.ref.payload_sha256)
            if key not in seen:
                seen.add(key)
                packets.append(packet)
            return packet.ref

        turn_ref = (
            pack(
                source,
                kind="user_turn",
                artifact_id=source.turn_id,
                authority="cognitive_gateway",
                artifact_session_id=source.session_id,
                artifact_turn_id=source.turn_id,
            )
            if source is not None
            else None
        )

        response = resolution.interaction_response
        transported_lineage: SemanticArtifactLineage | None = None
        transported_refs: dict[tuple[str, str], SemanticArtifactRef] = {}
        if response is not None and isinstance(response.metadata, dict):
            raw_lineage = response.metadata.get("semantic_artifact_lineage")
            if raw_lineage is not None:
                transported_lineage = SemanticArtifactLineage.model_validate(
                    raw_lineage
                )
                transported_refs = {
                    (ref.artifact_kind, ref.artifact_id): ref
                    for ref in transported_lineage.refs
                }

        def response_lineage_carries(ref: SemanticArtifactRef) -> bool:
            if transported_lineage is None:
                return True
            carried = transported_refs.get((ref.artifact_kind, ref.artifact_id))
            if carried is None:
                return False
            if carried.payload_sha256 != ref.payload_sha256:
                raise ValueError(
                    "semantic artifact lineage digest mismatch for "
                    f"{ref.artifact_kind}:{ref.artifact_id}"
                )
            return True

        metadata = resolution.metadata if isinstance(resolution.metadata, dict) else {}
        raw_core = metadata.get("core_interpretation")
        umi_ref: SemanticArtifactRef | None = None
        responsibility_refs: dict[str, SemanticArtifactRef] = {}
        if isinstance(raw_core, dict):
            core = CoreInterpretationResult.model_validate(raw_core)
            umi_ref = pack(
                core,
                kind="user_meaning_interpretation",
                artifact_id=core.turn_id,
                authority="user_meaning_interpretation",
                parents=[ref for ref in (turn_ref,) if ref is not None],
                artifact_session_id=core.session_id,
                artifact_turn_id=core.turn_id,
            )
            for item in core.responsibilities:
                responsibility_refs[item.local_ref] = pack(
                    item,
                    kind="responsibility",
                    artifact_id=f"{core.turn_id}:{item.local_ref}",
                    authority="user_meaning_interpretation",
                    parents=[ref for ref in (turn_ref, umi_ref) if ref is not None],
                    artifact_session_id=core.session_id,
                    artifact_turn_id=core.turn_id,
                )

        association = resolution.goal_association
        ga_ref: SemanticArtifactRef | None = None
        goal_refs: dict[str, SemanticArtifactRef] = {}
        if association is not None:
            ga_ref = pack(
                association,
                kind="goal_association",
                artifact_id=association.turn_id,
                authority="goal_association",
                parents=[
                    *[ref for ref in (turn_ref, umi_ref) if ref is not None],
                    *responsibility_refs.values(),
                ],
                artifact_turn_id=association.turn_id,
            )
            for index, goal in enumerate(association.new_goals):
                goal_id = str(goal.goal_id or f"{association.turn_id}:new:{index}")
                goal_refs[goal_id] = pack(
                    goal,
                    kind="goal",
                    artifact_id=goal_id,
                    authority="goal_association",
                    parents=[
                        ga_ref,
                        *(
                            responsibility_refs[ref]
                            for ref in goal.source_responsibility_refs
                            if ref in responsibility_refs
                        ),
                    ],
                    artifact_turn_id=association.turn_id,
                )

        plan_refs: list[SemanticArtifactRef] = []
        for plan in (resolution.fast_plan, resolution.terminal_plan):
            if plan is None:
                continue
            plan_ref = pack(
                plan,
                kind="planner_plan",
                artifact_id=plan.plan_id,
                authority="planner",
                parents=[
                    *[ref for ref in (umi_ref, ga_ref) if ref is not None],
                    *goal_refs.values(),
                ],
            )
            if plan_ref not in plan_refs:
                plan_refs.append(plan_ref)

        raw_social = (
            response.metadata.get("social_cognition_resolution")
            if response is not None and isinstance(response.metadata, dict)
            else None
        )
        social_ref: SemanticArtifactRef | None = None
        communicative_act_refs: list[SemanticArtifactRef] = []
        if isinstance(raw_social, dict):
            social = SocialCognitionResolution.model_validate(raw_social)
            social_ref = pack(
                social,
                kind="social_cognition",
                artifact_id=social.request_id,
                authority="social_cognition",
                parents=[
                    *[
                        ref for ref in (umi_ref, ga_ref)
                        if ref is not None and response_lineage_carries(ref)
                    ],
                    *[ref for ref in plan_refs if response_lineage_carries(ref)],
                ],
            )
            for act in social.activities:
                act_ref = pack(
                    act,
                    kind="communicative_act",
                    artifact_id=act.activity_id,
                    authority="social_cognition",
                    parents=[
                        social_ref,
                        *(
                            responsibility_refs[ref]
                            for ref in act.source_responsibility_refs
                            if ref in responsibility_refs
                            and response_lineage_carries(responsibility_refs[ref])
                        ),
                        *(
                            goal_refs[goal_id]
                            for goal_id in act.source_goal_ids
                            if goal_id in goal_refs
                            and response_lineage_carries(goal_refs[goal_id])
                        ),
                    ],
                )
                communicative_act_refs.append(act_ref)

        if transported_lineage is not None:
            # Response lineage is the set that existed when that presentation
            # artifact was authored. Concurrent sibling cognition may finish later
            # and legitimately appear in the final resolution without becoming an
            # ancestor of an already-authored SC response. Validate the immutable
            # refs that the response actually carried; never serialize the DAG by
            # requiring future GA/Planner siblings retroactively.
            for expected in (
                *[ref for ref in (turn_ref, umi_ref) if ref is not None],
                *responsibility_refs.values(),
                *([social_ref] if social_ref is not None else []),
                *communicative_act_refs,
            ):
                transported_lineage.require(expected)
            packet_refs = {
                (packet.ref.artifact_kind, packet.ref.artifact_id): packet.ref
                for packet in packets
            }
            for carried in transported_lineage.refs:
                expected = packet_refs.get(
                    (carried.artifact_kind, carried.artifact_id)
                )
                if (
                    expected is not None
                    and expected.payload_sha256 != carried.payload_sha256
                ):
                    raise ValueError(
                        "semantic artifact lineage digest mismatch for "
                        f"{carried.artifact_kind}:{carried.artifact_id}"
                    )

        return packets

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
        artifact_packets = self.semantic_artifact_packets(resolution, sid=sid)
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
            "semantic_artifact_envelopes": [
                item.envelope.model_dump(mode="json") for item in artifact_packets
            ],
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
            payload["semantic_artifact_packets"] = [
                item.model_dump(mode="json") for item in artifact_packets
            ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def provider_realization_diagnostics(
        traces: Iterable[CapabilityTrace],
    ) -> list[dict[str, Any]]:
        """Project trusted semantic->provider lowering for diagnostics only."""

        rows: list[dict[str, Any]] = []
        for trace in traces:
            for event in trace.events:
                if event.type != "provider_realization":
                    continue
                data = event.data if isinstance(event.data, dict) else {}
                rows.append({
                    "trace_id": trace.trace_id,
                    "request_id": trace.request_id,
                    "capability_id": trace.capability_id,
                    "provider_id": trace.provider_id,
                    "timestamp": event.timestamp.isoformat(),
                    "semantic_args": dict(data.get("semantic_args") or {}),
                    "provider_args": dict(data.get("provider_args") or {}),
                    "semantic_facade_applied": bool(
                        data.get("semantic_facade_applied")
                    ),
                })
        return rows

    def record_outcome(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str,
        final_response: InteractionResponse | None,
        delivery_status: str,
        suppression_reason: str = "",
        goal_state_results: list[dict[str, Any]] | None = None,
        capability_traces: Iterable[CapabilityTrace] = (),
    ) -> None:
        """Append the trusted post-execution half of a cognitive turn."""

        self.counters["outcome_bundles"] += 1
        self.counters[f"outcome_status:{bundle.aggregate_status}"] += 1
        self.counters[f"outcome_delivery:{delivery_status}"] += 1
        if not self.enabled:
            return
        outcome_packet = semantic_artifact_packet(
            bundle,
            artifact_kind="execution_outcome",
            artifact_id=bundle.outcome_id,
            authority="trusted_runtime",
            session_id=sid,
            turn_id=bundle.turn_id,
        )
        payload = {
            "schema_version": 2,
            "event": "cognitive_execution_outcome",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "turn_id": bundle.turn_id,
            "interaction_id": bundle.interaction_id,
            "run_identity": self._identity_reference(),
            "outcome_fingerprint": execution_outcome_fingerprint(bundle),
            "semantic_artifact_envelopes": [
                outcome_packet.envelope.model_dump(mode="json")
            ],
            "outcome_bundle": bundle.model_dump(mode="json", exclude_none=True),
            "goal_state_results": list(goal_state_results or []),
            "final_response": self._interaction_summary(final_response),
            "delivery_status": delivery_status,
            "suppression_reason": suppression_reason,
            "provider_realizations": self.provider_realization_diagnostics(
                capability_traces
            ),
        }
        if self.include_text:
            payload["semantic_artifact_packets"] = [
                outcome_packet.model_dump(mode="json")
            ]
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
        recent_auxiliary_evidence_limit: int = 12,
    ) -> None:
        self.interaction_runtime = interaction_runtime
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
        if not request.metadata.get("auxiliary_plan_activity"):
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
                "social_function": request.metadata.get("social_function"),
                "turn_id": request.metadata.get("turn_id"),
                "anchor_kind": request.metadata.get("anchor_kind"),
                "anchor_id": request.metadata.get("anchor_id"),
                "auxiliary_activity_id": request.metadata.get(
                    "auxiliary_activity_id"
                ),
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
                "social_cognition_request_id": request.metadata.get("social_cognition_request_id"),
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
    def _current_auxiliary_target_evidence(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Project current trusted target semantics without selecting a target."""

        for key in (
            "auxiliary_social_target",
            "social_attention_target",
            "active_user_target",
            "perceived_user_target",
        ):
            value = context.get(key)
            if not isinstance(value, dict) or not value:
                continue
            explicit_source = str(value.get("source") or "").strip()
            source = (
                explicit_source
                if explicit_source in {"live_perception", "conversation_context"}
                else "live_perception"
                if "perception" in key or "perceived" in key
                else "conversation_context"
            )
            raw_target = value.get("target")
            target = dict(raw_target) if isinstance(raw_target, dict) else dict(value)
            return {
                "available": True,
                "source": source,
                "target": {
                    name: target[name]
                    for name in (
                        "target_ref",
                        "relative_direction",
                        "confidence",
                        "evidence_refs",
                    )
                    if name in target
                },
            }
        return {"available": False}

    @staticmethod
    def _attention_target_error(
        attention: AuxiliaryPlanActivity,
        context: dict[str, Any],
    ) -> str | None:
        target = attention.target
        if target.source == "none":
            return None
        evidence = CanonicalPlanRuntimeAdapter._current_auxiliary_target_evidence(
            context
        )
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
        evidence = CanonicalPlanRuntimeAdapter._current_auxiliary_target_evidence(
            context
        )
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

    async def prepare_auxiliary_response(
        self,
        *,
        social_cognition: SocialCognitionResolution,
        session_id: str,
        turn_id: str,
        interaction: InteractionResponse | None,
        context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> InteractionResponse | dict[str, Any]:
        """Validate and execute SC-owned optional social expression.

        Runtime may accept or suppress the exact proposal. It never reselects the
        Capability, target, arguments, social function, or primary anchor. The
        resulting Activity has no Goal-completion or cognition-reentry authority.
        """

        if snapshot_is_current is not None and not snapshot_is_current():
            return {"status": "suppressed", "materialized_count": 0, "reasons": ["stale_social_snapshot"]}
        auxiliary_activities = [
            item for act in social_cognition.activities for item in act.auxiliary_activities
        ]
        primary_steps = list(interaction.capabilities) if interaction is not None else []
        materialized_ids = {str(ref) for speech in (interaction.speech if interaction else [])
                            for ref in speech.metadata.get("communicative_activity_ids", [])}
        communicative_ids = {act.activity_id for act in social_cognition.activities
                             if act.function == "nonverbal" or act.activity_id in materialized_ids}
        step_ids = set()
        has_plan_response = False
        planner_source_id = social_cognition.request_id
        planner_source_metadata = {
            "social_cognition_request_id": social_cognition.request_id,
            "social_cognition_snapshot_digest": social_cognition.snapshot_digest,
            "semantic_owner": "social_cognition",
        }
        auxiliary_source = "social_cognition_auxiliary_activity"
        if not auxiliary_activities:
            return {
                "status": "not_executed",
                "materialized_count": 0,
            }
        if interaction is None:
            return {
                "status": "rejected",
                "materialized_count": 0,
                "reasons": ["primary_interaction_not_materialized"],
            }
        runtime_context = dict(context or {})
        requests: list[CapabilityRequest] = []
        reasons: list[str] = []
        primary_capability_ids = {
            step.capability_id for step in primary_steps
        }
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
        for index, behavior in enumerate(auxiliary_activities):
            try:
                anchor_valid = (
                    behavior.anchor_id in step_ids
                    if behavior.anchor_kind == "plan_step"
                    else behavior.anchor_id in communicative_ids
                    if behavior.anchor_kind == "communicative_act"
                    else behavior.anchor_id == "response" and has_plan_response
                )
                if not anchor_valid:
                    reasons.append(
                        f"stale_or_invalid_anchor:{behavior.auxiliary_activity_id}"
                    )
                    continue
                target_error = self._attention_target_error(behavior, runtime_context)
                if target_error:
                    reasons.append(
                        f"target_error:{behavior.capability_id}:{target_error}"
                    )
                    continue
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
                    reasons.append(f"duplicate_auxiliary_capability:{behavior.capability_id}")
                    continue
                if any(
                    item.get("session_id") == session_id
                    and item.get("turn_id") == turn_id
                    and item.get("anchor_id") == behavior.anchor_id
                    and item.get("capability_id") == behavior.capability_id
                    for item in self._recent_auxiliary_behavior_evidence
                ):
                    reasons.append(
                        f"duplicate_auxiliary_dispatch:{behavior.capability_id}"
                    )
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
                    f"{turn_id}|{planner_source_id}|{behavior.auxiliary_activity_id}|{index}|{behavior.capability_id}".encode("utf-8")
                ).hexdigest()[:20]
                request = CapabilityRequest(
                    request_id=f"aux_{digest}",
                    capability_id=behavior.capability_id,
                    capability_version=definition.version,
                    args=dict(behavior.args),
                    timing="parallel",
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=False,
                    idempotency_key=(
                        f"{turn_id}:aux:{planner_source_id}:{behavior.auxiliary_activity_id}"
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
                        "source": auxiliary_source,
                        "auxiliary_plan_activity": True,
                        "behavior_domain": "social_attention",
                        "interaction_role": "auxiliary_expression",
                        "social_function": behavior.social_function,
                        "target": behavior.target.model_dump(
                            mode="json", exclude_none=True
                        ),
                        "reason": behavior.reason_summary,
                        "execution_lane": "activity",
                        "execution_role": "social_decoration",
                        "source_goal_ids": [],
                        "turn_id": turn_id,
                        **planner_source_metadata,
                        "auxiliary_activity_id": behavior.auxiliary_activity_id,
                        "anchor_kind": behavior.anchor_kind,
                        "anchor_id": behavior.anchor_id,
                        "primary_activity_goal_ids": [],
                    },
                )
                requests.append(request)
                seen.add(behavior.capability_id)
            except (TypeError, ValueError, ValidationError, RuntimeError) as exc:
                reasons.append(f"invalid:{behavior.capability_id}:{type(exc).__name__}")

        if snapshot_is_current is not None and not snapshot_is_current():
            return {"status": "suppressed", "materialized_count": 0, "reasons": ["stale_social_snapshot"]}
        if not requests:
            return {
                "status": "rejected" if reasons else "not_executed",
                "materialized_count": 0,
                "reasons": reasons,
            }
        interaction_id = f"aux_{turn_id}_{hashlib.sha256(planner_source_id.encode('utf-8')).hexdigest()[:10]}"
        response_metadata: dict[str, Any] = {
            "source": auxiliary_source + "s",
            "auxiliary_plan_activity": True,
            "turn_id": turn_id,
            "session_id": session_id,
            **planner_source_metadata,
            "source_goal_ids": [],
            "cognitive_reentry_eligible": False,
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
        response.metadata["auxiliary_reasons"] = reasons
        return response

    async def execute_auxiliary_activities(
        self, *, social_cognition: SocialCognitionResolution, session_id: str,
        turn_id: str, interaction: InteractionResponse | None,
        context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        response = await self.prepare_auxiliary_response(social_cognition=social_cognition,
            session_id=session_id, turn_id=turn_id, interaction=interaction,
            context=context, snapshot_is_current=snapshot_is_current)
        if not isinstance(response, InteractionResponse):
            return response
        requests = response.capabilities
        interaction_id = response.interaction_id
        reasons = response.metadata.get("auxiliary_reasons", [])
        for request in requests:
            self._record_auxiliary_behavior_request(request, session_id=session_id)
        dispatch = await self.interaction_runtime.submit_response(
            response,
            session_id=session_id,
        )
        execution = await self.interaction_runtime.wait_dispatch(dispatch)
        ledger = getattr(self.interaction_runtime, "interaction_ledger", None)
        if ledger is not None:
            ledger.record_social_results(
                session_id=session_id, turn_id=turn_id, interaction_id=interaction_id,
                requests=requests, results=execution.results,
            )
        return {
            "status": execution.status,
            "materialized_count": len(requests),
            "request_ids": [item.request_id for item in requests],
            "reasons": reasons,
        }


    async def prepare_social_response(
        self, response: InteractionResponse, *, social_cognition: SocialCognitionResolution,
        session_id: str, turn_id: str, context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> InteractionResponse:
        """Materialize exact SC anchors before either modality enters Runtime."""
        if response.metadata.get("social_expression_materialized") is True:
            return response
        auxiliary = await self.prepare_auxiliary_response(social_cognition=social_cognition,
            session_id=session_id, turn_id=turn_id, interaction=response,
            context=context, snapshot_is_current=snapshot_is_current)
        response = response.model_copy(deep=True)
        response.metadata["social_expression_materialized"] = True
        response.metadata.update({"session_id": session_id, "turn_id": turn_id})
        if not isinstance(auxiliary, InteractionResponse):
            response.metadata["social_expression_admission"] = auxiliary
            return response
        for request in auxiliary.capabilities:
            anchor = request.metadata.get("anchor_id")
            speeches = [speech for speech in response.speech
                        if anchor in speech.metadata.get("communicative_activity_ids", [])]
            if len(speeches) == 1:
                speech = speeches[0]
                identity = "sc:" + hashlib.sha256(f"{social_cognition.request_id}|{anchor}".encode()).hexdigest()[:24]
                shared = {"coordination_id": identity, "lane_start_policy": "prepared_start"}
                request.metadata.update(shared)
                speech.metadata.update({**shared, "execution_lane": "vocal"})
            self._record_auxiliary_behavior_request(request, session_id=session_id)
        response.capabilities.extend(auxiliary.capabilities)
        return response

    async def build_execution_only_response(
        self,
        *,
        plan: CanonicalPlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Release validated Work without optional communication as a barrier."""

        fingerprint = canonical_plan_fingerprint(plan)
        planner_response = PlannerResponseProjection(
            projection_id=f"execution_only_{fingerprint[:20]}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan,
            response_plan=ResponsePlan(),
            lane_coordination=[],
            confidence=1.0,
            rationale="Work without a required communication need can proceed independently of SC.",
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

    async def build_social_cognition_response(
        self, *, plan: CanonicalPlan, request: SocialCognitionRequest,
        resolution: SocialCognitionResolution, session_id: str, language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Join exact SC acts to immutable Work; never copy speech into the Plan."""
        resolution.validate_request(request)
        for act in resolution.activities:
            validate_communicative_activity_identity(
                activity_id=act.activity_id, text=act.text,
                interaction_context=(context or request.context).get("interaction_context"),
                repair_of_activity_ids=act.repair_of_activity_ids,
            )
        needs = {need.need_id: need for need in plan.communication_needs}
        responding_goals = {item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"}
        stages = []
        for act in resolution.activities:
            if not act.text.strip():
                continue
            addressed = [needs[key] for key in act.addressed_need_ids]
            kinds = {need.kind for need in addressed}
            completion_goals = sorted({
                goal_id for need in addressed
                if need.kind == "answer" and resolution.need_outcomes[need.need_id] == "covered"
                for goal_id in need.source_goal_ids if goal_id in responding_goals
            })
            confirmation = "confirmation" in kinds
            waiting = confirmation or "input" in kinds
            completion = bool(completion_goals) and not set(act.source_goal_ids).intersection(plan.executable_goal_ids())
            stages.append(ResponseStage(
                text=act.text, delivery_phase=act.delivery_phase,
                speech_act="ask_confirmation" if confirmation else "ask_clarification" if waiting else act.function,
                commitment_state="waiting_for_user" if waiting else "completed" if completion else "none",
                must_not_claim_completion=not (completion and not waiting),
                covers_goal_ids=list(act.source_goal_ids), metadata={
                    "wording_owner": "social_cognition",
                    "communicative_activity_ids": [act.activity_id],
                    "truth_stages": [act.truth_stage],
                    "evidence_refs": list(act.evidence_refs),
                    "addressed_need_ids": list(act.addressed_need_ids),
                    "source_responsibility_refs": list(act.source_responsibility_refs),
                    "communication_completion_goal_ids": completion_goals,
                    "required_before_work": confirmation or any(need.delivery_phase == "pre_action" or need.before_step_ids for need in addressed),
                    "communication_before_step_ids": sorted({key for need in addressed for key in need.before_step_ids}),
                    "communication_after_step_ids": sorted({key for need in addressed for key in need.after_step_ids}),
                },
            ))
        fingerprint = canonical_plan_fingerprint(plan)
        projection = PlannerResponseProjection(
            projection_id=f"sc_{resolution.snapshot_digest[:20]}",
            canonical_plan_id=plan.plan_id, canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan, response_plan=ResponsePlan(activities=stages),
            social_cognition_request=request, social_cognition=resolution,
            metadata={"authority": "social_cognition", "task_plan_immutable": True},
        )
        social_context = _lineage_context(
            dict(context or request.context),
            _social_semantic_lineage(request.semantic_artifact_lineage, resolution),
        )
        response = await self.build_response(
            plan=plan, planner_response=projection, session_id=session_id,
            language=language, context=social_context,
        )
        response.metadata["pending_communication_need_ids"] = [
            key for key, value in resolution.need_outcomes.items() if value == "pending"
        ]
        response.metadata["social_cognition_resolution"] = resolution.model_dump(mode="json")
        if any(act.auxiliary_activities for act in resolution.activities):
            response = await self.prepare_social_response(response, social_cognition=resolution,
                session_id=session_id, turn_id=str(request.source_turn.get("turn_id") or request.request_id),
                context=social_context)
        return response


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
                + len(planner_response.response_plan.progress)
                + len(planner_response.response_plan.activities),
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
        runtime_lineage = _plan_semantic_lineage(
            _semantic_lineage_from_context(runtime_context), plan,
        )
        runtime_context = _lineage_context(runtime_context, runtime_lineage)
        lineage_payload = runtime_lineage.model_dump(mode="json")
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
        speech_prohibited = user_turn_prohibits_speech(envelope)
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
        stage_items = PlannerResponseProjection._stages(response_plan)
        social_response = planner_response.social_cognition is not None
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
            final_items = (
                [("final", response_plan.final)]
                if response_plan.final is not None
                else []
            )
            covered_pre_execution = {
                goal_id for _, stage in available_pre_execution for goal_id in stage.covers_goal_ids
            }
            required_pre_execution_goal_ids = set(covered_pre_execution)

            # A safe, read-only lookup may start immediately without any spoken
            # acknowledgement. If the response model supplied a tiny natural
            # acknowledgement, it is optional and runs in parallel with the lookup.
            # Effectful or confirmation-gated pre-action speech retains the
            # delivery barrier. A Planner-authored final phase remains after Work
            # and is never forced to claim ownership of executable Goals.
            if safe_read_parallel:
                if pre_action_item is not None and required_pre_execution_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [pre_action_item]
                elif immediate_item is not None and required_pre_execution_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [immediate_item]
                else:
                    selected_pre_execution = list(available_pre_execution)
            else:
                if pure_execution_speech_optional:
                    selected_pre_execution = []
                elif pre_action_item is not None and required_pre_execution_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [pre_action_item]
                elif immediate_item is not None and required_pre_execution_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [immediate_item]
                else:
                    selected_pre_execution = list(available_pre_execution)

            stage_items = (PlannerResponseProjection._stages(response_plan) if social_response
                           else [*selected_pre_execution, *final_items])

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
                projected_speech_stages = [
                    {
                        "phase": phase,
                        "text": stage.text,
                        "speech_act": stage.speech_act,
                        "commitment_state": stage.commitment_state,
                        "must_not_claim_completion": (
                            True if phase != "final" else stage.must_not_claim_completion
                        ),
                        "covers_goal_ids": list(stage.covers_goal_ids),
                        "claims": stage.claims,
                        "source": "planner_communicative_activity",
                        "operational_text_source": "planner_wording_runtime_validated",
                        "runtime_confirmation_required": False,
                        "safe_read_micro_ack": (
                            safe_read_speech_optional and phase != "final"
                        ),
                        "coordination_id": stage.coordination_id,
                        "delivery_role": stage.delivery_role,
                        "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                        "reused_speech_event_id": stage.reused_speech_event_id,
                        "communicative_activity_ids": list(
                            (stage.metadata or {}).get("communicative_activity_ids") or []
                        ),
                        "truth_stages": list(
                            (stage.metadata or {}).get("truth_stages") or []
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
                        "truth_stages": list(
                            (stage.metadata or {}).get("truth_stages") or []
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
                    "truth_stages": list(
                        (stage.metadata or {}).get("truth_stages") or []
                    ),
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        if social_response:
            for projected, (_, stage) in zip(projected_speech_stages, stage_items):
                projected.update({
                    "source": "social_cognition", "wording_owner": "social_cognition",
                    "operational_text_source": "social_cognition_wording_runtime_validated",
                    **{key: stage.metadata[key] for key in (
                        "addressed_need_ids", "source_responsibility_refs", "evidence_refs",
                        "communication_completion_goal_ids", "required_before_work",
                        "communication_before_step_ids", "communication_after_step_ids",
                    )},
                })

        if speech_prohibited:
            projected_speech_stages = []

        speech: list[InteractionSpeech] = []
        for projected in projected_speech_stages:
            phase = str(projected["phase"])
            stage_safe_read_parallel = safe_read_parallel and phase != "final"
            coordination_id = str(projected.get("coordination_id") or "").strip()
            coordination = lane_coordination_by_id.get(coordination_id)
            coordinated_speech = bool(coordination is not None and "vocal" in coordination.lanes)
            playback_barrier = (
                projected.get("reuse_current_turn_speech") is True
                or (
                    (phase != "final" or not effectful_pre_execution)
                    and not stage_safe_read_parallel
                    and not coordinated_speech
                )
            )
            if social_response:
                playback_barrier = projected.get("required_before_work") is True or not effectful_pre_execution
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
                "truth_stages": list(projected.get("truth_stages") or []),
                "wait_for_playback_start": playback_barrier,
                "playback_start_required_for_delivery": playback_barrier,
            }
            if social_response:
                speech_metadata.update({key: projected[key] for key in (
                    "wording_owner", "addressed_need_ids", "source_responsibility_refs",
                    "evidence_refs", "communication_completion_goal_ids",
                    "communication_before_step_ids", "communication_after_step_ids",
                )})
            if social_response and (
                projected.get("required_before_work") is True
                or projected.get("communication_before_step_ids")
                or projected.get("communication_after_step_ids")
            ):
                speech_metadata["wait_for_voice_release"] = True
            ordered_context_grounded_after_work = (
                phase == "final"
                and set(speech_metadata["truth_stages"]) == {"context_grounded"}
                and not set(projected.get("covers_goal_ids") or []).intersection(
                    executable_goal_ids
                )
            )
            if ordered_context_grounded_after_work:
                speech_metadata["ordered_context_grounded_after_work"] = True
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
            elif stage_safe_read_parallel:
                speech_metadata.update(
                    {
                        "safe_read_micro_ack": safe_read_speech_optional,
                        "parallel_with_safe_read": True,
                        "playback_start_required_for_effects": False,
                    }
                )
            elif effectful_pre_execution:
                speech_metadata["playback_start_required_for_effects"] = (
                    projected.get("required_before_work") is True if social_response else True
                )
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
                        "after_capabilities"
                        if phase == "final" and effectful_pre_execution
                        else "parallel"
                        if stage_safe_read_parallel or coordinated_speech or (
                            social_response and effectful_pre_execution and not projected.get("required_before_work")
                        )
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
            if speech_prohibited and execution_lane == "vocal":
                raise ValueError("protective silence forbids a vocal Capability in this turn")
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
                        "semantic_artifact_lineage": lineage_payload,
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
                "social_cognition_runtime_validated" if social_response else
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
            "semantic_artifact_lineage": lineage_payload,
        }
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
                "social_cognition_runtime_validated" if social_response else "planner_wording_runtime_validated"
            )
        response = InteractionResponse(
            interaction_id=f"cognitive_{session_id}_{fingerprint[:20]}",
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
        self._auxiliary_execution_tasks: set[asyncio.Task[Any]] = set()
        self._social_turns: dict[str, tuple[str, asyncio.Task[Any]]] = {}
        self._social_dispatches: dict[str, str] = {}

    async def cancel_social_interaction(self) -> None:
        """Deterministic output interruption invalidates pending SC and delivery."""
        tasks = [entry[1] for entry in self._social_turns.values()]
        self._social_turns.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        ids = tuple(self._social_dispatches.values())
        self._social_dispatches.clear()
        for interaction_id in ids:
            await self.adapter.interaction_runtime.runtime.cancel_interaction(interaction_id)

    async def _cancel_social_turn(self, previous: tuple[str, asyncio.Task[Any]] | None) -> None:
        if previous is None:
            return
        request_id, task = previous
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        interaction_id = self._social_dispatches.pop(request_id, None)
        if interaction_id is not None:
            await self.adapter.interaction_runtime.runtime.cancel_interaction(interaction_id)

    def schedule_social_expression(
        self, response: InteractionResponse, *, session_id: str | None,
        context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> None:
        """Realize SC expression after its exact primary response is admitted."""
        if response.metadata.get("social_expression_materialized") is True:
            return
        raw = response.metadata.get("social_cognition_resolution")
        if self.policy.mode != "apply" or not isinstance(raw, dict):
            return
        result = SocialCognitionResolution.model_validate(raw)
        if not any(act.auxiliary_activities for act in result.activities):
            return
        if context is None:
            request_payload = response.metadata.get("social_cognition_request")
            if not isinstance(request_payload, dict):
                projection = response.metadata.get("planner_response_projection")
                request_payload = projection.get("social_cognition_request") if isinstance(projection, dict) else None
            if isinstance(request_payload, dict):
                source_request = SocialCognitionRequest.model_validate(request_payload)
                result.validate_request(source_request)
                context = source_request.context
        task = asyncio.create_task(self.adapter.execute_auxiliary_activities(
            social_cognition=result, interaction=response, session_id=str(session_id or ""),
            turn_id=str(response.metadata.get("turn_id") or result.request_id), context=context or {},
            snapshot_is_current=snapshot_is_current,
        ), name="social-expression:" + result.request_id)
        self._track_auxiliary_execution_task(task)

    def _state_social_request(
        self,
        *,
        work_request: CognitiveWorkRequest,
        turn_id: str,
        plan: CanonicalPlan | None = None,
        work_decision_pending: bool | None = None,
    ) -> SocialCognitionRequest:
        sid = str(work_request.sid or "")
        social_context = dict(work_request.context)
        if plan is not None:
            social_context = _lineage_context(
                social_context,
                _plan_semantic_lineage(
                    _semantic_lineage_from_context(social_context), plan,
                ),
            )
        pending = plan is None if work_decision_pending is None else work_decision_pending
        return SocialCognitionRequest(
            request_id="sc:" + hashlib.sha256(("plan:" + plan.plan_id if plan is not None else "umi:" + turn_id).encode("utf-8")).hexdigest(),
            trigger="work_state" if plan is not None else "interpretation",
            source_refs=[plan.plan_id] if plan is not None else [turn_id],
            goal_ids=list(plan.goal_ids) if plan is not None else [],
            language=work_request.language or "auto",
            responsibilities=list(work_request.responsibilities),
            meaning_uncertainties=list(work_request.meaning_uncertainties),
            source_turn=work_request.source_turn_provenance,
            context=ContextAssembly.project_context({
                **social_context, "work_decision_pending": pending,
                **({"canonical_plan_resolution": plan.prompt_projection(), "runtime_admission": "pending"} if plan is not None else {}),
                "history": list(work_request.history),
                "interaction_context": self._interaction_context(sid=sid, context=social_context),
            }),
        )

    def start_state_interaction(
        self, session: Any, *, work_request: CognitiveWorkRequest, turn_id: str,
        plan: CanonicalPlan | None = None,
    ) -> asyncio.Task[Any] | None:
        """Let a new UMI or committed Plan state invite SC without holding Work."""
        if self.policy.mode != "apply" or user_turn_prohibits_speech(work_request.context.get("user_turn_envelope")):
            return None
        sid = str(work_request.sid or "")
        key = self._goal_association_lock_key(work_request.context, sid)
        previous = self._social_turns.get(key)
        if previous is not None:
            previous[1].cancel()
        request = self._state_social_request(
            work_request=work_request, turn_id=turn_id, plan=plan,
        )
        def current() -> bool:
            entry = self._social_turns.get(key)
            return entry is not None and entry[0] == request.request_id
        async def run() -> None:
            await self._cancel_social_turn(previous)
            if not current():
                return
            resolved = await self.resolve_social_interaction(
                session, request=request, session_id=sid, snapshot_is_current=current,
            )
            if resolved is None or not current():
                return
            result, response = resolved
            runtime_dispatch = None
            if response.speech or response.capabilities:
                self._social_dispatches[request.request_id] = response.interaction_id
                runtime_dispatch = await self.adapter.interaction_runtime.submit_response(response, session_id=sid)
            if current():
                self.schedule_social_expression(response, session_id=sid, context=request.context, snapshot_is_current=current)
            if runtime_dispatch is not None:
                execution = await self.adapter.interaction_runtime.wait_dispatch(runtime_dispatch)
                await self.adapter.interaction_runtime.record_social_delivery(response, execution, session_id=sid)
                self._social_dispatches.pop(request.request_id, None)
                response.metadata["presentation_already_dispatched"] = True
            return result, response
        task = asyncio.create_task(run(), name="social-interpretation:" + turn_id)
        self._social_turns[key] = (request.request_id, task)
        self._track_auxiliary_execution_task(task)
        return task

    async def resolve_plan_interaction(
        self, session: Any, *, plan: CanonicalPlan, work_request: CognitiveWorkRequest,
        session_id: str, language: str, context: dict[str, Any],
        evidence_refs: list[str] | None = None,
    ) -> InteractionResponse:
        """Let SC fulfill established needs without a second Work judgment."""
        if plan.response_text or plan.communicative_acts or plan.auxiliary_activities or any(
            outcome.response_text for outcome in plan.goal_outcomes
        ):
            raise ValueError("SC cannot review or rewrite a Planner-authored communicative decision")
        key = self._goal_association_lock_key(context, session_id)
        previous = self._social_turns.pop(key, None)
        await self._cancel_social_turn(previous)
        source_context = ContextAssembly.project_context(context)
        source_context = _lineage_context(
            source_context,
            _plan_semantic_lineage(
                _semantic_lineage_from_context(source_context), plan,
            ),
        )
        # The delivery ledger distinguishes queued/started/completed speech.
        # Do not retain the retired, ambiguously named Planner history alias.
        source_context.pop("delivered_turn_speech", None)
        if source_context.get("canonical_plan_resolution"):
            source_context["source_canonical_plan"] = source_context["canonical_plan_resolution"]
        source_context["canonical_plan_resolution"] = plan.prompt_projection()
        source_context["interaction_context"] = self._interaction_context(
            sid=session_id, context=context, goal_ids=plan.goal_ids,
        )
        request = SocialCognitionRequest(
            request_id="sc:" + hashlib.sha256(plan.plan_id.encode("utf-8")).hexdigest(), trigger="evidence" if evidence_refs else "work_state",
            source_refs=[plan.plan_id, *(evidence_refs or [])], goal_ids=list(plan.goal_ids),
            language=language, responsibilities=list(work_request.responsibilities),
            meaning_uncertainties=list(work_request.meaning_uncertainties),
            source_turn=work_request.source_turn_provenance,
            evidence_refs=list(evidence_refs or []), communication_needs=list(plan.communication_needs),
            context=source_context,
        ).model_copy(deep=True)
        result = await self._observe_workflow_stage(
            sid=session_id, stage="social_cognition", input_payload=request,
            operation=self.agent_client.resolve_social_cognition(
                session, request=request,
                timeout_ms=max(self.policy.fast_planner_timeout_ms, self.policy.deep_planner_timeout_ms),
            ),
        )
        result.validate_request(request)
        current_interaction = self._interaction_context(sid=session_id, context=context, goal_ids=plan.goal_ids)
        for act in result.activities:
            validate_communicative_activity_identity(
                activity_id=act.activity_id, text=act.text, interaction_context=current_interaction,
                repair_of_activity_ids=act.repair_of_activity_ids,
            )
        return await self.adapter.build_social_cognition_response(
            plan=plan, request=request, resolution=result, session_id=session_id,
            language=language, context=source_context,
        )

    async def resolve_social_interaction(
        self, session: Any, *, request: SocialCognitionRequest,
        session_id: str, snapshot_is_current: Callable[[], bool],
    ) -> tuple[SocialCognitionResolution, InteractionResponse] | None:
        """Resolve trusted state into interaction without creating task Work.

        The calling state owner supplies its exact revision predicate. This
        makes the same transaction usable after UMI, GA, Work, Evidence or a
        perception change without interpreting event names as social decisions.
        """
        if self.policy.mode == "off" or not snapshot_is_current():
            return None
        request = request.model_copy(deep=True)
        metadata = {"semantic_owner": "social_cognition", "trigger": request.trigger,
                    "execution_authority": False}
        logger.info("social_cognition_start sid=%s request_id=%s trigger=%s",
                    session_id, request.request_id, request.trigger)
        async def resolve() -> SocialCognitionResolution:
            result = await self.agent_client.resolve_social_cognition(
                session, request=request,
                timeout_ms=max(self.policy.fast_planner_timeout_ms, self.policy.deep_planner_timeout_ms),
            )
            result.validate_request(request)
            metadata["model_call_count"] = result.model_call_count
            return result
        result = await self._observe_workflow_stage(
            sid=session_id, stage="social_cognition", input_payload=request,
            operation=resolve(), metadata=metadata,
            status_resolver=lambda _: "resolved" if snapshot_is_current() else "stale",
        )
        current = snapshot_is_current()
        if not current:
            return None
        interaction_context = (
            self.interaction_ledger.context(session_id, goal_ids=request.goal_ids,
                                            turn_id=str(request.source_turn.get("turn_id") or request.request_id)).model_dump(mode="json")
            if self.interaction_ledger is not None else request.context.get("interaction_context")
        )
        response = build_social_interaction_response(
            request, result, session_id=session_id, interaction_context=interaction_context,
        )
        social_lineage = _social_semantic_lineage(request.semantic_artifact_lineage, result)
        lineage_payload = social_lineage.model_dump(mode="json")
        response.metadata["semantic_artifact_lineage"] = lineage_payload
        for speech in response.speech:
            speech.metadata["semantic_artifact_lineage"] = lineage_payload
        for capability in response.capabilities:
            capability.metadata["semantic_artifact_lineage"] = lineage_payload
        if any(act.auxiliary_activities for act in result.activities):
            response = await self.adapter.prepare_social_response(response, social_cognition=result,
                session_id=session_id, turn_id=str(request.source_turn.get("turn_id") or request.request_id),
                context=request.context, snapshot_is_current=snapshot_is_current)
        logger.info(
            "social_cognition_done sid=%s request_id=%s disposition=%s activities=%d "
            "speech=%d capabilities=%d reason=%r",
            session_id,
            request.request_id,
            result.disposition,
            len(result.activities),
            len(response.speech),
            len(response.capabilities),
            result.reason_summary,
        )
        return result, response

    def _track_auxiliary_execution_task(self, task: asyncio.Task[Any]) -> None:
        """Retain fail-soft Runtime execution without creating cognition work."""

        self._auxiliary_execution_tasks.add(task)

        def _done(completed: asyncio.Task[Any]) -> None:
            self._auxiliary_execution_tasks.discard(completed)
            if completed.cancelled():
                return
            exc = completed.exception()
            if exc is not None:  # pragma: no cover - task visibility guard
                logger.warning(
                    "auxiliary Activity execution failed task=%s error_type=%s error=%s",
                    completed.get_name(),
                    type(exc).__name__,
                    exc,
                )

        task.add_done_callback(_done)



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
            "goal_association_candidates",
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
        status_resolver: Callable[[Any], str] | None = None,
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
            status=status_resolver(output) if status_resolver else self._workflow_output_status(output),
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
        payload = projection.model_dump(mode="json")

        # The append-only ledger is session-scoped, while ordinary dialogue
        # continuity spans several session/turn IDs inside one Conversation.
        # ConversationState already retains exact communicative text only after
        # delivery completed. Preserve those prior-turn facts for identity/repair
        # and contextual reasoning, but never put them in current-turn
        # ``already_spoken``: SC uses that surface to decide whether THIS addressed
        # turn already received a reply. Never project generic agent_result history;
        # authored or scheduled text is not delivery evidence.
        prior_delivered: list[dict[str, Any]] = []
        for turn in list(context.get("history") or [])[-16:]:
            if not isinstance(turn, dict) or turn.get("role") != "assistant":
                continue
            metadata = turn.get("metadata")
            if not isinstance(metadata, dict) or metadata.get("source") not in {
                "fast_planner_communicative_delivery", "social_cognition_communicative_delivery",
            }:
                continue
            text = " ".join(str(turn.get("text") or "").strip().split())
            if not text:
                continue
            turn_id = " ".join(
                str(metadata.get("turn_id") or turn.get("sid") or "").strip().split()
            )
            activity_id = " ".join(
                str(metadata.get("fast_activity_id") or next(iter(metadata.get("communicative_activity_ids") or []), "")).strip().split()
            )
            identity = hashlib.sha256(
                json.dumps(
                    [turn_id, activity_id, text],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:24]
            prior_delivered.append(
                {
                    "event_id": f"conversation_speech_{identity}",
                    "turn_id": turn_id,
                    "owner": "playback_delivery",
                    "domain": "vocal",
                    "event_type": "speech_playback_completed",
                    "state": "playback_completed",
                    "goal_ids": list(metadata.get("source_goal_ids") or []),
                    "subject_id": activity_id or f"speech_{identity}",
                    "speech_act": str(metadata.get("speech_act") or ""),
                    "text": text,
                    "evidence_refs": list(metadata.get("evidence_refs") or []),
                    "metadata": {
                        "delivery_role": str(
                            metadata.get("delivery_role") or ""
                        ),
                        "source": metadata["source"],
                        "wording_owner": metadata.get("wording_owner"),
                        "communicative_activity_ids": list(metadata.get("communicative_activity_ids") or []),
                        "addressed_need_ids": list(metadata.get("addressed_need_ids") or []),
                        "source_responsibility_refs": list(metadata.get("source_responsibility_refs") or []),
                    },
                }
            )

        current_turn_id = self._context_turn_id(context, sid)
        ledger_spoken = [
            item
            for item in list(payload.get("already_spoken") or [])
            if isinstance(item, dict)
        ]
        payload["already_spoken"] = [
            item
            for item in ledger_spoken
            if not current_turn_id
            or str(item.get("turn_id") or "") == current_turn_id
        ][-16:]
        historical = [
            item
            for item in [*ledger_spoken, *prior_delivered]
            if current_turn_id
            and str(item.get("turn_id") or "") != current_turn_id
        ]
        deduplicated_history: list[dict[str, Any]] = []
        history_keys: set[tuple[str, str, str]] = set()
        for item in historical:
            key = (
                str(item.get("turn_id") or ""),
                str(item.get("subject_id") or ""),
                str(item.get("text") or ""),
            )
            if key in history_keys:
                continue
            history_keys.add(key)
            deduplicated_history.append(item)
        payload["prior_delivered_speech"] = deduplicated_history[-16:]
        return payload


    @staticmethod
    def _cognitive_request_responsibility_refs(
        request: CognitiveWorkRequest, authority: str,
    ) -> list[str]:
        """Return exact UMI-authored activation scope for one cognitive owner.

        Runtime validates and schedules this already-authored request; it does not
        recreate cognitive readiness from output_mode, continuity_scope, bindings,
        keywords, or task classes.
        """

        known = [item.local_ref for item in request.responsibilities]
        known_set = set(known)
        activation = next(
            (item for item in request.cognitive_requests if item.authority == authority),
            None,
        )
        if activation is None:
            return []
        unknown = set(activation.responsibility_refs) - known_set
        if unknown:
            raise ValueError(
                f"cognitive activation authority={authority} references unknown Responsibilities: "
                + ",".join(sorted(unknown))
            )
        selected = set(activation.responsibility_refs)
        return [ref for ref in known if ref in selected]

    @staticmethod
    def _no_interaction_response(*, sid: str, reason: str) -> InteractionResponse:
        """Represent a model-authored decision not to wake SC without inventing speech."""

        return InteractionResponse(
            interaction_id=f"cognitive_{sid}_no_interaction",
            status="ok",
            metadata={
                "source": "model_driven_cognitive_orchestration",
                "social_cognition_requested": False,
                "reason": reason,
            },
        )

    @staticmethod
    def _subset_work_request(
        request: CognitiveWorkRequest, responsibility_refs: set[str],
    ) -> CognitiveWorkRequest:
        """Project one Responsibility-closed Planner input without reauthoring meaning."""

        return request.model_copy(
            deep=True,
            update={
                "responsibilities": [
                    item
                    for item in request.responsibilities
                    if item.local_ref in responsibility_refs
                ],
                "meaning_uncertainties": [
                    item
                    for item in request.meaning_uncertainties
                    if set(item.responsibility_refs).issubset(responsibility_refs)
                ],
            },
        )

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
    def _remaining_meaning_uncertainties(
        request: CognitiveWorkRequest,
        association: GoalAssociationResolution,
    ) -> list[Any]:
        """Return UMI uncertainties not resolved by canonical Goal continuity.

        GA may resolve an uncertainty only through its validated association output.
        Everything else remains visible to Planner/SC; absence from the current
        utterance is never treated as unresolved once canonical Goal continuity
        actually supplies the missing meaning.
        """

        resolved_refs = {
            ref
            for item in association.associations
            for ref in item.resolved_meaning_uncertainty_refs
        }
        return [
            item
            for item in request.meaning_uncertainties
            if item.local_ref not in resolved_refs
        ]

    @staticmethod
    def _goal_ids_by_responsibility(
        association: GoalAssociationResolution,
    ) -> dict[str, list[str]]:
        """Resolve the GA-owned Goal identity for every UMI Responsibility.

        Fast Planner is allowed to plan before Goal Association finishes, so its
        Activities carry UMI-local Responsibility references.  This is the single
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
        retained_goals: list[dict[str, Any]] | None = None,
    ) -> CanonicalPlan:
        """Bind Fast Planner's first Activity Plan to GA's canonical Goals."""

        if advance.disposition == "escalate":
            raise ValueError(
                "escalating Fast Planner advance cannot become a terminal canonical Plan"
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
        has_argument_sources = any(
            isinstance(activity, FastPlannerCapabilityActivity) and activity.argument_sources
            for activity in advance.activities
        )
        if retained_goals is not None and has_argument_sources:
            consistent_retained_ids: set[str] = set()
            for snapshot in retained_goals:
                if not isinstance(snapshot, dict):
                    continue
                snapshot_id = str(snapshot.get("goal_id") or "").strip()
                for key in ("goal", "semantic_goal"):
                    goal_payload = snapshot.get(key)
                    if (
                        snapshot_id
                        and isinstance(goal_payload, dict)
                        and str(goal_payload.get("goal_id") or "").strip() == snapshot_id
                    ):
                        consistent_retained_ids.add(snapshot_id)
                        break
            new_goal_ids = {goal.goal_id for goal in association.new_goals}
            missing_retained = sorted(set(goal_ids) - new_goal_ids - consistent_retained_ids)
            if missing_retained:
                raise ValueError(
                    "Fast argument source has no exact canonical Goal owner: inconsistent retained Goal snapshot: "
                    + ",".join(missing_retained)
                )
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

        parameter_resolutions = [
            PlanParameterResolution(
                step_id=activity.activity_id, parameter=parameter,
                strategy="semantic_realization", value=activity.args[parameter],
                source_quote=resolve_user_turn_source_span(user_text, span),
                confidence=advance.confidence,
                source_goal_ids=list(dict.fromkeys(
                    goal_id for ref in activity.source_responsibility_refs
                    for goal_id in refs_to_goals[ref]
                )),
            )
            for activity in advance.activities if isinstance(activity, FastPlannerCapabilityActivity)
            for parameter, span in activity.argument_sources.items()
        ]
        if any(not item.source_goal_ids for item in parameter_resolutions):
            raise ValueError("Fast argument source has no canonical Goal owner")

        outcomes: list[Any] = []
        unresolved = list(advance.unresolved)
        plan_seed = json.dumps(advance.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        plan_id = "fast_activity_plan_" + hashlib.sha256(plan_seed.encode()).hexdigest()[:20]
        needs: list[SocialCommunicationNeed] = []
        capability_indexes = [index for index, item in enumerate(advance.activities) if item.role == "capability"]
        for index, activity in enumerate(advance.activities):
            if activity.role == "capability":
                continue
            activity_goal_ids = list(dict.fromkeys(goal_id for ref in activity.source_responsibility_refs
                                                   for goal_id in refs_to_goals[ref]))
            # This preserves the validated ordered Work obligation. SC supplies
            # words later without moving that obligation across task Activities.
            phase = ("final" if capability_indexes and index > max(capability_indexes)
                     else "immediate" if capability_indexes and index > min(capability_indexes)
                     else "pre_action" if capability_indexes else "immediate") if activity.timing == "sequential" else "immediate"
            needs.append(SocialCommunicationNeed(
                need_id=communication_need_id(plan_id, activity.activity_id), owner="planner",
                kind="input" if activity.role == "clarification" else "answer",
                source_goal_ids=activity_goal_ids, source_responsibility_refs=list(activity.source_responsibility_refs),
                reference_id=plan_id, delivery_phase=phase, facts=activity.model_dump(mode="json"),
                before_step_ids=[item.activity_id for item in advance.activities[index+1:] if item.role == "capability"] if activity.timing == "sequential" else [],
                after_step_ids=[item.activity_id for item in advance.activities[:index] if item.role == "capability"] if activity.timing == "sequential" else [],
            ))
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
                    rationale="Fast Planner established an ordinary answer obligation.",
                )
                outcomes.append(
                    RespondGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="respond",
                        coverage="complete",
                        satisfaction=satisfaction,
                        rationale="No Capability Evidence is required for this Goal.",
                    )
                )
            elif advance.disposition == "unavailable":
                outcomes.append(
                    UnavailableGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="unavailable",
                        coverage=advance.coverage,
                        unresolved=unresolved,
                        rationale=(
                            advance.reason_summary
                            or "Fast Planner found no currently available way to satisfy this Goal."
                        ),
                    )
                )
            elif advance.disposition == "refused":
                outcomes.append(
                    RefusedGoalPlanOutcome(
                        goal_id=goal_id,
                        disposition="refused",
                        coverage=advance.coverage,
                        unresolved=unresolved,
                        rationale=(
                            advance.reason_summary
                            or "Fast Planner refused this Goal without executable Work."
                        ),
                    )
                )
            else:
                raise ValueError(
                    f"Fast Planner supplied no terminal Activity for Goal {goal_id!r}"
                )

        for outcome in outcomes:
            if outcome.disposition in {"unavailable", "refused"}:
                needs.append(SocialCommunicationNeed(
                    need_id=communication_need_id(plan_id, outcome.goal_id),
                    owner="planner", kind="result", reference_id=plan_id,
                    source_goal_ids=[outcome.goal_id],
                    source_responsibility_refs=[
                        ref for ref, ids in refs_to_goals.items() if outcome.goal_id in ids
                    ],
                    facts=outcome.model_dump(mode="json", exclude_none=True),
                ))
        dispositions = {item.disposition for item in outcomes}
        disposition = (
            next(iter(dispositions)) if len(dispositions) == 1 else "mixed"
        )
        top_coverage = (
            advance.coverage
            if disposition in {"clarify", "unavailable", "refused"}
            else "complete"
        )
        plan_seed = json.dumps(
            advance.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        global_satisfaction = None
        if dispositions.issubset({"execute", "respond"}):
            global_satisfaction = GoalSatisfactionAssessment(
                score=max(0.95, advance.confidence),
                status="exact",
                satisfied_goal_ids=goal_ids,
                rationale="Every canonical Goal has a complete Fast Planner outcome.",
            )
        return CanonicalPlan(
            plan_id=plan_id,
            planner_tier="fast",
            disposition=disposition,
            coverage=top_coverage,
            confidence=advance.confidence,
            goal_ids=goal_ids,
            goal_summary=user_text,
            communication_needs=needs,
            parameter_resolutions=parameter_resolutions,
            steps=steps,
            unresolved=(
                unresolved
                if disposition in {"clarify", "mixed", "unavailable", "refused"}
                else []
            ),
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
        already-started safe Work when a selected Activity's exact identity matches.
        Omitted Activities continue unchanged; cancellation must be explicit.
        Extra newly planned steps are allowed.
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
            if not candidates and activity.activity_id not in {step.reuse_activity_id for step in plan.steps}:
                continue
            if len(candidates) != 1:
                raise ValueError("Planner reuse changes provisional Work identity")
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

    @staticmethod
    def _validate_work_change_selection(plan: CanonicalPlan, activities: list[dict[str, Any]]) -> None:
        by_id = {str(item.get("activity_id") or ""): item for item in activities}
        if len(by_id) != len(activities):
            raise ValueError("ambiguous existing Work identity")
        if set(plan.cancel_activity_ids) - set(by_id):
            raise ValueError("Planner cancellation names unknown Work")
        for step in plan.steps:
            if not step.reuse_activity_id:
                continue
            activity = by_id.get(step.reuse_activity_id)
            if activity is None:
                raise ValueError("Planner reuse names unknown Work")
            if any(getattr(step, key) != activity.get(key) for key in ("capability_id", "args", "timing")):
                raise ValueError("Planner reuse changes immutable Work identity")
            if set(step.source_goal_ids) != set(activity.get("source_goal_ids") or []):
                raise ValueError("Planner reuse changes shared Work Goal ownership")
        for activity_id in plan.cancel_activity_ids:
            if not set(by_id[activity_id].get("source_goal_ids") or []).issubset(plan.goal_ids):
                raise ValueError("Planner cancellation exceeds shared Work Goal ownership")

    async def _apply_retained_work_reconciliation(
        self,
        *,
        plan: CanonicalPlan,
        activities: list[dict[str, Any]],
        turn_id: str,
    ) -> tuple[CanonicalPlan, str]:
        """Apply only explicit, scope-bound Planner changes to existing Work.

        Omitted Work is unchanged. Reuse may coexist with new steps. A cancellation
        names exact requests and must close before replacement can dispatch.
        """

        self._validate_work_change_selection(plan, activities)
        retained_by_id = {
            str(item.get("activity_id") or ""): item
            for item in activities if item.get("origin") == "retained_runtime"
        }
        if not retained_by_id:
            return plan, "not_applicable"
        selected = {
            step.reuse_activity_id: step for step in plan.steps
            if step.reuse_activity_id in retained_by_id
        }
        cancelled = set(plan.cancel_activity_ids).intersection(retained_by_id)
        if cancelled.intersection(selected):
            raise ValueError("one Activity cannot be both reused and cancelled")
        checked = set(selected) | cancelled
        live_by_id: dict[str, dict[str, Any]] = {}
        for activity_id in sorted(checked):
            activity = retained_by_id[activity_id]
            runtime_binding = activity.get("runtime_binding")
            if not isinstance(runtime_binding, dict):
                raise ValueError("retained Work lacks trusted runtime binding")
            if not set(activity.get("source_goal_ids") or []).issubset(plan.goal_ids):
                raise ValueError("Planner change exceeds shared Work Goal ownership")
            live = await self.adapter.interaction_runtime.reusable_request_snapshot(
                interaction_id=str(runtime_binding.get("interaction_id") or ""),
                request_id=activity_id,
            )
            if live is None or any(
                live.get(key) != activity.get(key)
                for key in ("capability_id", "args", "timing")
            ) or set(live.get("source_goal_ids") or []) != set(activity.get("source_goal_ids") or []) or any(
                live.get(key) != runtime_binding.get(key)
                for key in ("canonical_plan_id", "canonical_plan_fingerprint")
            ):
                raise CognitiveStageFailure("work_reconciliation", {
                    "failure_class": "retained_work_identity_changed",
                    "failure_domain": "runtime_state",
                    "architecture_attribution": "capability_runtime",
                    "retryable": False,
                    "request_id": activity_id,
                })
            if activity_id in selected and live.get("state") in {"cancelled", "failed", "refused", "timed_out"}:
                raise ValueError("failed terminal Work cannot be reused as successful planned Work")
            live_by_id[activity_id] = live

        updated_steps = []
        for step in plan.steps:
            activity = retained_by_id.get(step.reuse_activity_id)
            if activity is None:
                updated_steps.append(step)
                continue
            if any(getattr(step, key) != activity.get(key) for key in ("capability_id", "args", "timing")) or set(step.source_goal_ids) != set(activity.get("source_goal_ids") or []):
                raise ValueError("Planner reuse changes immutable Work identity")
            updated_steps.append(step.model_copy(deep=True, update={"metadata": {
                **step.metadata,
                "request_id": step.reuse_activity_id,
                "retained_work_reused": True,
                "retained_request_id": step.reuse_activity_id,
                "retained_runtime_state": live_by_id[step.reuse_activity_id]["state"],
            }}))

        grouped: dict[tuple[str, str, str], dict[str, set[str]]] = {}
        for activity_id in cancelled:
            if live_by_id[activity_id].get("state") in {"completed", "cancelled", "failed", "refused", "timed_out"}:
                continue  # Preserve terminal Evidence; there is no remaining execution to cancel.
            activity = retained_by_id[activity_id]
            binding = activity["runtime_binding"]
            key = (str(binding["interaction_id"]), str(binding["canonical_plan_id"]), str(binding["canonical_plan_fingerprint"]))
            group = grouped.setdefault(key, {"goal_ids": set(), "request_ids": set()})
            group["goal_ids"].update(activity.get("source_goal_ids") or [])
            group["request_ids"].add(activity_id)
        for (interaction_id, plan_id, fingerprint), group in grouped.items():
            receipt = await self.adapter.interaction_runtime.cancel_scope(CancellationDirective(
                source_turn_id=turn_id,
                requested_scope="specific_goal",
                foreground_interaction_id=interaction_id,
                target_goal_ids=tuple(sorted(group["goal_ids"])),
                target_request_ids=tuple(sorted(group["request_ids"])),
                expected_plan_id=plan_id,
                expected_plan_fingerprint=fingerprint,
                reason="Planner explicitly cancelled retained Work",
            ))
            actual = {item.request_id for item in receipt.selected_request_bindings}
            if actual != group["request_ids"] or receipt.stale_binding_request_bindings or receipt.shared_owner_conflict_request_bindings or receipt.non_interruptible_request_bindings or receipt.provider_cancel_failure_evidence or receipt.dispatch_failures:
                raise CognitiveStageFailure("work_reconciliation", {
                    "failure_class": "retained_work_cancellation_not_closed",
                    "failure_domain": "runtime_state",
                    "architecture_attribution": "capability_runtime",
                    "retryable": False,
                    "interaction_id": interaction_id,
                })
        return plan.model_copy(deep=True, update={
            "steps": updated_steps,
            "metadata": {
                **plan.metadata,
                "retained_work_reconciliation_only": bool(selected) and len(selected) == len(plan.steps),
            },
        }), "retained_work_delta_applied" if cancelled else "retained_work_reused" if selected else "retained_work_unchanged"

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
            association_lineage = _association_semantic_lineage(
                work_request.semantic_artifact_lineage, association,
            )
            context = _lineage_context(context, association_lineage)
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
            has_goal_state_operation = bool(
                association.associations
                or association.new_goals
                or association.referent_updates
            )
            goal_state_results: list[dict[str, Any]] = []
            goal_state_commit_stage = ""
            if self.policy.mode == "apply" and self.goal_state_apply is not None:
                if not has_goal_state_operation:
                    goal_state_commit_stage = "non_goal"
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

        # Goal facts can wake their own planning call while the UMI-triggered
        # Planner is still running. No candidate Plan is passed for review.
        context, history = self._refresh_continuity_context(context=context, sid=sid)
        context = _lineage_context(context, association_lineage)
        remaining_meaning_uncertainties = self._remaining_meaning_uncertainties(
            work_request, association
        )
        mapping = self._goal_ids_by_responsibility(association)
        goal_responsibility_refs = set(mapping)
        planning_work_request = (
            self._subset_work_request(work_request, goal_responsibility_refs)
            if goal_responsibility_refs
            else None
        )
        planning_context = {
            **context,
            "goal_association_resolution": association.prompt_projection(),
            "meaning_uncertainty_resolution": {
                "before_ga": [
                    item.model_dump(mode="json")
                    for item in work_request.meaning_uncertainties
                ],
                "after_ga": [
                    item.model_dump(mode="json")
                    for item in remaining_meaning_uncertainties
                ],
            },
        }
        goal_ids = self._association_goal_ids(association)
        runtime = self.adapter.interaction_runtime.runtime
        for item in context.get("active_goal_snapshots") or []:
            if isinstance(item, dict) and item.get("goal_id") in goal_ids:
                runtime.record_goal_state(str(item["goal_id"]), item)
        for goal in association.new_goals:
            runtime.record_goal_state(goal.goal_id, goal.model_dump(mode="json"))
        retained = self._retained_existing_work_activities(
            context=planning_context,
            goal_ids={*goal_ids, *(old for goal in association.new_goals for old in goal.supersedes_goal_ids)},
        )
        await runtime.bind_prepared_planner_work(turn_id, mapping)
        planning_snapshot = await runtime.planning_state_snapshot(list({*goal_ids, *(old for goal in association.new_goals for old in goal.supersedes_goal_ids)}), turn_id)
        actual_work = runtime.planning_work_activities(planning_snapshot)
        by_id = {item["activity_id"]: item for item in retained}
        by_id.update({item["activity_id"]: item for item in actual_work})
        retained = [item for item in by_id.values() if item["origin"] == "retained_runtime"]
        planning_context["existing_work_activities"] = list(by_id.values())
        planning_context["interaction_context"] = self._interaction_context(sid=sid, context=planning_context, goal_ids=goal_ids)
        planning_task = None
        if planning_work_request is not None and not has_named_goal_cancellation and (
            retained or any(item.get("turn_id") != turn_id for item in actual_work if item.get("origin") == "provisional_fast")
            or has_goal_replacement or any(item.goal_update for item in association.associations)
        ):
            planning_context["canonical_fast_revision_reason"] = "goal_state_planning"
            planning_task = asyncio.create_task(self._observe_workflow_stage(
                sid=sid,
                stage="fast_planner",
                input_payload={"goal_association": association, "trigger": "goal_association", "existing_work_activities": planning_context["existing_work_activities"]},
                operation=self.agent_client.resolve_fast_plan(
                    session,
                    request=planning_work_request.model_copy(deep=True, update={
                        "planning_task_id": "ga:" + goal_association_fingerprint(association),
                        "context": planning_context,
                        "history": history,
                    }),
                    timeout_ms=self.policy.fast_planner_timeout_ms,
                ),
            ), name="goal-planning:" + turn_id)

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
            planning_task=planning_task,
            planning_snapshot=planning_snapshot,
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
        context["recent_auxiliary_behavior_evidence"] = (
            self.adapter.recent_auxiliary_behavior_evidence(sid)
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
            context = _lineage_context(
                context,
                _core_semantic_lineage(
                    turn_envelope=turn_envelope,
                    core_interpretation=core_interpretation,
                ),
            )
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
            meaning_uncertainties=list(core_interpretation.meaning_uncertainties),
            cognitive_requests=list(core_interpretation.cognitive_requests),
            context=context,
            history=history,
        )

        def attach_core_identity(
            resolution: CognitiveRuntimeResolution,
        ) -> CognitiveRuntimeResolution:
            if core_interpretation is None:
                return resolution
            interpretation_payload = core_interpretation.model_dump(mode="json")
            metadata = dict(resolution.metadata)
            metadata["core_interpretation"] = interpretation_payload
            interaction = resolution.interaction_response
            if interaction is not None:
                interaction_metadata = dict(interaction.metadata)
                # The InteractionResponse is the immutable source correlation
                # retained through asynchronous Runtime completion. Re-entry
                # policy consumes this exact UMI provenance; without it, a valid
                # terminal result cannot be mapped back to its Responsibility
                # and must fail closed as missing_responsibility_provenance.
                interaction_metadata["user_meaning_interpretation"] = interpretation_payload
                interaction = interaction.model_copy(
                    update={"metadata": interaction_metadata}
                )
            return resolution.model_copy(
                update={
                    "metadata": metadata,
                    "interaction_response": interaction,
                }
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
        fast_plan: CanonicalPlan | None = None
        terminal_plan: CanonicalPlan | None = None
        interaction: InteractionResponse | None = None
        goal_state_results: list[dict[str, Any]] = []
        goal_state_commit_stage = ""
        stage_diagnostics: list[dict[str, Any]] = []
        fast_planner_path = ""
        deep_planner_invocation_reasons: list[str] = []
        needs_deep_planner = False
        association_task: asyncio.Task[_GoalAssociationStageResult] | None = None
        umi_planning_task: asyncio.Task[None] | None = None
        umi_planning_superseded = False
        planning_snapshot: dict[str, Any] | None = None
        planning_commit: dict[str, Any] | None = None
        initial_social_task: asyncio.Task[Any] | None = None
        initial_meaning_uncertainty_count = len(work_request.meaning_uncertainties)
        post_ga_meaning_uncertainty_count = initial_meaning_uncertainty_count
        planner_waited_for_goal_continuity = False

        def goal_planning_started() -> bool:
            return bool(association_task is not None and association_task.done()
                and not association_task.cancelled() and association_task.exception() is None
                and association_task.result().planning_task is not None)
        fast_vocal_activity_ids: list[str] = []
        ready_fast_communicative_executions: list[Any] = []
        fast_communicative_realization_status = "not_started"
        ready_fast_capability_execution: Any | None = None
        ready_fast_capability_status = "not_started"
        retained_work_activities: list[dict[str, Any]] = []
        retained_work_reconciliation_status = "not_applicable"
        work_reconciliation_required = False
        work_reconciliation_activity_count = 0

        def path_metadata() -> dict[str, Any]:
            first_deep_reason = (
                deep_planner_invocation_reasons[0] if deep_planner_invocation_reasons else ""
            )
            return {
                "social_cognition_started": initial_social_task is not None,
                "model_driven_cognitive_orchestration": True,
                "requested_cognitive_authorities": [
                    item.authority for item in work_request.cognitive_requests
                ],
                "fast_planner_advance": (
                    fast_advance.model_dump(mode="json", exclude_none=True)
                    if fast_advance is not None
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
                "fast_capability_activity_status": ready_fast_capability_status,
                "retained_work_reconciliation_status": (
                    retained_work_reconciliation_status
                ),
                "work_reconciliation_required": work_reconciliation_required,
                "work_reconciliation_activity_count": (
                    work_reconciliation_activity_count
                ),
                "umi_fanout_concurrent": not planner_waited_for_goal_continuity,
                "planner_waited_for_goal_continuity": (
                    planner_waited_for_goal_continuity
                ),
                "meaning_uncertainty_count_at_umi": (
                    initial_meaning_uncertainty_count
                ),
                "meaning_uncertainty_count_after_ga": (
                    post_ga_meaning_uncertainty_count
                ),
                "umi_planning_superseded": umi_planning_superseded,
                "independent_goal_planning": goal_planning_started(),
                "planning_commit": planning_commit,
                "retained_work_activities": [item for item in retained_work_activities
                    if terminal_plan is not None and item["activity_id"] not in terminal_plan.cancel_activity_ids],
                "goal_grouped_task_list": True,
            }

        async def cancel_uncommitted_fast_work(reason: str) -> None:
            """Stop unfinished fan-out while retaining any completed GA truth."""

            nonlocal ready_fast_capability_status
            nonlocal association, context, history, planning_context, situation
            nonlocal goal_state_results, goal_state_commit_stage
            nonlocal has_named_goal_cancellation, has_goal_replacement
            if umi_planning_task is not None and not umi_planning_task.done():
                umi_planning_task.cancel()
                await asyncio.gather(umi_planning_task, return_exceptions=True)
            if goal_planning_started():
                pending_plan = association_task.result().planning_task
                if pending_plan is not None:
                    pending_plan.cancel()
                    await asyncio.gather(pending_plan, return_exceptions=True)
            await self.adapter.interaction_runtime.runtime.discard_prepared_planner_work(
                self._context_turn_id(context, sid)
            )
            if association_task is not None:
                if not association_task.done():
                    association_task.cancel()
                # A concurrent GA transaction may have committed canonical Goal
                # truth before Fast fails. Retrieve its completed stage result and
                # project those already-established facts into the public failure
                # resolution rather than reporting an empty Goal state.
                association_results = await asyncio.gather(
                    association_task,
                    return_exceptions=True,
                )
                association_result = association_results[0]
                if isinstance(association_result, _GoalAssociationStageResult):
                    association = association_result.association
                    context = association_result.context
                    history = association_result.history
                    planning_context = association_result.planning_context
                    situation = association_result.situation
                    goal_state_results = association_result.goal_state_results
                    goal_state_commit_stage = association_result.goal_state_commit_stage
                    has_named_goal_cancellation = (
                        association_result.has_named_goal_cancellation
                    )
                    has_goal_replacement = association_result.has_goal_replacement
            execution = ready_fast_capability_execution
            execution_status = ready_fast_capability_status
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

            planner_refs = self._cognitive_request_responsibility_refs(
                work_request, "planner"
            )
            social_refs = self._cognitive_request_responsibility_refs(
                work_request, "social_cognition"
            )
            ga_refs = self._cognitive_request_responsibility_refs(
                work_request, "goal_association"
            )
            speculative_ref_set = set(planner_refs)
            speculative_work_request = (
                self._subset_work_request(work_request, speculative_ref_set)
                if speculative_ref_set
                else None
            )

            # UMI authors which existing cognitive authorities are useful now.
            # Runtime only validates their exact Responsibility scope and schedules
            # the requested computations; it never reconstructs readiness from WHAT.
            initial_social_task = (
                self.start_state_interaction(
                    session,
                    work_request=self._subset_work_request(
                        work_request, set(social_refs)
                    ),
                    turn_id=turn_id,
                )
                if social_refs
                else None
            )
            association_task = (
                asyncio.create_task(
                    self._resolve_and_commit_goal_association(
                        session,
                        work_request=work_request,
                        sid=sid,
                        text=text,
                        turn_id=turn_id,
                        context=context,
                        history=history,
                        timings=timings,
                    )
                )
                if ga_refs
                else None
            )
            if initial_social_task is not None or association_task is not None:
                await asyncio.sleep(0)

            async def plan_current_responsibilities(
                request_for_plan: CognitiveWorkRequest,
                plan_context: dict[str, Any],
                plan_history: list[dict[str, Any]],
            ) -> None:
                nonlocal fast_advance, needs_deep_planner
                nonlocal fast_communicative_realization_status
                nonlocal ready_fast_capability_execution, ready_fast_capability_status
                planner_started = time.perf_counter()
                stream_request = request_for_plan.model_copy(
                    deep=True, update={
                        "planning_task_id": "umi:" + turn_id,
                        "sid": turn_id,
                        "context": plan_context,
                        "history": plan_history,
                    }
                )
                terminal_frame: FastPlannerStreamTerminal | None = None
                async for frame in self.agent_client.stream_fast_advance(
                    session, request=stream_request, timeout_ms=self.policy.fast_planner_timeout_ms,
                ):
                    if isinstance(frame, FastPlannerStreamFailure):
                        raise CognitiveStageFailure("fast_planner_stream", frame.model_dump(mode="json"))
                    if not isinstance(frame, FastPlannerStreamTerminal) or terminal_frame is not None:
                        raise ValueError("Fast Work stream must contain exactly one terminal decision")
                    if frame.turn_id != turn_id or frame.advance.turn_id != turn_id:
                        raise ValueError("Fast Work stream changed turn identity")
                    terminal_frame = frame
                if terminal_frame is None:
                    raise ValueError("Fast Work stream ended without a terminal decision")
                fast_advance = terminal_frame.advance
                self._record_workflow_stage(
                    sid=sid, stage="fast_planner_stream_terminal",
                    started_monotonic_ms=planner_started * 1000.0,
                    finished_monotonic_ms=time.perf_counter() * 1000.0,
                    status="resolved", input_payload=stream_request,
                    output_payload=terminal_frame, errors=[], attempt=1,
                    metadata={"semantic_owner": "planner", "communication_authority": False},
                )
                timings["fast_planner_activity_plan"] = (
                    time.perf_counter() - planner_started
                ) * 1000.0
                timings["fast_planner_advance"] = timings[
                    "fast_planner_activity_plan"
                ]
                ready_fast_capability_status = "prepared_until_canonical_validation"
                capability_activities = [item for item in fast_advance.activities if isinstance(item, FastPlannerCapabilityActivity)]
                if self.policy.mode == "apply" and capability_activities and not goal_planning_started() and not any(
                    item.role != "capability" and item.timing == "sequential" for item in fast_advance.activities
                ):
                    eligible = await self.adapter.interaction_runtime.prepare_fast_planner_capability_activities(
                        capability_activities, turn_id=turn_id,
                    )
                    if eligible:
                        ready_fast_capability_execution = await self.adapter.interaction_runtime.start_fast_planner_capability_activities(
                            eligible, session_id=sid, turn_id=turn_id, language=language,
                        )
                        ready_fast_capability_status = "safe_reads_dispatched_before_goal_binding"
                needs_deep_planner = "deep_planner" in fast_advance.continuations

            if speculative_work_request is not None:
                umi_planning_task = asyncio.create_task(
                    plan_current_responsibilities(
                        speculative_work_request, context, history
                    ),
                    name="umi-planning:" + turn_id,
                )
                if association_task is not None:
                    done, _pending = await asyncio.wait(
                        {umi_planning_task, association_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if umi_planning_task in done:
                        await umi_planning_task
                    if association_task in done:
                        early_association = await association_task
                        if early_association.planning_task is not None:
                            done, _pending = await asyncio.wait(
                                {umi_planning_task, early_association.planning_task},
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if (
                                early_association.planning_task in done
                                and not umi_planning_task.done()
                            ):
                                umi_planning_task.cancel()
                                await asyncio.gather(
                                    umi_planning_task, return_exceptions=True
                                )
                                umi_planning_superseded = True
                            else:
                                await umi_planning_task
                        else:
                            await umi_planning_task
                    else:
                        await umi_planning_task
                else:
                    await umi_planning_task
            else:
                planner_waited_for_goal_continuity = False

            if association_task is None:
                if initial_social_task is not None:
                    social_resolved = await initial_social_task
                    if social_resolved is None:
                        raise CognitiveStageFailure(
                            "social_cognition",
                            {
                                "failure_class": "requested_social_interaction_unavailable",
                                "failure_domain": "model_or_runtime",
                                "architecture_attribution": "social_cognition",
                                "retryable": True,
                            },
                        )
                    _social_result, interaction = social_resolved
                else:
                    interaction = self._no_interaction_response(
                        sid=sid,
                        reason="UMI requested no GA or SC cognition",
                    )
                return self._finish(
                    mode=self.policy.mode,
                    status=(
                        "applied" if self.policy.mode == "apply"
                        else "report_only" if self.policy.mode == "report_only"
                        else "skipped"
                    ),
                    association=None,
                    fast_plan=None,
                    terminal_plan=None,
                    interaction=interaction if self.policy.mode == "apply" else None,
                    timings=timings,
                    started=started,
                    metadata={
                        **path_metadata(),
                        "model_driven_cognitive_orchestration": True,
                        "requested_cognitive_authorities": [
                            item.authority for item in work_request.cognitive_requests
                        ],
                    },
                )

            association_stage = await association_task
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

            association_goal_ids = self._association_goal_ids(association)
            goal_ids_by_responsibility = self._goal_ids_by_responsibility(association)
            goal_responsibility_refs = set(goal_ids_by_responsibility)

            if not association_goal_ids:
                expected_refs = {item.local_ref for item in work_request.responsibilities}
                non_goal_refs = set(association.non_goal_responsibility_refs)
                if non_goal_refs != expected_refs:
                    raise CognitiveStageFailure(
                        "goal_association",
                        {
                            "failure_class": "empty_canonical_goal_set",
                            "failure_domain": "model_contract",
                            "architecture_attribution": "goal_association",
                            "retryable": False,
                            "reason": (
                                "GA produced no canonical Goal without explicitly "
                                "classifying every Responsibility non_goal"
                            ),
                        },
                    )
                # GA has explicitly completed the continuity question without Goal-owned
                # Work. SC may already have delivered the social response in parallel;
                # return that exact interaction as the terminal turn result without ever
                # waking Planner.
                if umi_planning_task is not None and not umi_planning_task.done():
                    umi_planning_task.cancel()
                    await asyncio.gather(umi_planning_task, return_exceptions=True)
                if self.policy.mode != "apply":
                    return self._finish(
                        mode=self.policy.mode,
                        status="skipped" if self.policy.mode == "off" else "report_only",
                        association=association,
                        fast_plan=None,
                        terminal_plan=None,
                        timings=timings,
                        started=started,
                        metadata={
                            **path_metadata(),
                            "goal_continuity_checked": True,
                            "planner_avoided_no_goal": True,
                            "non_goal_responsibility_refs": list(
                                association.non_goal_responsibility_refs
                            ),
                        },
                    )
                if initial_social_task is None:
                    return self._finish(
                        mode="apply", status="applied", association=association,
                        fast_plan=None, terminal_plan=None,
                        interaction=self._no_interaction_response(
                            sid=sid,
                            reason="UMI requested GA but no SC cognition",
                        ),
                        timings=timings, started=started,
                        metadata={
                            **path_metadata(),
                            "goal_continuity_checked": True,
                            "planner_avoided_no_goal": True,
                            "model_driven_cognitive_orchestration": True,
                        },
                    )
                social_resolved = await initial_social_task
                if social_resolved is None:
                    raise CognitiveStageFailure(
                        "social_cognition",
                        {
                            "failure_class": "social_only_interaction_unavailable",
                            "failure_domain": "model_or_runtime",
                            "architecture_attribution": "social_cognition",
                            "retryable": True,
                        },
                    )
                _social_result, interaction = social_resolved
                return self._finish(
                    mode="apply", status="applied", association=association,
                    fast_plan=None, terminal_plan=None, interaction=interaction,
                    timings=timings, started=started,
                    metadata={
                        **path_metadata(),
                        "goal_continuity_checked": True,
                        "planner_avoided_no_goal": True,
                        "non_goal_responsibility_refs": list(
                            association.non_goal_responsibility_refs
                        ),
                    },
                )

            remaining_meaning_uncertainties = self._remaining_meaning_uncertainties(
                work_request, association
            )
            post_ga_meaning_uncertainty_count = len(remaining_meaning_uncertainties)
            post_ga_request = work_request.model_copy(
                deep=True,
                update={"meaning_uncertainties": remaining_meaning_uncertainties},
            )
            work_request = self._subset_work_request(
                post_ga_request, goal_responsibility_refs
            )
            planner_scope_changed_after_ga = bool(speculative_ref_set) and (
                speculative_ref_set != goal_responsibility_refs
            )

            if (
                fast_advance is None
                and association_stage.planning_task is None
                and not planner_refs
                and not association.associations
            ):
                if initial_social_task is not None:
                    social_resolved = await initial_social_task
                    if social_resolved is None:
                        raise CognitiveStageFailure(
                            "social_cognition",
                            {
                                "failure_class": "requested_social_interaction_unavailable",
                                "failure_domain": "model_or_runtime",
                                "architecture_attribution": "social_cognition",
                                "retryable": True,
                            },
                        )
                    _social_result, interaction = social_resolved
                else:
                    interaction = self._no_interaction_response(
                        sid=sid,
                        reason="UMI requested Goal continuity without Planner or SC cognition",
                    )
                return self._finish(
                    mode="apply",
                    status="applied",
                    association=association,
                    fast_plan=None,
                    terminal_plan=None,
                    interaction=interaction,
                    goal_state_results=goal_state_results,
                    timings=timings,
                    started=started,
                    metadata={
                        **path_metadata(),
                        "model_driven_cognitive_orchestration": True,
                        "planner_not_requested_by_umi": True,
                    },
                )

            if fast_advance is None and association_stage.planning_task is None:
                if not planner_refs:
                    planner_waited_for_goal_continuity = True
                await plan_current_responsibilities(
                    work_request, planning_context, history
                )
            if fast_advance is None and association_stage.planning_task is None:
                raise CognitiveStageFailure(
                    "fast_planner_advance",
                    {
                        "failure_class": "missing_responsibility_activity_plan",
                        "failure_domain": "model_contract",
                        "architecture_attribution": "user_meaning_interpretation",
                        "retryable": False,
                    },
                )
            if (
                self.policy.mode == "apply"
                and goal_state_commit_stage == "goal_association"
                and ready_fast_communicative_executions
            ):
                for ready_execution in ready_fast_communicative_executions:
                    self.adapter.interaction_runtime.bind_fast_planner_communicative_execution(
                        ready_execution,
                        session_id=sid,
                        goal_ids_by_responsibility=goal_ids_by_responsibility,
                    )

            retained_work_activities = [item for item in planning_context.get("existing_work_activities", [])
                                        if item.get("origin") == "retained_runtime"]
            work_reconciliation_required = not has_named_goal_cancellation and (
                bool(retained_work_activities) or association_stage.planning_task is not None
            )
            goal_update_reconciliation_required = any(
                bool(item.goal_update) for item in association.associations
            )
            canonical_fast_revision_reason = "goal_state_planning" if association_stage.planning_task is not None else ""
            planning_snapshot = association_stage.planning_snapshot
            if work_reconciliation_required:
                canonical_fast_revision_reason = (
                    "provisional_work_goal_reconciliation"
                    if ready_fast_capability_execution is not None
                    else "goal_replacement_work_reconciliation"
                    if has_goal_replacement
                    else "retained_goal_work_reconciliation"
                )
                work_reconciliation_activity_count = len(
                    planning_context["existing_work_activities"]
                )
            elif goal_update_reconciliation_required:
                # Fast Advance and Goal Association share the UMI result but run
                # concurrently. When GA authors an update to retained canonical
                # Goal meaning, only a new Fast Planner pass may decide whether
                # the provisional Activities or InformationGaps still apply.
                canonical_fast_revision_reason = (
                    "goal_association_update_reconciliation"
                )
            elif fast_advance is not None and planner_scope_changed_after_ga:
                # UMI exposed some Work early, but GA discovered additional Goal
                # continuity (for example a conversational re-engagement attached
                # to retained work). Re-run the same Planner authority over the full
                # canonical Goal-owned Responsibility set.
                canonical_fast_revision_reason = "goal_scope_expanded_after_association"
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

            if association_stage.planning_task is not None:
                needs_deep_planner = False
            if needs_deep_planner:
                deep_reason = "fast_planner_advance_complexity"
                deep_planner_invocation_reasons.append(deep_reason)
                deep_context = dict(planning_context)
                deep_context["deep_planner_invocation_reason"] = deep_reason
                stage = time.perf_counter()
                terminal_plan = await self._observe_workflow_stage(
                    sid=sid,
                    stage="deep_planner",
                    input_payload={
                        "user_text": text,
                        "goal_association": association,
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
            elif canonical_fast_revision_reason:
                # A material canonical-state change after the streamed Fast result
                # receives one same-Planner revision. GA supplies Goal continuity only;
                # it never decides Work compatibility. Provisional safe Work remains
                # available until Planner explicitly selects reuse or authors replacement
                # Work. A terminal unavailable/refused decision is not itself a revision
                # trigger.
                stage = time.perf_counter()
                if association_stage.planning_task is not None:
                    fast_plan = await association_stage.planning_task
                else:
                    fast_plan = await self._observe_workflow_stage(
                        sid=sid,
                        stage="fast_planner",
                        input_payload={
                            "user_text": text,
                            "goal_association": association,
                            "revision_reason": canonical_fast_revision_reason,
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
                    deep_context["deep_planner_invocation_reason"] = deep_reason
                    stage = time.perf_counter()
                    terminal_plan = await self._observe_workflow_stage(
                        sid=sid,
                        stage="deep_planner",
                        input_payload={
                            "user_text": text,
                            "goal_association": association,
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
                    user_text=work_request.original_user_text,
                    retained_goals=planning_context.get("active_goal_snapshots", []),
                )
                terminal_plan = fast_plan
                fast_planner_path = "terminal"

            await self.adapter.interaction_runtime.ensure_capability_definitions([step.capability_id for step in terminal_plan.steps])
            confirmation_steps = [step for step in terminal_plan.steps
                if self.adapter.interaction_runtime.capability_definition(step.capability_id).requires_confirmation]
            if confirmation_steps and not any(need.kind == "confirmation" for need in terminal_plan.communication_needs):
                terminal_plan = CanonicalPlan.model_validate({**terminal_plan.model_dump(),
                    "communication_needs": [*terminal_plan.communication_needs, SocialCommunicationNeed(
                        need_id=communication_need_id(terminal_plan.plan_id, "confirmation"), owner="runtime", kind="confirmation",
                        reference_id=terminal_plan.plan_id, source_goal_ids=list(dict.fromkeys(
                            goal_id for step in confirmation_steps for goal_id in step.source_goal_ids)),
                        delivery_phase="pre_action", facts={"provider_confirmation_steps": [step.model_dump(mode="json") for step in confirmation_steps]},
                    )]})
            known_work_ids = {item["activity_id"] for item in planning_context.get("existing_work_activities", [])}
            if set(terminal_plan.cancel_activity_ids) - known_work_ids:
                raise ValueError("Planner cancellation names unknown Work")

            runtime = self.adapter.interaction_runtime.runtime
            if association_stage.planning_task is None:
                # Joining unchanged Responsibility meaning to a canonical identity
                # is mechanical. No second model authored a decision from this state.
                await runtime.bind_prepared_planner_work(turn_id, self._goal_ids_by_responsibility(association))
                planning_snapshot = await runtime.planning_state_snapshot(
                    association_goal_ids, turn_id,
                )

            # Runtime authority starts from the validated canonical Plan and is
            # bounded by registered Capability, authorization, confirmation, resource,
            # and provider-safety contracts below. User Meaning Interpretation contributes WHAT only.
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
                # Fast may delegate unresolved meaning once to Deep. Each depth
                # authors one primary result; the Host validates authority and
                # runtime contracts without becoming another semantic planner.
                raise ValueError(
                    "runtime validation rejected terminal canonical plan: "
                    + json.dumps(runtime_errors, ensure_ascii=False)
                )

            self._validate_work_change_selection(terminal_plan, planning_context.get("existing_work_activities", []))
            if self.policy.mode == "apply" and planning_snapshot is not None:
                async with runtime.planning_commit_scope(planning_snapshot):
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
                            refs_to_goals = self._goal_ids_by_responsibility(association)
                        if refs_to_goals is not None:
                            ready_result = await self.adapter.interaction_runtime.bind_fast_planner_capability_execution(
                                ready_fast_capability_execution,
                                target_interaction_id=f"cognitive_{sid}_{canonical_plan_fingerprint(terminal_plan)[:20]}",
                                canonical_plan_id=terminal_plan.plan_id,
                                canonical_plan_fingerprint=canonical_plan_fingerprint(
                                    terminal_plan
                                ),
                                goal_ids_by_responsibility=refs_to_goals,
                                task_list_revision=int(
                                    terminal_plan.metadata.get("task_list_revision") or 1
                                ),
                                cancel_activity_ids=terminal_plan.cancel_activity_ids,
                            )
                            ready_fast_capability_status = (
                                "completed_before_canonical_dispatch:"
                                + ready_result.status
                            )
                        else:
                            raise ValueError("provisional Work lacks canonical Goal binding")
                    terminal_plan, retained_work_reconciliation_status = await self._apply_retained_work_reconciliation(
                        plan=terminal_plan, activities=planning_context.get("existing_work_activities", []), turn_id=turn_id,
                    )
                    cancelled_bindings = {
                        str(item["runtime_binding"]["interaction_id"]) + "/" + str(item["activity_id"])
                        for item in retained_work_activities
                        if item["activity_id"] in terminal_plan.cancel_activity_ids
                    }
                    await runtime.validate_planning_state(planning_snapshot, cancelled_bindings=cancelled_bindings)
                    prepared_ids = [item["activity_id"] for item in planning_snapshot["prepared"] if item.get("turn_id", turn_id) == turn_id]
                    selected_prepared = (prepared_ids if terminal_plan.metadata.get("resolver") == "fast_planner_advance"
                                         else [step.reuse_activity_id for step in terminal_plan.steps])
                    planning_commit = await runtime.reserve_planning_submission(
                        planning_snapshot, plan_id=terminal_plan.plan_id,
                        fingerprint=canonical_plan_fingerprint(terminal_plan),
                        prepared_activity_ids=[*selected_prepared, *terminal_plan.cancel_activity_ids],
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

            if terminal_plan.steps and not terminal_plan.communication_needs and not any(
                self.adapter.interaction_runtime.capability_definition(step.capability_id).requires_confirmation
                for step in terminal_plan.steps
            ):
                if self.policy.mode == "apply":
                    initial_social_task = self.start_state_interaction(
                        session, work_request=work_request.model_copy(update={"context": planning_context}),
                        turn_id=turn_id, plan=terminal_plan,
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
                        "wording_owner": "social_cognition",
                    },
                    operation=self.resolve_plan_interaction(
                        session, plan=terminal_plan, work_request=work_request,
                        session_id=sid, language=language, context=planner_response_context,
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
            await self.cancel_social_interaction()
            await cancel_uncommitted_fast_work("foreground_deadline")
            raise
        except CognitiveStageFailure as exc:
            await self.cancel_social_interaction()
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
            await self.cancel_social_interaction()
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
        if status == "applied" and interaction is not None and isinstance(metadata_payload.get("planning_commit"), dict):
            interaction = interaction.model_copy(deep=True, update={"metadata": {
                **interaction.metadata, "planning_commit": metadata_payload["planning_commit"],
                "retained_work_activities": metadata_payload.get("retained_work_activities", []),
            }})
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
