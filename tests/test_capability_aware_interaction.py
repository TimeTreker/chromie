from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityCatalog, CapabilityMatch, CapabilitySearchResult, CatalogCapability
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
)
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest


class _Outcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_forward",
                "description": "Walk forward for a bounded duration.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "duration_s": {"type": "number", "minimum": 0.1, "maximum": 5.0},
                        "speed": {
                            "type": "string",
                            "enum": ["slow", "normal", "medium", "quick", "fast_limited"],
                        },
                    },
                    "required": ["duration_s"],
                },
                "available": True,
                "requires_confirmation": True,
            }
        ],
    }


class _StrictWalkOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_forward",
                "description": "Walk forward a short distance at a safe speed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"speed": {"type": "string", "enum": ["normal"]}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number"}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _LookForwardOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "look_at_person",
                "description": "Look, face, or gaze forward toward the user for a bounded time.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number"}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "walk_forward",
                "description": "Walk forward a short distance at a safe speed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
        ],
    }


class _HeadGestureOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "shake_no",
                "description": "Shake the robot head no.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "nod_yes",
                "description": "Nod the robot head yes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _Invoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _Outcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _Outcome()


class _StrictWalkInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _StrictWalkOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _StrictWalkOutcome()


class _LookForwardInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _LookForwardOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _LookForwardOutcome()


class _HeadGestureInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _HeadGestureOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _HeadGestureOutcome()


class _Ollama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        system = str(kwargs["system"])
        assert "Only execute a skill when" in system
        assert "Never combine an unrelated spoken answer with a body skill" in system
        assert "Generalization-first principle" in system
        assert "do not turn prompt wording into phrase rules" in system
        return {
            "decision": "execute",
            "speech": "Walking ahead for 10 minutes.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                }
            ],
        }


class _InvalidWalkOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward for five seconds.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 5.0},
                }
            ],
        }


class _LookForwardOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.look_at_person" in prompt
        assert "soridormi.blink_eyes" in prompt
        assert "soridormi.walk_forward" in prompt
        assert "Task context" in prompt
        assert "Can you look forward for some time" in prompt
        system = str(kwargs["system"])
        assert "Distinguish gaze, attention, and orientation requests from locomotion requests" in system
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Looking forward and blinking.",
            "skills": [
                {
                    "skill_id": "soridormi.look_at_person",
                    "args": {"duration_s": 5.0},
                },
                {
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                },
            ],
        }


class _PoliteHeadQuestionOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "你能摇头吗" in prompt
        assert "soridormi.shake_no" in prompt
        assert kwargs["response_format"] == "json"
        system = str(kwargs["system"])
        assert "A polite ability-shaped request to perform a listed physical action" in system
        assert "not speech-only" in system
        return {
            "decision": "execute",
            "speech": "",
            "skills": [
                {
                    "skill_id": "soridormi.shake_no",
                    "args": {"count": 2},
                }
            ],
        }


class _AdverbSpeedOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert '"quick"' in prompt
        system = str(kwargs["system"])
        assert "Every enum argument must be copied exactly" in system
        assert "Map natural wording to enum tokens by semantic meaning" in system
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking ahead quickly.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0, "speed": "quickly"},
                }
            ],
        }


class _FullApiOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Available capability API surface" in prompt
        assert "soridormi.wave_hand" in prompt
        assert "soridormi.nod_yes" in prompt
        assert '"count"' in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Waving.",
            "skills": [
                {
                    "skill_id": "soridormi.wave_hand",
                    "args": {"count": 2},
                }
            ],
        }


class _BrokenCapabilityPlannerOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Available capability API surface" in prompt
        assert kwargs["response_format"] == "json"
        assert kwargs["options"]["num_ctx"] >= 4096
        assert kwargs["options"]["num_predict"] >= 512
        raise ValueError("truncated JSON from capability planner")


