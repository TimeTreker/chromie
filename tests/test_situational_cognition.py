from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.app.social_cognition import SocialCognitionResolver, social_cognition_response_schema
from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialCognitionResolution, SocialCommunicativeAct
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


class EmptyCatalog:
    async def prompt_entries(self, **kwargs):
        return []


class FakeOllama:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0
        self.prompt = ""

    async def generate(self, prompt: str, **_kwargs):
        self.calls += 1
        self.prompt = prompt
        return self.output


def request_for(observation: SituationRevisionObservation) -> SocialCognitionRequest:
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None
    return SocialCognitionRequest(
        request_id=observation.observation_id, trigger="situation", source_refs=observation.source_refs,
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
        {'disposition': 'communicate', 'activities': [{'activity_id': 'greet-dad', 'text': '爸爸回来啦。', 'function': 'acknowledge', 'truth_stage': 'context_grounded'}], 'reason_summary': 'A familiar important person just arrived home.'}
    )
    resolver = SocialCognitionResolver(ollama, EmptyCatalog())

    resolution = asyncio.run(resolver.resolve(request_for(observation)))

    assert resolution.disposition == "communicate"
    assert bool(resolution.activities)
    assert resolution.activities[0].text == "爸爸回来啦。"
    assert resolution.snapshot_digest == request_for(observation).snapshot_digest()
    assert resolution.request_id == observation.observation_id
    assert ollama.calls == 1
    assert observation.projection.digest in ollama.prompt


def test_slow_goal_free_readiness_reports_unavailable_deep_without_fabricating_silence() -> None:
    request = request_for(goal_free_observation())
    request.opportunity = request.opportunity.model_copy(update={"recommended_cognition": "slow"})
    model = FakeOllama({})
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(SocialCognitionResolver(model, EmptyCatalog()).resolve(request))
    assert model.calls == 0


def test_voice_assistant_uses_social_cognition_without_goal_work_api() -> None:
    observation = goal_free_observation()
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None

    class Agent:
        planner_calls = 0
        situation_calls = 0

        async def resolve_social_cognition(self, _session, *, request, timeout_ms):
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
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                disposition="communicate",
                activities=[SocialCommunicativeAct(
                    activity_id="greet-dad",
                    text="爸爸回来啦。",
                    function="acknowledge", truth_stage="context_grounded",
                )],
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
        mode="apply", fast_planner_timeout_ms=3000
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

        async def resolve_social_cognition(self, _session, *, request, timeout_ms):
            self.situation_calls += 1
            assert request.situation.interpretations[0].value == "present"
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                disposition="silence",
                activities=[],
                reason_summary="No useful outward social delta now.",
            )

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Agent()
    assistant.cognitive_runtime_policy = CognitiveRuntimePolicy(
        mode="apply", fast_planner_timeout_ms=3000
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
        async def resolve_social_cognition(self, _session, *, request, timeout_ms):
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                disposition="silence",
                activities=[],
                reason_summary="No speech needed.",
            )

    assistant = VoiceAssistant.__new__(VoiceAssistant)
    assistant.agent_client = Agent()
    assistant.cognitive_runtime_policy = CognitiveRuntimePolicy(
        mode="apply", fast_planner_timeout_ms=3000
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
        async def resolve_social_cognition(self, _session, *, request, timeout_ms):
            return SocialCognitionResolution(
                request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
                disposition="silence",
                activities=[],
                reason_summary="No meaningful outward response.",
            )

    class Host:
        def __init__(self) -> None:
            self.delivered = 0
            self.agent_client = Agent()
            self.cognitive_runtime_policy = CognitiveRuntimePolicy(
                mode="apply", fast_planner_timeout_ms=3000
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
    fast = FakeOllama({'disposition': 'deliberate', 'activities': [], 'memory_candidates': [], 'reason_summary': 'Need broader context.'})
    deep = FakeOllama({'disposition': 'communicate', 'activities': [{'activity_id': 'deep-social-1', 'text': '你还好吗？', 'function': 'ask', 'repair_of_activity_ids': [], 'truth_stage': 'context_grounded'}], 'memory_candidates': [], 'reason_summary': 'A small inquiry is appropriate.'})
    resolver = SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep)

    result = await resolver.resolve(request_for(observation))

    assert result.disposition == "communicate"
    assert result.activities and result.activities[0].activity_id == "deep-social-1"
    assert fast.calls == 1
    assert deep.calls == 1
    assert observation.projection.digest in deep.prompt


@pytest.mark.asyncio
async def test_deliberative_situational_cognition_cannot_recurse() -> None:
    observation = goal_free_observation()
    fast = FakeOllama({'disposition': 'deliberate', 'activities': [], 'memory_candidates': [], 'reason_summary': 'Need deeper reasoning.'})
    deep = FakeOllama({'disposition': 'deliberate', 'activities': [], 'memory_candidates': [], 'reason_summary': 'Again.'})
    resolver = SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep)
    with pytest.raises(ValueError, match="Schema rejected"):
        await resolver.resolve(request_for(observation))


