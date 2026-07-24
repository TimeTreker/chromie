from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path

from agent.app.agents.base import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch
from agent.app.response_composer import ResponseComposerResolver
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest, RouteDecision
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.skill_runtime import SkillDefinition
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
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


class _Runtime:
    def __init__(self, definition: SkillDefinition) -> None:
        self.definition = definition

    async def ensure_skill_definitions(self, skill_ids):
        if skill_ids != [self.definition.skill_id]:
            raise ValueError(skill_ids)

    def skill_definition(self, skill_id):
        if skill_id != self.definition.skill_id:
            raise ValueError(skill_id)
        return self.definition


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


def plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-style",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.95,
        goal_ids=["goal-answer"],
        goal_summary="answer the user",
        response_text="Here is the result.",
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

        asyncio.run(runtime.prepare_response_composition_context(item))

        style = item.context["social_interaction_style"]
        self.assertTrue(style["owner_approved"])
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

    def test_response_composer_prompt_contains_style_and_recent_evidence(self):
        item = request()
        canonical = plan()
        item.context = {
            "canonical_plan_resolution": canonical.model_dump(mode="json"),
            "social_attention_policy": {"mode": "report_only"},
            "social_interaction_style": (
                default_mind_profile()
                .social_interaction_style.model_dump(mode="json")
            ),
            "recent_auxiliary_behavior_evidence": [
                {
                    "evidence_kind": "host_accepted_auxiliary_request",
                    "execution_claim": "not_observed",
                    "skill_id": "soridormi.attention",
                }
            ],
            "social_attention_candidates": [
                _Catalog().entries()[0].model_dump(mode="json")
            ],
        }
        ollama = _Ollama(
            {
                "response_plan": {
                    "final": {
                        "text": "Here is the result.",
                        "covers_goal_ids": ["goal-answer"],
                    }
                },
                "social_attention_plan": {
                    "decision": "none",
                    "purpose": "neutral_presence",
                },
                "confidence": 0.9,
                "rationale": "Recent evidence favors stillness.",
            }
        )

        result = asyncio.run(ResponseComposerResolver(ollama).resolve(item))

        self.assertEqual(result.status, "resolved")
        self.assertIn("Owner-approved Social Interaction Style", ollama.prompt)
        self.assertIn("host_accepted_auxiliary_request", ollama.prompt)
        self.assertIn("timing=parallel", ollama.prompt)
        self.assertIn("simulator or physical backend metadata", ollama.prompt)

    def test_host_drops_sequential_auxiliary_request(self):
        canonical = plan()
        composition = CoordinatedResponsePlan(
            composition_id="composition-style",
            canonical_plan_id=canonical.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(canonical),
            canonical_plan=canonical,
            response_plan=ResponsePlan(
                final=ResponseStage(
                    text="Here is the result.",
                    covers_goal_ids=canonical.goal_ids,
                    must_not_claim_completion=True,
                )
            ),
            social_attention_plan=SocialAttentionPlan(
                decision="express",
                purpose="acknowledge",
                metadata={"auxiliary_social_attention": True},
                behaviors=[
                    {
                        "skill_id": "soridormi.attention",
                        "args": {"intensity": "subtle"},
                        "timing": "sequential",
                    }
                ],
            ),
            metadata={"social_attention_policy": {"mode": "on"}},
        )
        definition = SkillDefinition(
            skill_id="soridormi.attention",
            provider_id="soridormi.mcp",
            input_schema={
                "type": "object",
                "properties": {"intensity": {"type": "string"}},
                "additionalProperties": False,
            },
            available=True,
            requires_confirmation=False,
            metadata={"provider_backend": "physical"},
        )

        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                _Runtime(definition),
                social_attention_mode="on",
            ).build_response(
                plan=canonical,
                composition=composition,
                session_id="style",
                language="en-US",
                context={},
            )
        )

        self.assertEqual(response.skills, [])
        self.assertIn(
            "auxiliary_must_be_parallel:soridormi.attention",
            response.metadata["omitted_social_attention"],
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
