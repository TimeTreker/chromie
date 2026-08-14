from __future__ import annotations

import asyncio
import json
import unittest

from pydantic import ValidationError
from pathlib import Path

from agent.app.agents.base import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.social_attention import SocialAttentionPlan


class _Catalog:
    def __init__(self) -> None:
        self._entries = [
            CapabilityMatch(
                capability_id="soridormi.attention",
                agent_id="soridormi.skill",
                description="A reviewed Social Attention named skill.",
                effects=["physical_motion"],
                safety_class="physical_motion",
                requires_confirmation=False,
                available=True,
                route="robot_action",
                interaction_executable=True,
                can_run_parallel=True,
                parallel_metadata_declared=True,
                behavior_domains=["social_attention"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "intensity": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                metadata={"provider_backend": "opaque-provider-value"},
                score=0.9,
            )
        ]

    async def refresh_live_named_skills(self) -> None:
        return None

    def entries(self):
        return list(self._entries)

    async def get_capability(self, capability_id: str):
        return next(
            (item for item in self._entries if item.capability_id == capability_id),
            None,
        )


class _Ollama:
    def __init__(self, payload):
        self.payload = payload
        self.prompt = ""

    async def generate(self, prompt, *args, **kwargs):
        del args, kwargs
        self.prompt = prompt
        return self.payload




def request() -> AgentRunRequest:
    return AgentRunRequest(
        sid="style",
        text="Tell me the result.",
        language="en-US",
        route_decision=RouteDecision(
            route="chat",
            intent="user_question",
            confidence=0.95,
            source="llm",
        ),
        context={},
        history=[],
    )



class SocialInteractionStyleTests(unittest.TestCase):
    def test_maintained_agent_policy_default_is_on(self):
        self.assertEqual(
            AgentServices().effective_social_attention_mode(),
            "on",
        )

    def test_agent_supplies_owner_style_and_bounded_recent_evidence(self):
        item = request()
        item.context["mind"] = default_mind_profile().prompt_context()
        item.context["recent_auxiliary_behavior_evidence"] = [
            {"skill_id": f"soridormi.old_{index}"}
            for index in range(20)
        ]
        runtime = InteractionRuntime(
            AgentServices(
                social_attention_mode="on",
                capability_catalog=_Catalog(),
            )
        )

        asyncio.run(runtime.prepare_social_attention_context(item))

        style = item.context["social_interaction_style"]
        self.assertTrue(style["owner_approved"])
        self.assertEqual(style["preset"], "courteous")
        self.assertIn("explicit user action", style["restraint"])
        self.assertEqual(len(item.context["recent_auxiliary_behavior_evidence"]), 12)
        self.assertEqual(
            item.context["recent_auxiliary_behavior_evidence"][0]["skill_id"],
            "soridormi.old_8",
        )
        self.assertEqual(
            item.context["social_attention_candidates"][0]["capability_id"],
            "soridormi.attention",
        )

    def test_social_attention_prompt_contains_style_and_recent_evidence(self):
        item = request()
        item.context = {
            "mind": default_mind_profile().prompt_context(),
            "recent_auxiliary_behavior_evidence": [
                {
                    "evidence_kind": "host_accepted_auxiliary_request",
                    "execution_claim": "not_observed",
                    "skill_id": "soridormi.attention",
                }
            ],
        }
        ollama = _Ollama(
            {
                "decision": "none",
                "purpose": "neutral_presence",
                "behaviors": [],
                "confidence": 0.9,
                "reason": "Recent evidence favors stillness.",
            }
        )
        runtime = InteractionRuntime(
            AgentServices(
                social_attention_mode="report_only",
                capability_catalog=_Catalog(),
                social_attention_ollama=ollama,
            )
        )

        asyncio.run(runtime.prepare_social_attention_context(item))
        result = asyncio.run(runtime.social_attention_planner.plan(item))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.decision, "none")
        self.assertIn("owner-approved Social Interaction Style", ollama.prompt)
        self.assertIn("host_accepted_auxiliary_request", ollama.prompt)
        self.assertIn("timing=parallel", ollama.prompt)
        self.assertNotIn("opaque-provider-value", ollama.prompt)

    def test_contract_rejects_sequential_auxiliary_request(self):
        with self.assertRaises(ValidationError):
            SocialAttentionPlan.model_validate(
                {
                    "decision": "express",
                    "purpose": "acknowledge",
                    "behaviors": [
                        {
                            "skill_id": "soridormi.attention",
                            "args": {"intensity": "subtle"},
                            "timing": "sequential",
                        }
                    ],
                }
            )

    def test_file_backed_backend_parity_scenarios(self):
        fixture = (
            Path(__file__).parent
            / "scenarios"
            / "social_attention_embodiment_independence.json"
        )
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(payload["public_modes"], ["off", "report_only", "on"])
        self.assertEqual(
            {case["provider_backend"] for case in payload["cases"]},
            {"mujoco", "physical"},
        )
        self.assertEqual(
            {case["skill_id"] for case in payload["cases"]},
            {"soridormi.attention"},
        )
        self.assertEqual(
            {json.dumps(case["semantic_args"], sort_keys=True) for case in payload["cases"]},
            {'{"intensity": "subtle"}'},
        )


if __name__ == "__main__":
    unittest.main()