@pytest.mark.asyncio
async def test_goal_free_social_cognition_rejects_rewording_an_existing_activity():
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"already_spoken": [{
        "text": "Earlier words.", "state": "playback_completed",
        "metadata": {"communicative_activity_ids": ["same-act"]},
    }]}
    model = FakeOllama({'disposition': 'communicate', 'activities': [{'activity_id': 'same-act', 'text': 'Changed words.', 'function': 'inform', 'truth_stage': 'context_grounded'}], 'reason_summary': 'Controlled SC decision.'})
    with pytest.raises(ValueError, match="raw Schema rejected"):
        await SocialCognitionResolver(model, EmptyCatalog()).resolve(request)
    assert model.calls == 1


@pytest.mark.asyncio
async def test_delegation_cannot_discard_an_authored_memory_result():
    request = request_for(goal_free_observation())
    fast = FakeOllama({'disposition': 'deliberate', 'activities': [], 'memory_candidates': [{'text': 'A shared event.', 'subject_refs': ['person:dad'], 'source_refs': request.opportunity.source_refs}], 'reason_summary': 'Controlled SC decision.'})
    deep = FakeOllama({'disposition': 'silence', 'activities': [], 'reason_summary': 'Controlled SC decision.'})
    with pytest.raises(ValueError, match="raw Schema rejected"):
        await SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep).resolve(request)
    assert fast.calls == 1
    assert deep.calls == 0


@pytest.mark.asyncio
async def test_goal_free_social_cognition_rejects_repair_of_unheard_activity():
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"pending_speech": [{
        "text": "Unheard.", "metadata": {"communicative_activity_ids": ["pending"]},
    }]}
    schema = social_cognition_response_schema(request, [])
    fresh_id = schema['$defs']['SocialCommunicativeAct']['oneOf'][0]['properties']['activity_id']['enum'][0]
    model = FakeOllama({'disposition': 'communicate', 'activities': [{'activity_id': fresh_id, 'text': 'Correction.', 'function': 'repair', 'repair_of_activity_ids': ['pending'], 'truth_stage': 'context_grounded'}], 'reason_summary': 'Controlled SC decision.'})
    with pytest.raises(ValueError, match="raw Schema rejected"):
        await SocialCognitionResolver(model, EmptyCatalog()).resolve(request)
    assert model.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", ["silence", "communicate"])
async def test_completed_goal_free_decision_does_not_call_a_second_model(disposition):
    activity = {"activity_id": "new-act", "text": "Hello.", "function": "acknowledge", "truth_stage": "context_grounded"} if disposition == "communicate" else None
    fast = FakeOllama({'disposition': disposition, 'activities': [activity] if activity else [], 'reason_summary': 'Controlled SC decision.'})
    deep = FakeOllama({})
    result = await SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep).resolve(request_for(goal_free_observation()))
    assert result.disposition == disposition
    assert fast.calls == 1 and deep.calls == 0


