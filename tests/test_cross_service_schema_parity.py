from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.schema import AgentResult as ServiceAgentResult
from agent.app.schema import RouteDecision as AgentRouteDecision
from orchestrator.schemas.agent import AgentResult as HostAgentResult
from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
from router.app.schema import RouteDecision as RouterRouteDecision
from shared.chromie_contracts.route import RouteDecision as SharedRouteDecision


class CrossServiceSchemaParityTests(unittest.TestCase):
    def test_fast_speech_survives_agent_and_shared_route_boundaries(self) -> None:
        payload = {
            "route": "tool",
            "fast_speech": "Let me check.",
            "routes": [
                {
                    "route": "tool",
                    "fast_speech": {"text": "Checking now."},
                }
            ],
        }
        for model in (
            RouterRouteDecision,
            AgentRouteDecision,
            OrchestratorRouteDecision,
            SharedRouteDecision,
        ):
            with self.subTest(model=model.__module__):
                decision = model.model_validate(payload)
                self.assertEqual(decision.fast_speech.text, "Let me check.")
                self.assertEqual(decision.speak_first, "Let me check.")
                self.assertEqual(decision.routes[0].fast_speech.text, "Checking now.")

    def test_fast_speech_contract_markers_are_never_playable_across_boundaries(self) -> None:
        payload = {
            "route": "tool",
            "fast_speech": {
                "text": "acknowledge-and-check",
                "commitment": "checking_only",
            },
            "speak_first": "checking only",
            "routes": [
                {
                    "route": "tool",
                    "fast_speech": {"text": "safety prelude"},
                }
            ],
        }
        for model in (
            RouterRouteDecision,
            AgentRouteDecision,
            OrchestratorRouteDecision,
            SharedRouteDecision,
        ):
            with self.subTest(model=model.__module__):
                decision = model.model_validate(payload)
                self.assertEqual(decision.fast_speech.text, "")
                self.assertIsNone(decision.speak_first)
                self.assertEqual(decision.routes[0].fast_speech.text, "")

    def test_fast_speech_cannot_disable_completion_guard_across_boundaries(self) -> None:
        payload = {
            "route": "tool",
            "fast_speech": {
                "text": "I completed it.",
                "purpose": "acknowledge_and_check",
                "commitment": "checking_only",
                "must_not_claim_completion": False,
            },
        }
        for model in (
            RouterRouteDecision,
            AgentRouteDecision,
            OrchestratorRouteDecision,
            SharedRouteDecision,
        ):
            with self.subTest(model=model.__module__):
                with self.assertRaises(ValidationError):
                    model.model_validate(payload)

    def test_agent_metadata_survives_host_result_boundary(self) -> None:
        service = ServiceAgentResult(metadata={"semantic_authority_owner": "goal_driven_runtime"})
        host = HostAgentResult.model_validate(service.model_dump(mode="json"))
        self.assertEqual(
            host.metadata["semantic_authority_owner"],
            "goal_driven_runtime",
        )


if __name__ == "__main__":
    unittest.main()
