from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.capabilities.local import chromie_manifests
from agent.app.goal_association import GoalAssociationResolver, GoalSegmentationModelOutput
from agent.app.planner_contract import (
    PlannerModelOutput,
    ResourceResponsibilityCapabilityGroundingError,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
    canonical_goal_grounding,
    canonical_resource_argument_response_schema,
    resource_grounding_repair_response_schema,
    validate_resource_responsibility_capability_grounding,
)
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
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
    def _planner_output_for_capabilities(
        capability_ids: list[str],
    ) -> PlannerModelOutput:
        goal_id = "goal-resource"
        satisfaction = {
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": [goal_id],
            "unmet_goal_ids": [],
            "unmet_requirements": [],
            "rationale": "The declared Capability set covers the resource Goal.",
        }
        step_ids = (
            ["fetch"]
            if len(capability_ids) == 1
            else [f"resource-{index}" for index in range(1, len(capability_ids) + 1)]
        )
        steps = [
            {
                "step_id": step_id,
                "capability_id": capability_id,
                "args": {},
                "timing": "sequential",
                "source_goal_ids": [goal_id],
                "reason_summary": "Execute one advertised resource capability.",
            }
            for step_id, capability_id in zip(step_ids, capability_ids, strict=True)
        ]
        return PlannerModelOutput.model_validate(
            {
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 1.0,
                "goal_summary": "Fetch and deliver the red mug.",
                "response_text": "",
                "steps": steps,
                "escalation_reason": "",
                "unresolved": [],
                "parameter_resolutions": [],
                "goal_outcomes": {
                    goal_id: {
                        "disposition": "execute",
                        "coverage": "complete",
                        "response_text": "",
                        "unresolved": [],
                        "step_ids": step_ids,
                        "satisfaction": satisfaction,
                        "rationale": "The advertised Capability set is selected.",
                    }
                },
                "goal_satisfaction": satisfaction,
                "plan_relation": "exact",
                "user_confirmation_required": False,
            }
        )

    @classmethod
    def _planner_output(cls, capability_id: str) -> PlannerModelOutput:
        return cls._planner_output_for_capabilities([capability_id])

    @staticmethod
    def _resource_capability(
        capability_id: str,
        *,
        requires: list[str],
        provides: list[str],
        delivery_modes: list[str] | None = None,
    ) -> dict:
        scope = {
            "responsibility_type": "acquire_and_deliver_resource",
            "resource_kinds": ["physical_object"],
        }
        if delivery_modes:
            scope["delivery_modes"] = delivery_modes
        return {
            "capability_id": capability_id,
            "hints": {
                "semantic_scope": scope,
                "resource_contract": {
                    "plan_requires": requires,
                    "plan_provides": provides,
                    "completion_requires": provides,
                    "result_field": "resource_outcome",
                },
            },
        }

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
                quantity="1",
            ),
            source=ResourceSource(
                status="known",
                description="100 meters ahead",
                bindings={
                    "distance": {
                        "name": "distance",
                        "entity_type": "distance",
                        "value": "100",
                    },
                    "direction": {
                        "name": "direction",
                        "entity_type": "direction",
                        "value": "ahead",
                    },
                },
            ),
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

    def test_canonical_resource_projection_is_decoder_read_only(self) -> None:
        base_schema = {
            "$defs": {
                "PlannerModelStep": {
                    "oneOf": [
                        {
                            "properties": {
                                "capability_id": {
                                    "enum": [
                                        "soridormi.acquire_and_deliver_resource"
                                    ]
                                },
                                "args": {
                                    "type": "object",
                                    "properties": {
                                        "resource": {"type": "object"},
                                        "source": {"type": "object"},
                                        "recipient": {"type": "object"},
                                    },
                                    "required": [],
                                },
                            }
                        }
                    ]
                }
            },
            "properties": {
                "parameter_resolutions": {
                    "type": "array",
                    "maxItems": 8,
                }
            },
        }

        projected = canonical_resource_argument_response_schema(
            base_schema,
            authoritative_goals=[self._resource_goal()],
        )
        args = projected["$defs"]["PlannerModelStep"]["oneOf"][0][
            "properties"
        ]["args"]
        responsibility = self._resource_goal()["resource_responsibility"]
        self.assertEqual(
            args["properties"]["resource"]["const"],
            responsibility["resource"],
        )
        self.assertEqual(
            args["properties"]["source"]["const"],
            responsibility["source"],
        )
        self.assertEqual(
            args["properties"]["recipient"]["const"],
            responsibility["recipient"],
        )
        self.assertEqual(
            set(args["required"]),
            {"resource", "source", "recipient"},
        )
        self.assertEqual(
            projected["properties"]["parameter_resolutions"]["maxItems"],
            0,
        )
        self.assertEqual(
            base_schema["properties"]["parameter_resolutions"]["maxItems"],
            8,
        )

    def test_canonical_known_source_rejects_summary_without_typed_bindings(self) -> None:
        with self.assertRaisesRegex(ValidationError, "source.bindings"):
            ResourceSource(
                status="known",
                description="100 meters ahead",
            )

    def test_canonical_source_summary_rejects_unbound_numeric_fact(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "numeric facts.*source.bindings",
        ):
            ResourceSource(
                status="known",
                description="100 meters ahead",
                bindings={
                    "direction": {
                        "name": "direction",
                        "entity_type": "direction",
                        "value": "ahead",
                    }
                },
            )

    def test_canonical_resource_rejects_duplicate_typed_fact_across_owners(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "both resource attributes and source bindings",
        ):
            AcquireAndDeliverResource(
                resource=ResourceDescriptor(
                    kind="physical_object",
                    description="a bottle of water",
                    quantity="1",
                    attributes={
                        "distance_to_source": {
                            "name": "distance_to_source",
                            "entity_type": "distance",
                            "value": "100m",
                        }
                    },
                ),
                source=ResourceSource(
                    status="known",
                    description="100 meters ahead",
                    bindings={
                        "location_offset": {
                            "name": "location_offset",
                            "entity_type": "distance",
                            "value": "100m",
                        }
                    },
                ),
                delivery_mode="physical_handover",
            )

    def test_canonical_resource_rejects_equivalent_measurement_aliases(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "equivalent typed measurement.*resource attributes and source",
        ):
            AcquireAndDeliverResource(
                resource=ResourceDescriptor(
                    kind="physical_object",
                    description="a bottle of water",
                    quantity="1",
                    attributes={
                        "distance": {
                            "name": "distance",
                            "entity_type": "measurement",
                            "value": "100m",
                        }
                    },
                ),
                source=ResourceSource(
                    status="known",
                    bindings={
                        "location_description": {
                            "name": "location_description",
                            "entity_type": "location_instruction",
                            "value": "100 meters ahead",
                        }
                    },
                ),
                delivery_mode="physical_handover",
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
                    hints["resource_contract"]["plan_provides"],
                    ["resource_acquired"],
                )
                self.assertEqual(
                    hints["resource_contract"]["final_delivery_owner"],
                    "chromie_response_layer",
                )

    def test_information_domain_rejects_unrelated_current_read(self) -> None:
        goal = self._resource_goal()
        goal["resource_responsibility"] = {
            "responsibility_type": "acquire_and_deliver_resource",
            "resource": {
                "kind": "information",
                "description": "whether a person is present nearby",
                "attributes": {
                    "information_domain": {
                        "name": "information_domain",
                        "entity_type": "information_domain",
                        "value": "direct_environment_perception",
                    }
                },
            },
            "source": {"status": "unknown"},
            "recipient": {"description": "requester"},
            "delivery_mode": "spoken_explanation",
        }
        weather = {
            "capability_id": "chromie.weather.lookup",
            "hints": {
                "semantic_scope": {
                    "responsibility_type": "acquire_and_deliver_resource",
                    "resource_kinds": ["information"],
                    "delivery_modes": ["spoken_explanation"],
                    "domain": "weather_forecast",
                },
                "resource_contract": {
                    "plan_requires": [],
                    "plan_provides": ["resource_acquired"],
                    "final_delivery_owner": "chromie_response_layer",
                },
            },
        }

        with self.assertRaisesRegex(
            ResourceResponsibilityCapabilityUnavailableError,
            "semantic_scope.domain does not match canonical information domain",
        ):
            validate_resource_responsibility_capability_grounding(
                self._planner_output("chromie.weather.lookup"),
                authoritative_goals=[goal],
                capabilities=[weather],
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
            "complete_capability_ids=soridormi.acquire_and_deliver_resource",
            str(caught.exception),
        )
        self.assertEqual(caught.exception.goal_id, "goal-resource")
        self.assertEqual(
            caught.exception.complete_capability_ids,
            ["soridormi.acquire_and_deliver_resource"],
        )

        base_schema = {
            "$defs": {
                "PlannerModelStep": {
                    "properties": {
                        "capability_id": {
                            "enum": [
                                "soridormi.walk_forward",
                                "soridormi.acquire_and_deliver_resource",
                            ]
                        }
                    },
                    "oneOf": [
                        {
                            "properties": {
                                "capability_id": {
                                    "enum": ["soridormi.walk_forward"]
                                },
                                "args": {
                                    "properties": {"duration_s": {}},
                                    "required": ["duration_s"],
                                },
                            }
                        },
                        {
                            "properties": {
                                "capability_id": {
                                    "enum": [
                                        "soridormi.acquire_and_deliver_resource"
                                    ]
                                },
                                "args": {
                                    "properties": {
                                        "resource": {},
                                        "source": {},
                                        "recipient": {},
                                    },
                                    "required": [],
                                },
                            }
                        },
                    ],
                }
            },
            "properties": {"steps": {"type": "array", "maxItems": 4}},
        }
        tightened = resource_grounding_repair_response_schema(
            base_schema,
            error=caught.exception,
            authoritative_goals=[self._resource_goal()],
        )
        step_schema = tightened["$defs"]["PlannerModelStep"]
        self.assertEqual(
            step_schema["properties"]["capability_id"]["enum"],
            ["soridormi.acquire_and_deliver_resource"],
        )
        self.assertEqual(len(step_schema["oneOf"]), 1)
        args_schema = step_schema["oneOf"][0]["properties"]["args"]
        responsibility = self._resource_goal()["resource_responsibility"]
        self.assertEqual(
            args_schema["properties"]["resource"]["const"],
            responsibility["resource"],
        )
        self.assertEqual(
            args_schema["properties"]["source"]["const"],
            responsibility["source"],
        )
        self.assertEqual(
            tightened["properties"]["steps"]["minItems"],
            1,
        )
        self.assertEqual(
            tightened["properties"]["steps"]["maxItems"],
            1,
        )
        tightened["properties"]["parameter_resolutions"] = {"maxItems": 4}
        tightened_again = resource_grounding_repair_response_schema(
            tightened,
            error=caught.exception,
            authoritative_goals=[self._resource_goal()],
        )
        self.assertEqual(
            tightened_again["properties"]["parameter_resolutions"]["maxItems"],
            0,
        )

        movement_goal = {
            "goal_id": "goal-movement",
            "description": "向前走100米",
            "success_criteria": ["向前走100米"],
            "object": {
                "bindings": {
                    "distance": {
                        "name": "distance",
                        "entity_type": "distance",
                        "value": "100",
                        "confidence": 1.0,
                    }
                }
            },
        }
        multi_goal_schema = resource_grounding_repair_response_schema(
            base_schema,
            error=caught.exception,
            authoritative_goals=[movement_goal, self._resource_goal()],
        )
        multi_step_schema = multi_goal_schema["$defs"]["PlannerModelStep"]
        self.assertEqual(len(multi_step_schema["oneOf"]), 2)
        resource_branch = next(
            branch
            for branch in multi_step_schema["oneOf"]
            if branch["properties"]["capability_id"]["enum"]
            == ["soridormi.acquire_and_deliver_resource"]
        )
        self.assertEqual(
            resource_branch["properties"]["args"]["properties"]["resource"][
                "const"
            ],
            responsibility["resource"],
        )
        multi_steps = multi_goal_schema["properties"]["steps"]
        self.assertEqual(multi_steps["maxItems"], 4)
        self.assertEqual(multi_steps["minContains"], 1)
        self.assertEqual(
            multi_steps["contains"]["properties"]["source_goal_ids"]["contains"],
            {"const": "goal-resource"},
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


    def test_granular_capabilities_can_compose_complete_resource_goal(self) -> None:
        acquire = self._resource_capability(
            "soridormi.acquire_resource",
            requires=[],
            provides=["resource_acquired"],
        )
        deliver = self._resource_capability(
            "soridormi.deliver_resource",
            requires=["resource_acquired"],
            provides=["resource_delivered"],
            delivery_modes=["physical_handover"],
        )

        validate_resource_responsibility_capability_grounding(
            self._planner_output_for_capabilities(
                ["soridormi.acquire_resource", "soridormi.deliver_resource"]
            ),
            authoritative_goals=[self._resource_goal()],
            capabilities=[acquire, deliver],
        )

    def test_granular_capability_order_must_follow_provider_contract(self) -> None:
        acquire = self._resource_capability(
            "soridormi.acquire_resource",
            requires=[],
            provides=["resource_acquired"],
        )
        deliver = self._resource_capability(
            "soridormi.deliver_resource",
            requires=["resource_acquired"],
            provides=["resource_delivered"],
            delivery_modes=["physical_handover"],
        )

        with self.assertRaisesRegex(
            ResourceResponsibilityCapabilityGroundingError,
            "unsatisfied plan_requires",
        ):
            validate_resource_responsibility_capability_grounding(
                self._planner_output_for_capabilities(
                    ["soridormi.deliver_resource", "soridormi.acquire_resource"]
                ),
                authoritative_goals=[self._resource_goal()],
                capabilities=[acquire, deliver],
            )

    def test_partial_resource_plan_signals_composition_when_catalog_can_finish(self) -> None:
        acquire = self._resource_capability(
            "soridormi.acquire_resource",
            requires=[],
            provides=["resource_acquired"],
        )
        deliver = self._resource_capability(
            "soridormi.deliver_resource",
            requires=["resource_acquired"],
            provides=["resource_delivered"],
            delivery_modes=["physical_handover"],
        )

        with self.assertRaises(ResourceResponsibilityRequiresCompositionError) as caught:
            validate_resource_responsibility_capability_grounding(
                self._planner_output("soridormi.acquire_resource"),
                authoritative_goals=[self._resource_goal()],
                capabilities=[acquire, deliver],
            )
        self.assertIn(
            "additional_capability_ids=soridormi.deliver_resource",
            str(caught.exception),
        )

    def test_wrong_nonresource_selection_detects_composable_catalog(self) -> None:
        acquire = self._resource_capability(
            "soridormi.acquire_resource",
            requires=[],
            provides=["resource_acquired"],
        )
        deliver = self._resource_capability(
            "soridormi.deliver_resource",
            requires=["resource_acquired"],
            provides=["resource_delivered"],
            delivery_modes=["physical_handover"],
        )
        walk = {
            "capability_id": "soridormi.walk_forward",
            "hints": {"semantic_scope": {}, "resource_contract": {}},
        }

        with self.assertRaises(ResourceResponsibilityRequiresCompositionError) as caught:
            validate_resource_responsibility_capability_grounding(
                self._planner_output("soridormi.walk_forward"),
                authoritative_goals=[self._resource_goal()],
                capabilities=[walk, acquire, deliver],
            )
        self.assertIn("soridormi.acquire_resource", str(caught.exception))
        self.assertIn("soridormi.deliver_resource", str(caught.exception))

    def test_complete_capability_remains_atomic_when_granular_skills_also_exist(self) -> None:
        acquire = self._resource_capability(
            "soridormi.acquire_resource",
            requires=[],
            provides=["resource_acquired"],
        )
        deliver = self._resource_capability(
            "soridormi.deliver_resource",
            requires=["resource_acquired"],
            provides=["resource_delivered"],
            delivery_modes=["physical_handover"],
        )
        complete = self._resource_capability(
            "soridormi.acquire_and_deliver_resource",
            requires=[],
            provides=["resource_acquired", "resource_delivered"],
            delivery_modes=["physical_handover"],
        )

        validate_resource_responsibility_capability_grounding(
            self._planner_output("soridormi.acquire_and_deliver_resource"),
            authoritative_goals=[self._resource_goal()],
            capabilities=[acquire, deliver, complete],
        )

    def test_complete_capability_argument_conflict_enables_exact_dto_repair(self) -> None:
        goal = self._resource_goal()
        responsibility = goal["resource_responsibility"]
        responsibility["resource"]["quantity"] = "1"
        responsibility["source"] = {
            "status": "known",
            "description": "",
            "bindings": {
                "distance_binding": {
                    "name": "distance_binding",
                    "entity_type": "distance",
                    "value": "100",
                    "confidence": 1.0,
                }
            },
        }
        raw_output = self._planner_output(
            "soridormi.acquire_and_deliver_resource"
        ).model_dump(mode="json")
        raw_output["steps"][0]["args"] = {
            "resource": responsibility["resource"],
            "source": {
                "status": "known",
                "description": "100 meters ahead",
                "bindings": {
                    "distance_binding": {"type": "string", "value": "100"}
                },
            },
            "recipient": responsibility["recipient"],
        }
        output = PlannerModelOutput.model_validate(raw_output)
        complete = self._resource_capability(
            "soridormi.acquire_and_deliver_resource",
            requires=[],
            provides=["resource_acquired", "resource_delivered"],
            delivery_modes=["physical_handover"],
        )

        with self.assertRaises(
            ResourceResponsibilityCapabilityGroundingError
        ) as caught:
            validate_resource_responsibility_capability_grounding(
                output,
                authoritative_goals=[goal],
                capabilities=[complete],
            )

        self.assertEqual(caught.exception.goal_id, "goal-resource")
        self.assertEqual(
            caught.exception.complete_capability_ids,
            ["soridormi.acquire_and_deliver_resource"],
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


    def test_removed_responsibility_variant_is_rejected(self) -> None:
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
        canonical_payload = information.model_dump(mode="json")
        self.assertNotIn("responsibility_variant", canonical_payload)
        for removed_variant in (
            "fetch_and_deliver_information",
            "fetch_and_deliver_object",
        ):
            with self.subTest(removed_variant=removed_variant):
                with self.assertRaises(ValidationError):
                    AcquireAndDeliverResource.model_validate(
                        {
                            **canonical_payload,
                            "responsibility_variant": removed_variant,
                        }
                    )

    def test_absent_resource_contract_keeps_ordinary_goal_serialization_clean(self) -> None:
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
                        "source_responsibility_refs": ["resource"],
                        "description": "Fetch a bottle of water and deliver it to the requester.",
                        "output_mode": "body_action",
                        "bindings": [],
                        "resource_responsibility": {
                            "kind": "physical_object",
                            "description": "a bottle of water",
                            "quantity": "1",
                            "source": {
                                "status": "known",
                                "description": "100 meters ahead",
                                "acquisition_bindings": [
                                    {
                                        "name": "source_location",
                                        "entity_type": "place",
                                        "value": "100 meters ahead",
                                        "confidence": 1.0,
                                    }
                                ],
                            },
                            "recipient": {"description": "requester"},
                            "delivery_mode": "physical_handover",
                        },
                    }
                ],
                "referent_updates": [],
                "resolved_references": [],
                "confidence": 1.0,
                "reason_summary": "One complete resource responsibility.",
            }
        )
        request = CognitiveWorkRequest(
            sid="resource-contract",
            text="The water is 100 meters ahead. Bring me a bottle.",
            language="en-US",
            responsibilities=[
                {
                    "local_ref": "resource",
                    "outcome": "Fetch a bottle of water and deliver it to the requester.",
                    "bindings": {
                        "resource": "a bottle of water",
                        "source": "100 meters ahead",
                    },
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.9,
                }
            ],
            interpretation_confidence=0.9,
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
        self.assertEqual(resolution.new_goals[0].object, {})
        serialized = responsibility.model_dump(mode="json")
        self.assertNotIn("provider_id", serialized)
        self.assertNotIn("capability_id", serialized)


if __name__ == "__main__":
    unittest.main()
