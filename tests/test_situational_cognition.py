from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.app.situational_cognition import SituationalPlannerResolver
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimePolicy
from orchestrator.runtime.situation import (
    apply_goal_free_situation_opportunity,
    build_situation_projection,
    build_trusted_goal_free_situation_observation,
    derive_situation_revision_opportunity,
    resolve_goal_free_situation_response,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
)
from shared.chromie_contracts.situation import (
    CognitiveOpportunity,
    SituationInterpretation,
    SituationRevisionObservation,
    SituationSourceRef,
    SituationalCognitionRequest,
    SituationalCognitionResolution,
    SituationalCommunicativeAct,
)


def goal_free_observation(
    *, revision: int = 1, audience_refs: list[str] | None = None
) -> SituationRevisionObservation:
    source = SituationSourceRef(
        kind="interaction_state",
        reference_id=f"trusted-arrival-{revision}",
        owner="trusted_scene_adapter",
    )
    interpretation = SituationInterpretation(
        interpretation_id=f"dad-arrived-{revision}",
        subject_ref="person:dad",
        relation="social.arrival",
        value="arrived_home",
        epistemic_status="established",
        relevance_goal_ids=[],
        source_refs=[source.reference_id],
    )
    projection = build_situation_projection(
        context={},
        turn_id=f"situation-{revision}",
        focus_goal_ids=[],
        audience_refs=audience_refs or [],
        revision=revision,
        source_refs=[source],
        interpretations=[interpretation],
    )
    return SituationRevisionObservation(
        observation_id=f"arrival-observation-{revision}",
        source_id="trusted_scene_adapter",
        source_revision=revision,
        goal_ids=[],
        source_refs=[source.reference_id],
        projection=projection,
    )


def test_goal_free_situation_derives_readiness_without_fake_goal() -> None:
    observation = goal_free_observation()

    opportunity = derive_situation_revision_opportunity(observation)

    assert opportunity is not None
    assert opportunity.trigger == "situation_revision"
    assert opportunity.goal_ids == []
    assert opportunity.source_refs == ["trusted-arrival-1"]
    assert opportunity.subject_refs == ["person:dad"]
    assert opportunity.situation_digest == observation.projection.digest
    assert opportunity.situation_signature == observation.projection.interpretation_signature()
    assert opportunity.recommended_cognition == "fast"
    assert (
        derive_situation_revision_opportunity(
            observation,
            previous_situation_digest=observation.projection.digest,
        )
        is None
    )


def test_goal_free_opportunity_requires_trusted_situation_provenance() -> None:
    with pytest.raises(ValueError, match="trusted source_refs"):
        CognitiveOpportunity.create(
            trigger="situation_revision",
            goal_ids=[],
            source_refs=[],
            reason_codes=["trusted_situation_revision"],
            recommended_cognition="fast",
            situation_digest="a" * 64,
            situation_signature="b" * 64,
        )


def test_semantic_situation_signature_ignores_transport_revision() -> None:
    first = goal_free_observation(revision=1)
    second = goal_free_observation(revision=2)

    assert first.projection.digest != second.projection.digest
    assert (
        first.projection.interpretation_signature()
        == second.projection.interpretation_signature()
    )


def test_semantic_situation_signature_changes_with_trusted_audience() -> None:
    without_audience = goal_free_observation(revision=1)
    with_audience = goal_free_observation(
        revision=1,
        audience_refs=["person:dad", "self:chromie"],
    )

    assert without_audience.projection.digest != with_audience.projection.digest
    assert (
        without_audience.projection.interpretation_signature()
        != with_audience.projection.interpretation_signature()
    )


def test_trusted_goal_free_ingress_preserves_source_and_audience_without_inference() -> None:
    source = SituationSourceRef(
        kind="perception",
        reference_id="scene-observation-7",
        owner="trusted_scene_adapter",
    )
    interpretation = SituationInterpretation(
        interpretation_id="person-track-7-arrival",
        subject_ref="person:dad",
        relation="social.arrival",
        value="arrived_home",
        epistemic_status="established",
        relevance_goal_ids=[],
        source_refs=[source.reference_id],
    )

    observation = build_trusted_goal_free_situation_observation(
        context={},
        turn_id="scene-turn-7",
        source_id="trusted_scene_adapter",
        source_revision=7,
        source=source,
        interpretations=[interpretation],
        audience_refs=["person:dad", "self:chromie"],
    )

    assert observation.goal_ids == []
    assert observation.source_refs == ["scene-observation-7"]
    assert observation.projection.focus_goal_ids == []
    assert observation.projection.audience_refs == ["person:dad", "self:chromie"]
    assert observation.projection.interpretations == [interpretation]


