from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch, CapabilitySearchResult
from agent.app.interaction import (
    InteractionOutputCoordinator,
    NativeInteractionOutputError,
)
from agent.app.runtime import AgentRuntime, InteractionRuntime
from agent.app.schema import AgentResult, AgentRunRequest
from agent.app.task_graph.models import TaskGraph, TaskNode


class _FakePlanner:
    async def plan(self, **_: Any) -> TaskGraph:
        return TaskGraph(
            graph_id="graph_native",
            user_request="weather",
            created_by="llm",
            nodes=[
                TaskNode(
                    id="report",
                    tool="chromie.report",
                    type="report",
                    args={"message": "sunny"},
                )
            ],
        )


class _ConfirmingPlanner:
    async def plan(self, **_: Any) -> TaskGraph:
        return TaskGraph(
            graph_id="graph_confirm",
            user_request="walk to the kitchen",
            created_by="llm",
            requires_confirmation=True,
            nodes=[
                TaskNode(
                    id="submit",
                    tool="soridormi.task.submit",
                    type="action",
                    args={"task_type": "navigate_to_location"},
                )
            ],
        )


class _NativeRuntimeStub:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> Any:
        self.calls += 1
        return self.response


class _LegacyRuntimeStub:
    def __init__(self, result: AgentResult | None = None) -> None:
        self.result = result or AgentResult()
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> AgentResult:
        self.calls += 1
        return self.result


class _AgreementOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "Yes, you are correct."


class _ChatOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "I am listening."


class _JokeWalkIdentityOllama:
    def __init__(self) -> None:
        self.spoken_calls = 0

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        del prompt
        if kwargs.get("response_format") == "json":
            return {
                "decision": "execute",
                "speech": "",
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 15.0},
                    }
                ],
            }
        self.spoken_calls += 1
        if self.spoken_calls == 1:
            return "Hello. Why did the robot tell jokes? To keep the room charged."
        return "I'm Chromie, a 6-year-old AI robot."


class _UnsupportedStatusThenChatOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        if kwargs.get("response_format") == "json":
            return {"decision": "unsupported", "speech": "unsupported", "skills": []}
        return "Yes, that joke was pretty silly."


class _WeakAgreementCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "conversation_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=7,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.turn_in_place",
                    agent_id="soridormi.skill",
                    description="Rotate left or right with near-zero forward velocity.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.165,
                    metadata={"mode": "sim"},
                ),
                CapabilityMatch(
                    capability_id="soridormi.nod_yes",
                    agent_id="soridormi.skill",
                    description="Visible repeated bounded head pitch motion for yes/acknowledgement.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.03,
                    metadata={"mode": "sim"},
                ),
            ],
        )


class _AttentionCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=False,
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=9,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.express_attention",
                    agent_id="soridormi.skill",
                    description="Small head-only attention/listening gesture.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.0,
                    metadata={"mode": "sim"},
                )
            ],
        )


class _ChatCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="chat",
            suggested_agents=["conversation_agent", "speaker_agent"],
            catalog_version=3,
            matches=[],
        )


class _SpeechCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="chat",
            suggested_agents=[
                "capability_agent",
                "conversation_agent",
                "speaker_agent",
            ],
            catalog_version=10,
            matches=[
                CapabilityMatch(
                    capability_id="chromie.speak",
                    agent_id="chromie.speech",
                    description="Speak a short message to the user.",
                    effects=["user_interaction", "audio_output"],
                    safety_class="low_risk_action",
                    interaction_executable=False,
                    requires_confirmation=False,
                    route="chat",
                    score=0.455,
                ),
                CapabilityMatch(
                    capability_id="soridormi.express_attention",
                    agent_id="soridormi.skill",
                    description="Small head-only attention/listening gesture.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.0,
                    metadata={"mode": "sim"},
                ),
            ],
        )


