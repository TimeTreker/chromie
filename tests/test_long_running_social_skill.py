"""The long-running social skill: Social Cognition decides, the Host runs it across turns."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.planner_model_contract import is_planner_step_capability
from agent.app.social_cognition import (
    social_cognition_response_schema,
    validate_social_cognition_output,
)
from agent.app.tool_invocation import ToolCallOutcome
from orchestrator.runtime.interaction_ledger import InteractionLedger
from orchestrator.runtime.long_running_social_skill import LongRunningSocialSkill
from orchestrator.runtime.soridormi_capability_provider import import_soridormi_capability_catalog
from orchestrator.runtime.capability_runtime import CapabilityDefinitionRegistry
from shared.chromie_contracts.situation import CURRENT_SPEAKER_RELATION
from shared.chromie_contracts.social_cognition import (
    LongRunningSocialSkillDecision,
    SocialCognitionOutput,
    SocialCognitionResolution,
    social_skill_options,
)
from tests.test_social_cognition import request, response

SPEAKER_SITUATION = {"interpretations": [{
    "interpretation_id": "scene-1:object-1:speaker", "subject_ref": "scene-1:object-1",
    "relation": CURRENT_SPEAKER_RELATION, "value": "speaking with Chromie (simulated)",
    "epistemic_status": "established",
}]}
ATTEND = {"action": "attend", "capability_id": "soridormi.attend_to_person",
          "target_ref": "requester", "posture": "listening"}


def _context(*, available: bool = True, active: bool = False, speaker: bool = True) -> dict[str, Any]:
    return {
        "work": [{"id": "work:1", "status": "running"}],
        "active_goal_snapshots": [{"goal_id": "goal:1", "status": "active"}],
        "long_running_social_skill": {"available": available, "active": active},
        **({"situation": SPEAKER_SITUATION} if speaker else {}),
    }


def _decision(**skill: Any) -> SocialCognitionOutput:
    return SocialCognitionOutput.model_validate({**response(), "social_skill": skill or None})


@pytest.mark.parametrize(
    ("context", "attend_refs", "can_stop"),
    [
        (_context(), ["requester"], False),
        (_context(active=True), ["requester"], True),
        (_context(available=False, active=True), [], True),
        (_context(speaker=False), [], False),
    ],
)
def test_options_follow_the_offer_the_speaker_mark_and_what_runs(
    context: dict[str, Any], attend_refs: list[str], can_stop: bool,
) -> None:
    assert social_skill_options(context) == {"attend_target_refs": attend_refs, "can_stop": can_stop}


def test_a_decision_names_everything_to_attend_and_nothing_to_stop() -> None:
    assert LongRunningSocialSkillDecision.model_validate(ATTEND).posture == "listening"
    for invalid in ({**ATTEND, "posture": None}, {"action": "stop", "target_ref": "requester"},
                    {"action": "keep", "posture": "listening"},
                    {**ATTEND, "posture": "nodding"}, {**ATTEND, "capability_id": "soridormi.nod_yes"}):
        with pytest.raises(ValidationError):
            LongRunningSocialSkillDecision.model_validate(invalid)
    with pytest.raises(ValidationError):
        SocialCognitionOutput.model_validate({
            "disposition": "deliberate", "activities": [], "reason_summary": "unsure", "social_skill": ATTEND})


def test_the_decoder_offers_exact_branches_only_while_the_skill_is_offered() -> None:
    offered = social_cognition_response_schema(request(context=_context(active=True)), [])
    field = offered["properties"]["social_skill"]
    assert "social_skill" in offered["required"]
    null, keep, attend, stop = field["anyOf"]
    assert null == {"type": "null"}  # no decision: only deliberation keeps it while the skill runs
    communicate = next(branch for branch in offered["oneOf"]
                       if branch["properties"]["disposition"]["const"] == "communicate")
    assert communicate["properties"]["social_skill"] == {"anyOf": [keep, attend, stop]}
    assert keep["properties"] == {"action": {"type": "string", "const": "keep"}}
    assert attend["properties"]["target_ref"] == {"type": "string", "const": "requester"}
    assert attend["properties"]["posture"]["enum"] == ["listening", "thinking"]
    assert stop["properties"] == {"action": {"type": "string", "const": "stop"}}
    deliberate = next(branch for branch in offered["oneOf"]
                      if branch["properties"]["disposition"]["const"] == "deliberate")
    assert deliberate["properties"]["social_skill"] == {"type": "null"}
    validator = Draft202012Validator(offered)
    assert not list(validator.iter_errors({**response(), "social_skill": ATTEND}))
    assert list(validator.iter_errors({**response(), "social_skill": {**ATTEND, "target_ref": "guest"}}))
    idle = social_cognition_response_schema(request(context=_context()), [])["properties"]["social_skill"]
    assert [branch.get("properties", {}).get("action", {}).get("const") for branch in idle["anyOf"]] == [
        None, "attend"]

    for context in (_context(available=False), _context(speaker=False)):
        schema = social_cognition_response_schema(request(context=context), [])
        assert "social_skill" not in schema["properties"]
        assert "social_skill" not in schema["required"]


def test_while_it_runs_keep_is_the_one_way_to_leave_it_as_it_is() -> None:
    running = _context(active=True)
    running["long_running_social_skill"].update(target_ref="requester", posture="listening")
    schema = social_cognition_response_schema(request(context=running), [])
    attend = schema["properties"]["social_skill"]["anyOf"][2]
    assert attend["properties"]["posture"]["enum"] == ["thinking"]
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors({**response(), "social_skill": ATTEND}))
    assert list(validator.iter_errors({**response(), "social_skill": None}))
    # Live 2026-10-29: a deliberation while the skill ran was rejected by the raw Schema (422).
    deliberation = {**response(), "disposition": "deliberate", "activities": [], "need_outcomes": {},
                    "social_skill": None}
    assert not list(validator.iter_errors(deliberation))
    assert not list(validator.iter_errors({**response(), "social_skill": {"action": "keep"}}))
    assert not list(validator.iter_errors({**response(), "social_skill": {**ATTEND, "posture": "thinking"}}))


def test_agent_and_host_reject_a_decision_the_offer_does_not_allow() -> None:
    current = request(context=_context())
    validate_social_cognition_output(_decision(**ATTEND), current, [])
    for invalid, context in (
        (ATTEND, _context(speaker=False)),
        ({"action": "stop"}, _context()),
        (ATTEND, _context(available=False)),
    ):
        stale = request(context=context)
        with pytest.raises(ValueError):
            validate_social_cognition_output(_decision(**invalid), stale, [])
        resolution = SocialCognitionResolution.model_validate({
            **_decision(**invalid).model_dump(mode="json"), "request_id": stale.request_id,
            "snapshot_digest": stale.snapshot_digest(), "model_call_count": 1})
        with pytest.raises(ValueError, match="long-running social skill"):
            resolution.validate_request(stale)


class FakeSoridormi:
    """Records lifecycle tool calls; answers from a scripted attention state."""

    def __init__(self, *, offered: bool = True) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.offered = offered
        self.status: dict[str, Any] = {"skill_id": "attend_to_person", "active": False, "status": "idle"}
        self.start_output: dict[str, Any] | None = None

    async def invoke(self, tool: str, args: dict[str, Any], *, context: Any = None) -> ToolCallOutcome:
        self.calls.append((tool, dict(args)))
        if tool == "soridormi.skill.list":
            skills = [{"skill_id": "look_at_person"}]
            if self.offered:
                skills.append({"skill_id": "attend_to_person", "lifecycle": "long_running", "available": True})
            return ToolCallOutcome.success({"skills": skills})
        if tool == "soridormi.attention.start":
            output = self.start_output or {
                "attention_id": "attention-1", "started": True, "active": True, "status": "running",
                "posture": args["posture"], "target_ref": args["target_ref"]}
            if output.get("active"):
                self.status = dict(output)
            return ToolCallOutcome.success(output)
        if tool == "soridormi.attention.status":
            return ToolCallOutcome.success(dict(self.status))
        if tool == "soridormi.attention.stop":
            self.status = {**self.status, "active": False, "status": "ended", "end_reason": args["reason"]}
            return ToolCallOutcome.success(dict(self.status))
        raise AssertionError(tool)

    def tools(self) -> list[str]:
        return [tool for tool, _ in self.calls]


class Clocks:
    def __init__(self) -> None:
        self.monotonic = 100.0
        self.wall = 1_000_000.0


def _skill(soridormi: FakeSoridormi, ledger: InteractionLedger | None = None) -> tuple[LongRunningSocialSkill, Clocks]:
    clocks = Clocks()
    skill = LongRunningSocialSkill(
        invoker=soridormi, ledger=ledger, idle_timeout_s=180.0,
        clock=lambda: clocks.monotonic, wall_clock=lambda: clocks.wall,
    )
    return skill, clocks


def _events(ledger: InteractionLedger, sid: str = "sid-1") -> list[str]:
    return [event.event_type for event in ledger.events(sid)]


def test_social_cognition_starts_re_poses_and_stops_the_skill_across_turns() -> None:
    soridormi = FakeSoridormi()
    ledger = InteractionLedger()
    skill, clocks = _skill(soridormi, ledger)
    context = _context(active=False)

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        assert skill.context()["long_running_social_skill"]["available"] is True
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=context,
                          session_id="sid-1", turn_id="turn-1")
        assert skill.context()["long_running_social_skill"] == {
            "available": True, "capability_id": "soridormi.attend_to_person", "active": True,
            "target_ref": "requester", "posture": "listening", "status": "running"}
        soridormi.start_output = {"attention_id": "attention-1", "updated": True, "active": True,
                                  "status": "running", "posture": "listening"}
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=context,
                          session_id="sid-1", turn_id="turn-1")
        await skill.apply(LongRunningSocialSkillDecision(action="keep"), context=context,
                          session_id="sid-1", turn_id="turn-2")
        soridormi.start_output = {**soridormi.start_output, "posture": "thinking"}
        await skill.apply(LongRunningSocialSkillDecision.model_validate({**ATTEND, "posture": "thinking"}),
                          context=context, session_id="sid-1", turn_id="turn-2")
        await skill.apply(LongRunningSocialSkillDecision(action="stop"), context=context,
                          session_id="sid-1", turn_id="turn-3")

    asyncio.run(exercise())

    starts = [args for tool, args in soridormi.calls if tool == "soridormi.attention.start"]
    assert starts[0] == {"target_ref": "requester", "posture": "listening",
                         "target_lost_s": 5.0, "max_duration_s": 600.0}
    assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "social_cognition"})
    assert _events(ledger) == ["social_skill_started", "social_skill_changed", "social_skill_ended"]
    assert all(not event.goal_ids for event in ledger.events("sid-1"))
    assert skill.context()["long_running_social_skill"]["last_end"] == {
        "target_ref": "requester", "reason": "social_cognition"}


def test_an_unoffered_skill_or_unseen_person_does_not_run() -> None:
    soridormi = FakeSoridormi(offered=False)
    ledger = InteractionLedger()
    skill, clocks = _skill(soridormi, ledger)

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        offered, offered_clocks = _skill(FakeSoridormi())
        await offered.sync(last_activity_s=offered_clocks.wall, conversation_id="conv-1")
        offered.invoker.start_output = {"started": False, "active": False, "status": "target_unavailable",
                                        "target_resolution": {"status": "not_observed"}}
        await offered.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                            session_id="sid-1")
        assert offered.context()["long_running_social_skill"]["active"] is False

    asyncio.run(exercise())

    assert "soridormi.attention.start" not in soridormi.tools()
    assert _events(ledger) == ["social_skill_not_run"]
    assert ledger.events("sid-1")[0].metadata["reason"].startswith("the long-running social skill attends")


def test_status_records_suspension_resume_and_soridormis_own_end() -> None:
    soridormi = FakeSoridormi()
    ledger = InteractionLedger()
    skill, clocks = _skill(soridormi, ledger)

    async def step(status: dict[str, Any]) -> None:
        soridormi.status = {**soridormi.status, **status}
        clocks.monotonic += 1.5
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        await step({"status": "suspended"})
        await step({"status": "running"})
        await step({"status": "ended", "active": False, "end_reason": "target_lost"})

    asyncio.run(exercise())

    assert _events(ledger) == ["social_skill_started", "social_skill_suspended", "social_skill_resumed",
                               "social_skill_ended"]
    assert ledger.events("sid-1")[-1].metadata["reason"] == "target_lost"
    assert skill.context()["long_running_social_skill"]["active"] is False


def test_conversation_idle_counts_from_the_last_activity_or_body_work() -> None:
    soridormi = FakeSoridormi()
    skill, clocks = _skill(soridormi, InteractionLedger())
    last_spoke = clocks.wall

    async def exercise() -> None:
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        # A long fetch suspends attention from 100 s to 250 s after the person last spoke.
        soridormi.status = {**soridormi.status, "status": "suspended"}
        clocks.wall, clocks.monotonic = last_spoke + 100.0, clocks.monotonic + 2.0
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")
        soridormi.status = {**soridormi.status, "status": "running"}
        clocks.wall, clocks.monotonic = last_spoke + 250.0, clocks.monotonic + 2.0
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")
        assert skill.context()["long_running_social_skill"]["active"] is True
        clocks.wall, clocks.monotonic = last_spoke + 431.0, clocks.monotonic + 2.0
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")

    asyncio.run(exercise())

    assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "conversation_idle"})


def test_a_new_conversation_a_reflex_and_an_orphan_end_the_skill() -> None:
    soridormi = FakeSoridormi()
    soridormi.status = {"skill_id": "attend_to_person", "attention_id": "attention-old", "active": True,
                        "status": "running"}
    skill, clocks = _skill(soridormi, InteractionLedger())

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "host_started"})
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-2")
        assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "new_conversation"})
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        skill.schedule_stop("reflex:embodied_motion")
        await asyncio.gather(*skill._tasks)

    asyncio.run(exercise())

    assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "reflex:embodied_motion"})
    assert skill.context()["long_running_social_skill"]["active"] is False


def test_the_skill_is_never_a_planner_step_or_an_imported_named_capability() -> None:
    for tool in ("soridormi.attention.start", "soridormi.attention.status", "soridormi.attention.stop"):
        assert not is_planner_step_capability(tool)
    assert is_planner_step_capability("soridormi.look_at_person")
    registry = CapabilityDefinitionRegistry()
    import_soridormi_capability_catalog(registry, [
        {"skill_id": "attend_to_person", "lifecycle": "long_running", "available": True},
    ])
    with pytest.raises(ValueError, match="unknown capability"):
        registry.get("soridormi.attend_to_person")


def test_the_agent_catalog_does_not_import_a_long_running_skill() -> None:
    from agent.app.capabilities.catalog import CapabilityCatalog
    from tests.test_capability_catalog_service import _Invoker, _Outcome, _registry

    class LongRunningInvoker(_Invoker):
        async def invoke(self, tool_name: str, arguments: dict, *, context: Any = None) -> Any:
            outcome = await super().invoke(tool_name, arguments, context=context)
            skills = [*outcome.output["skills"], {
                "skill_id": "attend_to_person", "lifecycle": "long_running", "available": True,
                "parameters_schema": {"type": "object", "properties": {"target_ref": {"type": "string"}}},
                "effects": ["physical_motion"], "safety_class": "physical_motion",
                "metadata": {"behavior_domains": ["social_attention"], "lifecycle": "long_running"}}]
            return _Outcome(output={**outcome.output, "skills": skills})

    catalog = CapabilityCatalog(_registry(), live_invoker=LongRunningInvoker())
    snapshot = asyncio.run(catalog.snapshot())
    ids = {item["capability_id"] for item in snapshot["capabilities"]}
    assert "soridormi.nod_yes" in ids and "soridormi.attend_to_person" not in ids


def test_a_reflex_during_a_start_still_ends_the_skill() -> None:
    soridormi = FakeSoridormi()
    skill, clocks = _skill(soridormi, InteractionLedger())

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        skill.schedule(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                       session_id="sid-1")
        skill.schedule_stop("reflex:current_interaction")  # before the start has returned
        await asyncio.gather(*skill._tasks)

    asyncio.run(exercise())

    assert [tool for tool in soridormi.tools() if tool.startswith("soridormi.attention.")][-2:] == [
        "soridormi.attention.start", "soridormi.attention.stop"]
    assert skill.context()["long_running_social_skill"]["active"] is False


def test_a_failed_call_never_leaves_host_and_soridormi_disagreeing() -> None:
    soridormi = FakeSoridormi()
    ledger = InteractionLedger()
    skill, clocks = _skill(soridormi, ledger)
    original = soridormi.invoke

    async def flaky(tool: str, args: dict[str, Any], *, context: Any = None) -> ToolCallOutcome:
        outcome = await original(tool, args, context=context)
        if tool in {"soridormi.attention.start", "soridormi.attention.stop"} and flaky.fail.get(tool):
            flaky.fail[tool] -= 1
            return ToolCallOutcome(status="timeout", error="MCP tool timeout")
        return outcome

    flaky.fail = {"soridormi.attention.start": 1, "soridormi.attention.stop": 1}  # type: ignore[attr-defined]
    soridormi.invoke = flaky  # type: ignore[method-assign]

    async def exercise() -> None:
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")
        # The start timed out although Soridormi started: the Host adopts the run.
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        assert skill.context()["long_running_social_skill"]["active"] is True
        # The stop timed out: the run is kept and the next upkeep pass retries it.
        await skill.apply(LongRunningSocialSkillDecision(action="stop"), context=_context(active=True),
                          session_id="sid-1")
        assert skill.context()["long_running_social_skill"]["active"] is True
        clocks.monotonic += 1.5
        await skill.sync(last_activity_s=clocks.wall, conversation_id="conv-1")

    asyncio.run(exercise())

    assert soridormi.status["active"] is False
    assert skill.context()["long_running_social_skill"]["active"] is False
    assert _events(ledger) == ["social_skill_started", "social_skill_ended"]


def test_a_run_started_after_a_quiet_spell_is_not_stopped_as_idle_at_once() -> None:
    soridormi = FakeSoridormi()
    skill, clocks = _skill(soridormi, InteractionLedger())
    last_spoke = clocks.wall - 400.0  # the person last spoke long ago

    async def exercise() -> None:
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")
        await skill.apply(LongRunningSocialSkillDecision.model_validate(ATTEND), context=_context(),
                          session_id="sid-1")
        clocks.monotonic += 1.5
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")
        assert skill.context()["long_running_social_skill"]["active"] is True
        clocks.wall, clocks.monotonic = clocks.wall + 181.0, clocks.monotonic + 1.5
        await skill.sync(last_activity_s=last_spoke, conversation_id="conv-1")

    asyncio.run(exercise())

    assert soridormi.calls[-1] == ("soridormi.attention.stop", {"reason": "conversation_idle"})
