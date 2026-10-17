from __future__ import annotations

from .cognitive_gateway_modules.context_assembly import ContextAssembly

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.chromie_contracts.core_interpretation import (
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.goal import (
    GoalAssociationResolution,
    goal_association_fingerprint,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
)
from shared.chromie_contracts.reflection import ReflectionResolution
from shared.chromie_contracts.value_judgment import ValueJudgmentResult
from shared.chromie_contracts.semantic_artifact import (
    SemanticArtifactLineage,
    SemanticArtifactRef,
    merge_semantic_artifact_lineage,
    semantic_artifact_ref,
)
from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialCognitionResolution
from shared.chromie_contracts.reflex import CancellationDirective
from shared.chromie_contracts.plan import (
    communication_need_id,
    SocialCommunicationNeed,
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerStreamFailure,
    FastPlannerStreamFrame,
    FastPlannerStreamTerminal,
    validate_communicative_activity_identity,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.user_turn import (
    UserTurnEnvelope,
    user_turn_prohibits_speech,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer


from orchestrator.runtime.situation import build_situation_projection
from orchestrator.runtime.response_plan import build_social_interaction_response
from orchestrator.runtime import planner_advance_projection

if TYPE_CHECKING:
    from orchestrator.runtime.canonical_plan_adapter import CanonicalPlanRuntimeAdapter

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
    planner_timeout_ms: int = 3000
    # Deliberative deadline for Social Cognition and Reflection.
    deliberative_timeout_ms: int = 10000
    # Capabilities whose effects need a Value Judgment proceed verdict before dispatch
    # (owner-editable capabilities/value_review.json). Empty means no value gate.
    value_review_capability_ids: frozenset[str] = frozenset()


def value_judgment_verdict(result: ValueJudgmentResult) -> dict[str, Any]:
    """The verdict a Value Judgment result gives; a failed judgment is a decline."""
    judgment = result.judgment
    return {
        "status": result.status,
        "decision": judgment.decision if judgment is not None else "decline",
        "concern": judgment.concern if judgment is not None else "none",
        "affected": judgment.affected if judgment is not None else "nobody_else",
        "reason": judgment.reason if judgment is not None else "Chromie could not judge this request safely right now.",
        "failure_class": result.failure_class,
    }


def apply_value_judgment(
    plan: CanonicalPlan, reviewed_ids: set[str], result: ValueJudgmentResult | dict[str, Any],
    reviewed_need_ids: set[str] | frozenset[str] = frozenset(),
    reviewed_step_ids: set[str] | frozenset[str] = frozenset(),
) -> CanonicalPlan:
    """Annotate value-reviewed steps and answers with the verdict; the Plan itself stands.

    proceed leaves the effects free; ask makes them need the person's confirmation; decline
    or a failed judgment withholds them, so Runtime refuses them before provider start.
    Speech UMI marked value_review (owner choice B, 2026-10-12) is reviewed through the
    answers and steps realizing it: ask or decline withholds such an answer this turn, so
    Social Cognition may not say it. ``result`` may be a verdict already given in this turn.
    """
    verdict = dict(result) if isinstance(result, dict) else value_judgment_verdict(result)
    steps = []
    for step in plan.steps:
        metadata = dict(step.metadata)
        if step.capability_id in reviewed_ids or step.step_id in reviewed_step_ids:
            metadata["value_judgment"] = verdict
            if verdict["decision"] == "ask":
                metadata["value_confirmation_required"] = True
            elif verdict["decision"] == "decline":
                metadata["value_withheld"] = True
        steps.append(step.model_copy(update={"metadata": metadata}))
    needs = []
    withheld_goal_ids: list[str] = []
    for need in plan.communication_needs:
        if need.need_id in reviewed_need_ids:
            facts = {**need.facts, "value_judgment": verdict}
            if verdict["decision"] in {"ask", "decline"}:
                facts["value_withheld"] = True
                withheld_goal_ids.extend(need.source_goal_ids)
            need = need.model_copy(update={"facts": facts})
        needs.append(need)
    answer_verdict = {
        "reviewed_answer_need_ids": sorted(reviewed_need_ids),
        "withheld_answer_goal_ids": list(dict.fromkeys(withheld_goal_ids)),
    } if reviewed_need_ids else {}
    return CanonicalPlan.model_validate({**plan.model_dump(), "steps": [step.model_dump() for step in steps],
        "communication_needs": [need.model_dump() for need in needs],
        "metadata": {**plan.metadata, "value_judgment": {
            **verdict, "reviewed_capability_ids": sorted(reviewed_ids | {
                step.capability_id for step in plan.steps if step.step_id in reviewed_step_ids}), **answer_verdict}}})


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


_VALUE_JUDGMENT_STEP_ANNOTATIONS = ("value_judgment", "value_confirmation_required", "value_withheld")
_VALUE_JUDGMENT_NEED_ANNOTATIONS = ("value_judgment", "value_withheld")


def planner_authored_plan_payload(plan: CanonicalPlan) -> dict[str, Any]:
    """The Planner-authored artifact of a Plan, without Host-owned annotations.

    After the Planner, the Host may add Runtime-owned communication needs (confirmation)
    and Value Judgment verdicts to the same Plan identity. Those are not Planner
    authorship, so every ``planner_plan`` artifact digests this projection: the Planner's
    original and the annotated Plan stay one artifact, and real divergence still fails.
    """
    payload = plan.model_dump(mode="json", exclude_none=True)
    if "communication_needs" in payload:
        payload["communication_needs"] = [
            need for need in payload["communication_needs"] if need.get("owner") != "runtime"
        ]
        for need in payload["communication_needs"]:
            for key in _VALUE_JUDGMENT_NEED_ANNOTATIONS:
                if isinstance(need.get("facts"), dict):
                    need["facts"].pop(key, None)
    if isinstance(payload.get("metadata"), dict):
        payload["metadata"].pop("value_judgment", None)
    for step in payload.get("steps") or []:
        for key in _VALUE_JUDGMENT_STEP_ANNOTATIONS:
            if isinstance(step.get("metadata"), dict):
                step["metadata"].pop(key, None)
    return payload


def _plan_semantic_lineage(
    base: SemanticArtifactLineage, plan: CanonicalPlan,
) -> SemanticArtifactLineage:
    return merge_semantic_artifact_lineage(
        base, semantic_artifact_ref(
            planner_authored_plan_payload(plan), artifact_kind="planner_plan", artifact_id=plan.plan_id,
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


class _ResolutionRun(SimpleNamespace):
    """Mutable state shared by the stages of one ``_resolve`` call.

    ``GoalDrivenRuntimeCoordinator._begin_resolution`` sets the initial fields;
    each stage reads and advances them in order.
    """


class CognitiveAgentClient(Protocol):
    async def resolve_social_cognition(
        self, session: Any, **kwargs: Any
    ) -> SocialCognitionResolution: ...

    async def resolve_goal_association(
        self, session: Any, **kwargs: Any
    ) -> GoalAssociationResolution: ...

    def stream_plan_advance(
        self, session: Any, **kwargs: Any
    ) -> AsyncIterator[FastPlannerStreamFrame]: ...

    async def resolve_plan(self, session: Any, **kwargs: Any) -> CanonicalPlan: ...

    async def resolve_value_judgment(self, session: Any, **kwargs: Any) -> ValueJudgmentResult: ...

    async def resolve_reflection(
        self, session: Any, **kwargs: Any
    ) -> ReflectionResolution: ...

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
        communicative_goal_completion_apply: (
            Callable[..., list[dict[str, Any]]] | None
        ) = None,
        planner_gap_apply: Callable[..., list[dict[str, Any]]] | None = None,
        context_refresh: Callable[[str | None], dict[str, Any]] | None = None,
        delivered_turn_speech_provider: (Callable[[str], list[dict[str, Any]]] | None) = None,
        interaction_ledger: Any | None = None,
        workflow_stage_sink: Callable[..., None] | None = None,
        social_task_tracker: Callable[[str | None, asyncio.Task[Any]], None] | None = None,
    ) -> None:
        self.agent_client = agent_client
        self.adapter = adapter
        self.policy = policy
        self.goal_state_apply = goal_state_apply
        self.communicative_goal_completion_apply = (
            communicative_goal_completion_apply
        )
        self.planner_gap_apply = planner_gap_apply
        self.context_refresh = context_refresh
        self._goal_association_locks: dict[str, asyncio.Lock] = {}
        self.delivered_turn_speech_provider = delivered_turn_speech_provider
        self.workflow_stage_sink = workflow_stage_sink
        self.social_task_tracker = social_task_tracker
        self.interaction_ledger = interaction_ledger or getattr(
            getattr(adapter, "interaction_runtime", None),
            "interaction_ledger",
            None,
        )
        self._auxiliary_execution_tasks: set[asyncio.Task[Any]] = set()
        self._social_turns: dict[str, tuple[str, asyncio.Task[Any], str]] = {}
        self._social_dispatches: dict[str, str] = {}
        # Value Judgment verdicts given in a turn, keyed "capability:<id>" or
        # "responsibility:<UMI local_ref>", so a later Plan of the same turn reuses them.
        self._turn_value_verdicts: OrderedDict[str, dict[str, dict[str, Any]]] = OrderedDict()

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

    async def _cancel_social_turn(self, previous: tuple[str, asyncio.Task[Any], str] | None) -> None:
        if previous is None:
            return
        request_id, task, _ = previous
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        interaction_id = self._social_dispatches.pop(request_id, None)
        if interaction_id is not None:
            await self.adapter.interaction_runtime.runtime.cancel_interaction(interaction_id)

    async def _finish_or_cancel_social_turn(
        self, previous: tuple[str, asyncio.Task[Any], str] | None, *, turn_id: str,
    ) -> None:
        if previous is not None and previous[2] == turn_id and previous[0] in self._social_dispatches:
            # A same-turn state update does not retract already submitted expression.
            try:
                await asyncio.gather(previous[1], return_exceptions=True)
            except asyncio.CancelledError:
                await self._cancel_social_turn(previous)
                raise
        else:
            await self._cancel_social_turn(previous)

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
        self._track_auxiliary_execution_task(task, session_id=session_id)

    def _state_social_request(
        self,
        *,
        work_request: CognitiveWorkRequest,
        turn_id: str,
        plan: CanonicalPlan | None = None,
        work_decision_pending: bool | None = None,
        trigger: str | None = None,
        source_refs: list[str] | None = None,
        goal_ids: list[str] | None = None,
        communication_needs: list[SocialCommunicationNeed] | None = None,
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
        resolved_trigger = trigger or ("work_state" if plan is not None else "interpretation")
        resolved_source_refs = list(source_refs or ([plan.plan_id] if plan is not None else [turn_id]))
        resolved_goal_ids = list(goal_ids or (list(plan.goal_ids) if plan is not None else []))
        request_identity = "|".join([resolved_trigger, *resolved_source_refs, *resolved_goal_ids, turn_id])
        return SocialCognitionRequest(
            request_id="sc:" + hashlib.sha256(request_identity.encode("utf-8")).hexdigest(),
            trigger=resolved_trigger,
            source_refs=resolved_source_refs,
            goal_ids=resolved_goal_ids,
            language=work_request.language or "auto",
            responsibilities=list(work_request.responsibilities),
            meaning_uncertainties=list(work_request.meaning_uncertainties),
            source_turn=work_request.source_turn_provenance,
            communication_needs=list(communication_needs or []),
            context=ContextAssembly.project_context({
                **social_context, "work_decision_pending": pending,
                **({"canonical_plan_resolution": plan.prompt_projection()} if plan is not None else {}),
                "history": list(work_request.history),
                "interaction_context": self._interaction_context(sid=sid, context=social_context),
            }),
        )

    def start_state_interaction(
        self, session: Any, *, work_request: CognitiveWorkRequest, turn_id: str,
        plan: CanonicalPlan | None = None,
        trigger: str | None = None,
        source_refs: list[str] | None = None,
        goal_ids: list[str] | None = None,
        work_decision_pending: bool | None = None,
        communication_needs: list[SocialCommunicationNeed] | None = None,
    ) -> asyncio.Task[Any] | None:
        """Let a new UMI or committed Plan state invite SC without holding Work."""
        if self.policy.mode != "apply" or user_turn_prohibits_speech(work_request.context.get("user_turn_envelope")):
            return None
        sid = str(work_request.sid or "")
        key = self._goal_association_lock_key(work_request.context, sid)
        previous = self._social_turns.get(key)
        primary_plan = plan.model_copy(deep=True) if plan is not None else None
        request = self._state_social_request(
            work_request=work_request, turn_id=turn_id, plan=primary_plan,
            trigger=trigger, source_refs=source_refs, goal_ids=goal_ids,
            work_decision_pending=work_decision_pending,
            communication_needs=communication_needs,
        )
        execution_snapshot: dict[str, Any] | None = None
        def current() -> bool:
            entry = self._social_turns.get(key)
            return entry is not None and entry[0] == request.request_id and (
                execution_snapshot is None
                or self.adapter.interaction_runtime.runtime.execution_state_is_current(execution_snapshot)
            )
        async def run() -> None:
            nonlocal execution_snapshot
            await self._finish_or_cancel_social_turn(previous, turn_id=turn_id)
            if not current():
                return
            if primary_plan is not None:
                # Bind optional Work-state reporting to its actual execution
                # scope. Independent interpretation/greeting does not expire
                # merely because parallel user Work starts or finishes.
                execution_snapshot = await self.adapter.interaction_runtime.runtime.planning_state_snapshot(
                    request.goal_ids, turn_id,
                )
            # Earlier same-turn expression may have held this decision while
            # Work progressed. Read continuity and the ledger in the same event-
            # loop turn, preserving the admitted meaning and immutable Plan.
            social_context, social_history = self._refresh_continuity_context(
                context={**work_request.context, "history": list(work_request.history)}, sid=sid,
            )
            current_request = self._state_social_request(
                work_request=work_request.model_copy(update={"context": social_context, "history": social_history}),
                turn_id=turn_id, plan=primary_plan,
                trigger=trigger, source_refs=source_refs, goal_ids=goal_ids,
                work_decision_pending=work_decision_pending,
                communication_needs=communication_needs,
            )
            resolved = await self.resolve_social_interaction(
                session, request=current_request, session_id=sid, snapshot_is_current=current,
                primary_plan=primary_plan,
            )
            if resolved is None or not current():
                return
            result, response = resolved
            runtime_dispatch = None
            if response.speech or response.capabilities:
                self._social_dispatches[request.request_id] = response.interaction_id
                runtime_dispatch = await self.adapter.interaction_runtime.submit_response(response, session_id=sid)
            if current():
                self.schedule_social_expression(response, session_id=sid, context=current_request.context, snapshot_is_current=current)
            if runtime_dispatch is not None:
                cancelled = False
                try:
                    execution = await self.adapter.interaction_runtime.wait_dispatch(runtime_dispatch)
                    delivered = await self.adapter.interaction_runtime.record_social_delivery(response, execution, session_id=sid)
                    if execution.status != "completed" or not delivered:
                        raise RuntimeError(
                            f"social_interaction_delivery_failed: status={execution.status} speech_delivered={delivered}"
                        )
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                finally:
                    if not cancelled:
                        self._social_dispatches.pop(request.request_id, None)
                response.metadata["presentation_already_dispatched"] = True
            return result, response
        task = asyncio.create_task(run(), name="social-interpretation:" + turn_id)
        self._social_turns[key] = (request.request_id, task, turn_id)
        self._track_auxiliary_execution_task(task, session_id=sid)
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
        await self._finish_or_cancel_social_turn(
            previous, turn_id=str(work_request.source_turn_provenance.get("turn_id") or session_id),
        )
        # Required communication can wait behind already submitted same-turn
        # speech while Work advances. Refresh the existing state owners before
        # assembling the ledger, preserving the admitted meaning and exact Plan.
        current_context, _history = self._refresh_continuity_context(
            context=context, sid=session_id,
        )
        source_context = ContextAssembly.project_context(current_context)
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
            sid=session_id, context=current_context, goal_ids=plan.goal_ids,
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
        try:
            result = await self._observe_workflow_stage(
                sid=session_id, stage="social_cognition", input_payload=request,
                operation=self.agent_client.resolve_social_cognition(
                    session, request=request,
                    timeout_ms=max(self.policy.planner_timeout_ms, self.policy.deliberative_timeout_ms),
                ),
            )
            result.validate_request(request)
        except CognitiveStageFailure:
            raise
        except (RuntimeError, ValueError) as exc:
            # This is a cognitive service/contract failure, not a Host bug.
            # Preserve the existing completed-conversation containment while
            # retaining the failure and keeping non-speech Work fail closed.
            raise CognitiveStageFailure("social_cognition", {
                "failure_class": "social_cognition_request_failed",
                "failure_domain": "cognitive_service",
                "architecture_attribution": "not_evaluated",
                "retryable": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }) from exc
        current_interaction = self._interaction_context(sid=session_id, context=current_context, goal_ids=plan.goal_ids)
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
        primary_plan: CanonicalPlan | None = None,
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
                timeout_ms=max(self.policy.planner_timeout_ms, self.policy.deliberative_timeout_ms),
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
            logger.info("social_cognition_suppressed sid=%s request_id=%s reason=stale_snapshot",
                        session_id, request.request_id)
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
                context=request.context, snapshot_is_current=snapshot_is_current, primary_plan=primary_plan)
        if not snapshot_is_current():
            logger.info("social_cognition_suppressed sid=%s request_id=%s reason=stale_snapshot",
                        session_id, request.request_id)
            return None
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

    def _track_auxiliary_execution_task(
        self, task: asyncio.Task[Any], *, session_id: str | None,
    ) -> None:
        """Retain fail-soft Runtime execution without creating cognition work."""

        self._auxiliary_execution_tasks.add(task)
        if self.social_task_tracker is not None:
            self.social_task_tracker(session_id, task)

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

    _TURN_VALUE_VERDICT_LIMIT = 256

    @staticmethod
    def _plan_value_verdicts(plan: CanonicalPlan | None) -> dict[str, dict[str, Any]]:
        """Verdicts the Host already wrote onto an earlier Plan of the same turn."""
        verdicts: dict[str, dict[str, Any]] = {}
        if plan is None:
            return verdicts
        for step in plan.steps:
            verdict = step.metadata.get("value_judgment")
            if isinstance(verdict, dict) and verdict.get("decision"):
                verdicts.setdefault(f"capability:{step.capability_id}", dict(verdict))
        for need in plan.communication_needs:
            verdict = need.facts.get("value_judgment")
            if isinstance(verdict, dict) and verdict.get("decision"):
                for ref in need.source_responsibility_refs:
                    verdicts.setdefault(f"responsibility:{ref}", dict(verdict))
        return verdicts

    @staticmethod
    def goal_ids_by_responsibility_projection(association: Any) -> dict[str, list[str]]:
        """``planner_advance_projection.goal_ids_by_responsibility`` for a JSON Goal Association projection."""
        mapped: dict[str, list[str]] = {}
        if not isinstance(association, dict):
            return mapped
        rows = [(item.get("source_responsibility_refs"), item.get("target_goal_ids"))
                for item in association.get("associations") or [] if isinstance(item, dict)]
        rows += [(item.get("source_responsibility_refs"), [item.get("goal_id")])
                 for item in association.get("new_goals") or [] if isinstance(item, dict)]
        for refs, goal_ids in rows:
            goals = [goal_id for value in goal_ids or [] if (goal_id := " ".join(str(value or "").split()))]
            for value in refs or []:
                if (ref := " ".join(str(value or "").split())) and goals:
                    current = mapped.setdefault(ref, [])
                    current.extend(goal_id for goal_id in goals if goal_id not in current)
        return mapped

    async def apply_value_judgment_gate(
        self, session: Any, *, sid: str, text: str, plan: CanonicalPlan,
        work_request: CognitiveWorkRequest, goal_ids_by_responsibility: dict[str, list[str]],
        turn_id: str, judged_plan: CanonicalPlan | None = None,
    ) -> CanonicalPlan:
        """Value Judgment for any Plan of a turn, before its reviewed effects can start.

        A Plan needs a verdict for every value-reviewed Capability it uses and every
        answer or step realizing speech UMI marked value_review. A verdict already given
        in the same turn (this coordinator's record, or the Host annotations on
        ``judged_plan``) is reused; anything not yet judged takes one Value Judgment
        call. Decline or a failed judgment withholds the effect, ask requires the
        person's confirmation, and the Plan itself stands.
        """
        # Verdict annotations are Host-owned; a Planner-authored copy never counts.
        if "value_judgment" in plan.metadata or any(
                key in step.metadata for step in plan.steps for key in _VALUE_JUDGMENT_STEP_ANNOTATIONS) or any(
                key in need.facts for need in plan.communication_needs for key in _VALUE_JUDGMENT_NEED_ANNOTATIONS):
            plan = CanonicalPlan.model_validate({**plan.model_dump(),
                "steps": [{**step.model_dump(), "metadata": {
                    key: value for key, value in step.metadata.items() if key not in _VALUE_JUDGMENT_STEP_ANNOTATIONS}}
                    for step in plan.steps],
                "communication_needs": [{**need.model_dump(), "facts": {
                    key: value for key, value in need.facts.items() if key not in _VALUE_JUDGMENT_NEED_ANNOTATIONS}}
                    for need in plan.communication_needs],
                "metadata": {key: value for key, value in plan.metadata.items() if key != "value_judgment"}})
        if self.policy.mode != "apply":
            return plan
        reviewed_ids = {step.capability_id for step in plan.steps} & self.policy.value_review_capability_ids
        flagged_refs = {item.local_ref for item in work_request.responsibilities if item.value_review}
        goals_by_ref = {ref: set(goal_ids_by_responsibility.get(ref, [])) for ref in flagged_refs}
        need_refs = {need.need_id: refs for need in plan.communication_needs if need.kind == "answer" and (refs := (
            set(need.source_responsibility_refs) & flagged_refs
            | {ref for ref, goals in goals_by_ref.items() if goals & set(need.source_goal_ids)}))}
        step_refs = {step.step_id: refs for step in plan.steps if (refs := {
            ref for ref, goals in goals_by_ref.items() if goals & set(step.source_goal_ids)})}
        if not (reviewed_ids or need_refs or step_refs):
            return plan
        reviewed_refs = set().union(*need_refs.values(), *step_refs.values())
        recorded = self._turn_value_verdicts.get(turn_id, {}) if turn_id else {}
        known = {**self._plan_value_verdicts(judged_plan), **recorded}
        keys = {f"capability:{cid}" for cid in reviewed_ids} | {f"responsibility:{ref}" for ref in reviewed_refs}
        pending = sorted(keys - set(known))
        if pending:
            result = await self._observe_workflow_stage(
                sid=sid,
                stage="value_judgment",
                input_payload={"user_text": text, "reviewed_capability_ids": sorted(reviewed_ids),
                               "reviewed_answer_need_ids": sorted(need_refs),
                               "value_review_responsibility_refs": sorted(flagged_refs),
                               "judged_value_keys": pending,
                               "reused_value_keys": sorted(keys - set(pending))},
                operation=self._resolve_value_judgment(session, work_request),
                metadata={"semantic_owner": "value_judgment", "communication_authority": False},
            )
            verdict = value_judgment_verdict(result)
            known.update({key: verdict for key in pending})
            if turn_id:
                self._turn_value_verdicts.setdefault(turn_id, {}).update({key: verdict for key in pending})
                self._turn_value_verdicts.move_to_end(turn_id)
                while len(self._turn_value_verdicts) > self._TURN_VALUE_VERDICT_LIMIT:
                    self._turn_value_verdicts.popitem(last=False)
        # Apply each distinct verdict to what it judged; the most restrictive goes last,
        # so the Plan-level record carries it.
        severity = {"proceed": 0, "ask": 1, "decline": 2}
        groups: dict[str, tuple[dict[str, Any], set[str], set[str], set[str]]] = {}
        for key in sorted(keys):
            verdict = known[key]
            caps, needs, steps = groups.setdefault(json.dumps(verdict, sort_keys=True), (verdict, set(), set(), set()))[1:]
            kind, _, value = key.partition(":")
            if kind == "capability":
                caps.add(value)
            else:
                needs.update(need_id for need_id, refs in need_refs.items() if value in refs)
                steps.update(step_id for step_id, refs in step_refs.items() if value in refs)
        reviewed_capability_ids: set[str] = set()
        reviewed_answer_need_ids: set[str] = set()
        withheld_answer_goal_ids: list[str] = []
        for verdict, caps, needs, steps in sorted(groups.values(), key=lambda group: (
                severity.get(str(group[0].get("decision")), 2), bool(group[2]))):
            plan = apply_value_judgment(plan, caps, verdict, needs, steps)
            record = plan.metadata["value_judgment"]
            reviewed_capability_ids.update(record["reviewed_capability_ids"])
            reviewed_answer_need_ids.update(record.get("reviewed_answer_need_ids") or [])
            withheld_answer_goal_ids.extend(record.get("withheld_answer_goal_ids") or [])
        record = {**plan.metadata["value_judgment"], "reviewed_capability_ids": sorted(reviewed_capability_ids)}
        if reviewed_answer_need_ids:
            record.update({"reviewed_answer_need_ids": sorted(reviewed_answer_need_ids),
                           "withheld_answer_goal_ids": list(dict.fromkeys(withheld_answer_goal_ids))})
        plan = plan.model_copy(update={"metadata": {**plan.metadata, "value_judgment": record}})
        withheld_steps = [step for step in plan.steps if step.metadata.get("value_withheld")]
        withheld_answers = [need for need in plan.communication_needs if need.facts.get("value_withheld")]
        verdict = (withheld_steps[0].metadata["value_judgment"] if withheld_steps
                   else withheld_answers[0].facts["value_judgment"] if withheld_answers else {})
        if withheld_steps or (withheld_answers and verdict["decision"] == "decline"):
            # Chromie's decline is known before dispatch: SC says it now, and the
            # refused result never wakes the Planner to work around it.
            plan = CanonicalPlan.model_validate({**plan.model_dump(),
                "communication_needs": [*plan.communication_needs, SocialCommunicationNeed(
                    need_id=communication_need_id(plan.plan_id, "value_declined"),
                    owner="runtime", kind="result", reference_id=plan.plan_id,
                    source_goal_ids=list(dict.fromkeys(
                        [*(goal_id for step in withheld_steps for goal_id in step.source_goal_ids),
                         *(goal_id for need in withheld_answers for goal_id in need.source_goal_ids)])),
                    delivery_phase="immediate",
                    facts={"value_declined": verdict,
                           "withheld_capability_ids": [step.capability_id for step in withheld_steps],
                           "withheld_answer_need_ids": [need.need_id for need in withheld_answers]},
                )]})
        elif withheld_answers:
            # The answer waits on one fact; SC asks it now instead of answering.
            plan = CanonicalPlan.model_validate({**plan.model_dump(),
                "communication_needs": [*plan.communication_needs, SocialCommunicationNeed(
                    need_id=communication_need_id(plan.plan_id, "value_question"),
                    owner="runtime", kind="input", reference_id=plan.plan_id,
                    source_goal_ids=list(dict.fromkeys(
                        goal_id for need in withheld_answers for goal_id in need.source_goal_ids)),
                    delivery_phase="immediate",
                    facts={"value_question": verdict,
                           "withheld_answer_need_ids": [need.need_id for need in withheld_answers]},
                )]})
        return plan

    def with_runtime_confirmation_need(self, plan: CanonicalPlan) -> CanonicalPlan:
        """Add the Runtime-owned confirmation need for steps that need the person's yes."""
        confirmation_steps = [step for step in plan.steps
            if not step.metadata.get("value_withheld")
            and (self.adapter.interaction_runtime.capability_definition(step.capability_id).requires_confirmation
                 or step.metadata.get("value_confirmation_required"))]
        value_question = next((step.metadata["value_judgment"] for step in confirmation_steps
            if step.metadata.get("value_confirmation_required")), None)
        if confirmation_steps and not any(need.kind == "confirmation" for need in plan.communication_needs):
            plan = CanonicalPlan.model_validate({**plan.model_dump(),
                "communication_needs": [*plan.communication_needs, SocialCommunicationNeed(
                    need_id=communication_need_id(plan.plan_id, "confirmation"), owner="runtime", kind="confirmation",
                    reference_id=plan.plan_id, source_goal_ids=list(dict.fromkeys(
                        goal_id for step in confirmation_steps for goal_id in step.source_goal_ids)),
                    delivery_phase="pre_action", facts={"provider_confirmation_steps": [step.model_dump(mode="json") for step in confirmation_steps],
                        **({"value_question": value_question} if value_question else {})},
                )]})
        return plan

    async def _resolve_value_judgment(
        self, session: Any, request: CognitiveWorkRequest,
    ) -> ValueJudgmentResult:
        try:
            return await self.agent_client.resolve_value_judgment(
                session, request=request, timeout_ms=self.policy.planner_timeout_ms,
            )
        except Exception as exc:  # noqa: BLE001 - a failed judgment withholds reviewed effects
            logger.warning("value_judgment_unavailable sid=%s error_type=%s error=%s",
                           request.sid, type(exc).__name__, str(exc)[:300])
            return ValueJudgmentResult(status="failed", failure_class="value_judgment_unavailable",
                                       reason=str(exc)[:500])

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
        """Return the exact model-requested initial activation scope.

        Runtime closes only structural prerequisites. Planner may reason about any
        accepted Responsibility, including conversational/interaction Goals whose
        HOW is a response rather than Capability Work. Therefore an explicitly
        requested Planner mechanically implies turn-wide Goal Association so the
        eventual Plan can bind to canonical Goal identity. ``continuity_scope`` is
        not a Planner-routing flag and never strips an explicitly requested scope.
        """

        known = [item.local_ref for item in request.responsibilities]
        known_set = set(known)
        # UMI's value_review speech also requests the Planner (its contract): Value
        # Judgment reviews the Planner-established answer before anything is said.
        reviewed = {item.local_ref for item in request.responsibilities if item.value_review}
        activation = next(
            (item for item in request.cognitive_requests if item.authority == authority),
            None,
        )
        if activation is None:
            if authority == "goal_association" and (reviewed or any(
                item.authority == "planner" for item in request.cognitive_requests
            )):
                return known
            if authority == "planner" and reviewed:
                return [ref for ref in known if ref in reviewed]
            return []
        unknown = set(activation.responsibility_refs) - known_set
        if unknown:
            raise ValueError(
                f"cognitive activation authority={authority} references unknown Responsibilities: "
                + ",".join(sorted(unknown))
            )
        selected = set(activation.responsibility_refs) | (reviewed if authority == "planner" else set())
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
    def _continuity_unchanged(association: GoalAssociationResolution, refs: set[str]) -> bool:
        """Whether GA left everything a cognition already reading ``refs`` saw unchanged.

        A Goal created from a Responsibility with no association, relation, supersession
        or referent change only names what UMI already handed over. Charter: a purely
        identity-preserving GA result is bound without another model call, and GA
        continuity never erases a valid Planner result (live 2026-10-13: a GA re-plan of
        an unchanged "Nod twice" replaced the correct nod with a spoken reply).
        """

        if association.referent_updates or association.resolved_references:
            return False
        if any(set(item.source_responsibility_refs) & refs for item in association.associations):
            return False
        return not any(
            goal.related_goal_ids or goal.supersedes_goal_ids
            for goal in association.new_goals
            if set(goal.source_responsibility_refs) & refs
        )

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

        planner_advance_projection.validate_work_change_selection(plan, activities)
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

    def _reconcile_delivered_direct_social_response(
        self,
        *,
        association: GoalAssociationResolution,
        interaction: InteractionResponse,
        sid: str,
    ) -> list[dict[str, Any]]:
        """Close newly materialized speech Goals after their SC act was heard.

        Initial Social Cognition may finish concurrently with Goal Association, so
        its response carries Responsibility refs before canonical Goal IDs exist.
        Once GA has committed those IDs, this is the deterministic join already
        used by Planner.  SC's ``respond`` act remains the semantic completion
        decision; delivered playback remains the factual completion evidence.
        """

        if (
            self.communicative_goal_completion_apply is None
            or interaction.metadata.get("presentation_already_dispatched") is not True
            or not self._is_direct_spoken_association(association)
        ):
            return []
        goal_ids_by_responsibility = planner_advance_projection.goal_ids_by_responsibility(association)
        results: list[dict[str, Any]] = []
        for speech in interaction.speech:
            metadata = speech.metadata if isinstance(speech.metadata, dict) else {}
            if (
                str(metadata.get("wording_owner") or "") != "social_cognition"
                or str(metadata.get("speech_act") or "") != "respond"
                or metadata.get("communication_completion_goal_ids")
            ):
                continue
            goal_ids = list(
                dict.fromkeys(
                    goal_id
                    for responsibility_ref in metadata.get(
                        "source_responsibility_refs", []
                    )
                    for goal_id in goal_ids_by_responsibility.get(
                        responsibility_ref, []
                    )
                )
            )
            if not goal_ids:
                continue
            results.extend(
                self.communicative_goal_completion_apply(
                    sid,
                    goal_ids,
                    metadata={
                        "source": "social_cognition_communicative_completion",
                        "delivery_role": "response",
                        "speech_event_id": speech.id,
                        "evidence_refs": list(metadata.get("evidence_refs") or []),
                    },
                )
            )
        return results

    @staticmethod
    def _fast_plan_path(plan: CanonicalPlan | None) -> str:
        if plan is None:
            return ""
        value = str(plan.metadata.get("path_classification") or "").strip()
        if value in {"terminal", "contract_failure"}:
            return value
        if plan.metadata.get("failure_class"):
            return "contract_failure"
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
        planner_refs_in_flight: frozenset[str] = frozenset(),
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
        mapping = planner_advance_projection.goal_ids_by_responsibility(association)
        goal_responsibility_refs = set(mapping)
        ga_planner_request = next(
            (item for item in association.cognitive_requests if item.authority == "planner"),
            None,
        )
        ga_planner_refs = set(ga_planner_request.responsibility_refs) if ga_planner_request else set()
        if not ga_planner_refs.issubset(goal_responsibility_refs):
            raise CognitiveStageFailure(
                "goal_association",
                {
                    "failure_class": "invalid_cognitive_activation_scope",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "goal_association",
                    "retryable": False,
                    "reason": "GA requested Planner for non-Goal-owned Responsibilities",
                },
            )
        if (
            ga_planner_refs
            and ga_planner_refs <= planner_refs_in_flight
            and self._continuity_unchanged(association, ga_planner_refs)
        ):
            # The UMI-triggered Planner already plans exactly this unchanged meaning.
            logger.info("ga_planner_request_coalesced sid=%s refs=%s", sid, ",".join(sorted(ga_planner_refs)))
            ga_planner_refs = set()
        planning_work_request = (
            self._subset_work_request(work_request, ga_planner_refs)
            if ga_planner_refs
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
        goal_ids = planner_advance_projection.association_goal_ids(association)
        runtime = self.adapter.interaction_runtime.runtime
        for item in context.get("active_goal_snapshots") or []:
            if isinstance(item, dict) and item.get("goal_id") in goal_ids:
                runtime.record_goal_state(str(item["goal_id"]), item)
        for goal in association.new_goals:
            runtime.record_goal_state(goal.goal_id, goal.model_dump(mode="json"))
        retained = planner_advance_projection.retained_existing_work_activities(
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
        if planning_work_request is not None and not has_named_goal_cancellation:
            planning_context["canonical_fast_revision_reason"] = "ga_model_requested_reentry"
            planning_task = asyncio.create_task(self._observe_workflow_stage(
                sid=sid,
                stage="fast_planner",
                input_payload={"goal_association": association, "trigger": "goal_association", "existing_work_activities": planning_context["existing_work_activities"]},
                operation=self.agent_client.resolve_plan(
                    session,
                    request=planning_work_request.model_copy(deep=True, update={
                        "planning_task_id": "ga:" + goal_association_fingerprint(association),
                        "context": planning_context,
                        "history": history,
                    }),
                    timeout_ms=self.policy.planner_timeout_ms,
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
        run = self._begin_resolution(session, work_request)
        try:
            await self._start_cognition_fanout(run)
            await self._await_first_plan(run)
            resolution = await self._finish_without_goal_association(run)
            if resolution is not None:
                return resolution
            await self._adopt_goal_association(run)
            resolution = await self._finish_without_canonical_goals(run)
            if resolution is not None:
                return resolution
            self._scope_work_to_goals(run)
            await self._settle_competing_plans(run)
            await self._plan_uncovered_goals(run)
            resolution = await self._finish_without_planner(run)
            if resolution is not None:
                return resolution
            await self._require_requested_plan(run)
            self._commit_planner_gaps(run)
            self._refresh_planning_situation(run)
            await self._resolve_terminal_plan(run)
            await self._judge_terminal_plan(run)
            await self._admit_terminal_plan(run)
            resolution = await self._finish_execution_only_plan(run)
            if resolution is not None:
                return resolution
            return await self._respond_to_terminal_plan(run)
        except asyncio.CancelledError:
            # The Host owns the outer foreground deadline. If it cancels this
            # pipeline, stop only Fast work that never reached canonical Goal/Plan
            # binding, then propagate cancellation so the Host records the timeout.
            await self.cancel_social_interaction()
            await self._cancel_uncommitted_fast_work(run, "foreground_deadline")
            raise
        except CognitiveStageFailure as exc:
            return await self._finish_after_stage_failure(run, exc)
        except Exception as exc:
            return await self._finish_after_runtime_failure(run, exc)

    def _begin_resolution(
        self,
        session: Any,
        work_request: CognitiveWorkRequest,
    ) -> _ResolutionRun:
        """Bind the admitted Work request and the initial state of one resolution."""

        run = _ResolutionRun(session=session, work_request=work_request)
        run.started = time.perf_counter()
        run.text = run.work_request.text
        run.sid = str(run.work_request.sid or "")
        run.language = run.work_request.language or "auto"
        run.history = list(run.work_request.history)
        run.context = dict(run.work_request.context)
        run.context["interaction_context"] = self._interaction_context(
            sid=run.sid,
            context=run.context,
        )
        run.timings: dict[str, float] = {}
        run.association: GoalAssociationResolution | None = None
        run.fast_advance: FastPlannerAdvance | None = None
        run.fast_plan: CanonicalPlan | None = None
        run.terminal_plan: CanonicalPlan | None = None
        run.interaction: InteractionResponse | None = None
        run.goal_state_results: list[dict[str, Any]] = []
        run.goal_state_commit_stage = ""
        run.stage_diagnostics: list[dict[str, Any]] = []
        run.fast_planner_path = ""
        run.association_task: asyncio.Task[_GoalAssociationStageResult] | None = None
        run.umi_planning_task: asyncio.Task[None] | None = None
        run.umi_planning_superseded = False
        run.ga_revision_failure_contained = False
        run.planning_snapshot: dict[str, Any] | None = None
        run.planning_commit: dict[str, Any] | None = None
        run.state_social_task: asyncio.Task[Any] | None = None
        run.initial_social_task: asyncio.Task[Any] | None = None
        run.planner_refs: list[str] = []
        run.initial_meaning_uncertainty_count = len(run.work_request.meaning_uncertainties)
        run.post_ga_meaning_uncertainty_count = run.initial_meaning_uncertainty_count
        run.planner_waited_for_goal_continuity = False
        run.goal_association_dependency_added = False

        run.fast_vocal_activity_ids: list[str] = []
        run.ready_fast_communicative_executions: list[Any] = []
        run.fast_communicative_realization_status = "not_started"
        run.ready_fast_capability_execution: Any | None = None
        run.ready_fast_capability_status = "not_started"
        run.retained_work_activities: list[dict[str, Any]] = []
        run.retained_work_reconciliation_status = "not_applicable"
        run.work_reconciliation_required = False
        run.work_reconciliation_activity_count = 0
        return run

    def _goal_planning_started(self, run: _ResolutionRun) -> bool:
        return bool(run.association_task is not None and run.association_task.done()
            and not run.association_task.cancelled() and run.association_task.exception() is None
            and run.association_task.result().planning_task is not None)

    def _resolution_path_metadata(self, run: _ResolutionRun) -> dict[str, Any]:
        return {
            "social_cognition_started": run.state_social_task is not None,
            "model_driven_cognitive_orchestration": True,
            "requested_cognitive_authorities": [
                item.authority for item in run.work_request.cognitive_requests
            ],
            "goal_association_dependency_added": (
                run.goal_association_dependency_added
            ),
            "fast_planner_advance": (
                run.fast_advance.model_dump(mode="json", exclude_none=True)
                if run.fast_advance is not None
                else None
            ),
            "fast_planner_path": run.fast_planner_path,
            "terminal_planner_tier": (
                run.terminal_plan.planner_tier if run.terminal_plan is not None else ""
            ),
            "authoritative_goal_count": (
                len(planner_advance_projection.association_goal_ids(run.association))
                if run.association is not None
                else 0
            ),
            "fast_goal_outcome_count": (
                len(run.fast_plan.goal_outcomes) if run.fast_plan is not None else 0
            ),
            "fast_executable_step_count": (
                len(run.fast_plan.steps) if run.fast_plan is not None else 0
            ),
            "goal_state_commit_stage": run.goal_state_commit_stage,
            "fast_vocal_activity_ids": list(run.fast_vocal_activity_ids),
            "fast_communicative_realization_status": (
                run.fast_communicative_realization_status
            ),
            "fast_capability_activity_status": run.ready_fast_capability_status,
            "retained_work_reconciliation_status": (
                run.retained_work_reconciliation_status
            ),
            "work_reconciliation_required": run.work_reconciliation_required,
            "work_reconciliation_activity_count": (
                run.work_reconciliation_activity_count
            ),
            "umi_fanout_concurrent": not run.planner_waited_for_goal_continuity,
            "planner_waited_for_goal_continuity": (
                run.planner_waited_for_goal_continuity
            ),
            "meaning_uncertainty_count_at_umi": (
                run.initial_meaning_uncertainty_count
            ),
            "meaning_uncertainty_count_after_ga": (
                run.post_ga_meaning_uncertainty_count
            ),
            "umi_planning_superseded": run.umi_planning_superseded,
            "ga_revision_failure_contained": run.ga_revision_failure_contained,
            "independent_goal_planning": self._goal_planning_started(run),
            "planning_commit": run.planning_commit,
            "retained_work_activities": [item for item in run.retained_work_activities
                if run.terminal_plan is not None and item["activity_id"] not in run.terminal_plan.cancel_activity_ids],
            "goal_grouped_task_list": True,
        }

    async def _cancel_uncommitted_fast_work(self, run: _ResolutionRun, reason: str) -> None:
        """Stop unfinished fan-out while retaining any completed GA truth."""

        if run.umi_planning_task is not None and not run.umi_planning_task.done():
            run.umi_planning_task.cancel()
            await asyncio.gather(run.umi_planning_task, return_exceptions=True)
        if self._goal_planning_started(run):
            pending_plan = run.association_task.result().planning_task
            if pending_plan is not None:
                pending_plan.cancel()
                await asyncio.gather(pending_plan, return_exceptions=True)
        await self.adapter.interaction_runtime.runtime.discard_prepared_planner_work(
            self._context_turn_id(run.context, run.sid)
        )
        if run.association_task is not None:
            if not run.association_task.done():
                run.association_task.cancel()
            # A concurrent GA transaction may have committed canonical Goal
            # truth before Fast fails. Retrieve its completed stage result and
            # project those already-established facts into the public failure
            # resolution rather than reporting an empty Goal state.
            association_results = await asyncio.gather(
                run.association_task,
                return_exceptions=True,
            )
            association_result = association_results[0]
            if isinstance(association_result, _GoalAssociationStageResult):
                run.association = association_result.association
                run.context = association_result.context
                run.history = association_result.history
                run.planning_context = association_result.planning_context
                run.situation = association_result.situation
                run.goal_state_results = association_result.goal_state_results
                run.goal_state_commit_stage = association_result.goal_state_commit_stage
                run.has_named_goal_cancellation = (
                    association_result.has_named_goal_cancellation
                )
                run.has_goal_replacement = association_result.has_goal_replacement
        await self._cancel_early_safe_reads(run, reason)

    async def _cancel_early_safe_reads(self, run: _ResolutionRun, reason: str) -> None:
        """Stop safe reads a Fast Plan started before Goal binding."""

        execution = run.ready_fast_capability_execution
        execution_status = run.ready_fast_capability_status
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
            run.ready_fast_capability_status = "cancelled_before_goal_binding:" + reason
        except Exception as cleanup_exc:
            run.ready_fast_capability_status = (
                "cancellation_failed_before_goal_binding:"
                + type(cleanup_exc).__name__
            )
            logger.warning(
                "fast_activity_cleanup_failed sid=%s reason=%s error_type=%s error=%s",
                run.sid,
                reason,
                type(cleanup_exc).__name__,
                cleanup_exc,
            )

    async def _finish_independent_social_interaction(self, run: _ResolutionRun) -> None:
        """Work failure does not revoke this turn's already admitted SC work."""
        # State re-entry may replace the current task with intentional silence.
        # Join the original delivery too; silence cannot erase its receipt.
        for task in dict.fromkeys((run.initial_social_task, run.state_social_task)):
            if task is None:
                continue
            try:
                result, = await asyncio.gather(task, return_exceptions=True)
            except asyncio.CancelledError:
                # Outer deadline/interruption still owns submitted delivery.
                await self.cancel_social_interaction()
                raise
            if isinstance(result, BaseException):
                run.stage_diagnostics.append(self._stage_failure_metadata(
                    "social_cognition",
                    {"error_type": type(result).__name__, "error": str(result)},
                    default_failure_class="social_interaction_failed",
                ))
            elif result is not None:
                _social_result, response = result
                if run.interaction is None or response.speech or not run.interaction.speech:
                    run.interaction = response

    async def _communicate_terminal_work_failure(
        self, run: _ResolutionRun,
        *, stage: str, failure_class: str, failure_domain: str, failure_reason: str,
    ) -> None:
        """Give terminal Work failure and its known cause to Social Cognition.

        Host/runtime preserves diagnostic identity, while SC owns the user-facing
        abstraction. A typed result Need makes terminal failure an explicit
        communication obligation instead of an optional social update.
        """
        await self._finish_independent_social_interaction(run)
        if self.policy.mode != "apply":
            return
        failure_reference = f"work_failure:{run.turn_id}:{stage}"[:200]
        known_cause = " ".join(str(failure_reason or "").strip().split())[:500]
        failed_ref_set = set(run.planner_refs)
        failure_work_request = (
            self._subset_work_request(run.work_request, failed_ref_set)
            if failed_ref_set
            else run.work_request.model_copy(deep=True)
        )
        failure_context = {
            **failure_work_request.context,
            "work_failure": {
                "status": "failed",
                "effect_execution": "not_authorized_or_not_completed",
                "work_decision_pending": False,
                "failure_domain": failure_domain or "cognitive_work",
                "known_cause": known_cause,
                # Internal stage/class remain diagnostic identity only. SC may use
                # them to understand provenance but must not expose them verbatim.
                "internal_stage": stage,
                "internal_failure_class": failure_class,
            },
        }
        failure_request = failure_work_request.model_copy(
            deep=True, update={"context": failure_context},
        )
        failure_need = SocialCommunicationNeed(
            need_id=communication_need_id(
                "runtime:" + run.turn_id, failure_reference
            ),
            owner="runtime",
            kind="result",
            source_responsibility_refs=[
                item.local_ref for item in failure_request.responsibilities
            ],
            reference_id=failure_reference,
            facts={
                "status": "failed",
                "effect_execution": "not_authorized_or_not_completed",
                "failure_domain": failure_domain or "cognitive_work",
                "known_cause": known_cause,
                "required_result_update": True,
            },
            delivery_phase="immediate",
        )
        failure_task = self.start_state_interaction(
            run.session, work_request=failure_request, turn_id=run.turn_id,
            trigger="work_state",
            source_refs=[failure_reference],
            work_decision_pending=False,
            communication_needs=[failure_need],
        )
        if failure_task is None:
            return
        try:
            result, = await asyncio.gather(failure_task, return_exceptions=True)
        except asyncio.CancelledError:
            await self.cancel_social_interaction()
            raise
        if isinstance(result, BaseException):
            run.stage_diagnostics.append(self._stage_failure_metadata(
                "social_cognition",
                {"error_type": type(result).__name__, "error": str(result)},
                default_failure_class="work_failure_social_interaction_failed",
            ))
        elif result is not None:
            _social_result, run.interaction = result

    async def _plan_current_responsibilities(
        self, run: _ResolutionRun,
        request_for_plan: CognitiveWorkRequest,
        plan_context: dict[str, Any],
        plan_history: list[dict[str, Any]],
    ) -> None:
        planner_started = time.perf_counter()
        stream_request = request_for_plan.model_copy(
            deep=True, update={
                "planning_task_id": "umi:" + run.turn_id,
                "sid": run.turn_id,
                "context": plan_context,
                "history": plan_history,
            }
        )
        terminal_frame: FastPlannerStreamTerminal | None = None
        async for frame in self.agent_client.stream_plan_advance(
            run.session, request=stream_request, timeout_ms=self.policy.planner_timeout_ms,
        ):
            if isinstance(frame, FastPlannerStreamFailure):
                raise CognitiveStageFailure("fast_planner_stream", frame.model_dump(mode="json"))
            if not isinstance(frame, FastPlannerStreamTerminal) or terminal_frame is not None:
                raise ValueError("Fast Work stream must contain exactly one terminal decision")
            if frame.turn_id != run.turn_id or frame.advance.turn_id != run.turn_id:
                raise ValueError("Fast Work stream changed turn identity")
            terminal_frame = frame
        if terminal_frame is None:
            raise ValueError("Fast Work stream ended without a terminal decision")
        run.fast_advance = terminal_frame.advance
        self._record_workflow_stage(
            sid=run.sid, stage="fast_planner_stream_terminal",
            started_monotonic_ms=planner_started * 1000.0,
            finished_monotonic_ms=time.perf_counter() * 1000.0,
            status="resolved", input_payload=stream_request,
            output_payload=terminal_frame, errors=[], attempt=1,
            metadata={"semantic_owner": "planner", "communication_authority": False},
        )
        run.timings["fast_planner_activity_plan"] = (
            time.perf_counter() - planner_started
        ) * 1000.0
        run.timings["fast_planner_advance"] = run.timings[
            "fast_planner_activity_plan"
        ]
        run.ready_fast_capability_status = "prepared_until_canonical_validation"
        capability_activities = [item for item in run.fast_advance.activities
                                 if isinstance(item, FastPlannerCapabilityActivity) and not item.deferred]
        if self.policy.mode == "apply" and capability_activities and not self._goal_planning_started(run) and not any(
            item.role != "capability" and item.timing == "sequential" for item in run.fast_advance.activities
        ):
            eligible = await self.adapter.interaction_runtime.prepare_fast_planner_capability_activities(
                capability_activities, turn_id=run.turn_id,
            )
            if eligible:
                run.ready_fast_capability_execution = await self.adapter.interaction_runtime.start_fast_planner_capability_activities(
                    eligible, session_id=run.sid, turn_id=run.turn_id, language=run.language,
                )
                run.ready_fast_capability_status = "safe_reads_dispatched_before_goal_binding"

    async def _start_cognition_fanout(self, run: _ResolutionRun) -> None:
        """Start Social Cognition and Goal Association for the admitted turn, then yield once so both begin."""

        run.turn_id = self._context_turn_id(run.context, run.sid)

        run.planner_refs = self._cognitive_request_responsibility_refs(
            run.work_request, "planner"
        )
        explicit_ga_requested = any(
            item.authority == "goal_association"
            for item in run.work_request.cognitive_requests
        )
        ga_refs = self._cognitive_request_responsibility_refs(
            run.work_request, "goal_association"
        )
        run.goal_association_dependency_added = bool(run.planner_refs and not explicit_ga_requested)
        run.speculative_ref_set = set(run.planner_refs)
        run.speculative_work_request = (
            self._subset_work_request(run.work_request, run.speculative_ref_set)
            if run.speculative_ref_set
            else None
        )

        # Initial Social Cognition is a standing interaction responsibility for every
        # fresh admitted addressed turn, not a model-authored routing choice. Runtime
        # therefore wakes SC mechanically with the complete accepted turn. UMI still
        # selects only non-standing GA/Planner cognition; Runtime may close Planner's
        # hard turn-wide GA dependency without inferring readiness from WHAT labels.
        run.state_social_task = self.start_state_interaction(
            run.session,
            work_request=run.work_request,
            turn_id=run.turn_id,
        )
        run.initial_social_task = run.state_social_task
        run.association_task = (
            asyncio.create_task(
                self._resolve_and_commit_goal_association(
                    run.session,
                    work_request=run.work_request,
                    sid=run.sid,
                    text=run.text,
                    turn_id=run.turn_id,
                    context=run.context,
                    history=run.history,
                    timings=run.timings,
                    planner_refs_in_flight=frozenset(run.speculative_ref_set),
                )
            )
            if ga_refs
            else None
        )
        if run.state_social_task is not None or run.association_task is not None:
            await asyncio.sleep(0)

    async def _await_first_plan(self, run: _ResolutionRun) -> None:
        """Run the Planner over the UMI-requested Responsibilities and settle it against a GA-requested plan."""

        if run.speculative_work_request is not None:
            run.umi_planning_task = asyncio.create_task(
                self._plan_current_responsibilities(run,
                    run.speculative_work_request, run.context, run.history
                ),
                name="umi-planning:" + run.turn_id,
            )
            if run.association_task is not None:
                await asyncio.wait(
                    {run.umi_planning_task, run.association_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                umi_succeeded = (
                    run.umi_planning_task.done()
                    and not run.umi_planning_task.cancelled()
                    and run.umi_planning_task.exception() is None
                )
                if not umi_succeeded and run.umi_planning_task.done():
                    # A failed first plan defers only to a GA-requested plan
                    # settled after association; otherwise its failure stands.
                    early_outcome, = await asyncio.gather(
                        run.association_task, return_exceptions=True
                    )
                    if (
                        isinstance(early_outcome, BaseException)
                        or early_outcome.planning_task is None
                    ):
                        await run.umi_planning_task
                elif not umi_succeeded:
                    # A running first plan is settled against a GA-requested
                    # plan after association, never by completion order.
                    early_association = await run.association_task
                    if early_association.planning_task is None:
                        await run.umi_planning_task
            else:
                await run.umi_planning_task
        else:
            run.planner_waited_for_goal_continuity = False

    async def _finish_without_goal_association(self, run: _ResolutionRun) -> CognitiveRuntimeResolution | None:
        """Finish a turn for which UMI requested no Goal Association."""

        if run.association_task is None:
            if run.state_social_task is not None:
                run.social_resolved = await run.state_social_task
                if run.social_resolved is None:
                    raise CognitiveStageFailure(
                        "social_cognition",
                        {
                            "failure_class": "requested_social_interaction_unavailable",
                            "failure_domain": "model_or_runtime",
                            "architecture_attribution": "social_cognition",
                            "retryable": True,
                        },
                    )
                run._social_result, run.interaction = run.social_resolved
            else:
                run.interaction = self._no_interaction_response(
                    sid=run.sid,
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
                interaction=run.interaction if self.policy.mode == "apply" else None,
                timings=run.timings,
                started=run.started,
                metadata={
                    **self._resolution_path_metadata(run),
                    "model_driven_cognitive_orchestration": True,
                    "requested_cognitive_authorities": [
                        item.authority for item in run.work_request.cognitive_requests
                    ],
                },
            )

    async def _adopt_goal_association(self, run: _ResolutionRun) -> None:
        """Adopt the committed Goal Association stage result as the turn's Goal state."""

        run.association_stage = await run.association_task
        run.association = run.association_stage.association
        run.context = run.association_stage.context
        run.history = run.association_stage.history
        run.planning_context = run.association_stage.planning_context
        run.situation = run.association_stage.situation
        run.goal_state_results = run.association_stage.goal_state_results
        run.goal_state_commit_stage = run.association_stage.goal_state_commit_stage
        run.has_named_goal_cancellation = (
            run.association_stage.has_named_goal_cancellation
        )
        run.has_goal_replacement = run.association_stage.has_goal_replacement

        run.association_goal_ids = planner_advance_projection.association_goal_ids(run.association)
        run.goal_ids_by_responsibility = planner_advance_projection.goal_ids_by_responsibility(run.association)
        run.goal_responsibility_refs = set(run.goal_ids_by_responsibility)

    async def _finish_without_canonical_goals(self, run: _ResolutionRun) -> CognitiveRuntimeResolution | None:
        """Finish a turn whose Goal Association produced no canonical Goal."""

        if not run.association_goal_ids:
            expected_refs = {item.local_ref for item in run.work_request.responsibilities}
            non_goal_refs = set(run.association.non_goal_responsibility_refs)
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
            # GA has completed historical continuity without canonical Goal-owned
            # Work. A model-requested Planner may still reason about conversational
            # HOW (for example whether a joke/chat Responsibility is a direct response).
            # Let that bounded cognition finish, but it owns neither wording nor Goal
            # persistence and cannot turn a successful SC delivery into failure.
            turn_local_planner_status = "not_requested"
            if run.umi_planning_task is not None:
                planner_result, = await asyncio.gather(
                    run.umi_planning_task, return_exceptions=True
                )
                if isinstance(planner_result, BaseException):
                    turn_local_planner_status = "failed_nonblocking"
                    run.stage_diagnostics.append(self._stage_failure_metadata(
                        "fast_planner_stream",
                        {
                            "error_type": type(planner_result).__name__,
                            "error": str(planner_result),
                            "failure_domain": "conversational_how",
                            "architecture_attribution": "planner",
                            "retryable": False,
                        },
                        default_failure_class="turn_local_planner_failed",
                    ))
                else:
                    turn_local_planner_status = "considered"
            if self.policy.mode != "apply":
                return self._finish(
                    mode=self.policy.mode,
                    status="skipped" if self.policy.mode == "off" else "report_only",
                    association=run.association,
                    fast_plan=None,
                    terminal_plan=None,
                    timings=run.timings,
                    started=run.started,
                    metadata={
                        **self._resolution_path_metadata(run),
                        "goal_continuity_checked": True,
                        "planner_avoided_no_goal": True,
                        "turn_local_planner_status": turn_local_planner_status,
                        "non_goal_responsibility_refs": list(
                            run.association.non_goal_responsibility_refs
                        ),
                    },
                )
            if run.state_social_task is None:
                return self._finish(
                    mode="apply", status="applied", association=run.association,
                    fast_plan=None, terminal_plan=None,
                    interaction=self._no_interaction_response(
                        sid=run.sid,
                        reason="UMI requested GA but no SC cognition",
                    ),
                    timings=run.timings, started=run.started,
                    metadata={
                        **self._resolution_path_metadata(run),
                        "goal_continuity_checked": True,
                        "planner_avoided_no_goal": True,
                        "turn_local_planner_status": turn_local_planner_status,
                        "model_driven_cognitive_orchestration": True,
                    },
                )
            run.social_resolved = await run.state_social_task
            if run.social_resolved is None:
                raise CognitiveStageFailure(
                    "social_cognition",
                    {
                        "failure_class": "social_only_interaction_unavailable",
                        "failure_domain": "model_or_runtime",
                        "architecture_attribution": "social_cognition",
                        "retryable": True,
                    },
                )
            run._social_result, run.interaction = run.social_resolved
            return self._finish(
                mode="apply", status="applied", association=run.association,
                fast_plan=None, terminal_plan=None, interaction=run.interaction,
                timings=run.timings, started=run.started,
                metadata={
                    **self._resolution_path_metadata(run),
                    "goal_continuity_checked": True,
                    "planner_avoided_no_goal": True,
                    "turn_local_planner_status": turn_local_planner_status,
                    "non_goal_responsibility_refs": list(
                        run.association.non_goal_responsibility_refs
                    ),
                },
            )

    def _scope_work_to_goals(self, run: _ResolutionRun) -> None:
        """Narrow the Work request to Goal-owned Responsibilities and start any Social Cognition GA requested."""

        remaining_meaning_uncertainties = self._remaining_meaning_uncertainties(
            run.work_request, run.association
        )
        run.post_ga_meaning_uncertainty_count = len(remaining_meaning_uncertainties)
        run.post_ga_request = run.work_request.model_copy(
            deep=True,
            update={"meaning_uncertainties": remaining_meaning_uncertainties},
        )
        run.work_request = self._subset_work_request(
            run.post_ga_request, run.goal_responsibility_refs
        )

        run.ga_planner_requested = any(
            item.authority == "planner" for item in run.association.cognitive_requests
        )
        ga_social_request = next(
            (item for item in run.association.cognitive_requests if item.authority == "social_cognition"),
            None,
        )
        if (
            ga_social_request is not None
            and run.initial_social_task is not None
            and self._continuity_unchanged(run.association, set(ga_social_request.responsibility_refs))
        ):
            # The standing SC of this turn already holds this unchanged meaning.
            logger.info("ga_social_request_coalesced sid=%s refs=%s", run.sid,
                        ",".join(sorted(ga_social_request.responsibility_refs)))
            ga_social_request = None
        if ga_social_request is not None and self.policy.mode == "apply":
            ga_social_refs = set(ga_social_request.responsibility_refs)
            ga_social_request_work = self._subset_work_request(
                run.post_ga_request.model_copy(
                    deep=True, update={"context": run.planning_context, "history": run.history}
                ),
                ga_social_refs,
            )
            run.state_social_task = self.start_state_interaction(
                run.session,
                work_request=ga_social_request_work,
                turn_id=run.turn_id,
                trigger="goal_state",
                source_refs=["ga:" + goal_association_fingerprint(run.association)],
                goal_ids=run.association_goal_ids,
            )

    async def _settle_competing_plans(self, run: _ResolutionRun) -> None:
        """Choose between the UMI plan and a GA-requested plan; completion order never decides."""

        if run.umi_planning_task is not None and run.association_stage.planning_task is not None:
            # UMI and committed GA state are independent Planner triggers. A
            # successful GA-requested plan rests on newer continuity state and
            # supersedes the first plan; completion order never decides, and a
            # failed revision does not erase a valid first plan (Charter).
            ga_result, = await asyncio.gather(
                run.association_stage.planning_task, return_exceptions=True
            )
            ga_failed = isinstance(ga_result, BaseException) or (
                self._fast_plan_path(ga_result) == "contract_failure"
            )
            if not ga_failed:
                if not run.umi_planning_task.done():
                    run.umi_planning_task.cancel()
                    await asyncio.gather(run.umi_planning_task, return_exceptions=True)
                    run.umi_planning_superseded = True
                elif not run.umi_planning_task.cancelled() and run.umi_planning_task.exception() is not None:
                    umi_failure = run.umi_planning_task.exception()
                    run.stage_diagnostics.append(self._stage_failure_metadata(
                        "fast_planner_stream",
                        umi_failure.failure_metadata
                        if isinstance(umi_failure, CognitiveStageFailure)
                        else {"error_type": type(umi_failure).__name__, "error": str(umi_failure)},
                        default_failure_class="first_plan_failed_ga_plan_retained",
                    ))
            else:
                umi_result, = await asyncio.gather(
                    run.umi_planning_task, return_exceptions=True
                )
                ga_planner_refs = {
                    ref
                    for item in run.association_stage.association.cognitive_requests
                    if item.authority == "planner"
                    for ref in item.responsibility_refs
                }
                if (
                    not isinstance(umi_result, BaseException)
                    and run.fast_advance is not None
                    and ga_planner_refs <= run.speculative_ref_set
                ):
                    failure = (
                        ga_result.failure_metadata
                        if isinstance(ga_result, CognitiveStageFailure)
                        else {"error_type": type(ga_result).__name__, "error": str(ga_result)}
                        if isinstance(ga_result, BaseException)
                        else ga_result.metadata
                    )
                    run.stage_diagnostics.append(self._stage_failure_metadata(
                        "fast_planner",
                        {**failure, "architecture_attribution": "planner"},
                        default_failure_class="ga_revision_failed_first_plan_retained",
                    ))
                    run.association_stage = replace(run.association_stage, planning_task=None)
                    run.ga_revision_failure_contained = True
                elif isinstance(umi_result, BaseException):
                    # Both plans failed; retain the first plan's cause beside the
                    # GA failure that the turn reports.
                    run.stage_diagnostics.append(self._stage_failure_metadata(
                        "fast_planner_stream",
                        umi_result.failure_metadata
                        if isinstance(umi_result, CognitiveStageFailure)
                        else {"error_type": type(umi_result).__name__, "error": str(umi_result)},
                        default_failure_class="first_plan_failed",
                    ))

    async def _plan_uncovered_goals(self, run: _ResolutionRun) -> None:
        """Plan once over GA's Goal scope when the first plan missed Goal-owned Responsibilities."""

        uncovered_goal_refs = sorted(run.goal_responsibility_refs - run.speculative_ref_set) if run.speculative_ref_set else []
        if run.fast_advance is not None and run.association_stage.planning_task is None and uncovered_goal_refs:
            # GA made Goals for Responsibilities the speculative Planner never saw, and one
            # Plan must bind every Goal (live 2026-10-12: the turn failed on a Goal without a
            # decision). Plan once over exactly GA's Goal-owned scope; non-Goal refs stay out.
            logger.info("fast_planner_scope_extended_to_ga_goals sid=%s uncovered=%s",
                        run.sid, ",".join(uncovered_goal_refs))
            # That Plan supersedes the speculative one: drop its prepared Work and stop
            # any safe read it started, or the new Plan cannot be prepared (live
            # 2026-10-15: "one UMI planning task cannot replace its prepared result").
            await self.adapter.interaction_runtime.runtime.discard_prepared_planner_work(
                self._context_turn_id(run.context, run.sid)
            )
            await self._cancel_early_safe_reads(run, "scope_extended_to_ga_goals")
            run.ready_fast_capability_execution = None
            run.fast_advance = None
            await self._plan_current_responsibilities(run,
                self._subset_work_request(run.post_ga_request, run.goal_responsibility_refs),
                run.planning_context, run.history,
            )

    async def _finish_without_planner(self, run: _ResolutionRun) -> CognitiveRuntimeResolution | None:
        """Finish a Goal-continuity turn for which no Planner decision was requested."""

        if (
            run.fast_advance is None
            and run.association_stage.planning_task is None
            and not run.planner_refs
            and not run.ga_planner_requested
        ):
            if run.state_social_task is not None:
                run.social_resolved = await run.state_social_task
                if run.social_resolved is None:
                    raise CognitiveStageFailure(
                        "social_cognition",
                        {
                            "failure_class": "requested_social_interaction_unavailable",
                            "failure_domain": "model_or_runtime",
                            "architecture_attribution": "social_cognition",
                            "retryable": True,
                        },
                    )
                run._social_result, run.interaction = run.social_resolved
            else:
                run.interaction = self._no_interaction_response(
                    sid=run.sid,
                    reason="UMI requested Goal continuity without Planner or SC cognition",
                )
            run.direct_social_completion_results = (
                self._reconcile_delivered_direct_social_response(
                    association=run.association,
                    interaction=run.interaction,
                    sid=run.sid,
                )
            )
            return self._finish(
                mode="apply",
                status="applied",
                association=run.association,
                fast_plan=None,
                terminal_plan=None,
                interaction=run.interaction,
                goal_state_results=run.goal_state_results,
                timings=run.timings,
                started=run.started,
                metadata={
                    **self._resolution_path_metadata(run),
                    "model_driven_cognitive_orchestration": True,
                    "planner_not_requested_by_umi": True,
                    "direct_social_completion_results": (
                        run.direct_social_completion_results
                    ),
                },
            )

    async def _require_requested_plan(self, run: _ResolutionRun) -> None:
        """Plan requested Responsibilities still without a decision and bind ready communicative Activities."""

        if run.fast_advance is None and run.association_stage.planning_task is None and run.planner_refs:
            await self._plan_current_responsibilities(run,
                self._subset_work_request(run.post_ga_request, set(run.planner_refs)),
                run.planning_context, run.history
            )
        if run.fast_advance is None and run.association_stage.planning_task is None and (run.planner_refs or run.ga_planner_requested):
            raise CognitiveStageFailure(
                "fast_planner_advance",
                {
                    "failure_class": "missing_requested_responsibility_activity_plan",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "cognitive_orchestration",
                    "retryable": False,
                },
            )
        if (
            self.policy.mode == "apply"
            and run.goal_state_commit_stage == "goal_association"
            and run.ready_fast_communicative_executions
        ):
            for ready_execution in run.ready_fast_communicative_executions:
                self.adapter.interaction_runtime.bind_fast_planner_communicative_execution(
                    ready_execution,
                    session_id=run.sid,
                    goal_ids_by_responsibility=run.goal_ids_by_responsibility,
                )

    def _commit_planner_gaps(self, run: _ResolutionRun) -> None:
        """Prepare Work reconciliation and commit the Planner's information gaps to Goal state."""

        run.retained_work_activities = [item for item in run.planning_context.get("existing_work_activities", [])
                                    if item.get("origin") == "retained_runtime"]
        run.work_reconciliation_required = run.association_stage.planning_task is not None
        run.canonical_fast_revision_reason = (
            "ga_model_requested_reentry"
            if run.association_stage.planning_task is not None
            else ""
        )
        run.planning_snapshot = run.association_stage.planning_snapshot
        if run.work_reconciliation_required:
            run.work_reconciliation_activity_count = len(
                run.planning_context["existing_work_activities"]
            )
        if run.canonical_fast_revision_reason:
            run.planning_context["canonical_fast_revision_reason"] = (
                run.canonical_fast_revision_reason
            )
        planner_gaps_by_goal_id = (
            {}
            if run.canonical_fast_revision_reason
            else planner_advance_projection.planner_gaps_by_goal_id(
                advance=run.fast_advance,
                association=run.association,
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
                    turn_id=run.turn_id,
                    sid=run.sid,
                    user_text=run.text,
                    source="goal_driven_cognitive_runtime_fast_planner",
                )
            except Exception as exc:
                self._record_workflow_stage(
                    sid=run.sid,
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
                sid=run.sid,
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
            run.goal_state_results.extend(gap_results)
            run.goal_state_commit_stage = (
                f"{run.goal_state_commit_stage}+planner_information_gap"
                if run.goal_state_commit_stage
                else "planner_information_gap"
            )

    def _refresh_planning_situation(self, run: _ResolutionRun) -> None:
        """Refresh the planning Situation, interaction ledger and interaction context for the Goals."""

        planning_situation = build_situation_projection(
            context=run.context,
            turn_id=run.turn_id,
            focus_goal_ids=run.association_goal_ids or run.situation.focus_goal_ids,
            revision=run.situation.revision + 1,
        )
        run.planning_context["situation"] = planning_situation.prompt_projection()
        if self.policy.mode == "apply" and self.interaction_ledger is not None:
            self.interaction_ledger.record_goal_association(
                session_id=run.sid,
                turn_id=run.association.turn_id,
                interaction_id="",
                association_id=goal_association_fingerprint(run.association),
                goal_ids=run.association_goal_ids,
                relationships=[
                    *[item.relationship for item in run.association.associations],
                    *(["new"] if run.association.new_goals else []),
                ],
            )
        run.planning_context["interaction_context"] = self._interaction_context(
            sid=run.sid,
            context=run.planning_context,
            goal_ids=run.association_goal_ids,
        )
        if not run.association_goal_ids:
            raise CognitiveStageFailure(
                "goal_association",
                {
                    "failure_class": "empty_canonical_goal_set",
                    "failure_domain": "model_contract",
                    "architecture_attribution": "not_evaluated",
                    "retryable": True,
                    "reason": "resolved Goal Association produced no canonical goals",
                    "status": run.association.resolution_status,
                },
            )

    async def _resolve_terminal_plan(self, run: _ResolutionRun) -> None:
        """Take the GA-requested Plan revision, or bind the Planner advance, as the terminal Plan."""

        if run.canonical_fast_revision_reason:
            # GA explicitly requested another Planner decision after continuity.
            # Runtime supplies current Goal/Work/Evidence state but does not infer
            # that a Goal update, retained Activity, scope change, or field equality
            # requires replanning.
            run.stage = time.perf_counter()
            if run.association_stage.planning_task is not None:
                run.fast_plan = await run.association_stage.planning_task
            else:
                run.fast_plan = await self._observe_workflow_stage(
                    sid=run.sid,
                    stage="fast_planner",
                    input_payload={
                        "user_text": run.text,
                        "goal_association": run.association,
                        "revision_reason": run.canonical_fast_revision_reason,
                        "interaction_context": run.planning_context.get(
                            "interaction_context", {}
                        ),
                    },
                    operation=self.agent_client.resolve_plan(
                        run.session,
                        request=run.work_request.model_copy(
                            update={
                                "context": run.planning_context,
                                "history": run.history,
                            }
                        ),
                        timeout_ms=self.policy.planner_timeout_ms,
                    ),
                )
            run.timings["fast_planner"] = (
                time.perf_counter() - run.stage
            ) * 1000.0
            fast_failure = self._optional_stage_failure_metadata(
                "fast_planner", run.fast_plan.metadata
            )
            if fast_failure is not None:
                run.stage_diagnostics.append(fast_failure)
            run.terminal_plan = run.fast_plan
            run.fast_planner_path = self._fast_plan_path(run.fast_plan)
            if run.fast_planner_path == "contract_failure":
                # A rejected Planner result fails closed; nothing re-plans it.
                fast_failure = self._optional_stage_failure_metadata(
                    "fast_planner", run.fast_plan.metadata
                ) or self._stage_failure_metadata(
                    "fast_planner",
                    run.fast_plan.metadata,
                    default_failure_class=str(
                        run.fast_plan.metadata.get("reason") or "fast_planner_contract_failure"
                    ),
                )
                raise CognitiveStageFailure("fast_planner", fast_failure)
        else:
            run.fast_plan = planner_advance_projection.canonical_plan_from_fast_advance(
                advance=run.fast_advance,
                association=run.association,
                user_text=run.work_request.original_user_text,
                retained_goals=run.planning_context.get("active_goal_snapshots", []),
                responsibilities=list(run.work_request.responsibilities),
            )
            run.terminal_plan = run.fast_plan
            run.fast_planner_path = "terminal"

    async def _judge_terminal_plan(self, run: _ResolutionRun) -> None:
        """Apply Value Judgment and the runtime confirmation Need to the terminal Plan."""

        await self.adapter.interaction_runtime.ensure_capability_definitions([step.capability_id for step in run.terminal_plan.steps])
        # Value Judgment (owner amendment 2026-10-10): whether Chromie should act, never how.
        # It runs on this first Plan and on any later Plan of the turn that adds a
        # value-reviewed Capability or speech UMI marked value_review (choice B,
        # 2026-10-12) not yet judged. Its verdict permits, questions or withholds those
        # effects; the Plan itself stands.
        run.terminal_plan = await self.apply_value_judgment_gate(
            run.session, sid=run.sid, text=run.text, plan=run.terminal_plan,
            work_request=run.work_request.model_copy(update={"context": run.planning_context}),
            goal_ids_by_responsibility=planner_advance_projection.goal_ids_by_responsibility(run.association),
            turn_id=run.turn_id,
        )
        run.terminal_plan = self.with_runtime_confirmation_need(run.terminal_plan)
        known_work_ids = {item["activity_id"] for item in run.planning_context.get("existing_work_activities", [])}
        if set(run.terminal_plan.cancel_activity_ids) - known_work_ids:
            raise ValueError("Planner cancellation names unknown Work")

    async def _admit_terminal_plan(self, run: _ResolutionRun) -> None:
        """Validate the terminal Plan against the Runtime and reserve its planning submission."""

        runtime = self.adapter.interaction_runtime.runtime
        if run.association_stage.planning_task is None:
            # Joining unchanged Responsibility meaning to a canonical identity
            # is mechanical. No second model authored a decision from this state.
            await runtime.bind_prepared_planner_work(run.turn_id, planner_advance_projection.goal_ids_by_responsibility(run.association))
            run.planning_snapshot = await runtime.planning_state_snapshot(
                run.association_goal_ids, run.turn_id,
            )

        # Runtime authority starts from the validated canonical Plan and is
        # bounded by registered Capability, authorization, confirmation, resource,
        # and provider-safety contracts below. User Meaning Interpretation contributes WHAT only.
        runtime_errors = await self._observe_workflow_stage(
            sid=run.sid,
            stage="canonical_plan_validation",
            input_payload={"canonical_plan": run.terminal_plan},
            operation=self.adapter.validation_errors(run.terminal_plan),
            metadata={"phase": "pre_dispatch"},
        )
        if runtime_errors:
            self._record_workflow_stage(
                sid=run.sid,
                stage="canonical_plan_rejection",
                started_monotonic_ms=time.perf_counter() * 1000.0,
                finished_monotonic_ms=time.perf_counter() * 1000.0,
                status="rejected",
                input_payload={"canonical_plan": run.terminal_plan},
                output_payload={"validation_errors": runtime_errors},
                errors=list(runtime_errors),
                attempt=1,
                metadata={"dispatch_allowed": False},
            )
        if runtime_errors:
            # The Planner authors one primary result; the Host validates authority
            # and runtime contracts without becoming another semantic planner.
            raise ValueError(
                "runtime validation rejected terminal canonical plan: "
                + json.dumps(runtime_errors, ensure_ascii=False)
            )

        planner_advance_projection.validate_work_change_selection(run.terminal_plan, run.planning_context.get("existing_work_activities", []))
        if self.policy.mode == "apply" and run.planning_snapshot is not None:
            async with runtime.planning_commit_scope(run.planning_snapshot):
                if run.ready_fast_capability_execution is not None:
                    refs_to_goals: dict[str, list[str]] | None = None
                    if run.terminal_plan.metadata.get("resolver") == "fast_planner_advance":
                        raw_refs_to_goals = run.terminal_plan.metadata.get(
                            "goal_ids_by_responsibility"
                        )
                        if isinstance(raw_refs_to_goals, dict):
                            refs_to_goals = raw_refs_to_goals
                        else:
                            raise ValueError(
                                "Fast Activity Plan lacks canonical Goal grouping"
                            )
                    elif run.work_reconciliation_required:
                        reusable_plan = (
                            planner_advance_projection.canonical_plan_reusing_fast_capability_execution(
                                execution=run.ready_fast_capability_execution,
                                plan=run.terminal_plan,
                                association=run.association,
                            )
                        )
                        if reusable_plan is not None:
                            run.terminal_plan = reusable_plan
                        refs_to_goals = planner_advance_projection.goal_ids_by_responsibility(run.association)
                    if refs_to_goals is not None:
                        ready_result = await self.adapter.interaction_runtime.bind_fast_planner_capability_execution(
                            run.ready_fast_capability_execution,
                            target_interaction_id=f"cognitive_{run.sid}_{canonical_plan_fingerprint(run.terminal_plan)[:20]}",
                            canonical_plan_id=run.terminal_plan.plan_id,
                            canonical_plan_fingerprint=canonical_plan_fingerprint(
                                run.terminal_plan
                            ),
                            goal_ids_by_responsibility=refs_to_goals,
                            task_list_revision=int(
                                run.terminal_plan.metadata.get("task_list_revision") or 1
                            ),
                            cancel_activity_ids=run.terminal_plan.cancel_activity_ids,
                        )
                        run.ready_fast_capability_status = (
                            "completed_before_canonical_dispatch:"
                            + ready_result.status
                        )
                    else:
                        raise ValueError("provisional Work lacks canonical Goal binding")
                run.terminal_plan, run.retained_work_reconciliation_status = await self._apply_retained_work_reconciliation(
                    plan=run.terminal_plan, activities=run.planning_context.get("existing_work_activities", []), turn_id=run.turn_id,
                )
                cancelled_bindings = {
                    str(item["runtime_binding"]["interaction_id"]) + "/" + str(item["activity_id"])
                    for item in run.retained_work_activities
                    if item["activity_id"] in run.terminal_plan.cancel_activity_ids
                }
                await runtime.validate_planning_state(run.planning_snapshot, cancelled_bindings=cancelled_bindings)
                prepared_ids = [item["activity_id"] for item in run.planning_snapshot["prepared"] if item.get("turn_id", run.turn_id) == run.turn_id]
                selected_prepared = (prepared_ids if run.terminal_plan.metadata.get("resolver") == "fast_planner_advance"
                                     else [step.reuse_activity_id for step in run.terminal_plan.steps])
                run.planning_commit = await runtime.reserve_planning_submission(
                    run.planning_snapshot, plan_id=run.terminal_plan.plan_id,
                    fingerprint=canonical_plan_fingerprint(run.terminal_plan),
                    prepared_activity_ids=[*selected_prepared, *run.terminal_plan.cancel_activity_ids],
                )

    async def _finish_execution_only_plan(self, run: _ResolutionRun) -> CognitiveRuntimeResolution | None:
        """Record the Plan; finish a safe-read Plan that needs no communication."""

        if self.policy.mode == "apply" and self.interaction_ledger is not None:
            self.interaction_ledger.record_plan(
                session_id=run.sid,
                turn_id=self._context_turn_id(run.planning_context, run.sid),
                interaction_id="",
                plan=run.terminal_plan,
            )
        run.planning_context["interaction_context"] = self._interaction_context(
            sid=run.sid,
            context=run.planning_context,
            goal_ids=run.terminal_plan.goal_ids,
        )

        if run.terminal_plan.steps and not run.terminal_plan.communication_needs and not any(
            self.adapter.interaction_runtime.capability_definition(step.capability_id).requires_confirmation
            for step in run.terminal_plan.steps
        ):
            if self.policy.mode == "apply":
                run.state_social_task = self.start_state_interaction(
                    run.session, work_request=run.work_request.model_copy(update={"context": run.planning_context}),
                    turn_id=run.turn_id, plan=run.terminal_plan,
                )
                run.stage = time.perf_counter()
                run.interaction = await self._observe_workflow_stage(
                    sid=run.sid,
                    stage="runtime_adapter",
                    input_payload={
                        "canonical_plan": run.terminal_plan,
                        "execution_only_safe_read": True,
                    },
                    operation=self.adapter.build_execution_only_response(
                        plan=run.terminal_plan,
                        session_id=run.sid,
                        language=run.language,
                        context=run.planning_context,
                    ),
                )
                run.timings["runtime_adapter"] = (time.perf_counter() - run.stage) * 1000.0
                run.timings["planner_communicative_activity_validation"] = 0.0
                run.interaction.metadata["goal_association"] = run.association.model_dump(
                    mode="json", exclude_none=True
                )
                if run.goal_state_commit_stage == "goal_association":
                    run.interaction.metadata["goal_state_results"] = run.goal_state_results
                run.interaction.metadata["continuous_cognition"] = {
                    "provider_work_started_before_goal_association_completed": (
                        run.ready_fast_capability_status.startswith(
                            "completed_before_canonical_dispatch"
                        )
                    ),
                    "duplicate_response_model_absent": True,
                }
                return self._finish(
                    mode="apply",
                    status="applied",
                    association=run.association,
                    fast_plan=run.fast_plan,
                    terminal_plan=run.terminal_plan,
                    interaction=run.interaction,
                    goal_state_results=run.goal_state_results,
                    timings=run.timings,
                    started=run.started,
                    metadata={
                        "execution_only_safe_read": True,
                        "stage_diagnostics": run.stage_diagnostics,
                        **self._resolution_path_metadata(run),
                    },
                )
            run.timings["planner_communicative_activity_validation"] = 0.0
            return self._finish(
                mode="report_only",
                status="report_only",
                association=run.association,
                fast_plan=run.fast_plan,
                terminal_plan=run.terminal_plan,
                timings=run.timings,
                started=run.started,
                metadata={
                    "execution_only_safe_read": True,
                    "stage_diagnostics": run.stage_diagnostics,
                    **self._resolution_path_metadata(run),
                },
            )

    async def _respond_to_terminal_plan(self, run: _ResolutionRun) -> CognitiveRuntimeResolution:
        """Have Social Cognition respond to the terminal Plan and finish the turn."""

        planner_response_context = dict(run.planning_context)
        planner_response_context["canonical_plan_resolution"] = run.terminal_plan.prompt_projection()
        delivered_turn_speech = (
            self.delivered_turn_speech_provider(run.sid)
            if callable(self.delivered_turn_speech_provider)
            else []
        )
        planner_response_context["delivered_turn_speech"] = [
            dict(item) for item in delivered_turn_speech if isinstance(item, dict)
        ]
        run.timings["planner_communicative_activity_validation"] = 0.0

        if self.policy.mode == "apply":
            run.stage = time.perf_counter()
            run.interaction = await self._observe_workflow_stage(
                sid=run.sid,
                stage="planner_communicative_activity_validation",
                input_payload={
                    "canonical_plan": run.terminal_plan,
                    "wording_owner": "social_cognition",
                },
                operation=self.resolve_plan_interaction(
                    run.session, plan=run.terminal_plan, work_request=run.work_request,
                    session_id=run.sid, language=run.language, context=planner_response_context,
                ),
            )
            run.timings["runtime_adapter"] = (time.perf_counter() - run.stage) * 1000.0
            if run.goal_state_commit_stage == "goal_association":
                run.interaction.metadata["goal_association"] = run.association.model_dump(
                    mode="json", exclude_none=True
                )
                run.interaction.metadata["goal_state_results"] = run.goal_state_results
            return self._finish(
                mode="apply",
                status="applied",
                association=run.association,
                fast_plan=run.fast_plan,
                terminal_plan=run.terminal_plan,
                interaction=run.interaction,
                goal_state_results=run.goal_state_results,
                timings=run.timings,
                started=run.started,
                metadata={
                    "stage_diagnostics": run.stage_diagnostics,
                    "architecture_attribution": (
                        "not_evaluated" if run.stage_diagnostics else "not_evaluated"
                    ),
                    **self._resolution_path_metadata(run),
                },
            )

        return self._finish(
            mode="report_only",
            status="report_only",
            association=run.association,
            fast_plan=run.fast_plan,
            terminal_plan=run.terminal_plan,
            timings=run.timings,
            started=run.started,
            metadata={
                "stage_diagnostics": run.stage_diagnostics,
                "architecture_attribution": (
                    "not_evaluated" if run.stage_diagnostics else "not_evaluated"
                ),
                **self._resolution_path_metadata(run),
            },
        )

    async def _finish_after_stage_failure(
        self, run: _ResolutionRun, exc: CognitiveStageFailure
    ) -> CognitiveRuntimeResolution:
        """Contain or report a failed cognitive stage and finish the turn."""

        await self._cancel_uncommitted_fast_work(run, exc.stage)

        # Parallel cognition cannot retroactively turn an already delivered
        # conversational Responsibility into a user-visible task failure. Once
        # Social Cognition actually delivered the fresh speech-only turn, GA and
        # Planner are optional bookkeeping/HOW cognition for that completed social
        # act. Preserve their diagnostic failure, but do not apologize, retry, or
        # re-deliver the same answer. Non-speech Work never enters this containment.
        await self._finish_independent_social_interaction(run)
        delivered_current_interaction = bool(
            run.interaction is not None
            and run.interaction.metadata.get("presentation_already_dispatched") is True
            and any(speech.text.strip() for speech in run.interaction.speech)
        )
        # Only speech that answered every Responsibility completes the turn; an
        # acknowledgement does not (live 2026-10-12: "Got it." before a value review,
        # then a failed Plan was suppressed and the person heard nothing more).
        resolution = (run.interaction.metadata.get("social_cognition_resolution")
                      if run.interaction is not None else None) or {}
        answered_refs = {
            str(ref)
            for activity in resolution.get("activities") or []
            if isinstance(activity, dict) and activity.get("function") not in {"acknowledge", "nonverbal"}
            for ref in activity.get("source_responsibility_refs") or []
        }
        conversational_only = bool(run.work_request.responsibilities) and all(
            item.output_mode == "speech" and item.local_ref in answered_refs
            for item in run.work_request.responsibilities
        )
        if delivered_current_interaction and conversational_only and run.interaction is not None:
            run.direct_social_completion_results = (
                self._reconcile_delivered_direct_social_response(
                    association=run.association, interaction=run.interaction, sid=run.sid,
                ) if run.association is not None else []
            )
            return self._finish(
                mode=self.policy.mode,
                status=(
                    "applied" if self.policy.mode == "apply"
                    else "report_only" if self.policy.mode == "report_only"
                    else "skipped"
                ),
                association=run.association,
                fast_plan=run.fast_plan,
                terminal_plan=run.terminal_plan,
                interaction=run.interaction if self.policy.mode == "apply" else None,
                goal_state_results=run.goal_state_results,
                timings=run.timings,
                started=run.started,
                metadata={
                    "optional_cognition_failure_after_delivered_interaction": True,
                    "suppressed_failure_stage": exc.stage,
                    "suppressed_failure_class": str(
                        exc.failure_metadata.get("failure_class") or type(exc).__name__
                    ),
                    "direct_social_completion_results": run.direct_social_completion_results,
                    "stage_diagnostics": run.stage_diagnostics,
                    **self._resolution_path_metadata(run),
                },
            )

        await self._communicate_terminal_work_failure(run,
            stage=exc.stage,
            failure_class=str(exc.failure_metadata.get("failure_class") or type(exc).__name__),
            failure_domain=str(exc.failure_metadata.get("failure_domain") or "cognitive_work"),
            failure_reason=str(
                exc.failure_metadata.get("reason")
                or exc.failure_metadata.get("error")
                or str(exc)
            ),
        )
        failure_metadata = {
            **exc.failure_metadata,
            "failure_stage": exc.stage,
            "stage_diagnostics": run.stage_diagnostics,
            **self._resolution_path_metadata(run),
        }
        return self._finish(
            mode=self.policy.mode,
            status="error",
            association=run.association,
            fast_plan=run.fast_plan,
            terminal_plan=run.terminal_plan,
            interaction=run.interaction,
            goal_state_results=run.goal_state_results,
            timings=run.timings,
            started=run.started,
            fallback_reason=str(exc)[:500],
            metadata=failure_metadata,
        )

    async def _finish_after_runtime_failure(
        self, run: _ResolutionRun, exc: Exception
    ) -> CognitiveRuntimeResolution:
        """Report an unexpected runtime failure through Social Cognition and finish with an error."""

        await self._cancel_uncommitted_fast_work(run, type(exc).__name__)
        await self._communicate_terminal_work_failure(run,
            stage="runtime", failure_class=type(exc).__name__,
            failure_domain="cognitive_runtime", failure_reason=str(exc),
        )
        return self._finish(
            mode=self.policy.mode,
            status="error",
            association=run.association,
            fast_plan=run.fast_plan,
            terminal_plan=run.terminal_plan,
            interaction=run.interaction,
            goal_state_results=run.goal_state_results,
            timings=run.timings,
            started=run.started,
            fallback_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
            metadata={
                "failure_stage": "runtime",
                "failure_class": type(exc).__name__,
                "failure_domain": "cognitive_runtime",
                "architecture_attribution": "not_evaluated",
                "retryable": False,
                "stage_diagnostics": run.stage_diagnostics,
                **self._resolution_path_metadata(run),
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
