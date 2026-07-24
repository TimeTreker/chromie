from __future__ import annotations

import asyncio
import unittest

from agent.app.agents.base import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch
from agent.app.response_composer import ResponseComposerResolver
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest, RouteDecision
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.skill_runtime import SkillDefinition, SkillRegistry
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    CoordinatedResponsePlan,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.social_attention import (
    SocialAttentionPlan,
    normalize_social_attention_mode,
)


class _Catalog:
    def __init__(self) -> None:
        self._entries = [
            CapabilityMatch(
                capability_id="soridormi.sim_attention",
                agent_id="soridormi.skill",
                description="Simulator-only social attention.",
                effects=["physical_motion"],
                safety_class="physical_motion",
                requires_confirmation=False,
                available=True,
                route="robot_action",
                interaction_executable=True,
                behavior_domains=["social_attention"],
                input_schema={"type": "object", "properties": {}},
                metadata={"mode": "sim"},
                score=0.9,
            ),
            CapabilityMatch(
                capability_id="soridormi.hardware_attention",
                agent_id="soridormi.skill",
                description="Hardware social attention.",
                effects=["physical_motion"],
                safety_class="physical_motion",
                requires_confirmation=False,
                available=True,
                route="robot_action",
                interaction_executable=True,
                behavior_domains=["social_attention"],
                input_schema={"type": "object", "properties": {}},
                metadata={"mode": "hardware"},
                score=0.8,
            ),
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

    async def generate(self, *args, **kwargs):
        del args, kwargs
        return self.payload


class _Runtime:
    def __init__(self, definitions):
        self.definitions = {item.skill_id: item for item in definitions}

    async def ensure_skill_definitions(self, skill_ids):
        for skill_id in skill_ids:
            if skill_id not in self.definitions:
                raise ValueError(skill_id)

    def skill_definition(self, skill_id):
        return self.definitions[skill_id]


def _request() -> AgentRunRequest:
    return AgentRunRequest(
        sid="social-policy",
        text="Hello.",
        language="en-US",
        route_decision=RouteDecision(
            route="chat",
            intent="greeting",
            confidence=0.95,
            source="llm",
        ),
        context={},
        history=[],
    )


def _plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-social-policy",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=0.95,
        goal_ids=["goal-chat"],
        goal_summary="greet the user",
        response_text="Hello.",
    )


def _composition(mode: str, *, skill_id: str = "soridormi.sim_attention"):
    plan = _plan()
    return CoordinatedResponsePlan(
        composition_id=f"composition-{mode}",
        canonical_plan_id=plan.plan_id,
        canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
        canonical_plan=plan,
        response_plan=ResponsePlan(
            final=ResponseStage(
                text="Hello.",
                covers_goal_ids=plan.goal_ids,
                must_not_claim_completion=True,
            )
        ),
        social_attention_plan=SocialAttentionPlan(
            decision="express",
            behaviors=[{"skill_id": skill_id, "args": {}, "timing": "parallel"}],
            metadata={"auxiliary_social_attention": True},
        ),
        metadata={
            "social_attention_policy": {
                "mode": mode,
                "execution_enabled": mode == "on",
            }
        },
    )


