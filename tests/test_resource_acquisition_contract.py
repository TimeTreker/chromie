from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.capabilities.local import chromie_manifests
from agent.app.goal_association import GoalAssociationResolver, GoalSegmentationModelOutput
from agent.app.planner_contract import (
    PlannerModelOutput,
    ResourceResponsibilityCapabilityGroundingError,
    ResourceResponsibilityCapabilityUnavailableError,
    canonical_goal_grounding,
    validate_resource_responsibility_capability_grounding,
)
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
    @staticmethod
    def _planner_output(capability_id: str) -> PlannerModelOutput:
        goal_id = "goal-resource"
        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The declared Capability covers the resource Goal.",
        }
        return PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Fetch and deliver the red mug.",
                "response_text": "",
                "steps": [
                    {
                        "step_id": "fetch",
                        "capability_id": capability_id,
                        "args": {},
                        "timing": "sequential",
                        "source_goal_ids": [goal_id],
                        "reason_summary": "Execute the resource responsibility.",
                    }
                ],
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [],
                "goal_outcomes": {
                    goal_id: {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": ["fetch"],
                        "satisfaction": satisfaction,
                        "rationale": "The exact provider Capability is selected.",
                    }
                },
                "goal_satisfaction": satisfaction,
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

    @staticmethod
    def _resource_goal() -> dict:
        return {
            "goal_id": "goal-resource",
            "description": "Fetch the red mug and hand it to the requester.",
            "resource_responsibility": {
                "responsibility_type": "acquire_and_deliver_resource",
                "resource": {
                    "kind": "physical_object",
                    "description": "the red mug",
                },
                "source": {"status": "unknown"},
                "recipient": {"description": "requester"},
                "delivery_mode": "physical_handover",
            },
        }

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

    def test_builtin_information_providers_share_resource_responsibility(self) -> None:
        tools = {
            tool.name: tool
            for manifest in chromie_manifests()
            for tool in manifest.tools
        }
        for capability_id in (
            "chromie.weather.lookup",
            "chromie.external_information.retrieve",
        ):
            with self.subTest(capability_id=capability_id):
                hints = tools[capability_id].llm_hints
                scope = hints["semantic_scope"]
                self.assertEqual(
                    scope["responsibility_type"],
                    "acquire_and_deliver_resource",
                )
                self.assertIn("information", scope["resource_kinds"])
                self.assertIn("spoken_explanation", scope["delivery_modes"])
                self.assertTrue(hints["resource_contract"])
                self.assertEqual(
                    hints["resource_contract"]["final_delivery_owner"],
                    "chromie_response_layer",
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

    def test_generic_motion_cannot_claim_typed_resource_responsibility(self) -> None:
        output = self._planner_output("soridormi.walk_forward")

        with self.assertRaisesRegex(
            ResourceResponsibilityCapabilityUnavailableError,
            "resource responsibility Capability contract mismatch",
        ):
            validate_resource_responsibility_capability_grounding(
                output,
                authoritative_goals=[self._resource_goal()],
                capabilities=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "hints": {
                            "semantic_scope": {},
                            "resource_contract": {},
                        },
                    }
                ],
            )

    def test_wrong_selection_distinguishes_an_available_matching_provider(self) -> None:
        output = self._planner_output("soridormi.walk_forward")

        with self.assertRaises(ResourceResponsibilityCapabilityGroundingError) as caught:
            validate_resource_responsibility_capability_grounding(
                output,
                authoritative_goals=[self._resource_goal()],
                capabilities=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "hints": {
                            "semantic_scope": {},
                            "resource_contract": {},
                        },
                    },
                    {
                        "capability_id": "soridormi.acquire_and_deliver_resource",
                        "hints": {
                            "semantic_scope": {
                                "responsibility_type": (
                                    "acquire_and_deliver_resource"
                                ),
                                "resource_kinds": ["physical_object"],
                                "delivery_modes": ["physical_handover"],
                            },
                            "resource_contract": {
                                "result_field": "resource_outcome"
                            },
                        },
                    },
                ],
            )

        self.assertNotIsInstance(
            caught.exception,
            ResourceResponsibilityCapabilityUnavailableError,
        )
        self.assertIn(
            "matching_capability_ids=soridormi.acquire_and_deliver_resource",
            str(caught.exception),
        )

    def test_resource_capability_accepts_legacy_or_canonical_delivery_scope(self) -> None:
        for scope in (
            {
                "responsibility_type": "acquire_and_deliver_resource",
                "resource_kinds": ["physical_object"],
                "delivery": "physical_handover",
            },
            {
                "responsibility_type": "acquire_and_deliver_resource",
                "resource_kinds": ["physical_object"],
                "delivery_modes": ["physical_handover"],
            },
        ):
            validate_resource_responsibility_capability_grounding(
                self._planner_output("soridormi.acquire_and_deliver_resource"),
                authoritative_goals=[self._resource_goal()],
                capabilities=[
                    {
                        "capability_id": "soridormi.acquire_and_deliver_resource",
                        "hints": {
                            "semantic_scope": scope,
                            "resource_contract": {"result_field": "resource_outcome"},
                        },
                    }
                ],
            )

    def test_planner_grounding_preserves_new_resource_responsibility(self) -> None:
        resource_goal = self._resource_goal()
        authoritative_goals = canonical_goal_grounding(
            {
                "goal_association_resolution": {
                    "associations": [],
                    "new_goals": [resource_goal],
                }
            }
        )

        self.assertEqual(
            authoritative_goals[0]["resource_responsibility"],
            resource_goal["resource_responsibility"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "resource responsibility Capability contract mismatch",
        ):
            validate_resource_responsibility_capability_grounding(
                self._planner_output("soridormi.walk_forward"),
                authoritative_goals=authoritative_goals,
                capabilities=[
                    {
                        "capability_id": "soridormi.walk_forward",
                        "hints": {
                            "semantic_scope": {},
                            "resource_contract": {},
                        },
                    }
                ],
            )

    def test_planner_grounding_preserves_retained_resource_responsibility(self) -> None:
        resource_goal = self._resource_goal()
        authoritative_goals = canonical_goal_grounding(
            {
                "goal_association_resolution": {
                    "associations": [
                        {
                            "relationship": "continue",
                            "target_goal_ids": ["goal-resource"],
                        }
                    ],
                    "new_goals": [],
                },
                "active_goal_snapshots": [
                    {
                        "goal_id": "goal-resource",
                        "goal": resource_goal,
                    }
                ],
            }
        )

        self.assertEqual(
            authoritative_goals[0]["resource_responsibility"],
            resource_goal["resource_responsibility"],
        )

    def test_exact_resource_capability_declares_scope_and_result_contract(self) -> None:
        output = self._planner_output("soridormi.acquire_and_deliver_resource")

        validate_resource_responsibility_capability_grounding(
            output,
            authoritative_goals=[self._resource_goal()],
            capabilities=[
                {
                    "capability_id": "soridormi.acquire_and_deliver_resource",
                    "hints": {
                        "semantic_scope": {
                            "responsibility_type": "acquire_and_deliver_resource",
                            "resource_kinds": ["physical_object"],
                            "delivery_modes": ["physical_handover"],
                        }
                    },
                    "metadata": {
                        "resource_contract": {
                            "result_field": "resource_outcome",
                        }
                    },
                }
            ],
        )


    def test_legacy_responsibility_variant_is_input_only_compatibility(self) -> None:
        information = AcquireAndDeliverResource(
            resource=ResourceDescriptor(
                kind="information",
                description="Chongqing weather tomorrow",
            ),
            source=ResourceSource(
                status="provider_resolved",
                description="current weather information",
            ),
            delivery_mode="spoken_explanation",
        )
        self.assertEqual(
            information.responsibility_type,
            "acquire_and_deliver_resource",
        )
        canonical_payload = information.model_dump(mode="json")
        self.assertNotIn("responsibility_variant", canonical_payload)
        restored = AcquireAndDeliverResource.model_validate(
            {
                **canonical_payload,
                "responsibility_variant": "fetch_and_deliver_information",
            }
        )
        self.assertEqual(restored.resource.kind, "information")
        self.assertNotIn("responsibility_variant", restored.model_dump(mode="json"))

        with self.assertRaises(ValidationError):
            AcquireAndDeliverResource.model_validate(
                {
                    **canonical_payload,
                    "responsibility_variant": "fetch_and_deliver_object",
                }
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
        self.assertNotIn(
            "responsibility_variant",
            responsibility.model_dump(mode="json"),
        )
        self.assertEqual(
            responsibility.source.bindings["source_location"]["value"],
            "100 meters ahead",
        )
        serialized = responsibility.model_dump(mode="json")
        self.assertNotIn("provider_id", serialized)
        self.assertNotIn("capability_id", serialized)


if __name__ == "__main__":
    unittest.main()