class _WalkCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del text, kwargs
        return CapabilitySearchResult(
            query="walk",
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=11,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.walk_velocity",
                    agent_id="soridormi.skill",
                    description="Track a bounded body velocity command.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.5,
                    metadata={"mode": "sim"},
                )
            ],
        )


class _JokeWalkIdentityCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        normalized = " ".join((text or "").lower().split())
        strong_walk = "walk forward" in normalized
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=15,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.walk_velocity",
                    agent_id="soridormi.skill",
                    description="Track a bounded body velocity command.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "vx_mps": {"type": "number", "minimum": -0.2, "maximum": 0.2},
                            "duration_s": {"type": "number", "minimum": 0.1, "maximum": 20.0},
                        },
                        "required": ["vx_mps", "duration_s"],
                        "additionalProperties": False,
                    },
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.82 if strong_walk else 0.225,
                    metadata={"mode": "sim"},
                )
            ],
        )


class _JokeOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "Why did the robot bring a ladder? To reach the cloud."


class _SongOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "La la, here is a small song just for you."


class _SongMotionCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=12,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.curve_walk",
                    agent_id="soridormi.skill",
                    description="Walk forward while tracking a yaw command.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.5,
                    metadata={"mode": "sim"},
                )
            ],
        )


class _CompoundMotionCatalog:
    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=[
                "capability_agent",
                "safety_agent",
                "speaker_agent",
            ],
            catalog_version=13,
            matches=[
                CapabilityMatch(
                    capability_id="soridormi.turn_in_place",
                    agent_id="soridormi.skill",
                    description="Rotate left or right with near-zero forward velocity.",
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.51,
                    metadata={"mode": "sim"},
                ),
                CapabilityMatch(
                    capability_id="soridormi.walk_velocity",
                    agent_id="soridormi.skill",
                    description="Track a bounded body velocity command.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "vx_mps": {"type": "number"},
                            "duration_s": {"type": "number"},
                        },
                    },
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.43,
                    metadata={"mode": "sim"},
                ),
                CapabilityMatch(
                    capability_id="soridormi.look_at_person",
                    agent_id="soridormi.skill",
                    description="Turn head toward a structured person target direction.",
                    input_schema={
                        "type": "object",
                        "properties": {"target_yaw_rad": {"type": "number"}},
                    },
                    effects=["physical_motion"],
                    safety_class="physical_motion",
                    interaction_executable=True,
                    requires_confirmation=True,
                    route="robot_action",
                    score=0.35,
                    metadata={"mode": "sim"},
                ),
                CapabilityMatch(
                    capability_id="soridormi.blink_eyes",
                    agent_id="soridormi.skill",
                    description="Blink the simulated social eyes.",
                    input_schema={
                        "type": "object",
                        "properties": {"count": {"type": "number"}},
                    },
                    effects=["visual_expression"],
                    safety_class="low_risk_action",
                    interaction_executable=True,
                    requires_confirmation=False,
                    route="robot_action",
                    score=0.35,
                    metadata={"mode": "sim"},
                ),
            ],
        )


class _CompoundMotionOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["response_format"] == "json"
        assert "soridormi.turn_in_place" in prompt
        assert "soridormi.walk_velocity" in prompt
        assert "soridormi.blink_eyes" in prompt
        return {
            "decision": "execute",
            "speech": "I will walk, look right, and blink.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_velocity",
                    "args": {"vx_mps": 0.2, "duration_s": 10.0},
                },
                {
                    "skill_id": "soridormi.look_at_person",
                    "args": {"target_yaw_rad": -0.35},
                },
                {
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                },
            ],
        }


def _request(
    *,
    text: str = "nod",
    route: str = "robot_action",
    intent: str = "nod",
    agents: list[str] | None = None,
) -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "native-interaction",
            "text": text,
            "route_decision": {
                "route": route,
                "agents": agents or [],
                "intent": intent,
                "confidence": 1.0,
                "language": "en-US",
                "source": "rules",
            },
        }
    )


class NativeInteractionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_runtime_emits_named_skill_without_result_adapter(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "native-interaction",
                "text": "nod",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.nod_yes",
                    "confidence": 1.0,
                    "language": "en-US",
                    "source": "llm",
                    "actions": [
                        {
                            "capability_id": "soridormi.nod_yes",
                            "args": {"count": 2},
                            "sequence": 0,
                        }
                    ],
                },
            }
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
            )
        ).run(request)

        self.assertEqual(response.metadata["interaction_output_mode"], "native")
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "Nodding.")
        self.assertIn("capability_agent", response.metadata["handled_by"])

    async def test_speech_while_body_action_waits_for_playback_start(self) -> None:
        request = AgentRunRequest.model_validate(
            {
                "sid": "native-interaction",
                "text": "sing a song for me while walk forward for 10 seconds",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_velocity",
                    "confidence": 0.99,
                    "language": "en-US",
                    "source": "catalog",
                    "speak_first": "La la, walking with you.",
                    "actions": [
                        {
                            "capability_id": "soridormi.walk_velocity",
                            "args": {"vx_mps": 0.18, "duration_s": 10.0},
                            "sequence": 0,
                        }
                    ],
                },
            }
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_WalkCatalog(),  # type: ignore[arg-type]
            )
        ).run(request)

        self.assertEqual(response.speech[0].timing, "immediate")
        self.assertNotIn("alignment", response.speech[0].metadata)
        self.assertNotIn("wait_for_playback_start", response.speech[0].metadata)
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_velocity")

    async def test_affirmative_chat_adds_parallel_attention_cue(self) -> None:
        request = _request(
            text="I think the sun is hot and round, do you agree with me?",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_AgreementOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_AttentionCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="sim_only",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(response.speech[0].text, "Yes, you are correct.")
        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.express_attention")
        self.assertEqual(
            response.skills[0].args,
            {"style": "neutral", "duration_s": 2.4, "hold_fraction": 0.35},
        )
        self.assertEqual(response.skills[0].timing, "parallel")
        self.assertTrue(response.skills[0].requires_confirmation)
        self.assertEqual(
            response.skills[0].metadata["source"],
            "expressive_body_cue",
        )
        self.assertEqual(response.metadata["expressive_body_cue"], "soridormi.express_attention")

    async def test_chat_only_response_adds_attention_cue(self) -> None:
        request = _request(
            text="Tell me something interesting.",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_AttentionCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="sim_only",
            )
        ).run(request)

        self.assertEqual(response.speech[0].text, "I am listening.")
        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.express_attention")
        self.assertEqual(
            response.skills[0].args,
            {"style": "neutral", "duration_s": 2.4, "hold_fraction": 0.35},
        )
        self.assertEqual(response.skills[0].timing, "parallel")
        self.assertEqual(
            response.skills[0].metadata["reason"],
            "chat_attention",
        )
        self.assertEqual(
            response.metadata["expressive_body_cue"],
            "soridormi.express_attention",
        )

    async def test_chat_catalog_speech_match_still_uses_conversation_llm(self) -> None:
        request = _request(
            text="tell a joke to me",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_JokeOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_SpeechCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="sim_only",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(request.route_decision.intent, "general_conversation")
        self.assertNotEqual(
            response.metadata.get("capability_decision"),
            "blocked",
        )
        self.assertEqual(
            response.speech[0].text,
            "Why did the robot bring a ladder? To reach the cloud.",
        )
        self.assertEqual(response.skills[0].skill_id, "soridormi.express_attention")

    async def test_capability_unsupported_status_label_is_not_spoken(self) -> None:
        ollama = _UnsupportedStatusThenChatOllama()
        request = _request(
            text="It's really kidding.",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        request.route_decision.source = "fallback"
        request.route_decision.confidence = 0.45

        response = await InteractionRuntime(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertNotIn("capability_decision", response.metadata)
        self.assertEqual(response.speech[0].text, "Yes, that joke was pretty silly.")
        self.assertNotEqual(response.speech[0].text.lower(), "unsupported")
        self.assertIn("conversation_agent", response.metadata["handled_by"])
        self.assertEqual(len(ollama.calls), 1)

    async def test_capability_unsupported_status_label_gets_natural_fallback_without_conversation(self) -> None:
        request = _request(
            text="Walk forward for 15 seconds.",
            route="robot_action",
            intent="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
        )

        response = await InteractionRuntime(
            AgentServices(
                ollama=_UnsupportedStatusThenChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_WalkCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(response.metadata["capability_decision"], "unsupported")
        self.assertEqual(
            response.speech[0].text,
            "I cannot safely map that to an available action. Please say it another way.",
        )
        self.assertEqual(response.skills, [])

    async def test_deep_thought_route_survives_capability_preflight(self) -> None:
        request = _request(
            text="Let's design the session memory architecture carefully.",
            route="deep_thought",
            intent="session_memory_design",
            agents=["conversation_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_ChatCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="sim_only",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "deep_thought")
        self.assertEqual(request.route_decision.agents, ["deepthinking_agent", "speaker_agent"])
        self.assertEqual(response.speech[0].text, "I am listening.")
        self.assertEqual(response.skills, [])

    async def test_confident_llm_chat_is_not_overwritten_by_motion_catalog(self) -> None:
        request = _request(
            text="Go ahead and sing a song for me.",
            route="chat",
            intent="chat",
            agents=["conversation_agent", "speaker_agent"],
        )
        request.route_decision.source = "llm"
        request.route_decision.confidence = 0.72

        response = await InteractionRuntime(
            AgentServices(
                ollama=_SongOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_SongMotionCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(response.speech[0].text, "La la, here is a small song just for you.")
        self.assertNotIn("capability_decision", response.metadata)
        self.assertEqual(response.skills, [])

    async def test_fallback_chat_is_not_promoted_by_strong_motion_catalog_match(self) -> None:
        request = _request(
            text="Walk forward at 0.2 speed for one second.",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        request.route_decision.source = "fallback"
        request.route_decision.confidence = 0.3

        response = await InteractionRuntime(
            AgentServices(
                ollama=_ChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_WalkCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(request.route_decision.agents, ["conversation_agent", "speaker_agent"])
        self.assertEqual(request.route_decision.source, "fallback")
        self.assertEqual(response.speech[0].text, "I am listening.")
        self.assertEqual(response.skills, [])
        self.assertNotIn("capability_decision", response.metadata)

    async def test_broad_llm_robot_action_is_not_narrowed_to_top_catalog_match(self) -> None:
        request = _request(
            text="please walk forward at 0.20 for 10 seconds and turn your head right and blink your eyes",
            route="robot_action",
            intent="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
        )
        request.route_decision.source = "llm"
        request.route_decision.confidence = 0.55

        response = await InteractionRuntime(
            AgentServices(
                ollama=_CompoundMotionOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_CompoundMotionCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "robot_action")
        self.assertEqual(request.route_decision.intent, "robot_action")
        self.assertEqual(request.route_decision.source, "llm")
        self.assertEqual(
            [skill.skill_id for skill in response.skills],
            [
                "soridormi.walk_velocity",
                "soridormi.look_at_person",
                "soridormi.blink_eyes",
            ],
        )
        self.assertEqual(response.skills[0].args, {"vx_mps": 0.2, "duration_s": 10.0})
        self.assertEqual(response.skills[2].args, {"count": 2})

    async def test_expressive_body_cues_off_keeps_chat_speech_only(self) -> None:
        request = _request(
            text="Tell me something interesting.",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_AttentionCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        ).run(request)

        self.assertEqual(response.speech[0].text, "I am listening.")
        self.assertEqual(response.skills, [])

    async def test_weak_catalog_motion_match_is_not_phrase_corrected_in_runtime(self) -> None:
        request = _request(
            text="I think the sun is hot and round, do you agree with me?",
            route="robot_action",
            intent="capability:soridormi.turn_in_place",
            agents=["capability_agent", "conversation_agent", "safety_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "robot_action")
        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.speech[0].text,
            "I heard you, but my language model is not responding.",
        )

    async def test_weak_catalog_match_does_not_promote_chat_identity_to_motion(self) -> None:
        request = _request(
            text="Who are you? What's your name?",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        request.route_decision.source = "fallback"
        request.route_decision.confidence = 0.45
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ChatOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(request.route_decision.agents, ["conversation_agent", "speaker_agent"])
        self.assertEqual(response.skills, [])
        self.assertEqual(response.speech[0].text, "I am listening.")
        self.assertNotIn("capability_promotion_blocked", request.context)

    async def test_joke_walk_identity_sequence_does_not_carry_motion_into_identity_chat(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_JokeWalkIdentityOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_JokeWalkIdentityCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="off",
            )
        )

        first = _request(
            text="Hello, how are you? can you tell me a joke?",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        first.route_decision.source = "fallback"
        first.route_decision.confidence = 0.45
        first_response = await runtime.run(first)

        self.assertEqual(first.route_decision.route, "chat")
        self.assertEqual(first_response.skills, [])
        self.assertIn("robot", first_response.speech[0].text.lower())
        self.assertIn("joke", first_response.speech[0].text.lower())

        second = _request(
            text="OK, please walk forward for 15s quickly, please.",
            route="robot_action",
            intent="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
        )
        second.route_decision.source = "llm"
        second.route_decision.confidence = 0.72
        second.history = [
            {"role": "user", "text": first.text},
            {"role": "assistant", "text": first_response.speech[0].text},
        ]
        second_response = await runtime.run(second)

        self.assertEqual(second.route_decision.route, "robot_action")
        self.assertEqual([item.skill_id for item in second_response.skills], ["soridormi.walk_velocity"])
        self.assertEqual(second_response.skills[0].args, {"vx_mps": 0.2, "duration_s": 15.0})
        self.assertEqual(second_response.speech[0].text, "Walking forward for 15 seconds.")

        third = _request(
            text="How are you ? what's your name and how old are you?",
            route="chat",
            intent="general_conversation",
            agents=["conversation_agent", "speaker_agent"],
        )
        third.route_decision.source = "fallback"
        third.route_decision.confidence = 0.45
        third.history = [
            {"role": "user", "text": first.text},
            {"role": "assistant", "text": first_response.speech[0].text},
            {"role": "user", "text": second.text},
            {"role": "assistant", "text": second_response.speech[0].text},
        ]
        third.context["current_task_context"] = {
            "task_id": "task-walk-15s",
            "task_relation": "side_conversation",
            "task_type": "robot_action",
            "goal": second.text,
            "last_meaningful_user_turn": second.text,
            "last_assistant_response": second_response.speech[0].text,
        }
        third_response = await runtime.run(third)

        self.assertEqual(third.route_decision.route, "chat")
        self.assertEqual(third.route_decision.agents, ["conversation_agent", "speaker_agent"])
        self.assertEqual(third_response.skills, [])
        self.assertIn("chromie", third_response.speech[0].text.lower())
        self.assertIn("6-year-old", third_response.speech[0].text.lower())
        self.assertNotIn("walking", third_response.speech[0].text.lower())
        self.assertNotIn("capability_promotion_blocked", third.context)

    async def test_appearance_compliment_is_not_phrase_corrected_in_runtime(self) -> None:
        request = _request(
            text="You look beautiful, don't you?",
            route="robot_action",
            intent="capability:soridormi.turn_in_place",
            agents=["capability_agent", "conversation_agent", "safety_agent", "speaker_agent"],
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "robot_action")
        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.speech[0].text,
            "I heard you, but my language model is not responding.",
        )

    async def test_legacy_run_contract_remains_unchanged(self) -> None:
        request = _request(
            agents=["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
        )
        request.context["allow_legacy_rule_agents"] = True
        result = await AgentRuntime(
            AgentServices(ollama=None, use_llm=False, max_speak_chars=160)
        ).run(request)

        self.assertEqual(result.actions[0].type, "head.nod")
        self.assertEqual(result.actions[0].params, {"times": 1})
        self.assertEqual(result.speak_immediate[0].text, "Okay.")

    async def test_native_task_graph_is_emitted_as_structured_skill(self) -> None:
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=True,
                max_speak_chars=160,
                task_graph_planner=_FakePlanner(),  # type: ignore[arg-type]
            )
        ).run(
            _request(
                text="check the weather",
                route="tool",
                intent="weather_query",
                agents=["tool_agent", "speaker_agent"],
            )
        )

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "chromie.task_graph.execute")
        self.assertEqual(
            response.skills[0].args["graph"]["graph_id"],
            "graph_native",
        )

    async def test_native_task_graph_propagates_graph_confirmation(self) -> None:
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=True,
                max_speak_chars=160,
                task_graph_planner=_ConfirmingPlanner(),  # type: ignore[arg-type]
            )
        ).run(
            _request(
                text="walk to the kitchen",
                route="tool",
                intent="soridormi_task_planning",
                agents=["tool_agent", "speaker_agent"],
            )
        )

        self.assertTrue(response.requires_confirmation)
        self.assertTrue(response.skills[0].requires_confirmation)

    async def test_native_validation_failure_is_fail_closed_by_default(self) -> None:
        native = _NativeRuntimeStub(
            {
                "status": "ok",
                "skills": [
                    {
                        "skill_id": "unsafe.test",
                        "args": {"joint_targets": [0.1, 0.2]},
                    }
                ],
            }
        )
        legacy = _LegacyRuntimeStub()
        coordinator = InteractionOutputCoordinator(native, legacy)

        with self.assertRaises(NativeInteractionOutputError):
            await coordinator.run(_request())

        self.assertEqual(native.calls, 1)
        self.assertEqual(legacy.calls, 0)

    async def test_explicit_fallback_uses_legacy_adapter_after_validation_error(self) -> None:
        native = _NativeRuntimeStub(
            {
                "status": "ok",
                "skills": [
                    {
                        "skill_id": "unsafe.test",
                        "args": {"joint_targets": [0.1, 0.2]},
                    }
                ],
            }
        )
        legacy_result = AgentResult()
        legacy_result.add_speak_immediate("Fallback response.")
        legacy_result.add_action(
            "robot_pose_controller",
            "head.nod",
            params={"times": 1},
        )
        legacy = _LegacyRuntimeStub(legacy_result)
        coordinator = InteractionOutputCoordinator(
            native,
            legacy,
            fallback_to_legacy=True,
        )

        response = await coordinator.run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "legacy-fallback")
        self.assertIn("native_validation_error", response.metadata)
        self.assertNotIn("[0.1,0.2]", response.model_dump_json())
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(legacy.calls, 1)

    async def test_legacy_adapter_mode_skips_native_runtime(self) -> None:
        native = _NativeRuntimeStub({"status": "ok"})
        legacy_result = AgentResult()
        legacy_result.add_speak_immediate("Compatibility response.")
        legacy = _LegacyRuntimeStub(legacy_result)
        coordinator = InteractionOutputCoordinator(
            native,
            legacy,
            mode="legacy-adapter",
        )

        response = await coordinator.run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "legacy-adapter")
        self.assertEqual(response.speech[0].text, "Compatibility response.")
        self.assertEqual(native.calls, 0)
        self.assertEqual(legacy.calls, 1)


if __name__ == "__main__":
    unittest.main()