def test_trusted_goal_free_ingress_rejects_goal_semantics() -> None:
    source = SituationSourceRef(
        kind="perception",
        reference_id="scene-goal-leak",
        owner="trusted_scene_adapter",
    )
    interpretation = SituationInterpretation(
        interpretation_id="goal-leak",
        subject_ref="person:dad",
        relation="social.presence",
        value="present",
        epistemic_status="established",
        relevance_goal_ids=["goal-should-not-exist"],
        source_refs=[source.reference_id],
    )

    with pytest.raises(ValueError, match="cannot reference Goals"):
        build_trusted_goal_free_situation_observation(
            context={},
            turn_id="scene-goal-leak",
            source_id="trusted_scene_adapter",
            source_revision=1,
            source=source,
            interpretations=[interpretation],
        )


class FakeOllama:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0
        self.prompt = ""

    async def generate(self, prompt: str, **_kwargs):
        self.calls += 1
        self.prompt = prompt
        return self.output


def request_for(observation: SituationRevisionObservation) -> SituationalCognitionRequest:
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None
    return SituationalCognitionRequest(
        opportunity=opportunity,
        situation=observation.projection,
        language="zh-CN",
        context={
            "memory_summary": "爸爸今天会晚一点回来。",
            "extracted_memory": [],
            "mind": {"identity": {"name": "Chromie"}},
            "interaction_context": {"already_spoken": []},
        },
    )


def test_situational_cognition_binds_model_wording_to_runtime_provenance() -> None:
    observation = goal_free_observation()
    ollama = FakeOllama(
        {
            "disposition": "communicate",
            "activity": {
                "activity_id": "greet-dad",
                "text": "爸爸回来啦。",
                "speech_act": "greeting",
            },
            "reason_summary": "A familiar important person just arrived home.",
        }
    )
    resolver = SituationalPlannerResolver(ollama)

    resolution = asyncio.run(resolver.resolve(request_for(observation)))

    assert resolution.disposition == "communicate"
    assert resolution.activity is not None
    assert resolution.activity.text == "爸爸回来啦。"
    assert resolution.source_refs == observation.source_refs
    assert resolution.subject_refs == ["person:dad"]
    assert ollama.calls == 1
    assert "no fake Goal or user request exists" in ollama.prompt
    assert "Capability availability" in ollama.prompt


def test_slow_goal_free_readiness_fails_quiet_without_deep_planner() -> None:
    observation = goal_free_observation()
    request = request_for(observation)
    request = request.model_copy(
        update={
            "opportunity": request.opportunity.model_copy(
                update={"recommended_cognition": "slow"}
            )
        }
    )
    ollama = FakeOllama({})
    resolver = SituationalPlannerResolver(ollama)

    resolution = asyncio.run(resolver.resolve(request))

    assert resolution.disposition == "silence"
    assert resolution.activity is None
    assert ollama.calls == 0