@pytest.mark.asyncio
async def test_direct_deep_goal_free_call_preserves_its_scope():
    request = request_for(goal_free_observation())
    request = request.model_copy(update={"opportunity": request.opportunity.model_copy(update={"recommended_cognition": "slow"})})
    fast = FakeOllama({})
    deep = FakeOllama({'disposition': 'communicate', 'activities': [{'activity_id': 'deep-act', 'text': 'Hello.', 'function': 'acknowledge', 'truth_stage': 'context_grounded'}], 'reason_summary': 'Controlled SC decision.'})
    result = await SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep).resolve(request)
    assert result.snapshot_digest == request.snapshot_digest()
    assert result.request_id == request.request_id
    assert fast.calls == 0 and deep.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden", ["goal_ids", "steps", "capabilities", "authorization"])
async def test_goal_free_output_cannot_acquire_goal_or_work_authority(forbidden):
    fast = FakeOllama({'disposition': 'silence', forbidden: [], 'activities': [], 'reason_summary': 'Controlled SC decision.'})
    deep = FakeOllama({'disposition': 'silence', 'activities': [], 'reason_summary': 'Controlled SC decision.'})
    with pytest.raises(ValueError):
        await SocialCognitionResolver(fast, EmptyCatalog(), deep_model=deep).resolve(request_for(goal_free_observation()))
    assert fast.calls == 1 and deep.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("same_identity", [True, False])
async def test_goal_free_social_cognition_preserves_same_words_without_semantic_filtering(same_identity):
    request = request_for(goal_free_observation())
    request.context["interaction_context"] = {"already_spoken": [{
        "text": "Hello.", "metadata": {"communicative_activity_ids": ["old-act"]},
    }]}
    schema = social_cognition_response_schema(request, [])
    fresh_id = schema['$defs']['SocialCommunicativeAct']['oneOf'][0]['properties']['activity_id']['enum'][0]
    model = FakeOllama({'disposition': 'communicate', 'activities': [{'activity_id': 'old-act' if same_identity else fresh_id, 'text': 'Hello.', 'function': 'acknowledge', 'truth_stage': 'context_grounded'}], 'reason_summary': 'Controlled SC decision.'})
    result = await SocialCognitionResolver(model, EmptyCatalog()).resolve(request)
    assert result.activities[0].text == "Hello."
    assert model.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["unheard_repair", "subject_widening", "self_memory_widening"])
async def test_host_validates_complete_social_cognition_result_before_any_memory_write(failure):
    from unittest.mock import Mock
    observation = goal_free_observation()
    opportunity = derive_situation_revision_opportunity(observation)
    activity = SocialCommunicativeAct(activity_id="new", text="Hello.", function="acknowledge", truth_stage="context_grounded")
    if failure == "unheard_repair":
        activity = SocialCommunicativeAct(activity_id="repair", text="Correction.", function="repair", truth_stage="context_grounded", repair_of_activity_ids=["unheard"])
    async def resolve(*args, request, **kwargs):
        return SocialCognitionResolution(
            request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
            disposition="communicate", activities=[activity], reason_summary="Controlled response.",
            memory_candidates=[{"text": "Shared event.", "subject_refs": ["person:stranger"] if failure == "subject_widening" else ["person:dad"], "source_refs": observation.source_refs}],
            self_memory_candidates=[{"kind": "interest", "text": "An interest.", "subject_refs": ["self:chromie", "person:stranger"], "source_refs": observation.source_refs}] if failure == "self_memory_widening" else [],
        )
    async def session():
        return object()
    state = SimpleNamespace(activated_memory_context=lambda **kwargs: {"summary": "", "entries": [], "selection": {}},
        record_cognitive_relational_experience=Mock(), record_cognitive_self_context=Mock())
    host = SimpleNamespace(build_context=lambda sid: {}, conversation_state=state,
        cognitive_runtime=SimpleNamespace(interaction_ledger=None), session_log=lambda *args: None,
        sessions=SimpleNamespace(current_sid=None), get_http_session=session,
        agent_client=SimpleNamespace(resolve_social_cognition=resolve),
        cognitive_runtime_policy=CognitiveRuntimePolicy(mode="apply", fast_planner_timeout_ms=3000))
    with pytest.raises(ValueError):
        await resolve_goal_free_situation_response(host, observation=observation, opportunity=opportunity,
            session_id="sid", language="en-US")
    state.record_cognitive_relational_experience.assert_not_called()
    state.record_cognitive_self_context.assert_not_called()


