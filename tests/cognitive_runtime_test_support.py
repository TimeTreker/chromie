"""Shared fakes and plan fixtures for Goal-Driven Cognitive Runtime tests."""

from __future__ import annotations

from types import SimpleNamespace

from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityDefinitionRegistry,
    CapabilityRuntime,
)
from orchestrator.runtime.cognitive_gateway import CognitiveGateway
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
)
from shared.chromie_contracts.core_interpretation import (
    CoreInterpretationResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerCapabilityActivity,
    FastPlannerResponseNeed,
    FastPlannerStreamTerminal,
    SocialCommunicationNeed,
)
from shared.chromie_contracts.semantic_task import SemanticGoal
from shared.chromie_contracts.user_turn import AttentionReviewResult

TEST_SKILL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"completed": {"type": "boolean"}},
    "required": ["completed"],
    "additionalProperties": False,
}


def admitted_core(
    text: str,
    *,
    sid: str,
    language: str,
    responsibilities: list[dict] | None = None,
    meaning_uncertainties: list[str] | None = None,
    cognitive_requests: list[dict] | None = None,
):
    gateway = CognitiveGateway()
    capture = gateway.capture(
        text,
        session_id=sid,
        conversation_id=f"conversation-{sid}",
        channel="text",
        language=language,
    )
    snapshot = gateway.assemble_context(capture, {})
    envelope = gateway.admit_attention(
        capture,
        snapshot,
        AttentionReviewResult(
            turn_id=capture.turn_id,
            session_id=capture.session_id,
            context_digest=snapshot.digest,
            disposition="admit",
            speech_act="request",
            confidence=1.0,
            source="test",
            reason="runtime test input",
        ),
    )
    rows = responsibilities or [
        {
            "local_ref": "r1",
            "outcome": text,
            "bindings": {},
            "confidence": 0.95,
        }
    ]
    responsibility_refs = [str(item.get("local_ref") or "r1") for item in rows]
    uncertainties = [
        {
            "local_ref": f"u{index}",
            "kind": "other",
            "description": str(description),
            "responsibility_refs": [responsibility_refs[0]],
        }
        for index, description in enumerate(meaning_uncertainties or [], start=1)
    ]
    refs = [str(item.get("local_ref") or "r1") for item in rows]
    default_requests = (
        [
            {
                "authority": "goal_association",
                "responsibility_refs": refs,
                "reason_summary": "Fixture requests canonical Goal continuity.",
            },
            {
                "authority": "social_cognition",
                "responsibility_refs": refs,
                "reason_summary": "Fixture requests interaction cognition.",
            },
        ]
        if all(
            str(item.get("output_mode") or "speech") == "speech"
            and str(item.get("continuity_scope") or "goal") == "turn"
            for item in rows
        )
        else [
            {
                "authority": "goal_association",
                "responsibility_refs": refs,
                "reason_summary": "Fixture requests canonical Goal continuity.",
            },
            {
                "authority": "social_cognition",
                "responsibility_refs": refs,
                "reason_summary": "Fixture requests interaction cognition.",
            },
            {
                "authority": "planner",
                "responsibility_refs": refs,
                "reason_summary": "Fixture requests Work cognition.",
            },
        ]
    )
    core = CoreInterpretationResult(
        turn_id=envelope.turn_id,
        session_id=envelope.session_id,
        confidence=min(float(item.get("confidence", 0.95)) for item in rows),
        language=language,
        responsibilities=rows,
        meaning_uncertainties=uncertainties,
        cognitive_requests=(cognitive_requests if cognitive_requests is not None else default_requests),
    )
    return core, envelope


