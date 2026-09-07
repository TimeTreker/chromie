from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.app.situational_cognition import SituationalCognitionResolver
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
    resolver = SituationalCognitionResolver(ollama)

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
    resolver = SituationalCognitionResolver(ollama)

    resolution = asyncio.run(resolver.resolve(request))

    assert resolution.disposition == "silence"
    assert resolution.activity is None
    assert ollama.calls == 0


def test_voice_assistant_goal_free_cognition_never_calls_planner_or_emits_work() -> None:
    observation = goal_free_observation()
    opportunity = derive_situation_revision_opportunity(observation)
    assert opportunity is not None

    class Agent:
        planner_calls = 0
        situation_calls = 0

        async def resolve_situational_cognition(self, _session, *, request, timeout_ms):
            self.situation_calls += 1
            assert request.opportunity.goal_ids == []
            assert timeout_ms == 3000
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
            raise AssertionError("Planner must not own Goal-free situational cognition")

        async def resolve_deep_plan(self, *_args, **_kwargs):
            self.planner_calls += 1
            raise AssertionError("Deep Planner must not own Goal-free cognition")

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