@pytest.mark.asyncio
async def test_newer_situation_supersedes_inflight_speech_and_memory():
    from unittest.mock import Mock

    old_started = asyncio.Event()
    release_old = asyncio.Event()
    memory_write = Mock()

    async def resolve(_session, *, request, **kwargs):
        if request.situation.revision == 1:
            old_started.set()
            await release_old.wait()
        return SocialCognitionResolution(
            request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
            disposition="communicate", reason_summary="Current arrival.",
            activities=[SocialCommunicativeAct(activity_id=request.request_id, text="欢迎回来。",
                                               function="acknowledge", truth_stage="context_grounded")],
            memory_candidates=[{"text": "An arrival.", "subject_refs": ["person:dad"], "source_refs": request.source_refs}],
        )

    host = SimpleNamespace(
        build_context=lambda sid: {}, session_log=lambda *args: None,
        get_http_session=lambda: asyncio.sleep(0, result=object()),
        agent_client=SimpleNamespace(resolve_social_cognition=resolve),
        cognitive_runtime=SimpleNamespace(interaction_ledger=None),
        cognitive_runtime_policy=CognitiveRuntimePolicy(mode="apply"),
        sessions=SimpleNamespace(current_sid=None),
        conversation_state=SimpleNamespace(
            activated_memory_context=lambda **kwargs: {"summary": "", "entries": [], "selection": {}},
            record_cognitive_relational_experience=memory_write,
        ),
    )
    old, new = goal_free_observation(), goal_free_observation(revision=2)
    async def run(observation):
        return await resolve_goal_free_situation_response(
            host, observation=observation, opportunity=derive_situation_revision_opportunity(observation),
            session_id="sid", language="zh-CN",
        )
    old_task = asyncio.create_task(run(old))
    await old_started.wait()
    current = await run(new)
    release_old.set()
    assert await old_task is None
    assert current.speech[0].metadata["communicative_activity_ids"] == [new.observation_id]
    memory_write.assert_called_once()
    assert memory_write.call_args.args[0][0].source_refs == new.source_refs
    assert await run(new) is None


@pytest.mark.asyncio
async def test_environment_nonverbal_sc_uses_existing_soridormi_expression_runtime():
    from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
    from tests.test_planner_auxiliary_activity_contract import _Runtime, _definition

    provider = _Runtime([_definition()])
    async def resolve(_session, *, request, **kwargs):
        return SocialCognitionResolution(
            request_id=request.request_id, snapshot_digest=request.snapshot_digest(), model_call_count=1,
            disposition="communicate", reason_summary="A wordless acknowledgement.",
            activities=[SocialCommunicativeAct(
                activity_id="wordless", function="nonverbal", truth_stage="context_grounded",
                auxiliary_activities=[{"auxiliary_activity_id": "blink", "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 1}, "anchor_kind": "communicative_act", "anchor_id": "wordless"}],
            )],
        )
    deliveries = []
    async def deliver(response, **kwargs):
        deliveries.append(response)
        dispatch = await provider.submit_response(response, session_id="sid")
        await provider.wait_dispatch(dispatch)
        return "interaction_runtime_completed"
    host = SimpleNamespace(
        build_context=lambda sid: {}, session_log=lambda *args: None,
        get_http_session=lambda: asyncio.sleep(0, result=object()),
        agent_client=SimpleNamespace(resolve_social_cognition=resolve),
        cognitive_runtime=SimpleNamespace(interaction_ledger=None, adapter=CanonicalPlanRuntimeAdapter(provider)),
        cognitive_runtime_policy=CognitiveRuntimePolicy(mode="apply"),
        sessions=SimpleNamespace(current_sid=None), _execute_cognitive_outcome_response=deliver,
        conversation_state=SimpleNamespace(
            activated_memory_context=lambda **kwargs: {"summary": "", "entries": [], "selection": {}},
        ),
    )
    await apply_goal_free_situation_opportunity(host, goal_free_observation(), session_id="sid")
    assert deliveries[0].speech == [] and len(deliveries[0].capabilities) == 1
    request = provider.executed[0][0].capabilities[0]
    assert request.capability_id == "soridormi.blink_eyes"
    assert request.metadata["anchor_id"] == "wordless"
    assert request.metadata["source_goal_ids"] == []