def test_voice_assistant_uses_restricted_planner_without_goal_work_api() -> None:
    observation = goal_free_observation()
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None

    class Agent:
        planner_calls = 0
        situation_calls = 0

        async def resolve_situational_cognition(self, _session, *, request, timeout_ms):
            self.situation_calls += 1
            assert request.opportunity.goal_ids == []
            assert timeout_ms == 10000
            assert request.context["extracted_memory"][0]["key"] == "dad_relationship"
            assert request.context["relational_memory_selection"][
                "activation_subject_ref_count"
            ] == 1
            assert request.context["relational_memory_selection"][
                "audience_resolved"
            ] is False
            return SituationalCognitionResolution(
                opportunity_id=request.opportunity.opportunity_id,
                situation_digest=request.situation.digest,
                source_refs=request.opportunity.source_refs,
                subject_refs=request.opportunity.subject_refs,
                disposition="communicate",
                activity=SituationalCommunicativeAct(
                    activity_id="greet-dad",
                    text="爸爸回来啦。",
                    speech_act="greeting",
                ),
                reason_summary="Small family greeting.",
            )

        async def resolve_fast_plan(self, *_args, **_kwargs):
            self.planner_calls += 1
            raise AssertionError("Goal-bound Planner API requires Goal provenance")

        async def resolve_deep_plan(self, *_args, **_kwargs):
            self.planner_calls += 1
            raise AssertionError("Goal-bound Deep API requires Goal provenance")

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Agent()
    assistant.cognitive_runtime_policy = CognitiveRuntimePolicy(
        fast_planner_timeout_ms=3000
    )
    assistant.cognitive_runtime = SimpleNamespace(interaction_ledger=None)
    assistant.sessions = SimpleNamespace(current_sid=None)
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.conversation_state = SimpleNamespace(
        activated_memory_context=lambda **kwargs: {
            "entries": [
                {
                    "kind": "person_relationship",
                    "key": "dad_relationship",
                    "text": "Dad is a close family relationship for Chromie.",
                    "relation": "family",
                    "subject_refs": ["person:dad"],
                    "disclosure_scope": "public",
                }
            ],
            "summary": "- Dad is a close family relationship for Chromie.",
            "selection": {
                "policy": "context_subject_relevance_then_recency",
                "activation_subject_ref_count": len(
                    kwargs.get("activation_subject_refs") or []
                ),
                "audience_resolved": bool(kwargs.get("audience_refs")),
            },
        }
    )
    assistant.build_context = lambda _sid: {
        "conversation_id": "conversation-1",
        "memory_summary": "",
        "extracted_memory": [],
        "mind": {"identity": {"name": "Chromie"}},
    }
    assistant.get_http_session = lambda: asyncio.sleep(0, result=object())
    assistant._delivered_turn_speech_events = lambda _sid: []

    response = asyncio.run(
        resolve_goal_free_situation_response(
            assistant,
            observation=observation,
            opportunity=opportunity,
            session_id=None,
            language="zh-CN",
        )
    )

    assert response is not None
    assert response.capabilities == []
    assert [item.text for item in response.speech] == ["爸爸回来啦。"]
    assert response.speech[0].metadata["goal_completion_authority"] is False
    assert response.metadata["goal_ids"] == []
    assert assistant.agent_client.situation_calls == 1
    assert assistant.agent_client.planner_calls == 0


def test_routine_presence_still_uses_core_semantic_judgment_not_host_rules() -> None:
    source = SituationSourceRef(
        kind="perception",
        reference_id="routine-presence-source",
        owner="trusted_scene_adapter",
    )
    projection = build_situation_projection(
        context={},
        turn_id="routine-presence-turn",
        focus_goal_ids=[],
        revision=1,
        source_refs=[source],
        interpretations=[
            SituationInterpretation(
                interpretation_id="routine-presence",
                subject_ref="person:dad",
                relation="social.presence",
                value="present",
                epistemic_status="established",
                source_refs=[source.reference_id],
            )
        ],
    )
    observation = SituationRevisionObservation(
        observation_id="routine-presence-observation",
        source_id="trusted_scene_adapter",
        source_revision=1,
        source_refs=[source.reference_id],
        projection=projection,
    )
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None
    assert opportunity.recommended_cognition == "fast"

    class Agent:
        situation_calls = 0

        async def resolve_situational_cognition(self, _session, *, request, timeout_ms):
            self.situation_calls += 1
            assert request.situation.interpretations[0].value == "present"
            return SituationalCognitionResolution(
                opportunity_id=request.opportunity.opportunity_id,
                situation_digest=request.situation.digest,
                source_refs=request.opportunity.source_refs,
                subject_refs=request.opportunity.subject_refs,
                disposition="silence",
                activity=None,
                reason_summary="No useful outward social delta now.",
            )

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Agent()
    assistant.cognitive_runtime_policy = CognitiveRuntimePolicy(
        fast_planner_timeout_ms=3000
    )
    assistant.cognitive_runtime = SimpleNamespace(interaction_ledger=None)
    assistant.sessions = SimpleNamespace(current_sid=None)
    assistant.session_log = lambda *_args, **_kwargs: None
    assistant.conversation_state = SimpleNamespace(
        activated_memory_context=lambda **_kwargs: {
            "entries": [],
            "summary": "",
            "selection": {},
        }
    )
    assistant.build_context = lambda _sid: {
        "conversation_id": "conversation-1",
        "mind": {"identity": {"name": "Chromie"}},
    }
    assistant.get_http_session = lambda: asyncio.sleep(0, result=object())
    assistant._delivered_turn_speech_events = lambda _sid: []

    response = asyncio.run(
        resolve_goal_free_situation_response(
            assistant,
            observation=observation,
            opportunity=opportunity,
            session_id=None,
            language="zh-CN",
        )
    )

    assert response is None
    assert assistant.agent_client.situation_calls == 1


