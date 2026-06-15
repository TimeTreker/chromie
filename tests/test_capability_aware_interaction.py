from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityCatalog
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
                    },
                    "required": ["duration_s"],
                },
                "available": True,
                "requires_confirmation": True,
            }
        ],
    }


class _Invoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _Outcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _Outcome()


class _Ollama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Moving forward.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                }
            ],
        }


def _catalog() -> CapabilityCatalog:
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
    return CapabilityCatalog(registry, live_invoker=_Invoker(), min_score=0.10)


class CapabilityAwareInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_interaction_self_corrects_chat_route_using_catalog(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_Ollama(),  # type: ignore[arg-type]
                use_llm=True,
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

        self.assertEqual(request.route_decision.source, "catalog")
        self.assertEqual(request.route_decision.route, "robot_action")
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args, {"duration_s": 1.0})
        self.assertTrue(response.skills[0].requires_confirmation)
        self.assertEqual(response.speech[0].text, "Moving forward.")
        self.assertIn("capability_agent", response.metadata["handled_by"])
        self.assertNotIn("conversation_agent", response.metadata["handled_by"])


if __name__ == "__main__":
    unittest.main()
