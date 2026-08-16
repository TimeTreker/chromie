from __future__ import annotations

import importlib
import unittest

from pydantic import ValidationError

from agent.app.cognitive_core.goal_interpreter.schema import RouteItem as GoalInterpreterRouteItem
from agent.app.schema import RouteItem as AgentRouteItem
from orchestrator.runtime.episode import (
    EpisodeCapabilityRequestRecord,
    EpisodeCapabilityResultRecord,
)
from orchestrator.schemas.route import RouteItem as OrchestratorRouteItem
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRuntime,
)
from shared.chromie_contracts import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
    CanonicalPlanStep,
    ExecutionEvidence,
    InteractionResponse,
    RouteItem as SharedRouteItem,
    SocialAttentionBehavior,
    TaskProposal,
)
from shared.chromie_contracts.interaction import CapabilityTraceEvent


class CapabilityTerminologyContractTests(unittest.TestCase):
    def test_canonical_request_uses_capability_identity_and_version_only(self) -> None:
        request = CapabilityRequest(
            request_id="req-1",
            capability_id="chromie.weather.lookup",
            capability_version="1.2.3",
            args={"location": "内乡"},
        )

        payload = request.model_dump(mode="json")

        self.assertEqual(payload["capability_id"], "chromie.weather.lookup")
        self.assertEqual(payload["capability_version"], "1.2.3")
        self.assertNotIn("skill_id", payload)
        self.assertNotIn("skill_version", payload)
        self.assertNotIn("skill_id", request.model_json_schema()["properties"])
        self.assertNotIn("skill_version", request.model_json_schema()["properties"])

    def test_legacy_request_identity_is_rejected_instead_of_normalized(self) -> None:
        with self.assertRaises(ValidationError):
            CapabilityRequest.model_validate(
                {
                    "request_id": "req-legacy",
                    "skill_id": "soridormi.nod_yes",
                    "args": {},
                }
            )

        with self.assertRaises(ValidationError):
            CapabilityRequest.model_validate(
                {
                    "request_id": "req-legacy-version",
                    "capability_id": "soridormi.nod_yes",
                    "skill_version": "1.0.0",
                }
            )

    def test_result_and_trace_emit_canonical_identity(self) -> None:
        result = CapabilityResult(
            request_id="req-result",
            capability_id="soridormi.stand_idle",
            capability_version="1.0.0",
            status="completed",
        )
        trace = CapabilityTrace(
            interaction_id="interaction-1",
            request_id="req-result",
            capability_id="soridormi.stand_idle",
            provider_id="soridormi.mcp",
            events=[CapabilityTraceEvent(type="completed")],
        )

        self.assertEqual(result.capability_id, "soridormi.stand_idle")
        self.assertEqual(trace.capability_id, "soridormi.stand_idle")
        self.assertNotIn("skill_id", result.model_dump(mode="json"))
        self.assertNotIn("skill_id", trace.model_dump(mode="json"))

    def test_interaction_response_uses_capabilities_not_skills(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-canonical",
            capabilities=[
                {
                    "request_id": "req-nested",
                    "capability_id": "soridormi.look_at_person",
                }
            ],
        )

        payload = response.model_dump(mode="json")

        self.assertEqual(
            payload["capabilities"][0]["capability_id"],
            "soridormi.look_at_person",
        )
        self.assertNotIn("skills", payload)
        with self.assertRaises(ValidationError):
            InteractionResponse.model_validate(
                {
                    "interaction_id": "legacy-interaction",
                    "skills": [
                        {
                            "request_id": "legacy-request",
                            "capability_id": "soridormi.look_at_person",
                        }
                    ],
                }
            )

    def test_plan_evidence_and_optional_identity_contracts_are_canonical(self) -> None:
        contracts = [
            CanonicalPlanStep(
                step_id="weather-lookup",
                capability_id="chromie.weather.lookup",
                source_goal_ids=["goal-1"],
            ),
            ExecutionEvidence(
                evidence_id="evidence-1",
                request_id="req-1",
                step_id="weather-lookup",
                capability_id="chromie.weather.lookup",
                source_goal_ids=["goal-1"],
                status="completed",
            ),
            SharedRouteItem(route="tool", capability_id="chromie.weather.lookup"),
            AgentRouteItem(route="tool", capability_id="chromie.weather.lookup"),
            GoalInterpreterRouteItem(route="tool", capability_id="chromie.weather.lookup"),
            OrchestratorRouteItem(route="tool", capability_id="chromie.weather.lookup"),
            SocialAttentionBehavior(capability_id="soridormi.blink_eyes"),
            TaskProposal(
                id="proposal-1",
                state="advisory",
                capability_id="chromie.weather.lookup",
            ),
            EpisodeCapabilityRequestRecord(
                request_id="request-episode",
                capability_id="chromie.weather.lookup",
            ),
            EpisodeCapabilityResultRecord(
                request_id="request-episode",
                capability_id="chromie.weather.lookup",
                status="completed",
            ),
        ]

        for contract in contracts:
            with self.subTest(contract=type(contract).__name__):
                payload = contract.model_dump(mode="json")
                self.assertEqual(payload["capability_id"], contract.capability_id)
                self.assertNotIn("skill_id", payload)
                self.assertNotIn("skill_id", contract.model_json_schema()["properties"])

        optional = SharedRouteItem(route="chat")
        self.assertIsNone(optional.capability_id)
        with self.assertRaises(ValidationError):
            SharedRouteItem.model_validate(
                {"route": "tool", "skill_id": "chromie.weather.lookup"}
            )

    def test_executable_skill_class_aliases_are_removed(self) -> None:
        interaction_module = importlib.import_module("shared.chromie_contracts.interaction")
        runtime_module = importlib.import_module("orchestrator.runtime.capability_runtime")
        shared_package = importlib.import_module("shared.chromie_contracts")

        for name in ("SkillRequest", "SkillResult", "SkillTrace", "SkillTraceEvent"):
            self.assertFalse(hasattr(interaction_module, name), name)
            self.assertFalse(hasattr(shared_package, name), name)

        for name in (
            "SkillRuntime",
            "SkillDefinition",
            "SkillRegistry",
            "SkillProvider",
            "TrustedCapabilityRuntime",
        ):
            self.assertFalse(hasattr(runtime_module, name), name)

        self.assertTrue(issubclass(CapabilityDefinition, object))
        self.assertTrue(issubclass(CapabilityRegistry, object))
        self.assertTrue(issubclass(CapabilityRuntime, object))


if __name__ == "__main__":
    unittest.main()
