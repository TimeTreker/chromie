from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from agent.app.agents.base import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest, RouteDecision
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.skill_runtime import SkillDefinition, SkillRegistry
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
                can_run_parallel=True,
                parallel_metadata_declared=True,
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
                can_run_parallel=True,
                parallel_metadata_declared=True,
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


class _Runtime:
    def __init__(self, definitions):
        self.definitions = {item.skill_id: item for item in definitions}
        self.executed = []

    async def ensure_skill_definitions(self, skill_ids):
        for skill_id in skill_ids:
            if skill_id not in self.definitions:
                raise ValueError(skill_id)

    def skill_definition(self, skill_id):
        return self.definitions[skill_id]

    async def execute(self, response, *, session_id):
        self.executed.append((response, session_id))
        return SimpleNamespace(status="completed")


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


def _definition(skill_id: str, *, backend: str) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        provider_id="soridormi.mcp",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "required": ["completed"],
            "additionalProperties": False,
        },
        available=True,
        requires_confirmation=False,
        can_run_parallel=True,
        exclusive_group=f"social:{skill_id}",
        metadata={
            "provider_backend": backend,
            "behavior_domains": ["social_attention"],
            "effects": ["social_expression"],
            "parallel_metadata_declared": True,
            "resource_claims": [f"social:{skill_id}"],
        },
    )


def _social_plan(skill_id: str = "soridormi.sim_attention") -> SocialAttentionPlan:
    return SocialAttentionPlan.model_validate(
        {
            "purpose": "engagement",
            "decision": "express",
            "behaviors": [
                {
                    "capability_id": skill_id,
                    "args": {},
                    "timing": "parallel",
                }
            ],
            "confidence": 0.95,
            "metadata": {"semantic_owner": "social_attention"},
        }
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
            await runtime.prepare_social_attention_context(request)
            return request.context

        off = asyncio.run(run("off"))
        self.assertEqual(off["social_attention_policy"]["mode"], "off")
        self.assertNotIn("social_attention_candidates", off)

        report = asyncio.run(run("report_only"))
        self.assertEqual(
            {item["capability_id"] for item in report["social_attention_candidates"]},
            {"soridormi.sim_attention", "soridormi.hardware_attention"},
        )
        self.assertEqual(report["social_attention_policy"]["semantic_owner"], "social_attention")

        enabled = asyncio.run(run("on"))
        self.assertEqual(len(enabled["social_attention_candidates"]), 2)

    def test_host_policy_is_more_restrictive_than_social_attention_plan(self):
        runtime = _Runtime([_definition("soridormi.sim_attention", backend="sim")])
        outcome = asyncio.run(
            CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="off").execute_social_attention_event(
                plan=_social_plan(),
                session_id="social-policy",
                turn_id="turn-1",
                event="understanding_ready",
                context={},
            )
        )
        self.assertEqual(outcome["status"], "not_executed")
        self.assertEqual(outcome["materialized_count"], 0)
        self.assertEqual(runtime.executed, [])

    def test_legacy_simulator_scoped_configuration_migrates_to_on(self):
        self.assertEqual(normalize_social_attention_mode("sim" + "_only"), "on")

    def test_host_accepts_reviewed_skill_independent_of_backend_metadata(self):
        runtime = _Runtime(
            [_definition("soridormi.hardware_attention", backend="physical")]
        )
        adapter = CanonicalPlanRuntimeAdapter(runtime, social_attention_mode="on")
        outcome = asyncio.run(
            adapter.execute_social_attention_event(
                plan=_social_plan("soridormi.hardware_attention"),
                session_id="social-policy",
                turn_id="turn-2",
                event="understanding_ready",
                context={},
            )
        )
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["materialized_count"], 1)
        response, session_id = runtime.executed[0]
        self.assertEqual(session_id, "social-policy")
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.hardware_attention"],
        )
        evidence = adapter.recent_auxiliary_behavior_evidence("social-policy")
        self.assertEqual(evidence[-1]["capability_id"], "soridormi.hardware_attention")
        self.assertEqual(evidence[-1]["execution_claim"], "not_observed")
        self.assertEqual(adapter.recent_auxiliary_behavior_evidence("other-session"), [])

    def test_registry_preserves_semantic_taxonomy_not_backend_mode(self):
        registry = SkillRegistry()
        registry.import_soridormi_catalog(
            [
                {
                    "skill_id": "opaque_attention",
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
        )
        definition = registry.get("soridormi.opaque_attention")
        self.assertNotIn("mode", definition.metadata)
        self.assertEqual(definition.metadata["behavior_domains"], ["social_attention"])

    def test_model_facing_candidates_hide_backend_identity_and_calibration(self):
        catalog = _Catalog()
        request = _request()
        runtime = InteractionRuntime(
            AgentServices(
                use_llm=False,
                capability_catalog=catalog,  # type: ignore[arg-type]
                social_attention_mode="on",
            )
        )
        asyncio.run(runtime.prepare_social_attention_context(request))
        candidates = request.context["social_attention_candidates"]
        self.assertEqual(len(candidates), 2)
        self.assertNotIn("mode", candidates[0].get("metadata", {}))
        self.assertNotIn("mode", candidates[1].get("metadata", {}))

    def test_provider_owned_calibration_schema_is_not_model_facing(self):
        catalog = _Catalog()
        catalog._entries.append(
            CapabilityMatch(
                capability_id="soridormi.calibrated_head_target",
                agent_id="soridormi.skill",
                description="Provider-calibrated head target.",
                available=True,
                route="robot_action",
                interaction_executable=True,
                behavior_domains=["social_attention"],
                input_schema={
                    "type": "object",
                    "properties": {"head_yaw_rad": {"type": "number"}},
                },
                score=0.7,
            )
        )
        request = _request()
        runtime = InteractionRuntime(
            AgentServices(
                use_llm=False,
                capability_catalog=catalog,  # type: ignore[arg-type]
                social_attention_mode="on",
            )
        )
        asyncio.run(runtime.prepare_social_attention_context(request))
        ids = {item["capability_id"] for item in request.context["social_attention_candidates"]}
        self.assertNotIn("soridormi.calibrated_head_target", ids)


if __name__ == "__main__":
    unittest.main()
