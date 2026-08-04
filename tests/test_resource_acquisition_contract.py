from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.goal_association import GoalAssociationResolver, GoalSegmentationModelOutput
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.resource import (
    AcquireAndDeliverResource,
    ResourceDescriptor,
    ResourceRecipient,
    ResourceSource,
)
from shared.chromie_contracts.semantic_task import SemanticGoal


class _NoopOllama:
    async def generate(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("model must not be called")


class ResourceAcquisitionContractTests(unittest.TestCase):
    def test_contract_is_provider_neutral_and_rejects_backend_fields(self) -> None:
        responsibility = AcquireAndDeliverResource(
            resource=ResourceDescriptor(
                kind="physical_object",
                description="a bottle of water",
                quantity="one",
            ),
            source=ResourceSource(status="known", description="100 meters ahead"),
            recipient=ResourceRecipient(description="requester"),
            delivery_mode="physical_handover",
        )

        payload = responsibility.model_dump(mode="json")
        self.assertNotIn("provider_id", payload)
        self.assertNotIn("capability_id", payload)
        self.assertNotIn("execution_mode", payload)

        with self.assertRaises(ValidationError):
            AcquireAndDeliverResource.model_validate(
                {**payload, "provider_id": "soridormi"}
            )
        with self.assertRaises(ValidationError):
            AcquireAndDeliverResource.model_validate(
                {
                    **payload,
                    "metadata": {"capability_id": "soridormi.fetch_object"},
                }
            )

    def test_information_and_physical_delivery_modes_are_distinct(self) -> None:
        AcquireAndDeliverResource(
            resource=ResourceDescriptor(
                kind="information",
                description="grounded nearby restaurant recommendations",
            ),
            source=ResourceSource(
                status="provider_resolved",
                description="current external information",
            ),
            delivery_mode="spoken_explanation",
        )

        with self.assertRaises(ValidationError):
            AcquireAndDeliverResource(
                resource=ResourceDescriptor(
                    kind="information",
                    description="current weather",
                ),
                source=ResourceSource(status="provider_resolved"),
                delivery_mode="physical_handover",
            )

    def test_absent_resource_contract_does_not_change_legacy_goal_serialization(self) -> None:
        goal = SemanticGoal(
            description="Tell the user a joke.",
            source_text="Tell me a joke.",
        )
        self.assertNotIn("resource_responsibility", goal.model_dump(mode="json"))

    def test_goal_association_expands_provider_neutral_physical_resource(self) -> None:
        model_output = GoalSegmentationModelOutput.model_validate(
            {
                "decision": "create_goals",
                "new_goals": [
                    {
                        "description": "Fetch a bottle of water and deliver it to the requester.",
                        "responsibility_kind": "executable_action",
                        "bindings": [
                            {
                                "name": "source_location",
                                "entity_type": "place",
                                "value": "100 meters ahead",
                                "confidence": 1.0,
                            }
                        ],
                        "resource_responsibility": {
                            "resource_kind": "physical_object",
                            "resource_description": "a bottle of water",
                            "source_status": "known",
                            "source_binding_names": ["source_location"],
                            "recipient_description": "requester",
                            "delivery_mode": "physical_handover",
                        },
                    }
                ],
                "referent_updates": [],
                "resolved_references": [],
                "clarification": "",
                "confidence": 1.0,
                "reason_summary": "One complete resource responsibility.",
            }
        )
        request = AgentRunRequest(
            sid="resource-contract",
            text="The water is 100 meters ahead. Bring me a bottle.",
            language="en-US",
            route_decision=RouteDecision(
                route="robot_action",
                intent="fetch_water",
                confidence=0.9,
                source="llm",
            ),
            context={},
        )

        resolution = GoalAssociationResolver(_NoopOllama())._expand_model_output(
            model_output,
            request=request,
            turn_id="turn-resource",
        )
        responsibility = resolution.new_goals[0].resource_responsibility
        self.assertIsNotNone(responsibility)
        assert responsibility is not None
        self.assertEqual(responsibility.resource.kind, "physical_object")
        self.assertEqual(
            responsibility.source.bindings["source_location"]["value"],
            "100 meters ahead",
        )
        serialized = responsibility.model_dump(mode="json")
        self.assertNotIn("provider_id", serialized)
        self.assertNotIn("capability_id", serialized)


if __name__ == "__main__":
    unittest.main()