class FakeRuntime:
    def __init__(self, definitions: list[CapabilityDefinition] | None = None):
        self.definitions = {item.capability_id: item for item in (definitions or [])}
        self.ensure_calls: list[list[str]] = []
        registry = CapabilityDefinitionRegistry()
        for definition in definitions or []:
            registry.register(definition)
        self.runtime = CapabilityRuntime(registry)

    async def submit_response(self, response, **kwargs):
        del kwargs
        return response

    async def wait_dispatch(self, dispatch):
        del dispatch
        return SimpleNamespace(status="completed", results=[])

    async def record_social_delivery(self, *args, **kwargs):
        del args, kwargs
        return True

    async def ensure_capability_definitions(self, capability_ids):
        ids = list(capability_ids)
        self.ensure_calls.append(ids)
        missing = [item for item in ids if item not in self.definitions]
        if missing:
            raise ValueError(f"unknown capabilities: {missing}")

    def capability_definition(self, skill_id):
        if skill_id not in self.definitions:
            raise ValueError(f"unknown skill {skill_id}")
        return self.definitions[skill_id]

    async def prepare_fast_planner_capability_activities(self, activities, *, turn_id):
        await self.runtime.prepare_planner_work(turn_id, [item.model_dump(mode="json") for item in activities])
        # These adapter tests have no provider. Actual early dispatch is tested
        # through InteractionRuntimeCoordinator and CapabilityRuntime.
        return []


class RecordingPlannerAdapter(CanonicalPlanRuntimeAdapter):
    def __init__(self, runtime: FakeRuntime):
        super().__init__(runtime)
        self.planner_response_contexts: list[dict] = []


    async def build_social_cognition_response(self, **kwargs):
        self.planner_response_contexts.append(dict(kwargs.get("context") or {}))
        return await super().build_social_cognition_response(**kwargs)


def _stream_advance_from_canonical_plan(
    plan: CanonicalPlan,
    association: GoalAssociationResolution,
) -> FastPlannerAdvance:
    """Project legacy test fixtures onto the one-call streamed Fast contract.

    Runtime tests historically used ``unavailable`` as a sentinel that forced a
    second ``/fast-plan`` call.  The maintained contract now treats the streamed
    terminal result as authoritative unless canonical state actually changes.
    This helper keeps those fixtures about their intended Planner result instead
    of preserving the retired retry protocol.
    """

    refs_by_goal: dict[str, list[str]] = {}
    all_refs: list[str] = []

    def bind(ref: str, goal_id: str) -> None:
        if ref not in all_refs:
            all_refs.append(ref)
        refs_by_goal.setdefault(goal_id, [])
        if ref not in refs_by_goal[goal_id]:
            refs_by_goal[goal_id].append(ref)

    for item in association.associations:
        for goal_id in item.target_goal_ids:
            for ref in item.source_responsibility_refs:
                bind(ref, goal_id)
    for goal in association.new_goals:
        for ref in goal.source_responsibility_refs:
            bind(ref, goal.goal_id)

    from scripts.behavior_scenarios import canonical_step_dependencies

    activities = []
    dependencies = canonical_step_dependencies(plan.steps)
    for step in plan.steps:
        source_refs = [
            ref
            for goal_id in step.source_goal_ids
            for ref in refs_by_goal.get(goal_id, [])
        ] or list(all_refs)
        activities.append(
            FastPlannerCapabilityActivity(
                role="capability",
                activity_id=step.step_id,
                capability_id=step.capability_id,
                args=dict(step.args),
                depends_on=dependencies[step.step_id],
                source_responsibility_refs=source_refs,
                reason_summary=step.reason_summary,
            )
        )

    for need in plan.communication_needs:
        refs = list(need.source_responsibility_refs) or [ref for goal_id in need.source_goal_ids for ref in refs_by_goal.get(goal_id, [])] or all_refs
        if need.kind == "answer":
            activities.append(FastPlannerResponseNeed(activity_id=need.need_id, role="complete_response",
                source_responsibility_refs=refs, timing="sequential", rationale="The scripted Work fixture establishes an answer obligation."))
        elif need.kind == "input":
            raise ValueError("Script an explicit FastPlannerInputNeed with exact UMI gap provenance for input cases.")

    return FastPlannerAdvance(
        turn_id="test-fast-advance",
        disposition=plan.disposition,
        coverage=plan.coverage,
        covered_responsibility_refs=list(all_refs),
        activities=activities,
        confidence=plan.confidence,
        unresolved=list(plan.unresolved),
        reason_summary=(
            str(plan.metadata.get("reason") or "")
            or plan.goal_summary
            or "Fixture preserves the canonical Planner decision."
        ),
        metadata={
            "fixture_source_plan_id": plan.plan_id,
            "path_classification": plan.metadata.get("path_classification", ""),
            **(
                {
                    "failure_class": plan.metadata["failure_class"],
                    "failure_domain": plan.metadata.get("failure_domain", "model_contract"),
                }
                if plan.metadata.get("failure_class")
                else {}
            ),
        },
    )


