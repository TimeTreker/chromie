from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.cognitive_core.goal_interpreter.schema import RouteItem as GoalInterpreterRouteItem
from agent.app.schema import RouteItem as AgentRouteItem
from orchestrator.runtime.episode import (
    EpisodeSkillRequestRecord,
    EpisodeSkillResultRecord,
)
from orchestrator.schemas.route import RouteItem as OrchestratorRouteItem
from orchestrator.runtime.skill_runtime import (
    CapabilityDefinition,
    CapabilityRegistry,
    SkillDefinition,
    SkillRegistry,
    SkillRuntime,
    TrustedCapabilityRuntime,
)
from shared.chromie_contracts import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
    CanonicalPlanStep,
    ExecutionEvidence,
    InteractionResponse,
    SkillRequest,
    SkillResult,
    SkillTrace,
    RouteItem as SharedRouteItem,
    SocialAttentionBehavior,
    TaskProposal,
)
from shared.chromie_contracts.interaction import CapabilityTraceEvent


class CapabilityTerminologyContractTests(unittest.TestCase):
    def test_canonical_request_serializes_only_capability_id(self) -> None:
        request = CapabilityRequest(
            request_id="req-1",
            capability_id="chromie.weather.lookup",
            args={"location": "内乡"},
        )

        payload = request.model_dump(mode="json")

        self.assertEqual(payload["capability_id"], "chromie.weather.lookup")
        self.assertNotIn("skill_id", payload)
        self.assertEqual(request.skill_id, request.capability_id)

    def test_legacy_request_normalizes_immediately(self) -> None:
        request = CapabilityRequest.model_validate(
            {
                "request_id": "req-legacy",
                "skill_id": "soridormi.nod_yes",
                "args": {},
            }
        )

        self.assertEqual(request.capability_id, "soridormi.nod_yes")
        self.assertEqual(
            set(request.model_dump(mode="json")),
            {
                "capability_id",
                "request_id",
                "skill_version",
                "args",
                "timing",
                "timeout_ms",
                "cancellable",
                "requires_confirmation",
                "idempotency_key",
                "committed_output_schema_sha256",
                "committed_completion_evidence_sha256",
                "metadata",
            },
        )

    def test_equal_dual_identity_is_accepted_and_canonicalized(self) -> None:
        request = CapabilityRequest.model_validate(
            {
                "request_id": "req-dual",
                "capability_id": "soridormi.blink_eyes",
                "skill_id": "soridormi.blink_eyes",
            }
        )

        self.assertEqual(request.capability_id, "soridormi.blink_eyes")
        self.assertNotIn("skill_id", request.model_dump(mode="json"))

    def test_conflicting_dual_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "conflicting capability_id and legacy skill_id",
        ):
            CapabilityRequest.model_validate(
                {
                    "request_id": "req-conflict",
                    "capability_id": "soridormi.nod_yes",
                    "skill_id": "soridormi.shake_no",
                }
            )

    def test_legacy_class_aliases_use_canonical_contract(self) -> None:
        self.assertIs(SkillRequest, CapabilityRequest)
        self.assertIs(SkillResult, CapabilityResult)
        self.assertIs(SkillTrace, CapabilityTrace)

        request = SkillRequest(request_id="req-alias", skill_id="chromie.speak")
        self.assertEqual(request.capability_id, "chromie.speak")
        self.assertNotIn("skill_id", request.model_dump(mode="json"))

    def test_result_and_trace_emit_canonical_identity(self) -> None:
        result = CapabilityResult(
            request_id="req-result",
            skill_id="soridormi.stand_idle",
            status="completed",
        )
        trace = CapabilityTrace(
            interaction_id="interaction-1",
            request_id="req-result",
            skill_id="soridormi.stand_idle",
            provider_id="soridormi.mcp",
            events=[CapabilityTraceEvent(type="completed")],
        )

        self.assertEqual(result.capability_id, "soridormi.stand_idle")
        self.assertEqual(trace.capability_id, "soridormi.stand_idle")
        self.assertNotIn("skill_id", result.model_dump(mode="json"))
        self.assertNotIn("skill_id", trace.model_dump(mode="json"))

    def test_interaction_nested_serialization_is_canonical(self) -> None:
        response = InteractionResponse(
            interaction_id="interaction-canonical",
            skills=[
                {
                    "request_id": "req-nested",
                    "skill_id": "soridormi.look_at_person",
                }
            ],
        )

        payload = response.model_dump(mode="json")

        self.assertEqual(
            payload["skills"][0]["capability_id"],
            "soridormi.look_at_person",
        )
        self.assertNotIn("skill_id", payload["skills"][0])

    def test_plan_step_accepts_legacy_and_serializes_canonical(self) -> None:
        step = CanonicalPlanStep(
            step_id="weather-lookup",
            skill_id="chromie.weather.lookup",
            source_goal_ids=["goal-1"],
        )

        payload = step.model_dump(mode="json")

        self.assertEqual(payload["capability_id"], "chromie.weather.lookup")
        self.assertNotIn("skill_id", payload)

    def test_execution_evidence_accepts_legacy_and_serializes_canonical(self) -> None:
        evidence = ExecutionEvidence(
            evidence_id="evidence-1",
            request_id="req-1",
            step_id="weather-lookup",
            skill_id="chromie.weather.lookup",
            source_goal_ids=["goal-1"],
            status="completed",
        )

        payload = evidence.model_dump(mode="json")

        self.assertEqual(payload["capability_id"], "chromie.weather.lookup")
        self.assertNotIn("skill_id", payload)

    def test_model_copy_normalizes_legacy_update(self) -> None:
        request = CapabilityRequest(
            request_id="req-copy",
            capability_id="soridormi.nod_yes",
        )

        copied = request.model_copy(update={"skill_id": "soridormi.shake_no"})

        self.assertEqual(copied.capability_id, "soridormi.shake_no")
        self.assertNotIn("skill_id", copied.model_dump(mode="json"))


    def test_remaining_model_and_evidence_contracts_emit_capability_id(self) -> None:
        contracts = [
            SharedRouteItem(route="tool", skill_id="chromie.weather.lookup"),
            AgentRouteItem(route="tool", skill_id="chromie.weather.lookup"),
            GoalInterpreterRouteItem(route="tool", skill_id="chromie.weather.lookup"),
            OrchestratorRouteItem(route="tool", skill_id="chromie.weather.lookup"),
            SocialAttentionBehavior(skill_id="soridormi.blink_eyes"),
            TaskProposal(
                id="proposal-1",
                state="advisory",
                skill_id="chromie.weather.lookup",
            ),
            EpisodeSkillRequestRecord(
                request_id="request-episode",
                skill_id="chromie.weather.lookup",
            ),
            EpisodeSkillResultRecord(
                request_id="request-episode",
                skill_id="chromie.weather.lookup",
                status="completed",
            ),
        ]

        for contract in contracts:
            with self.subTest(contract=type(contract).__name__):
                payload = contract.model_dump(mode="json")
                self.assertEqual(payload["capability_id"], contract.capability_id)
                self.assertNotIn("skill_id", payload)
                self.assertNotIn("skill_id", contract.model_json_schema()["properties"])

    def test_optional_identity_contracts_accept_omitted_identity_and_reject_conflict(self) -> None:
        item = SharedRouteItem(route="chat")
        self.assertIsNone(item.capability_id)
        self.assertNotIn("skill_id", item.model_dump(mode="json"))

        with self.assertRaisesRegex(ValidationError, "conflicting capability_id"):
            SharedRouteItem.model_validate(
                {
                    "route": "tool",
                    "capability_id": "chromie.weather.lookup",
                    "skill_id": "chromie.memory.retrieve_verified_tool_result",
                }
            )

    def test_runtime_definition_uses_canonical_identity_with_legacy_reader(self) -> None:
        definition = CapabilityDefinition(
            skill_id="chromie.test.capability",
            provider_id="test.provider",
        )

        payload = definition.model_dump(mode="json")

        self.assertEqual(definition.capability_id, "chromie.test.capability")
        self.assertEqual(definition.skill_id, "chromie.test.capability")
        self.assertEqual(payload["capability_id"], "chromie.test.capability")
        self.assertNotIn("skill_id", payload)

    def test_runtime_names_are_canonical_aliases_not_second_authority(self) -> None:
        self.assertIs(CapabilityDefinition, SkillDefinition)
        self.assertIs(CapabilityRegistry, SkillRegistry)
        self.assertIs(TrustedCapabilityRuntime, SkillRuntime)


if __name__ == "__main__":
    unittest.main()