def test_trusted_audience_is_used_by_memory_privacy_gate() -> None:
    observation = goal_free_observation(
        audience_refs=["person:dad", "self:chromie"]
    )
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None
    captured: dict[str, object] = {}

    class Agent:
        async def resolve_situational_cognition(self, _session, *, request, timeout_ms):
            return SituationalCognitionResolution(
                opportunity_id=request.opportunity.opportunity_id,
                situation_digest=request.situation.digest,
                source_refs=request.opportunity.source_refs,
                subject_refs=request.opportunity.subject_refs,
                disposition="silence",
                activity=None,
                reason_summary="No speech needed.",
            )

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Agent()
    assistant.cognitive_runtime_policy = CognitiveRuntimePolicy(
        fast_planner_timeout_ms=3000
    )
    assistant.cognitive_runtime = SimpleNamespace(interaction_ledger=None)
    assistant.sessions = SimpleNamespace(current_sid=None)
    assistant.session_log = lambda *_args, **_kwargs: None

    def activated_memory_context(**kwargs):
        captured.update(kwargs)
        return {"entries": [], "summary": "", "selection": {}}

    assistant.conversation_state = SimpleNamespace(
        activated_memory_context=activated_memory_context
    )
    assistant.build_context = lambda _sid: {
        "conversation_id": "conversation-audience",
        "mind": {"identity": {"name": "Chromie"}},
    }
    assistant.get_http_session = lambda: asyncio.sleep(0, result=object())
    assistant._delivered_turn_speech_events = lambda _sid: []

    response = asyncio.run(
        resolve_goal_free_situation_response(
            assistant,
            observation=observation,
            opportunity=opportunity,
            session_id=None,
            language="zh-CN",
        )
    )

    assert response is None
    assert captured["audience_refs"] == ["person:dad", "self:chromie"]


def test_goal_free_apply_path_treats_silence_and_no_change_as_success() -> None:
    source = SituationSourceRef(
        kind="interaction_state",
        reference_id="ambient-source",
        owner="trusted_scene_adapter",
    )
    projection = build_situation_projection(
        context={},
        turn_id="ambient-turn",
        focus_goal_ids=[],
        revision=1,
        source_refs=[source],
        interpretations=[
            SituationInterpretation(
                interpretation_id="ambient-presence",
                subject_ref="place:room",
                relation="ambient.presence",
                value="unchanged",
                epistemic_status="established",
                source_refs=[source.reference_id],
            )
        ],
    )
    observation = SituationRevisionObservation(
        observation_id="ambient-observation",
        source_id="trusted_scene_adapter",
        source_revision=1,
        source_refs=[source.reference_id],
        projection=projection,
    )

    class Agent:
        async def resolve_situational_cognition(self, _session, *, request, timeout_ms):
            return SituationalCognitionResolution(
                opportunity_id=request.opportunity.opportunity_id,
                situation_digest=request.situation.digest,
                source_refs=request.opportunity.source_refs,
                subject_refs=request.opportunity.subject_refs,
                disposition="silence",
                activity=None,
                reason_summary="No meaningful outward response.",
            )

    class Host:
        def __init__(self) -> None:
            self.delivered = 0
            self.agent_client = Agent()
            self.cognitive_runtime_policy = CognitiveRuntimePolicy(
                fast_planner_timeout_ms=3000
            )
            self.cognitive_runtime = SimpleNamespace(interaction_ledger=None)
            self.sessions = SimpleNamespace(current_sid=None)
            self.conversation_state = SimpleNamespace(
                activated_memory_context=lambda **_kwargs: {
                    "entries": [],
                    "summary": "None",
                    "selection": {},
                }
            )

        def session_log(self, *_args, **_kwargs):
            return None

        def build_context(self, _sid):
            return {
                "conversation_id": "conversation-ambient",
                "mind": {"identity": {"name": "Chromie"}},
            }

        async def get_http_session(self):
            return object()

        def _delivered_turn_speech_events(self, _sid):
            return []

        async def _execute_cognitive_outcome_response(self, *_args, **_kwargs):
            self.delivered += 1
            return "unexpected"

    host = Host()
    silence = asyncio.run(
        apply_goal_free_situation_opportunity(host, observation)
    )
    no_change = asyncio.run(
        apply_goal_free_situation_opportunity(
            host,
            observation,
            previous_situation_digest=observation.projection.digest,
        )
    )

    assert silence == "silence"
    assert no_change == "no_change"
    assert host.delivered == 0