class _FullApiCatalog:
    version = 7

    def __init__(self) -> None:
        self.wrong = CatalogCapability(
            capability_id="soridormi.nod_yes",
            agent_id="soridormi.skill",
            description="Nod the robot head yes.",
            input_schema={"type": "object", "properties": {"count": {"type": "number"}}},
            effects=["physical_motion"],
            requires_confirmation=False,
            available=True,
            route="robot_action",
            invocation_kind="named_skill",
            interaction_executable=True,
        )
        self.target = CatalogCapability(
            capability_id="soridormi.wave_hand",
            agent_id="soridormi.skill",
            description="Wave the robot hand to greet someone.",
            input_schema={
                "type": "object",
                "properties": {"count": {"type": "number", "minimum": 1, "maximum": 3}},
                "required": ["count"],
                "additionalProperties": False,
            },
            effects=["physical_motion"],
            requires_confirmation=False,
            available=True,
            route="robot_action",
            invocation_kind="named_skill",
            interaction_executable=True,
        )

    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "speaker_agent"],
            matches=[CapabilityMatch(**self.wrong.model_dump(mode="python"), score=0.9)],
            catalog_version=self.version,
        )

    def entries(self) -> list[CatalogCapability]:
        return [self.wrong, self.target]


def _catalog() -> CapabilityCatalog:
    return _catalog_with_invoker(_Invoker())


def _catalog_with_invoker(invoker: Any) -> CapabilityCatalog:
    registry = CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="soridormi-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List named skills.",
                                effects=["read_only"],
                                safety_class="safe_read",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    return CapabilityCatalog(registry, live_invoker=invoker, min_score=0.10)


class CapabilityAwareInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_interaction_does_not_self_correct_chat_route_using_catalog(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "catalog-route",
                "text": "Move forward slowly for one second.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(request.route_decision.source, "fallback")
        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(response.skills, [])
        self.assertIn("conversation_agent", response.metadata["handled_by"])
        self.assertNotIn("capability_agent", response.metadata["handled_by"])

    async def test_capability_plan_normalizes_schema_enum_adverbs(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_AdverbSpeedOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "catalog-speed",
                "text": "Walk forward for 1 second quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args["speed"], "quick")
        self.assertTrue(response.skills[0].metadata["schema_normalized_args"])

    async def test_polite_chinese_head_ability_question_executes_matching_skill(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_PoliteHeadQuestionOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_HeadGestureInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "polite-head-question",
                "text": "你能摇头吗",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.shake_no")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "Shaking my head.")

    async def test_capability_plan_blocks_schema_invalid_args_before_runtime(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_InvalidWalkOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_StrictWalkInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "invalid-walk",
                "text": "Walk forward for five seconds.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.speech[0].text, "Please clarify the action before I move.")
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.metadata["invalid_capability_args"]["errors"],
            ["args has unknown fields: ['duration_s']"],
        )

    async def test_capability_planner_failure_returns_clarification_not_exception(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_BrokenCapabilityPlannerOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "planner-json-failure",
                "text": "Walk forward for 1 second.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.speech[0].text,
            "I could not safely plan that action. Please try again.",
        )
        self.assertEqual(response.metadata["capability_decision"], "clarify")

    async def test_capability_plan_uses_task_context_for_look_forward_followup(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_LookForwardOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_LookForwardInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "look-followup",
                "text": "5 seconds and blink your eyes.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
                "context": {
                    "current_task_context": {
                        "task_id": "task-look",
                        "task_relation": "continue_task",
                        "task_type": "robot_action",
                        "goal": "Can you look forward for some time?",
                        "last_meaningful_user_turn": "Can you look forward for some time?",
                        "last_assistant_response": "Look forward for how long?",
                    }
                },
                "history": [
                    {"role": "user", "text": "Can you look forward for some time?"},
                    {"role": "assistant", "text": "Look forward for how long?"},
                ],
            }
        )

        response = await runtime.run(request)

        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.look_at_person", "soridormi.blink_eyes"],
        )
        self.assertEqual(response.skills[0].args, {"duration_s": 5.0})
        self.assertEqual(response.skills[1].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "I will do those actions in order.")

    async def test_capability_plan_sees_full_api_surface_beyond_search_match(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FullApiOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_FullApiCatalog(),  # type: ignore[arg-type]
                capability_match_limit=1,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "full-api-surface",
                "text": "Wave twice.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.wave_hand"])
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.metadata["capability_catalog_version"], 7)


if __name__ == "__main__":
    unittest.main()
