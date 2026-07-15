from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent.app.agents import AgentServices
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.schemas.route import RouteDecision
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveRuntimePolicy,
    GoalDrivenRuntimeCoordinator,
)
from shared.chromie_contracts.semantic_authority import (
    SemanticAuthorityClaim,
    context_with_semantic_authority,
    semantic_authority_from_context,
    semantic_authority_route_matrix,
)
from tests.test_capability_router_actions import _catalog
from tests.test_cognitive_runtime_pr7 import FakeRuntime, ScriptedClient, new_goal_association


class _CountingCapabilityOllama:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt
        self.calls += 1
        self.assert_json = kwargs.get("response_format") == "json"
        return {
            "decision": "execute",
            "speech": "Nodding.",
            "skills": [{"skill_id": "soridormi.nod_yes", "args": {}}],
        }


def _robot_request(
    *,
    context: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "authority-turn",
            "text": "Nod once.",
            "context": context or {},
            "route_decision": {
                "route": "robot_action",
                "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                "intent": "robot_action",
                "confidence": 0.99,
                "language": "en-US",
                "source": "catalog",
                "actions": actions or [],
            },
        }
    )


class SemanticAuthorityContractTests(unittest.TestCase):
    def test_invalid_legacy_fallback_claim_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SemanticAuthorityClaim(
                owner="legacy_capability_fallback",
                role="authoritative",
                turn_id="turn",
                emergency_fallback=False,
            )

    def test_context_contains_one_replaceable_authority_claim(self) -> None:
        first = context_with_semantic_authority(
            {"history": []},
            SemanticAuthorityClaim(
                owner="goal_driven_runtime",
                role="authoritative",
                turn_id="turn",
            ),
        )
        second = context_with_semantic_authority(
            first,
            SemanticAuthorityClaim(
                owner="router_action_adapter",
                role="adapter",
                turn_id="turn",
            ),
        )
        claim = semantic_authority_from_context(second)
        self.assertIsNotNone(claim)
        self.assertEqual(claim.owner, "router_action_adapter")
        self.assertEqual(claim.role, "adapter")
        self.assertEqual(
            [key for key in second if key == "semantic_authority"],
            ["semantic_authority"],
        )

    def test_route_matrix_covers_every_semantic_entrypoint(self) -> None:
        matrix = semantic_authority_route_matrix()
        entrypoints = {item["entrypoint"] for item in matrix}
        self.assertEqual(
            entrypoints,
            {
                "orchestrator.handle_routed_text/apply",
                "orchestrator.handle_routed_text/report_only",
                "agent./interaction with exact Router actions",
                "agent./interaction or /run emergency compatibility",
                "post_interrupt_correction",
            },
        )
        for row in matrix:
            self.assertIn(row["role"], {"authoritative", "observer", "adapter"})
            self.assertTrue(row["planner_path"])
        apply_rows = [
            row
            for row in matrix
            if row["entrypoint"]
            in {
                "orchestrator.handle_routed_text/apply",
                "post_interrupt_correction",
            }
        ]
        self.assertTrue(
            all(row["owner"] == "goal_driven_runtime" for row in apply_rows)
        )
        self.assertTrue(
            all(
                row["fallback"] == "fail_closed_after_authority_acquisition"
                for row in apply_rows
            )
        )

    def test_orchestrator_claims_are_mutually_exclusive(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.legacy_semantic_fallback_enabled = True
        direct = RouteDecision(
            route="robot_action",
            intent="compound_robot_action",
            agents=["capability_agent"],
            source="catalog",
            actions=[{"capability_id": "soridormi.nod_yes", "args": {}}],
        )
        fallback = RouteDecision(
            route="robot_action",
            intent="robot_action",
            agents=["capability_agent"],
            source="llm",
        )
        direct_claim = semantic_authority_from_context(
            assistant._legacy_agent_authority_context(
                {}, session_id="direct", decision=direct, reason="test"
            )
        )
        fallback_claim = semantic_authority_from_context(
            assistant._legacy_agent_authority_context(
                {}, session_id="fallback", decision=fallback, reason="test"
            )
        )
        self.assertEqual((direct_claim.owner, direct_claim.role), ("router_action_adapter", "adapter"))
        self.assertEqual(
            (fallback_claim.owner, fallback_claim.role, fallback_claim.emergency_fallback),
            ("legacy_capability_fallback", "authoritative", True),
        )

    def test_default_configuration_has_one_authority_and_fail_closed_policy(self) -> None:
        common = Path(".env.common").read_text(encoding="utf-8")
        example = Path(".env.example").read_text(encoding="utf-8")
        launcher = Path("scripts/start_chromie.sh").read_text(encoding="utf-8")
        for text in (common, example):
            self.assertIn("ORCH_COGNITIVE_RUNTIME_MODE=apply", text)
            self.assertIn("ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed", text)
            self.assertIn("ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0", text)
            self.assertIn("AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=0", text)
        self.assertIn("ORCH_COGNITIVE_RUNTIME_MODE=apply", launcher)
        self.assertIn("ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed", launcher)
        self.assertIn("ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0", launcher)
        self.assertIn("AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=0", launcher)

    def test_goal_driven_runtime_never_emits_legacy_fallback(self) -> None:
        client = ScriptedClient(
            association=new_goal_association(),
            fast_plans=[],
        )
        coordinator = GoalDrivenRuntimeCoordinator(
            agent_client=client,
            adapter=CanonicalPlanRuntimeAdapter(FakeRuntime()),
            policy=CognitiveRuntimePolicy(mode="apply", fallback_policy="legacy"),
        )
        result = __import__("asyncio").run(
            coordinator.resolve(
                object(),
                text="hello",
                sid="authority",
                context={"history": [], "active_goal_snapshots": []},
                history=[],
                language="en-US",
                route_decision=RouteDecision(
                    route="chat",
                    intent="greeting",
                    agents=["conversation_agent"],
                    source="llm",
                ),
            )
        )
        self.assertEqual(result.status, "error")
        self.assertNotEqual(result.status, "legacy_fallback")


class CapabilityAuthorityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_planner_is_disabled_without_service_and_turn_claim(self) -> None:
        ollama = _CountingCapabilityOllama()
        runtime = InteractionRuntime(
            AgentServices(
                ollama=ollama,
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        response = await runtime.run(_robot_request())
        self.assertEqual(ollama.calls, 0)
        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.metadata["planning_result"],
            "legacy_semantic_planner_disabled",
        )

    async def test_exact_router_actions_are_adapter_only_even_with_llm(self) -> None:
        ollama = _CountingCapabilityOllama()
        runtime = InteractionRuntime(
            AgentServices(
                ollama=ollama,
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        response = await runtime.run(
            _robot_request(
                actions=[
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {},
                        "sequence": 0,
                    }
                ]
            )
        )
        self.assertEqual(ollama.calls, 0)
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.nod_yes"],
        )
        self.assertEqual(
            response.metadata["semantic_authority_owner"],
            "router_action_adapter",
        )
        self.assertEqual(response.metadata["semantic_authority_role"], "adapter")

    async def test_legacy_planner_requires_both_service_gate_and_turn_claim(self) -> None:
        claim = SemanticAuthorityClaim(
            owner="legacy_capability_fallback",
            role="authoritative",
            turn_id="authority-turn",
            reason="explicit_test_emergency",
            emergency_fallback=True,
        )

        service_disabled_ollama = _CountingCapabilityOllama()
        service_disabled = InteractionRuntime(
            AgentServices(
                ollama=service_disabled_ollama,
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
                legacy_capability_fallback_enabled=False,
            )
        )
        blocked = await service_disabled.run(
            _robot_request(context=context_with_semantic_authority({}, claim))
        )
        self.assertEqual(service_disabled_ollama.calls, 0)
        self.assertEqual(blocked.skills, [])

        authorized_ollama = _CountingCapabilityOllama()
        authorized = InteractionRuntime(
            AgentServices(
                ollama=authorized_ollama,
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
                legacy_capability_fallback_enabled=True,
            )
        )
        response = await authorized.run(
            _robot_request(context=context_with_semantic_authority({}, claim))
        )
        self.assertEqual(authorized_ollama.calls, 1)
        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.nod_yes"],
        )
        self.assertTrue(response.metadata["legacy_emergency_fallback"])
        self.assertEqual(
            response.metadata["semantic_authority_owner"],
            "legacy_capability_fallback",
        )


if __name__ == "__main__":
    unittest.main()