@pytest.mark.asyncio
async def test_fast_situational_cognition_can_escalate_to_same_scope_deliberation() -> None:
    observation = goal_free_observation()
    fast = FakeOllama({"disposition": "deliberate", "activity": None, "memory_candidates": [], "reason_summary": "Need broader context."})
    deep = FakeOllama({"disposition": "communicate", "activity": {"activity_id": "deep-social-1", "text": "你还好吗？", "speech_act": "inquire", "repair_of_activity_ids": []}, "memory_candidates": [], "reason_summary": "A small inquiry is appropriate."})
    resolver = SituationalPlannerResolver(fast, deliberative_ollama=deep)

    result = await resolver.resolve(request_for(observation))

    assert result.disposition == "communicate"
    assert result.activity is not None and result.activity.activity_id == "deep-social-1"
    assert fast.calls == 1
    assert deep.calls == 1
    assert "DELiberative".lower() in deep.prompt.lower()


@pytest.mark.asyncio
async def test_deliberative_situational_cognition_cannot_recurse() -> None:
    observation = goal_free_observation()
    fast = FakeOllama({"disposition": "deliberate", "activity": None, "memory_candidates": [], "reason_summary": "Need deeper reasoning."})
    deep = FakeOllama({"disposition": "deliberate", "activity": None, "memory_candidates": [], "reason_summary": "Again."})
    resolver = SituationalPlannerResolver(fast, deliberative_ollama=deep)
    with pytest.raises(ValueError, match="cannot recurse"):
        await resolver.resolve(request_for(observation))


@pytest.mark.asyncio
async def test_goal_free_planner_rejects_rewording_an_existing_activity():
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"already_spoken": [{
        "text": "Earlier words.", "state": "playback_completed",
        "metadata": {"communicative_activity_ids": ["same-act"]},
    }]}
    model = FakeOllama({"disposition": "communicate", "activity": {
        "activity_id": "same-act", "text": "Changed words.", "speech_act": "inform",
    }})
    with pytest.raises(ValueError, match="wording"):
        await SituationalPlannerResolver(model).resolve(request)
    assert model.calls == 1


@pytest.mark.asyncio
async def test_delegation_cannot_discard_an_authored_memory_result():
    request = request_for(goal_free_observation())
    fast = FakeOllama({"disposition": "deliberate", "activity": None,
        "memory_candidates": [{"text": "A shared event.", "subject_refs": ["person:dad"],
            "source_refs": request.opportunity.source_refs}]})
    deep = FakeOllama({"disposition": "silence", "activity": None})
    with pytest.raises(ValueError, match="deliberate"):
        await SituationalPlannerResolver(fast, deliberative_ollama=deep).resolve(request)
    assert fast.calls == 1
    assert deep.calls == 0


@pytest.mark.asyncio
async def test_goal_free_planner_rejects_repair_of_unheard_activity():
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"pending_speech": [{
        "text": "Unheard.", "metadata": {"communicative_activity_ids": ["pending"]},
    }]}
    model = FakeOllama({"disposition": "communicate", "activity": {
        "activity_id": "repair-new", "text": "Correction.", "speech_act": "repair",
        "repair_of_activity_ids": ["pending"],
    }})
    with pytest.raises(ValueError, match="delivered"):
        await SituationalPlannerResolver(model).resolve(request)
    assert model.calls == 1


def test_every_planner_system_prompt_uses_one_communication_contract():
    from agent.app.planner_prompt import fast_system_prompt, deep_system_prompt, fast_streaming_advance_system_prompt
    from shared.chromie_contracts.semantic_authority import PLANNER_COMMUNICATION_AUTHORITY_PROMPT
    for system in (fast_system_prompt(), deep_system_prompt(), fast_streaming_advance_system_prompt(),
                   SituationalPlannerResolver._system_prompt(), SituationalPlannerResolver._system_prompt(deliberative=True)):
        assert PLANNER_COMMUNICATION_AUTHORITY_PROMPT in system


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["silence", "communicate"])
async def test_completed_goal_free_decision_does_not_call_a_second_model(disposition):
    activity = {"activity_id": "new-act", "text": "Hello.", "speech_act": "greeting"} if disposition == "communicate" else None
    fast = FakeOllama({"disposition": disposition, "activity": activity})
    deep = FakeOllama({})
    result = await SituationalPlannerResolver(fast, deliberative_ollama=deep).resolve(request_for(goal_free_observation()))
    assert result.disposition == disposition
    assert fast.calls == 1 and deep.calls == 0


