from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityCatalog
from agent.app.capabilities.models import AgentManifest, CapabilityBundle, CapabilityRegistry, ToolCapability
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest


class _Outcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {"skill_id": "walk_velocity", "description": "Walk.", "parameters_schema": {"type": "object"}, "available": True},
            {"skill_id": "turn_in_place", "description": "Turn.", "parameters_schema": {"type": "object"}, "available": True},
            {"skill_id": "nod_yes", "description": "Nod.", "parameters_schema": {"type": "object"}, "available": True},
        ],
    }


class _Invoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _Outcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _Outcome()


def _catalog() -> CapabilityCatalog:
    registry = CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="test",
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
    return CapabilityCatalog(registry, live_invoker=_Invoker(), min_score=0.0)


class CapabilityRouterActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_actions_become_sequential_skill_requests_without_llm(self) -> None:
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
                "sid": "compound",
                "text": "Walk forward, turn left, then nod twice.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "compound_robot_action",
                    "confidence": 0.99,
                    "language": "en-US",
                    "source": "catalog",
                    "actions": [
                        {"capability_id": "soridormi.walk_velocity", "args": {"vx_mps": 0.15, "duration_s": 10.0}, "sequence": 0},
                        {"capability_id": "soridormi.turn_in_place", "args": {"yaw_radps": -0.12}, "sequence": 1},
                        {
                            "capability_id": "soridormi.nod_yes",
                            "args": {"count": 2, "amplitude": "small", "duration_s": 1.4},
                            "sequence": 2,
                        },
                    ],
                },
            }
        )
        response = await runtime.run(request)
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.walk_velocity", "soridormi.turn_in_place", "soridormi.nod_yes"],
        )
        self.assertTrue(all(item.timing == "sequential" for item in response.skills))
        self.assertEqual(response.skills[0].args["duration_s"], 10.0)
        self.assertEqual(response.skills[2].args["count"], 2)
        self.assertEqual(response.skills[2].args["amplitude"], "small")
        self.assertEqual(response.skills[2].args["duration_s"], 1.4)
        self.assertEqual(response.speech[0].text, "I will do those actions in order.")

    async def test_router_speak_first_suppresses_generic_direct_plan_speech(self) -> None:
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
                "sid": "say-hello",
                "text": "Walk forward and nod your head to say hello.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "compound_robot_action",
                    "confidence": 0.99,
                    "language": "en-US",
                    "source": "catalog",
                    "speak_first": "Hello.",
                    "actions": [
                        {"capability_id": "soridormi.walk_velocity", "args": {"vx_mps": 0.1}, "sequence": 0},
                        {"capability_id": "soridormi.nod_yes", "args": {"count": 2}, "sequence": 1},
                    ],
                },
            }
        )
        response = await runtime.run(request)
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )
        self.assertEqual([item.text for item in response.speech], ["Hello."])


if __name__ == "__main__":
    unittest.main()
