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
    def test_fast_speech_contract_is_consistent_across_route_boundaries(self) -> None:
        models = (
            RouterRouteDecision,
            AgentRouteDecision,
            OrchestratorRouteDecision,
            SharedRouteDecision,
        )
        cases = (
            {
                "name": "playable_text_survives",
                "payload": {
                    "route": "tool",
                    "fast_speech": "Let me check.",
                    "routes": [
                        {
                            "route": "tool",
                            "fast_speech": {"text": "Checking now."},
                        }
                    ],
                },
                "expected": ("Let me check.", "Let me check.", "Checking now."),
                "raises": False,
            },
            {
                "name": "contract_markers_are_not_playable",
                "payload": {
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
                },
                "expected": ("", None, ""),
                "raises": False,
            },
            {
                "name": "completion_guard_cannot_be_disabled",
                "payload": {
                    "route": "tool",
                    "fast_speech": {
                        "text": "I completed it.",
                        "purpose": "acknowledge_and_check",
                        "commitment": "checking_only",
                        "must_not_claim_completion": False,
                    },
                },
                "expected": None,
                "raises": True,
            },
        )

        for model in models:
            for case in cases:
                with self.subTest(model=model.__module__, case=case["name"]):
                    if case["raises"]:
                        with self.assertRaises(ValidationError):
                            model.model_validate(case["payload"])
                        continue

                    decision = model.model_validate(case["payload"])
                    expected_fast, expected_first, expected_nested = case["expected"]
                    self.assertEqual(decision.fast_speech.text, expected_fast)
                    self.assertEqual(decision.speak_first, expected_first)
                    self.assertEqual(
                        decision.routes[0].fast_speech.text,
                        expected_nested,
                    )

    def test_agent_metadata_survives_host_result_boundary(self) -> None:
        service = ServiceAgentResult(metadata={"semantic_authority_owner": "goal_driven_runtime"})
        host = HostAgentResult.model_validate(service.model_dump(mode="json"))
        self.assertEqual(
            host.metadata["semantic_authority_owner"],
            "goal_driven_runtime",
        )


if __name__ == "__main__":
    unittest.main()