@pytest.mark.asyncio
async def test_direct_deep_goal_free_call_preserves_its_scope():
    request = request_for(goal_free_observation())
    request = request.model_copy(update={"opportunity": request.opportunity.model_copy(update={"recommended_cognition": "slow"})})
    fast = FakeOllama({})
    deep = FakeOllama({"disposition": "communicate", "activity": {
        "activity_id": "deep-act", "text": "Hello.", "speech_act": "greeting"}})
    result = await SituationalPlannerResolver(fast, deliberative_ollama=deep).resolve(request)
    assert result.source_refs == request.opportunity.source_refs
    assert result.subject_refs == request.opportunity.subject_refs
    assert fast.calls == 0 and deep.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden", ["goal_ids", "steps", "capabilities", "authorization"])
async def test_goal_free_output_cannot_acquire_goal_or_work_authority(forbidden):
    fast = FakeOllama({"disposition": "silence", forbidden: []})
    deep = FakeOllama({"disposition": "silence"})
    with pytest.raises(ValueError):
        await SituationalPlannerResolver(fast, deliberative_ollama=deep).resolve(request_for(goal_free_observation()))
    assert fast.calls == 1 and deep.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("same_identity", [True, False])
async def test_goal_free_planner_preserves_same_words_without_semantic_filtering(same_identity):
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"already_spoken": [{
        "text": "Hello.", "metadata": {"communicative_activity_ids": ["old-act"]},
    }]}
    model = FakeOllama({"disposition": "communicate", "activity": {
        "activity_id": "old-act" if same_identity else "new-act", "text": "Hello.", "speech_act": "greeting"}})
    result = await SituationalPlannerResolver(model).resolve(request)
    assert result.activity.text == "Hello."
    assert model.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unheard_repair", "subject_widening", "self_memory_widening"])
async def test_host_validates_complete_planner_result_before_any_memory_write(failure):
    from unittest.mock import Mock
    observation = goal_free_observation()
    opportunity = derive_situation_revision_opportunity(observation)
    activity = SituationalCommunicativeAct(activity_id="new", text="Hello.", speech_act="greeting")
    if failure == "unheard_repair":
        activity = SituationalCommunicativeAct(activity_id="repair", text="Correction.", speech_act="repair", repair_of_activity_ids=["unheard"])
    resolution = SituationalCognitionResolution(
        opportunity_id=opportunity.opportunity_id, situation_digest=observation.projection.digest,
        source_refs=observation.source_refs,
        subject_refs=["person:stranger"] if failure == "subject_widening" else opportunity.subject_refs,
        disposition="communicate", activity=activity,
        memory_candidates=[{"text": "Shared event.", "subject_refs": ["person:dad"], "source_refs": observation.source_refs}],
        self_memory_candidates=[{"kind": "interest", "text": "An interest.", "subject_refs": ["self:chromie", "person:stranger"], "source_refs": observation.source_refs}] if failure == "self_memory_widening" else [],
    )
    async def resolve(*args, **kwargs):
        return resolution
    async def session():
        return object()
    state = SimpleNamespace(activated_memory_context=lambda **kwargs: {"summary": "", "entries": [], "selection": {}},
        record_cognitive_relational_experience=Mock(), record_cognitive_self_context=Mock())
    host = SimpleNamespace(build_context=lambda sid: {}, conversation_state=state,
        cognitive_runtime=SimpleNamespace(interaction_ledger=None), session_log=lambda *args: None,
        sessions=SimpleNamespace(current_sid=None), get_http_session=session,
        agent_client=SimpleNamespace(resolve_situational_cognition=resolve),
        cognitive_runtime_policy=CognitiveRuntimePolicy(fast_planner_timeout_ms=3000))
    with pytest.raises(ValueError):
        await resolve_goal_free_situation_response(host, observation=observation, opportunity=opportunity,
            session_id="sid", language="en-US")
    state.record_cognitive_relational_experience.assert_not_called()
    state.record_cognitive_self_context.assert_not_called()