def work_fixture(plan: CanonicalPlan) -> CanonicalPlan:
    """Migrate a historical test scenario to a word-free Work decision.

    ScriptedClient retains the scenario's words separately for the SC response.
    Production code never performs this legacy fixture conversion.
    """
    data = plan.model_dump(mode="json")
    needs = list(data["communication_needs"])
    for goal_id in plan.goal_ids:
        outcome = next((row for row in plan.goal_outcomes if row.goal_id == goal_id), None)
        disposition = outcome.disposition if outcome is not None else plan.disposition
        if disposition in {"respond", "clarify", "unavailable", "refused"} and not any(goal_id in need["source_goal_ids"] for need in needs):
            needs.append(SocialCommunicationNeed(need_id=f"fixture:{plan.plan_id}:{goal_id}", owner="planner",
                kind="answer" if disposition == "respond" else "input" if disposition == "clarify" else "result",
                source_goal_ids=[goal_id], reference_id=plan.plan_id,
                facts={"rationale": "Established by the explicit Work fixture."}).model_dump(mode="json"))
    data["communication_needs"] = needs
    data["response_text"] = ""
    data["communicative_acts"] = []
    data["auxiliary_activities"] = []
    for outcome in data["goal_outcomes"]:
        outcome["response_text"] = ""
    return CanonicalPlan.model_validate(data)


class ScriptedClient:
    def __init__(
        self,
        *,
        association: GoalAssociationResolution,
        fast_plans: list[CanonicalPlan],
        fast_advances: list[FastPlannerAdvance] | None = None,
    ):
        self.association = association
        self.social_requests = []
        self.social_words = {}
        for plan in fast_plans:
            for goal_id in plan.goal_ids:
                outcome = next((item for item in plan.goal_outcomes if item.goal_id == goal_id), None)
                words = (outcome.response_text if outcome is not None else "") or plan.response_text
                if words:
                    self.social_words[goal_id] = words
        self.fast_plans = [work_fixture(plan) for plan in fast_plans]
        self._explicit_fast_advances = fast_advances is not None
        self.fast_advances = list(
            fast_advances
            if fast_advances is not None
            else (
                [_stream_advance_from_canonical_plan(self.fast_plans[0], association)]
                if self.fast_plans
                else [
                    FastPlannerAdvance(
                        turn_id=association.turn_id,
                        disposition="unavailable",
                        coverage="uncertain",
                        covered_responsibility_refs=[
                            ref
                            for item in [*association.associations, *association.new_goals]
                            for ref in item.source_responsibility_refs
                        ],
                        activities=[],
                        confidence=0.95,
                        unresolved=["no scripted Fast decision supplied"],
                        reason_summary="No scripted Fast decision supplied.",
                    )
                ]
            )
        )
        self.calls: list[str] = []

    async def stream_fast_advance(self, *args, **kwargs):
        self.calls.append("stream")
        if not self.fast_advances:
            raise AssertionError("unexpected Fast Planner stream")
        advance = self.fast_advances.pop(0)
        request = kwargs["request"]
        advance = advance.model_copy(update={"turn_id": request.sid})
        yield FastPlannerStreamTerminal(turn_id=request.sid, advance=advance)

    async def resolve_social_cognition(self, session, *, request, **kwargs):
        from shared.chromie_contracts.social_cognition import SocialCognitionResolution
        self.social_requests.append(request)
        acts = []
        for index, need in enumerate(request.communication_needs):
            text = next((self.social_words[g] for g in need.source_goal_ids if g in self.social_words), "Fixture response.")
            if need.kind in {"input", "confirmation"}:
                text = "Please confirm." if need.kind == "confirmation" else "Which input do you mean?"
            acts.append({"activity_id": f"{request.request_id}:act:{index}", "text": text,
                "function": "ask" if need.kind in {"input", "confirmation"} else "respond",
                "truth_stage": "context_grounded", "delivery_phase": need.delivery_phase or "immediate",
                "source_goal_ids": need.source_goal_ids, "source_responsibility_refs": need.source_responsibility_refs,
                "addressed_need_ids": [need.need_id]})
        return SocialCognitionResolution(request_id=request.request_id, snapshot_digest=request.snapshot_digest(),
            disposition="communicate" if acts else "silence", activities=acts,
            need_outcomes={need.need_id: "covered" for need in request.communication_needs},
            reason_summary="Explicit test SC result, separate from the Work fixture.", model_call_count=1)

    async def resolve_goal_association(self, *args, **kwargs):
        self.calls.append("association")
        return self.association

    async def resolve_fast_plan(self, *args, **kwargs):
        self.calls.append("fast")
        return self.fast_plans.pop(0)