class SocialAttentionPolicyClosureTests(unittest.TestCase):
    def test_candidate_preparation_respects_all_modes(self):
        async def run(mode: str):
            request = _request()
            runtime = InteractionRuntime(
                AgentServices(
                    social_attention_mode=mode,
                    capability_catalog=_Catalog(),
                )
            )
            await runtime.prepare_response_composition_context(request)
            return request.context

        off = asyncio.run(run("off"))
        self.assertEqual(off["social_attention_policy"]["mode"], "off")
        self.assertNotIn("social_attention_candidates", off)

        report = asyncio.run(run("report_only"))
        self.assertEqual(
            {item["capability_id"] for item in report["social_attention_candidates"]},
            {"soridormi.sim_attention", "soridormi.hardware_attention"},
        )

        enabled = asyncio.run(run("on"))
        self.assertEqual(len(enabled["social_attention_candidates"]), 2)

    def test_response_composer_off_drops_model_attention(self):
        plan = _plan()
        request = _request()
        request.context = {
            "canonical_plan_resolution": plan.model_dump(mode="json"),
            "social_attention_policy": {"mode": "off"},
        }
        result = asyncio.run(
            ResponseComposerResolver(
                _Ollama(
                    {
                        "response_plan": {
                            "final": {
                                "text": "Hello.",
                                "covers_goal_ids": ["goal-chat"],
                            }
                        },
                        "social_attention_plan": {
                            "decision": "express",
                            "speech_expression": {
                                "mode": "adapt",
                                "style": "warm",
                                "pacing": "normal",
                                "reason": "Be friendly.",
                            },
                        },
                    }
                )
            ).resolve(request)
        )
        self.assertEqual(result.status, "resolved")
        self.assertIsNone(result.composition.social_attention_plan)
        self.assertIn(
            "policy_off",
            result.composition.metadata["social_attention_validation_reasons"],
        )

    def test_response_composer_report_only_retains_advisory_plan(self):
        plan = _plan()
        request = _request()
        request.context = {
            "canonical_plan_resolution": plan.model_dump(mode="json"),
            "social_attention_policy": {"mode": "report_only"},
            "social_attention_candidates": [
                _Catalog().entries()[0].model_dump(mode="json")
            ],
        }
        result = asyncio.run(
            ResponseComposerResolver(
                _Ollama(
                    {
                        "response_plan": {
                            "final": {
                                "text": "Hello.",
                                "covers_goal_ids": ["goal-chat"],
                            }
                        },
                        "social_attention_plan": {
                            "decision": "express",
                            "behaviors": [
                                {
                                    "skill_id": "soridormi.sim_attention",
                                    "args": {},
                                    "timing": "parallel",
                                }
                            ],
                        },
                    }
                )
            ).resolve(request)
        )
        attention = result.composition.social_attention_plan
        self.assertEqual(attention.decision, "express")
        self.assertEqual(attention.metadata["policy_mode"], "report_only")
        self.assertFalse(attention.metadata["execution_permitted"])

    def test_host_policy_is_more_restrictive_than_agent_plan(self):
        definition = SkillDefinition(
            skill_id="soridormi.sim_attention",
            provider_id="soridormi.mcp",
            input_schema={"type": "object", "properties": {}},
            available=True,
            requires_confirmation=False,
            metadata={"mode": "sim"},
        )
        response = asyncio.run(
            CanonicalPlanRuntimeAdapter(
                _Runtime([definition]),
                social_attention_mode="off",
            ).build_response(
                plan=_plan(),
                composition=_composition("on"),
                session_id="social-policy",
                language="en-US",
                context={},
            )
        )
        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["social_attention_policy_mode"], "off")
        self.assertIn("policy_off", response.metadata["omitted_social_attention"])

    def test_legacy_simulator_scoped_configuration_migrates_to_on(self):
        self.assertEqual(
            normalize_social_attention_mode("sim" + "_only"),
            "on",
        )

    def test_host_accepts_reviewed_skill_independent_of_backend_metadata(self):
        hardware = SkillDefinition(
            skill_id="soridormi.hardware_attention",
            provider_id="soridormi.mcp",
            input_schema={"type": "object", "properties": {}},
            available=True,
            requires_confirmation=False,
            metadata={"provider_backend": "physical"},
        )
        adapter = CanonicalPlanRuntimeAdapter(
            _Runtime([hardware]),
            social_attention_mode="on",
        )
        response = asyncio.run(
            adapter.build_response(
                plan=_plan(),
                composition=_composition(
                    "on", skill_id="soridormi.hardware_attention"
                ),
                session_id="social-policy",
                language="en-US",
                context={},
            )
        )
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.hardware_attention"],
        )
        evidence = adapter.recent_auxiliary_behavior_evidence()
        self.assertEqual(evidence[-1]["skill_id"], "soridormi.hardware_attention")
        self.assertEqual(evidence[-1]["execution_claim"], "not_observed")
        self.assertEqual(evidence[-1]["session_id"], "social-policy")
        self.assertEqual(adapter.recent_auxiliary_behavior_evidence("other-session"), [])

    def test_registry_preserves_semantic_taxonomy_not_backend_mode(self):
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "sim_attention",
                    "description": "Attention",
                    "parameters_schema": {"type": "object", "properties": {}},
                    "metadata": {
                        "mode": "physical",
                        "behavior_domains": ["social_attention"],
                    },
                    "requires_confirmation": False,
                    "effects": [],
                }
            ],
            requires_confirmation=False,
        )
        definition = registry.get("soridormi.sim_attention")
        self.assertNotIn("mode", definition.metadata)
        self.assertEqual(
            definition.metadata["behavior_domains"], ["social_attention"]
        )


if __name__ == "__main__":
    unittest.main()
