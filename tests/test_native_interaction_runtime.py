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
        response = await InteractionRuntime(
            AgentServices(ollama=None, use_llm=False, max_speak_chars=160)
        ).run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "native")
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "Okay.")
        self.assertIn("robot_pose_controller_agent", response.metadata["handled_by"])

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

        self.assertEqual(response.speech[0].timing, "sequential")
        self.assertEqual(response.speech[0].metadata["alignment"], "body_start")
        self.assertTrue(response.speech[0].metadata["wait_for_playback_start"])
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_velocity")

    async def test_affirmative_chat_adds_parallel_sim_nod_cue(self) -> None:
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
                capability_catalog=_WeakAgreementCatalog(),  # type: ignore[arg-type]
                expressive_body_cues="sim_only",
            )
        ).run(request)

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(response.speech[0].text, "Yes, you are correct.")
        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(
            response.skills[0].args,
            {"count": 2, "amplitude": "small", "duration_s": 1.4},
        )
        self.assertEqual(response.skills[0].timing, "parallel")
        self.assertTrue(response.skills[0].requires_confirmation)
        self.assertEqual(
            response.skills[0].metadata["source"],
            "expressive_body_cue",
        )
        self.assertEqual(response.metadata["expressive_body_cue"], "soridormi.nod_yes")

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

    async def test_weak_catalog_motion_match_does_not_override_chat_intent(self) -> None:
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

        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(request.route_decision.reason, "weak_catalog_robot_action_match")
        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.speech[0].text,
            "I heard you, but my language model is not responding.",
        )

    async def test_legacy_run_contract_remains_unchanged(self) -> None:
        result = await AgentRuntime(
            AgentServices(ollama=None, use_llm=False, max_speak_chars=160)
        ).run(_request())

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