def new_goal_association(goal_id: str = "goal-1", *, source_ref: str = "r1") -> GoalAssociationResolution:
    return GoalAssociationResolution(
        resolution_status="resolved",
        turn_id="turn-1",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                source_responsibility_refs=[source_ref],
                description="Respond to the user.",
                source_text="hello",
                metadata={
                    "output_mode": "speech",
                },
            )
        ],
        confidence=0.95,
        reason_summary="A new independent user goal.",
        metadata={"status": "resolved"},
    )


def body_goal_association(goal_id: str = "goal-1", *, source_ref: str = "r1") -> GoalAssociationResolution:
    return GoalAssociationResolution(
        resolution_status="resolved",
        turn_id="turn-body",
        new_goals=[
            SemanticGoal(
                goal_id=goal_id,
                source_responsibility_refs=[source_ref],
                description="Blink the eyes.",
                source_text="blink",
                metadata={
                    "output_mode": "body_action",
                },
            )
        ],
        confidence=0.95,
        reason_summary="A new observable body-action responsibility.",
        metadata={"status": "resolved"},
    )


def respond_plan(goal_id: str = "goal-1") -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-chat",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.96,
        goal_ids=[goal_id],
        goal_summary="greet the user",
        response_text="你好。",
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        },
    )


def execute_plan(
    *,
    plan_id: str = "plan-blink",
    goal_id: str = "goal-1",
    relation: str | None = None,
) -> CanonicalPlan:
    metadata = {}
    if relation:
        metadata = {
            "plan_relation": relation,
            "user_confirmation_required": True,
        }
    return CanonicalPlan(
        plan_id=plan_id,
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=0.91,
        goal_ids=[goal_id],
        goal_summary="blink the eyes",
        response_text="好的，我会眨四下眼睛。",
        steps=[
            {
                "step_id": "blink",
                "capability_id": "soridormi.blink_eyes",
                "args": {"count": 4},
                "timing": "sequential",
                "source_goal_ids": [goal_id],
            }
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
        },
        metadata=metadata,
    )


def blink_definition(*, confirmation: bool = False) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="soridormi.blink_eyes",
        provider_id="soridormi.mcp",
        description="Blink the robot eyes.",
        input_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 10}
            },
            "required": ["count"],
        },
        output_schema=TEST_SKILL_OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=confirmation,
        interruptible=True,
        can_run_parallel=True,
        exclusive_group="eye_expression",
        metadata={"resource_claims": ["eye_expression"]},
    )


def walk_definition() -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id="soridormi.walk_forward",
        provider_id="soridormi.mcp",
        description="Walk forward for a bounded duration.",
        input_schema={
            "type": "object",
            "properties": {
                "duration_s": {"type": "number", "minimum": 0.1, "maximum": 30}
            },
            "required": ["duration_s"],
            "additionalProperties": False,
        },
        output_schema=TEST_SKILL_OUTPUT_SCHEMA,
        available=True,
        requires_confirmation=False,
        interruptible=True,
        can_run_parallel=False,
        metadata={
            "safety_class": "physical_motion",
            "effects": ["physical_motion"],
        },
    )
