from __future__ import annotations

import asyncio
import copy
import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import (
    GoalAssociationModelAssociation,
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelInformationResourceResponsibility,
    GoalAssociationModelOutput,
    GoalAssociationModelPhysicalResourceResponsibility,
    GoalAssociationResolver,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, CognitiveWorkRequest
from shared.chromie_contracts.resource import (
    AcquireAndDeliverResource,
    ResourceDescriptor,
    ResourceRecipient,
    ResourceSource,
    resource_semantic_bindings,
)


class FakeOllama:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ScriptedOllama:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if not self.payloads:
            raise AssertionError("unexpected extra model call")
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


def binding(
    name: str,
    entity_type: str,
    value: str,
    *,
    referent_id: str = "",
) -> dict:
    payload = {
        "name": name,
        "entity_type": entity_type,
        "value": value,
        "confidence": 1.0,
    }
    if referent_id:
        payload["referent_id"] = referent_id
    return payload


def resource_responsibility(
    *,
    kind: str = "physical_object",
    description: str = "一杯水",
    quantity: str = "1",
    attributes: list[dict] | None = None,
    source_status: str = "unknown",
    source_description: str = "",
    source_bindings: list[dict] | None = None,
    recipient: str = "用户",
    recipient_referent_id: str | None = None,
    delivery_mode: str | None = None,
    information_domain: str = "weather_forecast",
) -> dict:
    recipient_payload = {"description": recipient}
    if recipient_referent_id:
        recipient_payload["referent_id"] = recipient_referent_id
    if kind == "information":
        source_payload: dict = {"status": source_status}
        if source_status == "known":
            source_payload["source_name"] = source_description or "named source"
        return {
            "kind": "information",
            "information_domain": information_domain,
            "description": description,
            "quantity": quantity,
            "query_scope": list(attributes or []),
            "source": source_payload,
            "recipient": recipient_payload,
            "delivery_mode": delivery_mode or "spoken_explanation",
        }
    return {
        "kind": "physical_object",
        "description": description,
        "quantity": quantity,
        "source": {
            "status": source_status,
            "description": source_description,
            "acquisition_bindings": list(source_bindings or []),
        },
        "recipient": recipient_payload,
        "delivery_mode": delivery_mode or "physical_handover",
    }


def goal(
    description: str,
    output_mode: str,
    *,
    bindings: list[dict] | None = None,
    resource: dict | None = None,
    **extra,
) -> dict:
    payload = {
        "source_responsibility_refs": ["r1"],
        "description": description,
        "output_mode": output_mode,
        "bindings": list(bindings or []),
        "resource_responsibility": resource,
        **extra,
    }
    return payload


def create_goals(*goals: dict) -> dict:
    return {
        "decision": "create_goals",
        "new_goals": list(goals),
        "confidence": 1.0,
        "reason_summary": "The candidate set represents the current responsibility.",
    }


def coverage_item(
    source_excerpt: str,
    *goal_indices: int,
    role: str = "responsibility",
    coverage: str = "covered",
    independently_satisfiable: bool = True,
    temporal_dimensions: list[str] | None = None,
    required_goal_shape: str = "ordinary",
    required_information_domain: str | None = None,
    required_output_mode: str | None = None,
) -> dict:
    return {
        "source_excerpt": source_excerpt,
        "role": role,
        "coverage": coverage,
        "independently_satisfiable": (
            independently_satisfiable if role == "responsibility" else False
        ),
        "candidate_goal_indices": list(goal_indices),
        "temporal_dimensions": list(temporal_dimensions or []),
        "required_goal_shape": required_goal_shape,
        "required_information_domain": (
            required_information_domain
            if required_information_domain is not None
            else "weather_forecast"
            if required_goal_shape == "information_resource"
            else "none"
        ),
        "required_output_mode": (
            required_output_mode
            if required_output_mode is not None
            else "capability_work"
            if required_goal_shape in {"information_resource", "persistent_effect"}
            else "body_action"
            if required_goal_shape == "physical_resource"
            else "none"
        ),
    }


def certificate(*items: dict) -> dict:
    return {
        "responsibility_items": [
            item for item in items if item.get("role") == "responsibility"
        ],
        "supporting_items": [
            item for item in items if item.get("role") != "responsibility"
        ],
        "reason_summary": "The item judgments prove candidate responsibility coverage.",
    }



def typed_responsibilities(*items: dict) -> list[CognitiveResponsibilityProposal]:
    return [CognitiveResponsibilityProposal.model_validate(item) for item in items]

def request(
    text: str,
    *,
    active_goals=None,
    language: str = "zh-CN",
    discourse_referents=None,
    responsibility_outcomes: list[str] | None = None,
    interpretation_unresolved: list[str] | None = None,
) -> CognitiveWorkRequest:
    outcomes = list(responsibility_outcomes or [text])
    return CognitiveWorkRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        responsibilities=[
            {
                "local_ref": f"r{index}",
                "outcome": outcome,
                "bindings": {},
                "completion_requires_work": True,
                "completion_requires_fresh_evidence": False,
                "confidence": 0.9,
            }
            for index, outcome in enumerate(outcomes, start=1)
        ],
        interpretation_confidence=0.9,
        interpretation_unresolved=list(interpretation_unresolved or []),
        context={
            "active_goal_snapshots": active_goals or [],
            "recent_goal_snapshots": [],
            "history": [],
            "discourse_referents": discourse_referents or [],
            "discourse_focus": [],
            "recent_tool_evidence": [],
        },
    )


def active_goal(goal_id: str, description: str) -> dict:
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "responsibility_status": "open",
        "work_status": "open",
        "goal": {
            "goal_id": goal_id,
            "version": 1,
            "responsibility_status": "open",
            "description": description,
            "source_text": description,
            "beneficiary": "user",
            "object": {"bindings": {}},
            "constraints": {},
            "success_criteria": [],
            "metadata": {},
        },
        "open_information_gaps": [],
        "last_user_update": description,
        "metadata": {},
    }


class GoalExecutionContractTests(unittest.TestCase):
    def test_qualitative_speed_binding_uses_provider_neutral_canonical_value(self):
        self.assertEqual(
            GoalAssociationModelBinding(
                name="speed",
                entity_type="speed",
                value="quick",
                confidence=1.0,
            ).value,
            "quick",
        )
        with self.assertRaisesRegex(ValidationError, "qualitative speed bindings"):
            GoalAssociationModelBinding(
                name="speed",
                entity_type="speed",
                value="quickly",
                confidence=1.0,
            )

    def test_day_part_binding_uses_canonical_runtime_vocabulary(self):
        with self.assertRaisesRegex(ValueError, "canonical day-part value"):
            GoalAssociationModelBinding.model_validate(
                binding("time", "day_part", "daytime")
            )

        parsed = GoalAssociationModelBinding.model_validate(
            binding("time", "day_part", "day")
        )
        self.assertEqual(parsed.value, "day")

        night = GoalAssociationModelBinding.model_validate(
            binding("time", "day_part", "night")
        )
        self.assertEqual(night.value, "night")
        with self.assertRaisesRegex(ValueError, "canonical day-part value"):
            GoalAssociationModelBinding.model_validate(
                binding("time", "day_part", "tonight")
            )

    def test_date_binding_uses_canonical_runtime_vocabulary(self):
        for noncanonical in ("今天", "明天", "next Tuesday", "2026-8-19"):
            with self.subTest(noncanonical=noncanonical):
                with self.assertRaisesRegex(ValueError, "canonical relative date"):
                    GoalAssociationModelBinding.model_validate(
                        binding("date", "date", noncanonical)
                    )

        for canonical in ("today", "tomorrow", "2026-08-19"):
            with self.subTest(canonical=canonical):
                parsed = GoalAssociationModelBinding.model_validate(
                    binding("date", "date", canonical)
                )
                self.assertEqual(parsed.value, canonical)

    def test_host_execution_projection_is_derived_from_output_mode(self):
        item = GoalAssociationModelGoal.model_validate(
            goal("Check tomorrow's weather.", "capability_work")
        )

        self.assertEqual(item.responsibility_kind, "capability_dependent")
        self.assertEqual(item.execution_lane, "activity")
        self.assertTrue(item.provider_required)

    def test_model_cannot_author_host_execution_projection(self):
        with self.assertRaises(ValidationError):
            GoalAssociationModelGoal.model_validate(
                {
                    **goal("Sing.", "singing"),
                    "responsibility_kind": "executable_action",
                }
            )

    def test_physical_resource_has_one_acquisition_binding_surface(self):
        nested = resource_responsibility(
            source_status="known",
            source_description="前方100米处",
            source_bindings=[
                binding("distance", "distance", "100"),
                binding("direction", "direction", "前方"),
            ],
        )
        parsed = GoalAssociationModelGoal.model_validate(
            goal("从前方100米处拿一杯水并交给用户。", "body_action", resource=nested)
        )
        resource = parsed.resource_responsibility
        self.assertEqual(resource.quantity, "1")
        self.assertEqual(resource.kind, "physical_object")
        self.assertEqual(
            [item.name for item in resource.source.acquisition_bindings],
            ["distance", "direction"],
        )

        with self.assertRaisesRegex(ValueError, "authored only inside"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "从前方100米处拿一杯水并交给用户。",
                    "body_action",
                    bindings=[binding("distance", "distance", "100")],
                    resource=nested,
                )
            )

    def test_resource_quantity_requires_normalized_numeric_string(self):
        with self.assertRaisesRegex(ValueError, "normalized numeric string"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring one bottle.",
                    "body_action",
                    resource=resource_responsibility(quantity="one"),
                )
            )

    def test_physical_resource_rejects_information_query_scope_surface(self):
        payload = resource_responsibility(
            source_status="known",
            source_bindings=[binding("source_location", "place", "table")],
        )
        payload["query_scope"] = [binding("distance", "distance", "100")]
        with self.assertRaises(ValidationError):
            GoalAssociationModelGoal.model_validate(
                goal("Bring the bottle.", "body_action", resource=payload)
            )

    def test_known_physical_source_requires_acquisition_bindings(self):
        with self.assertRaisesRegex(ValueError, "acquisition_bindings"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the water from 100 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        source_status="known",
                        source_description="100 meters ahead",
                    ),
                )
            )

    def test_physical_source_summary_cannot_supply_unbound_numeric_fact(self):
        with self.assertRaisesRegex(ValueError, "numeric facts.*acquisition_bindings"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the water from 100 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        source_status="known",
                        source_description="100 meters ahead",
                        source_bindings=[binding("direction", "direction", "ahead")],
                    ),
                )
            )

    def test_information_resource_has_one_query_scope_surface(self):
        information = resource_responsibility(
            kind="information",
            description="Chongqing weather tonight",
            quantity="",
            attributes=[
                binding("location", "location", "Chongqing"),
                binding("time", "time", "tonight"),
            ],
            source_status="provider_resolved",
        )
        parsed = GoalAssociationModelGoal.model_validate(
            goal("Check Chongqing weather tonight.", "capability_work", resource=information)
        )
        resource = parsed.resource_responsibility
        self.assertEqual(resource.kind, "information")
        self.assertEqual([item.name for item in resource.query_scope], ["location", "time"])
        self.assertFalse(hasattr(resource.source, "bindings"))

    def test_information_query_scope_cannot_recreate_source_authority(self):
        with self.assertRaisesRegex(ValueError, "query_scope cannot duplicate"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Check the named source.",
                    "capability_work",
                    resource=resource_responsibility(
                        kind="information",
                        description="named-source result",
                        quantity="",
                        attributes=[binding("source", "information_source", "BBC")],
                        source_status="provider_resolved",
                    ),
                )
            )

    def test_information_source_has_no_arbitrary_binding_surface(self):
        payload = resource_responsibility(
            kind="information",
            description="weather",
            quantity="",
            attributes=[binding("location", "location", "重庆")],
            source_status="provider_resolved",
        )
        payload["source"]["bindings"] = [binding("location", "location", "重庆")]
        with self.assertRaises(ValidationError):
            GoalAssociationModelGoal.model_validate(
                goal("Check 重庆 weather.", "capability_work", resource=payload)
            )

    def test_resource_kind_requires_its_semantic_completion_mode(self):
        information = resource_responsibility(
            kind="information",
            description="tonight's Chongqing weather",
            quantity="",
            attributes=[binding("location", "location", "Chongqing")],
            source_status="provider_resolved",
        )
        with self.assertRaisesRegex(ValueError, "output_mode=capability_work"):
            GoalAssociationModelGoal.model_validate(
                goal("Check tonight's weather.", "speech", resource=information)
            )

        parsed = GoalAssociationModelGoal.model_validate(
            goal("Check tonight's weather.", "capability_work", resource=information)
        )
        self.assertEqual(parsed.output_mode, "capability_work")

    def test_information_resource_requires_typed_query_scope_not_description_only(self):
        information = resource_responsibility(
            kind="information",
            description="Chongqing current weather",
            quantity="",
            source_status="provider_resolved",
        )
        with self.assertRaisesRegex(ValueError, "query_scope"):
            GoalAssociationModelGoal.model_validate(
                goal("Check Chongqing weather.", "capability_work", resource=information)
            )

    def test_vocal_goal_cannot_claim_resource_authority(self):
        with self.assertRaisesRegex(ValueError, "output_mode=body_action"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Sing a song.",
                    "singing",
                    resource=resource_responsibility(),
                )
            )

    def test_resource_discriminator_is_explicitly_required(self):
        for contract in (
            GoalAssociationModelInformationResourceResponsibility,
            GoalAssociationModelPhysicalResourceResponsibility,
        ):
            schema = contract.model_json_schema()
            self.assertIn("kind", schema.get("required", []))
            self.assertNotIn("default", schema["properties"]["kind"])

        information_schema = (
            GoalAssociationModelInformationResourceResponsibility.model_json_schema()
        )
        self.assertIn("information_domain", information_schema["required"])
        self.assertNotIn(
            "default",
            information_schema["properties"]["information_domain"],
        )

        physical_schema = (
            GoalAssociationModelPhysicalResourceResponsibility.model_json_schema()
        )
        self.assertIn("delivery_mode", physical_schema.get("required", []))
        self.assertNotIn(
            "default",
            physical_schema["properties"]["delivery_mode"],
        )

    def test_resource_and_coverage_invariants_are_in_decoder_schemas(self):
        goal_schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_refs=["r1"],
        )
        Draft202012Validator.check_schema(goal_schema)
        goal_validator = Draft202012Validator(goal_schema)

        weather = create_goals(
            goal(
                "Check tonight's Chongqing weather.",
                "speech",
                resource=resource_responsibility(
                    kind="information",
                    description="tonight's Chongqing weather",
                    quantity="",
                    attributes=[binding("location", "location", "Chongqing")],
                    source_status="provider_resolved",
                ),
            )
        )
        weather.update(
            referent_updates=[],
            resolved_references=[],
        )
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather["new_goals"][0]["output_mode"] = "capability_work"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather["new_goals"][0]["bindings"] = [
            binding("location", "location", "Chongqing")
        ]
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather["new_goals"][0]["bindings"] = []

        weather_scope = weather["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ]
        weather_scope.append(binding("time", "day_part", "daytime"))
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather_scope[-1]["value"] = "day"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather_scope.append(binding("date", "date", "今天"))
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather_scope[-1]["value"] = "today"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather_scope[-1]["value"] = "2026-08-19"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather_scope[-1]["value"] = "2026-8-19"
        self.assertTrue(list(goal_validator.iter_errors(weather)))

        bounded_goal_schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=2,
            responsibility_refs=["r1", "r2"],
            responsibility_output_modes={"r1": "body_action", "r2": "singing"},
        )
        bounded_goal_validator = Draft202012Validator(bounded_goal_schema)
        for branch in bounded_goal_schema["$defs"]["GoalAssociationModelGoal"][
            "oneOf"
        ]:
            self.assertIn("description", branch["required"])
            self.assertIn("output_mode", branch["required"])
            self.assertIn("bindings", branch["required"])
            self.assertIn("resource_responsibility", branch["required"])
            self.assertIn("description", branch["properties"])
            self.assertIn("bindings", branch["properties"])
            self.assertIn("resource_responsibility", branch["properties"])
        goal_branches = bounded_goal_schema["$defs"][
            "GoalAssociationModelGoal"
        ]["oneOf"]
        body_branches = [
            branch
            for branch in goal_branches
            if branch["properties"]["source_responsibility_refs"].get("const")
            == ["r1"]
        ]
        self.assertEqual(len(body_branches), 2)
        self.assertEqual(
            body_branches[0]["properties"]["resource_responsibility"],
            {"type": "null"},
        )
        self.assertEqual(
            body_branches[1]["properties"]["resource_responsibility"]["$ref"],
            "#/$defs/GoalAssociationModelPhysicalResourceResponsibility",
        )
        self.assertEqual(
            body_branches[1]["properties"]["bindings"]["maxItems"],
            0,
        )
        vocal_branches = [
            branch
            for branch in goal_branches
            if branch["properties"]["source_responsibility_refs"].get("const")
            == ["r2"]
        ]
        self.assertEqual(len(vocal_branches), 1)
        self.assertEqual(
            vocal_branches[0]["properties"]["resource_responsibility"],
            {"type": "null"},
        )
        fresh_evidence_schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["weather"],
            responsibility_output_modes={"weather": "capability_work"},
            responsibility_fresh_evidence_refs={"weather"},
        )
        fresh_evidence_branches = fresh_evidence_schema["$defs"][
            "GoalAssociationModelGoal"
        ]["oneOf"]
        self.assertEqual(len(fresh_evidence_branches), 1)
        self.assertEqual(
            fresh_evidence_branches[0]["properties"][
                "resource_responsibility"
            ]["$ref"],
            "#/$defs/GoalAssociationModelInformationResourceResponsibility",
        )
        two_body_actions = create_goals(
            goal("Run forward for 15 seconds.", "body_action"),
            goal("Sing.", "singing", source_responsibility_refs=["r2"]),
        )
        two_body_actions.update(
            referent_updates=[],
            resolved_references=[],
        )
        self.assertEqual(
            list(bounded_goal_validator.iter_errors(two_body_actions)),
            [],
        )
        two_body_actions["new_goals"][1]["output_mode"] = "body_action"
        self.assertTrue(list(bounded_goal_validator.iter_errors(two_body_actions)))
        two_body_actions["new_goals"][1]["output_mode"] = "singing"
        three_goals = create_goals(
            *two_body_actions["new_goals"],
            goal("Say that the actions are being handled.", "speech"),
        )
        three_goals.update(
            referent_updates=[],
            resolved_references=[],
        )
        self.assertTrue(list(bounded_goal_validator.iter_errors(three_goals)))

        untyped_known_source = create_goals(
            goal(
                "Bring water from 100 meters ahead.",
                "body_action",
                resource=resource_responsibility(
                    attributes=[binding("distance", "distance", "100")],
                    source_status="known",
                    source_description="100 meters ahead",
                ),
            )
        )
        untyped_known_source.update(
            referent_updates=[],
            resolved_references=[],
        )
        self.assertTrue(list(goal_validator.iter_errors(untyped_known_source)))

        typed_physical_attribute_resource = resource_responsibility(
            description="the red bottle",
            source_status="known",
            source_bindings=[binding("source_location", "place", "the table")],
        )
        typed_physical_attribute_resource["query_scope"] = [
            binding("color", "color", "red")
        ]
        typed_physical_attribute = create_goals(
            goal(
                "Bring the red bottle from the table.",
                "body_action",
                resource=typed_physical_attribute_resource,
            )
        )
        typed_physical_attribute.update(
            referent_updates=[],
            resolved_references=[],
        )
        self.assertTrue(list(goal_validator.iter_errors(typed_physical_attribute)))

        coverage_schema = GoalAssociationResolver._coverage_certificate_response_schema(
            [
                GoalAssociationModelGoal.model_validate(
                    goal("Walk forward.", "body_action")
                )
            ]
        )
        Draft202012Validator.check_schema(coverage_schema)
        coverage_validator = Draft202012Validator(coverage_schema)
        coverage_items_schema = coverage_schema["properties"]["responsibility_items"]
        self.assertEqual(coverage_items_schema["minItems"], 1)
        covered_responsibility_branch = coverage_items_schema["items"]["oneOf"][0]
        self.assertEqual(
            covered_responsibility_branch["properties"]["role"]["const"],
            "responsibility",
        )
        self.assertEqual(
            covered_responsibility_branch["properties"]["required_goal_shape"][
                "const"
            ],
            "ordinary",
        )
        self.assertEqual(
            covered_responsibility_branch["properties"]["required_output_mode"][
                "const"
            ],
            "body_action",
        )
        supporting_items_schema = coverage_schema["properties"]["supporting_items"]
        self.assertIn(
            "Durations",
            supporting_items_schema["items"]["properties"][
                "temporal_dimensions"
            ]["description"],
        )
        self.assertIn(
            "required_information_domain",
            covered_responsibility_branch["required"],
        )
        self.assertIn(
            "required_output_mode",
            covered_responsibility_branch["required"],
        )
        constraint_only = certificate(
            coverage_item(
                "tonight",
                role="constraint",
                temporal_dimensions=["date", "day_part"],
            )
        )
        self.assertTrue(list(coverage_validator.iter_errors(constraint_only)))
        invalid_context = certificate(
            {
                "source_excerpt": "I am a little tired",
                "role": "context",
                "coverage": "missing",
                "independently_satisfiable": True,
                "candidate_goal_indices": [],
            }
        )
        self.assertTrue(list(coverage_validator.iter_errors(invalid_context)))
        valid_context = certificate(
            coverage_item(
                "help me decide",
                0,
                required_output_mode="body_action",
            ),
            coverage_item(
                "I am a little tired",
                role="context",
                independently_satisfiable=False,
            )
        )
        self.assertEqual(list(coverage_validator.iter_errors(valid_context)), [])
        recovered_context = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item("Walk forward", 0),
                {
                    "source_excerpt": "I am a little tired",
                    "role": "context",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "candidate_goal_indices": [],
                    "temporal_dimensions": [],
                    "required_goal_shape": "ordinary",
                    "required_information_domain": "none",
                    "required_output_mode": "none",
                },
            ),
            request=request("Walk forward. I am a little tired.", language="en-US"),
            goal_count=1,
            candidate_goals=[
                GoalAssociationModelGoal.model_validate(
                    goal("Walk forward.", "body_action")
                )
            ],
        )
        self.assertFalse(recovered_context.supporting_items[0].independently_satisfiable)

        source_bound_coverage_schema = (
            GoalAssociationResolver._coverage_certificate_response_schema(
                [
                    GoalAssociationModelGoal.model_validate(
                        goal("Walk forward.", "body_action")
                    )
                ],
                authoritative_turn="边跑边唱歌。",
            )
        )
        excerpt_contract = source_bound_coverage_schema["$defs"][
            "GoalResponsibilityCoverageItem"
        ]["properties"]["source_excerpt"]
        self.assertIn("边跑边唱歌", excerpt_contract["enum"])
        self.assertNotIn("边跑的唱歌", excerpt_contract["enum"])

    def test_resource_and_coverage_prompts_share_information_ownership(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        req = request(
            "I am in chongqing now, please help me check whether it will rain "
            "tonight and whether it it cold",
            language="en-US",
        )

        interpretation_prompt = resolver._build_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn(
            "a resolved place is a query_scope binding named location",
            interpretation_prompt,
        )
        self.assertIn(
            "time and requested result aspects as separate bindings",
            interpretation_prompt,
        )
        self.assertNotIn(
            "For weather, a resolved place belongs in a binding named location",
            interpretation_prompt,
        )

        coverage_prompt = resolver._build_responsibility_coverage_prompt(
            request=req,
            raw=create_goals(
                goal(
                    "Check Chongqing weather tonight.",
                    "capability_work",
                    resource=resource_responsibility(
                        kind="information",
                        description="Chongqing weather tonight",
                        quantity="",
                        attributes=[
                            binding("location", "location", "chongqing"),
                            binding("time", "time", "tonight"),
                            binding("aspects", "list", "rain, temperature"),
                        ],
                        source_status="provider_resolved",
                    ),
                )
            ),
        )
        self.assertIn(
            "Multiple aspects requested from one information result likewise remain "
            "one responsibility",
            coverage_prompt,
        )
        self.assertIn(
            "requested location, time, and result aspects are covered only by "
            "resource_responsibility.query_scope",
            coverage_prompt,
        )
        coverage_system = resolver._responsibility_coverage_system_prompt()
        self.assertIn(
            "Binding entity_type, not the arbitrary binding name",
            coverage_system,
        )
        self.assertIn(
            "one entity_type=date binding plus one entity_type=day_part binding preserves "
            "both dimensions",
            coverage_system,
        )
        self.assertIn(
            "If both typed bindings carry equivalent normalized values, mark both source "
            "constraints covered",
            coverage_prompt,
        )
        self.assertIn(
            "one role=constraint item with temporal_dimensions=date_and_day_part",
            coverage_prompt,
        )
        self.assertIn(
            "A responsibility item always uses temporal_dimensions=none",
            coverage_prompt,
        )
        self.assertIn(
            "Never return only constraints",
            coverage_prompt,
        )
        self.assertIn(
            "reject your own draft if any temporal dimension appears on a "
            "non-constraint item",
            coverage_prompt,
        )
        self.assertIn("required_goal_shape", coverage_prompt)
        self.assertIn(
            "prose, a binding name, and a day_part value never imply a missing date "
            "binding",
            coverage_system,
        )
        self.assertIn("Reference grounding is part of responsibility coverage", coverage_prompt)
        self.assertIn("silently invents a generic object", coverage_prompt)
        self.assertIn("multiple scene candidates remain plausible", coverage_prompt)

        execution_contract = resolver._build_prompt(
            request(
                "Set a reminder for later.",
                language="en-US",
            ),
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn("deferred reminder", execution_contract)
        self.assertIn("stateful capability work", execution_contract)
        self.assertIn("saying the reminder now does not complete", execution_contract)
        self.assertIn("ordinary typed Goal bindings", execution_contract)
        self.assertIn("persistent state mutations", execution_contract)
        self.assertIn("local/private/runtime source", execution_contract)
        self.assertIn("source.status=unknown", execution_contract)

    def test_unscoped_optional_referent_correction_is_dropped(self):
        normalized, dropped = (
            GoalAssociationResolver._drop_invalid_optional_referent_introductions(
                {
                    "decision": "create_goals",
                    "referent_updates": [
                        {
                            "operation": "correct",
                            "canonical_value": "Dad",
                            "target_referent_ids": [],
                        }
                    ],
                }
            )
        )

        self.assertEqual(normalized["referent_updates"], [])
        self.assertEqual(dropped[0]["reason"], "missing_target_referent_ids")

    def test_resource_semantic_binding_view_is_transient(self):
        canonical = AcquireAndDeliverResource(
            resource=ResourceDescriptor(
                kind="information",
                description="temperature reading",
                quantity="1",
                attributes={"location": binding("location", "location", "重庆")},
            ),
            source=ResourceSource(
                status="provider_resolved",
                description="",
                bindings={},
            ),
            recipient=ResourceRecipient(description="用户"),
            delivery_mode="spoken_explanation",
        )
        bindings = resource_semantic_bindings(canonical)

        self.assertEqual(set(bindings), {"location", "quantity"})
        bindings["location"]["value"] = "changed"
        self.assertEqual(
            canonical.resource.attributes["location"]["value"],
            "重庆",
        )

    def test_certificate_has_no_model_authored_verdict(self):
        parsed = GoalResponsibilityCoverageCertificate.model_validate(
            certificate(coverage_item("Blink twice.", 0))
        )
        self.assertEqual(len(parsed.items), 1)
        with self.assertRaises(ValidationError):
            GoalResponsibilityCoverageCertificate.model_validate(
                {
                    **certificate(coverage_item("Blink twice.", 0)),
                    "decision": "accept",
                }
            )

    def test_coverage_certificate_tolerates_redundant_overlapping_excerpt_evidence(self):
        parsed = GoalResponsibilityCoverageCertificate.model_validate(
            certificate(
                coverage_item("帮我们选一个", 0),
                coverage_item(
                    "帮我们选一个",
                    0,
                    role="constraint",
                    independently_satisfiable=False,
                ),
            )
        )
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "accept")
        self.assertEqual(problems, [])

    def test_representation_mismatch_rejects_state_change_as_information_resource(self):
        parsed = GoalResponsibilityCoverageCertificate.model_validate(
            certificate(
                coverage_item(
                    "Set a reminder for tomorrow morning",
                    0,
                    role="responsibility",
                    coverage="representation_mismatch",
                    independently_satisfiable=True,
                )
            )
        )
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "reject")
        self.assertIn(
            "representation_mismatch:responsibility:Set a reminder for tomorrow morning",
            problems,
        )

    def test_representation_mismatch_must_identify_the_mismatched_candidate(self):
        with self.assertRaises(ValidationError):
            GoalResponsibilityCoverageCertificate.model_validate(
                certificate(
                    coverage_item(
                        "帮我拿杯水",
                        role="responsibility",
                        coverage="representation_mismatch",
                        independently_satisfiable=True,
                    )
                )
            )

    def test_coverage_normalizes_missing_with_named_candidate_to_representation_mismatch(self):
        req = request("今天晚上有大雨吗？")
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "今天晚上有大雨吗？",
                    0,
                    coverage="missing",
                    independently_satisfiable=True,
                )
            ),
            request=req,
            goal_count=1,
        )

        self.assertEqual(parsed.items[0].coverage, "representation_mismatch")
        self.assertEqual(parsed.items[0].candidate_goal_indices, [0])
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "reject")
        self.assertIn(
            "representation_mismatch:responsibility:今天晚上有大雨吗？",
            problems,
        )

    def test_coverage_removes_only_exact_duplicate_item_noise(self):
        req = request("帮我看看现在几点。")
        item = coverage_item(
            "帮我看看现在几点。",
            0,
            required_goal_shape="information_resource",
        )
        raw = certificate(item, dict(item))

        parsed = GoalAssociationResolver._validate_coverage_certificate(
            raw,
            request=req,
            goal_count=1,
        )

        self.assertEqual(len(parsed.responsibility_items), 1)
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed,
            goal_count=1,
        )
        self.assertEqual(verdict, "accept")
        self.assertEqual(problems, [])

    def test_non_information_coverage_clears_redundant_information_domain(self):
        req = request("bring the bottle to me", language="en-US")
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "bring the bottle to me",
                    0,
                    required_goal_shape="physical_resource",
                    required_information_domain="direct_environment_perception",
                )
            ),
            request=req,
            goal_count=1,
        )

        self.assertEqual(parsed.items[0].required_goal_shape, "physical_resource")
        self.assertEqual(parsed.items[0].required_information_domain, "none")

    def test_supporting_coverage_clears_ineligible_output_mode(self):
        req = request("singing while blinking", language="en-US")
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item("singing", 0),
                coverage_item(
                    "while blinking",
                    0,
                    role="constraint",
                    required_output_mode="body_action",
                ),
            ),
            request=req,
            goal_count=1,
        )

        self.assertEqual(parsed.supporting_items[0].required_output_mode, "none")

    def test_compact_coverage_temporal_scalar_is_mechanical_transport(self):
        schema = GoalAssociationResolver._coverage_certificate_response_schema(
            [
                GoalAssociationModelGoal.model_validate(
                    goal("Walk forward for 10 seconds.", "body_action")
                )
            ],
            temporal_scalar=True,
        )
        Draft202012Validator.check_schema(schema)
        temporal = schema["$defs"]["GoalResponsibilityCoverageItem"][
            "properties"
        ]["temporal_dimensions"]
        self.assertEqual(
            temporal["enum"],
            ["none", "date", "day_part", "date_and_day_part"],
        )

        raw = certificate(
            {
                **coverage_item(
                    "Walk forward for 10 seconds.",
                    0,
                    required_output_mode="body_action",
                ),
                "temporal_dimensions": "none",
            }
        )
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            raw,
            request=request("Walk forward for 10 seconds.", language="en-US"),
            goal_count=1,
        )

        self.assertEqual(parsed.responsibility_items[0].temporal_dimensions, [])

    def test_context_coverage_clears_ineligible_goal_ownership(self):
        req = request("there is a bottle ahead; bring it", language="en-US")
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item("bring it", 0),
                coverage_item(
                    "there is a bottle ahead",
                    0,
                    role="context",
                    required_output_mode="body_action",
                ),
            ),
            request=req,
            goal_count=1,
        )

        context_item = parsed.supporting_items[0]
        self.assertEqual(context_item.candidate_goal_indices, [])
        self.assertEqual(context_item.required_output_mode, "none")

    def test_coverage_rejects_wrong_requested_output_mode(self):
        req = request("sing while moving", language="en-US")
        candidate = GoalAssociationModelGoal.model_validate(
            goal(
                "sing while moving",
                "body_action",
                bindings=[binding("activity", "activity", "singing")],
            )
        )
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "sing",
                    0,
                    required_output_mode="singing",
                )
            ),
            request=req,
            goal_count=1,
            candidate_goals=[candidate],
        )

        self.assertEqual(parsed.items[0].coverage, "representation_mismatch")
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed,
            goal_count=1,
        )
        self.assertEqual(verdict, "reject")
        self.assertIn(
            "required_output_mode:singing:responsibility:sing",
            problems,
        )

    def test_goal_candidate_must_conserve_interpreted_output_mode(self):
        req = request("sing a song", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "sing a song",
                        "bindings": {},
                        "output_mode": "singing",
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.98,
                    }
                )
            }
        )
        wrong = GoalSegmentationModelOutput.model_validate(
            create_goals(goal("Sing a song.", "body_action"))
        )

        conflicts = GoalAssociationResolver._responsibility_output_mode_conflicts(
            wrong,
            request=req,
        )

        self.assertEqual(
            conflicts,
            ["new_goals[0] source_ref=r1 expected=singing actual=body_action"],
        )

    def test_physical_resource_cannot_drop_direct_gi_acquisition_bindings_into_prose(self):
        req = request(
            "bring the bottle from 50 meters ahead",
            language="en-US",
            responsibility_outcomes=["bring the bottle to the requester"],
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "bring the bottle to the requester",
                        "bindings": {
                            "object": "bottle",
                            "distance": "50 meters",
                            "direction": "ahead",
                        },
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.98,
                    }
                )
            }
        )
        missing_source = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "Bring the bottle from 50 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        description="bottle",
                        source_status="unknown",
                    ),
                )
            )
        )

        conflicts = GoalAssociationResolver._source_grounded_binding_coverage_conflicts(
            missing_source,
            request=req,
        )

        self.assertTrue(any("missing='50 meters'" in item for item in conflicts))
        self.assertTrue(any("missing='ahead'" in item for item in conflicts))

        grounded_source = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "Bring the bottle from 50 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        description="bottle",
                        source_status="known",
                        source_description="50 meters ahead",
                        source_bindings=[
                            binding("distance", "distance", "50 meters"),
                            binding("direction", "direction", "ahead"),
                        ],
                    ),
                )
            )
        )
        self.assertEqual(
            GoalAssociationResolver._source_grounded_binding_coverage_conflicts(
                grounded_source,
                request=req,
            ),
            [],
        )

    def test_goal_description_owns_exact_action_while_bindings_own_parameters(self):
        req = request(
            "singing and blinking eyes simultaneously",
            language="en-US",
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "singing",
                        "bindings": {"action": "singing"},
                        "output_mode": "singing",
                        "completion_requires_work": True,
                        "confidence": 0.98,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "blinking eyes simultaneously",
                        "bindings": {
                            "action": "blinking eyes",
                            "simultaneously": "simultaneously",
                        },
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "confidence": 0.98,
                    },
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal("singing", "singing"),
                goal(
                    "blinking eyes simultaneously",
                    "body_action",
                    bindings=[
                        binding(
                            "simultaneously",
                            "temporal_scope",
                            "simultaneously",
                        )
                    ],
                    source_responsibility_refs=["r2"],
                ),
            )
        )

        self.assertEqual(
            GoalAssociationResolver._source_grounded_binding_coverage_conflicts(
                output,
                request=req,
            ),
            [],
        )

    def test_physical_resource_prose_cannot_hide_body_action_parameters(self):
        req = request(
            "walk ahead for 15 seconds quickly",
            language="en-US",
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "walk ahead for 15 seconds quickly",
                        "bindings": {
                            "direction": "ahead",
                            "duration": "15 seconds",
                            "speed": "quickly",
                        },
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 1.0,
                    }
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "walk ahead for 15 seconds quickly",
                    "body_action",
                    resource=resource_responsibility(
                        description="walk ahead for 15 seconds quickly",
                        source_status="known",
                        source_bindings=[
                            binding("direction", "direction", "ahead"),
                        ],
                    ),
                )
            )
        )

        self.assertEqual(
            GoalAssociationResolver._source_grounded_binding_coverage_conflicts(
                output,
                request=req,
            ),
            [
                "new_goals[0] source_refs=r1 missing='15 seconds'",
                "new_goals[0] source_refs=r1 missing='quickly'",
            ],
        )

    def test_canonical_qualitative_speed_conserves_source_speed_dimension(self):
        req = request(
            "walk ahead for 15 seconds quickly",
            language="en-US",
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "walk ahead for 15 seconds quickly",
                        "bindings": {
                            "direction": "ahead",
                            "duration": "15 seconds",
                            "speed": "quickly",
                        },
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 1.0,
                    }
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "walk ahead for 15 seconds quickly",
                    "body_action",
                    bindings=[
                        binding("direction", "direction", "ahead"),
                        binding("duration", "duration", "15 seconds"),
                        binding("speed", "speed", "quick"),
                    ],
                )
            )
        )

        self.assertEqual(
            GoalAssociationResolver._source_grounded_binding_coverage_conflicts(
                output,
                request=req,
            ),
            [],
        )

    def test_named_canonical_binding_rejects_generic_entity_type(self):
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "Bring the milk from about 50 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        description="a bottle of milk",
                        source_status="known",
                        source_bindings=[
                            binding("distance", "measurement", "about 50 meters"),
                        ],
                    ),
                )
            )
        )

        self.assertEqual(
            GoalAssociationResolver._binding_semantic_contract_conflicts(output),
            ["new_goals[0].bindings[0]=distance/measurement"],
        )

    def test_physical_resource_source_rejects_body_action_parameters(self):
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "Walk ahead for 15 seconds quickly.",
                    "body_action",
                    resource=resource_responsibility(
                        description="Walk ahead for 15 seconds quickly",
                        source_status="known",
                        source_bindings=[
                            binding("direction", "direction", "ahead"),
                            binding("duration", "duration", "15 seconds"),
                            binding("speed", "speed", "quick"),
                        ],
                    ),
                )
            )
        )

        conflicts = (
            GoalAssociationResolver._resource_source_binding_contract_conflicts(
                output
            )
        )
        self.assertEqual(
            conflicts,
            [
                "new_goals[0].resource_responsibility."
                "source.acquisition_bindings[duration]="
                "non_source_semantics(duration/duration)",
                "new_goals[0].resource_responsibility."
                "source.acquisition_bindings[speed]="
                "non_source_semantics(speed/speed)",
            ],
        )

    def test_verbatim_relative_location_is_valid_location_provenance(self):
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "Bring the milk from ahead of you.",
                    "body_action",
                    resource=resource_responsibility(
                        description="a bottle of milk",
                        source_status="known",
                        source_bindings=[
                            binding("location", "relative_location", "ahead of you"),
                        ],
                    ),
                )
            )
        )

        self.assertEqual(
            GoalAssociationResolver._non_verbatim_explicit_location_bindings(
                output,
                request=request("bring the milk from ahead of you", language="en-US"),
            ),
            [],
        )

    def test_location_name_cannot_hide_non_location_query_semantics(self):
        payload = create_goals(
            goal(
                "Determine the current local time.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="current local time",
                    attributes=[
                        binding(
                            "location",
                            "unspecified location for time query",
                            "帮我看看现在几点",
                        )
                    ],
                ),
            )
        )
        payload.update(referent_updates=[], resolved_references=[])
        model_output = GoalSegmentationModelOutput.model_validate(payload)

        rejected = GoalAssociationResolver._non_verbatim_explicit_location_bindings(
            model_output,
            request=request("帮我看看现在几点。"),
        )

        self.assertEqual(len(rejected), 1)
        self.assertIn("non_location_semantics", rejected[0])

    def test_grounded_generic_location_type_is_mechanically_normalized(self):
        payload = create_goals(
            goal(
                "Determine whether someone is outside.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="direct_environment_perception",
                    description="whether someone is outside",
                    attributes=[binding("location", "string", "外面")],
                ),
            )
        )

        normalized, repairs = (
            GoalAssociationResolver._normalize_grounded_generic_location_types(
                payload,
                request=request("你觉得外面有人吗？"),
            )
        )

        location = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ][0]
        self.assertEqual(location["entity_type"], "place")
        self.assertEqual(location["value"], "外面")
        self.assertEqual(repairs[0]["from"], "string")
        self.assertTrue(repairs[0]["value_unchanged"])

    def test_coverage_reconciles_self_contradictory_typed_temporal_constraint(self):
        req = request("今天晚上重庆会不会下大雨啊？")
        candidate = GoalAssociationModelGoal.model_validate(
            goal(
                "Determine whether it will rain heavily in Chongqing tonight",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="Chongqing heavy rain tonight",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("date", "date", "today"),
                        binding("day_part", "day_part", "night"),
                        binding("weather_aspect", "weather_attribute", "heavy rain"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        raw = certificate(
            coverage_item(
                "重庆会不会下大雨",
                0,
                independently_satisfiable=False,
                required_goal_shape="information_resource",
            ),
            coverage_item(
                "今天",
                0,
                coverage="representation_mismatch",
                independently_satisfiable=False,
                required_output_mode="capability_work",
            ),
            coverage_item(
                "晚上",
                0,
                coverage="representation_mismatch",
                independently_satisfiable=False,
                required_output_mode="capability_work",
            ),
            coverage_item(
                "今天",
                0,
                role="constraint",
                temporal_dimensions=["date"],
            ),
            coverage_item(
                "晚上",
                0,
                role="constraint",
                coverage="representation_mismatch",
                temporal_dimensions=["day_part"],
            ),
        )

        parsed = GoalAssociationResolver._validate_coverage_certificate(
            raw,
            request=req,
            goal_count=1,
            candidate_goals=[candidate],
        )

        self.assertEqual(
            [item.source_excerpt for item in parsed.responsibility_items],
            ["重庆会不会下大雨"],
        )
        self.assertEqual(
            [item.coverage for item in parsed.supporting_items],
            ["covered", "covered"],
        )
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "accept")
        self.assertEqual(problems, [])

    def test_temporal_mismatch_still_rejects_when_typed_dimension_is_absent(self):
        req = request("今天晚上重庆会不会下大雨啊？")
        candidate = GoalAssociationModelGoal.model_validate(
            goal(
                "Determine whether it will rain heavily in Chongqing tonight",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="Chongqing heavy rain tonight",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("date", "date", "today"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )

        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "重庆会不会下大雨",
                    0,
                    independently_satisfiable=True,
                    required_goal_shape="information_resource",
                ),
                coverage_item(
                    "晚上",
                    0,
                    role="constraint",
                    coverage="representation_mismatch",
                    temporal_dimensions=["day_part"],
                ),
            ),
            request=req,
            goal_count=1,
            candidate_goals=[candidate],
        )

        self.assertEqual(parsed.supporting_items[0].coverage, "representation_mismatch")
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "reject")
        self.assertIn("representation_mismatch:constraint:晚上", problems)

    def test_coverage_typed_claims_reject_missing_date_and_information_resource(self):
        req = request("今晚重庆会不会下雨哦？")
        candidate = GoalAssociationModelGoal.model_validate(
            goal(
                "determine whether it will rain in Chongqing tonight",
                "capability_work",
                bindings=[
                    binding("location", "location", "重庆"),
                    binding("time", "day_part", "night"),
                ],
            )
        )
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "今晚",
                    0,
                    role="constraint",
                    independently_satisfiable=False,
                    temporal_dimensions=["date", "day_part"],
                ),
                coverage_item(
                    "重庆会不会下雨",
                    0,
                    required_goal_shape="information_resource",
                ),
            ),
            request=req,
            goal_count=1,
            candidate_goals=[candidate],
        )

        self.assertEqual(
            [item.coverage for item in parsed.items],
            ["representation_mismatch", "representation_mismatch"],
        )
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed, goal_count=1
        )
        self.assertEqual(verdict, "reject")
        self.assertIn("representation_mismatch:constraint:今晚", problems)
        self.assertIn(
            "representation_mismatch:responsibility:重庆会不会下雨",
            problems,
        )
        self.assertIn(
            "temporal_dimensions:date,day_part:constraint:今晚",
            problems,
        )
        self.assertIn(
            "required_goal_shape:information_resource:responsibility:重庆会不会下雨",
            problems,
        )

    def test_coverage_rejects_wrong_information_domain(self):
        req = request("你觉得外面有人吗？")
        candidate = GoalAssociationModelGoal.model_validate(
            goal(
                "Determine whether someone is outside.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="whether someone is outside",
                    attributes=[binding("location", "place", "外面")],
                ),
            )
        )

        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "外面有人吗",
                    0,
                    required_goal_shape="information_resource",
                    required_information_domain="direct_environment_perception",
                )
            ),
            request=req,
            goal_count=1,
            candidate_goals=[candidate],
        )

        self.assertEqual(parsed.items[0].coverage, "representation_mismatch")
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed,
            goal_count=1,
        )
        self.assertEqual(verdict, "reject")
        self.assertIn(
            "required_information_domain:direct_environment_perception:"
            "responsibility:外面有人吗",
            problems,
        )

    def test_typed_coverage_feedback_repairs_bundle_goal_shape_once(self):
        initial = create_goals(
            goal(
                "determine whether it will rain in Chongqing tonight",
                "capability_work",
                bindings=[
                    binding("location", "location", "重庆"),
                    binding("time", "day_part", "night"),
                ],
            )
        )
        rejected_coverage = certificate(
            coverage_item(
                "今晚",
                0,
                role="constraint",
                independently_satisfiable=False,
                temporal_dimensions=["date", "day_part"],
            ),
            coverage_item(
                "重庆",
                0,
                role="constraint",
                independently_satisfiable=False,
            ),
            coverage_item(
                "会不会下雨",
                0,
                required_goal_shape="information_resource",
            ),
            coverage_item("哦", role="framing", independently_satisfiable=False),
        )
        corrected = create_goals(
            goal(
                "determine whether it will rain in Chongqing tonight",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="重庆今晚降雨情况",
                    attributes=[
                        binding("location", "location", "重庆"),
                        binding("date", "date", "today"),
                        binding("day_part", "day_part", "night"),
                        binding("requested_aspect", "weather_aspect", "rain"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        accepted_coverage = certificate(
            coverage_item(
                "今晚",
                0,
                role="constraint",
                independently_satisfiable=False,
                temporal_dimensions=["date", "day_part"],
            ),
            coverage_item(
                "重庆",
                0,
                role="constraint",
                independently_satisfiable=False,
            ),
            coverage_item(
                "会不会下雨",
                0,
                required_goal_shape="information_resource",
            ),
            coverage_item("哦", role="framing", independently_satisfiable=False),
        )
        ollama = ScriptedOllama(
            [initial, rejected_coverage, corrected, accepted_coverage]
        )
        req = request("今晚重庆会不会下雨哦？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "determine whether it will rain in Chongqing tonight",
                        "bindings": {"location": "重庆", "time": "tonight"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                )
            }
        )

        result = asyncio.run(GoalAssociationResolver(ollama).resolve(req))

        self.assertEqual(result.resolution_status, "resolved")
        resource = result.new_goals[0].resource_responsibility.resource
        self.assertEqual(resource.attributes["date"]["value"], "today")
        self.assertEqual(resource.attributes["day_part"]["value"], "night")
        fresh_prompt = str(ollama.prompts[2][0])
        self.assertIn(
            "required_goal_shape:information_resource:responsibility:会不会下雨",
            fresh_prompt,
        )
        self.assertIn(
            "temporal_dimensions:date,day_part:constraint:今晚",
            fresh_prompt,
        )
        self.assertEqual(
            [kwargs["prompt_family"] for _, kwargs in ollama.prompts],
            [
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_coverage_keeps_provisional_owner_for_gi_unresolved_meaning(self):
        req = request(
            "把那个拿过来",
            interpretation_unresolved=["那个 refers to more than one object"],
        )
        parsed = GoalAssociationResolver._validate_coverage_certificate(
            certificate(
                coverage_item(
                    "那个",
                    0,
                    coverage="clarification_required",
                    independently_satisfiable=True,
                )
            ),
            request=req,
            goal_count=1,
        )

        self.assertEqual(parsed.items[0].coverage, "clarification_required")
        self.assertEqual(parsed.items[0].candidate_goal_indices, [0])
        verdict, problems = GoalAssociationResolver._coverage_verdict(
            parsed,
            goal_count=1,
        )
        self.assertEqual(verdict, "accept")
        self.assertEqual(problems, [])

    def test_goal_association_projection_omits_fast_planner_response_wording(self):
        req = request("今天晚上有大雨吗？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
{
                        "local_ref": "weather_1",
                        "outcome": "确认今晚是否有大雨",
                        "bindings": {"precipitation_severity": "heavy"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                ),
                "context": {
                    **req.context,
                    "fast_planner_advance": {
                        "covered_responsibility_refs": ["weather_1"],
                        "continuations": ["goal_association"],
                        "immediate_vocal_activity": {
                            "activity_id": "vocal_1",
                            "role": "progress",
                            "response_text": "这句 Planner 文案绝不能进入 GA。",
                            "source_responsibility_refs": ["weather_1"],
                        },
                        "reason_summary": "Planner HOW, not Goal meaning.",
                        "unresolved": ["not_goal_meaning"],
                    },
                }
            }
        )
        prompt = GoalAssociationResolver(FakeOllama({}))._build_prompt(
            req, [], output_type=GoalSegmentationModelOutput
        )

        self.assertNotIn("这句 Planner 文案绝不能进入 GA。", prompt)
        self.assertNotIn("Planner HOW, not Goal meaning.", prompt)
        self.assertNotIn('"activity_id":"vocal_1"', prompt)
        self.assertNotIn('"role":"progress"', prompt)
        self.assertIn("authored concurrently", prompt)
        self.assertIn("must never become, justify, or be copied", prompt)

    def test_fresh_reinterpretation_keeps_fast_responsibility_evidence(self):
        req = request("你能往前走个100米，那边有个水瓶，帮我拿杯水可以吗？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
{
                        "local_ref": "responsibility-1",
                        "outcome": "拿一杯水",
                        "bindings": {
                            "resource": "水",
                            "source": "水瓶",
                            "recipient": "我",
                        },
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                ),
                "context": dict(req.context),
            }
        )
        prompt = GoalAssociationResolver(FakeOllama({}))._build_fresh_interpretation_prompt(
            request=req,
            candidate_goals=[],
            output_type=GoalSegmentationModelOutput,
            problems=["unjustified_goal_indices:1"],
        )
        self.assertIn('"outcome":"拿一杯水"', prompt)
        self.assertIn("Do not discard independently supported current-turn Responsibility evidence", prompt)
        self.assertIn("Removing an unjustified sibling Goal never permits dropping", prompt)

    def test_coverage_prompt_distinguishes_preferences_state_changes_and_information(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        prompt = resolver._build_responsibility_coverage_prompt(
            request=request("I want noodles, my sister wants rice; help us choose one.", language="en-US"),
            raw=create_goals(goal("Choose lunch fairly.", "speech")),
        )
        self.assertIn("Stated preferences", prompt)
        self.assertIn("changes what counts as a valid decision", prompt)
        self.assertIn("must be role=constraint", prompt)
        self.assertIn("state mutation or deferred effect", prompt)
        self.assertIn("representation_mismatch", prompt)
        self.assertIn("drops or generalizes a material qualifier", prompt)
        self.assertIn("candidate_goal_indices must be empty", prompt)

    def test_resource_binding_duplicates_are_mechanically_dropped(self):
        resource = resource_responsibility(
            kind="information",
            description="package status",
            attributes=[binding("tracking_number", "identifier", "ABC123")],
            source_status="provider_resolved",
        )
        raw = create_goals(
            goal(
                "Check package status.",
                "capability_work",
                bindings=list(resource["query_scope"]),
                resource=resource,
            )
        )

        normalized, dropped = (
            GoalAssociationResolver._drop_inactive_resource_bindings(raw)
        )

        self.assertEqual(normalized["new_goals"][0]["bindings"], [])
        self.assertEqual(dropped[0]["path"], "new_goals[0].bindings")
        self.assertEqual(dropped[0]["migrated_count"], 0)

    def test_nonduplicate_inactive_resource_bindings_move_to_active_owner(self):
        resource = resource_responsibility(
            kind="information",
            description="package status",
            attributes=[binding("tracking_number", "identifier", "ABC123")],
            source_status="provider_resolved",
        )
        raw = create_goals(
            goal(
                "Check package status.",
                "capability_work",
                bindings=[binding("carrier", "organization", "ParcelCo")],
                resource=resource,
            )
        )

        normalized, dropped = (
            GoalAssociationResolver._drop_inactive_resource_bindings(raw)
        )

        self.assertEqual(normalized["new_goals"][0]["bindings"], [])
        self.assertEqual(dropped[0]["binding_count"], 1)
        self.assertEqual(dropped[0]["migrated_count"], 1)
        self.assertEqual(
            normalized["new_goals"][0]["resource_responsibility"]["query_scope"][-1],
            binding("carrier", "organization", "ParcelCo"),
        )

    def test_unknown_physical_source_grounding_is_cleared_for_coverage_audit(self):
        raw = create_goals(
            goal(
                "Walk forward for ten seconds.",
                "body_action",
                bindings=[binding("duration", "time_duration", "10 seconds")],
                resource={
                    "kind": "physical_object",
                    "description": "walking forward",
                    "source": {
                        "status": "unknown",
                        "acquisition_bindings": [
                            binding("direction", "direction", "forward")
                        ],
                    },
                    "delivery_mode": "physical_handover",
                },
            )
        )

        normalized, dropped = (
            GoalAssociationResolver._drop_inactive_resource_bindings(raw)
        )

        candidate = normalized["new_goals"][0]
        self.assertEqual(candidate["bindings"], [])
        self.assertNotIn(
            "acquisition_bindings",
            candidate["resource_responsibility"]["source"],
        )
        self.assertEqual(dropped[0]["migrated_count"], 0)
        self.assertEqual(dropped[0]["inactive_acquisition_binding_count"], 1)

    def test_invalid_optional_resource_quantity_is_dropped_without_inference(self):
        raw = create_goals(
            goal(
                "Bring the bottle from ahead.",
                "body_action",
                resource=resource_responsibility(
                    description="bottle",
                    quantity=",",
                    source_status="known",
                    source_description="ahead",
                    source_bindings=[binding("direction", "direction", "ahead")],
                ),
            )
        )

        normalized, dropped = (
            GoalAssociationResolver._drop_invalid_optional_resource_quantities(raw)
        )

        resource = normalized["new_goals"][0]["resource_responsibility"]
        self.assertNotIn("quantity", resource)
        self.assertEqual(dropped[0]["reason"], "invalid_optional_quantity_scalar")

    def test_missing_goal_description_copies_exact_source_outcome_only(self):
        req = request("sing while moving", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "sing",
                        "outcome": "sing while moving",
                        "bindings": {},
                        "output_mode": "singing",
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 0.98,
                    }
                )
            }
        )
        raw = create_goals(goal("discarded", "singing", source_responsibility_refs=["sing"]))
        raw["new_goals"][0].pop("description")

        normalized, recovered = (
            GoalAssociationResolver._restore_missing_goal_descriptions(
                raw,
                request=req,
            )
        )

        self.assertEqual(
            normalized["new_goals"][0]["description"],
            "sing while moving",
        )
        self.assertEqual(recovered[0]["source_responsibility_ref"], "sing")
        self.assertTrue(recovered[0]["semantic_value_unchanged"])

        ambiguous = copy.deepcopy(raw)
        ambiguous["new_goals"][0]["source_responsibility_refs"] = ["sing", "other"]
        unchanged, recovered = (
            GoalAssociationResolver._restore_missing_goal_descriptions(
                ambiguous,
                request=req,
            )
        )
        self.assertNotIn("description", unchanged["new_goals"][0])
        self.assertEqual(recovered, [])

    def test_fresh_interpretation_explains_ordinary_effect_shape(self):
        prompt = GoalAssociationResolver(FakeOllama({}))._build_fresh_interpretation_prompt(
            request=request("你往前走 10 秒。"),
            candidate_goals=[],
            output_type=GoalSegmentationModelOutput,
            problems=["required_goal_shape:ordinary:responsibility:你往前走 10 秒"],
        )

        self.assertIn("required_goal_shape:ordinary", prompt)
        self.assertIn("must have no resource_responsibility", prompt)
        self.assertIn("body motion, locomotion", prompt)
        self.assertIn("top-level semantic bindings", prompt)

    def test_fresh_interpretation_requires_known_physical_source_grounding(self):
        prompt = GoalAssociationResolver(FakeOllama({}))._build_fresh_interpretation_prompt(
            request=request(
                "bring the bottle from 50 meters ahead",
                language="en-US",
            ),
            candidate_goals=[],
            output_type=GoalSegmentationModelOutput,
            problems=[
                "missing_source_grounded_binding=new_goals[0] missing='50 meters'",
                "missing_source_grounded_binding=new_goals[0] missing='ahead'",
            ],
        )

        self.assertIn("source.status=known", prompt)
        self.assertIn("source.acquisition_bindings", prompt)
        self.assertIn("unknown is not a placeholder", prompt)

    def test_unentailed_resource_query_location_is_dropped_without_replacement(self):
        raw = create_goals(
            goal(
                "Report the current local time.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="current local time",
                    attributes=[
                        binding("time", "time", "now"),
                        binding("location", "unspecified", "current location"),
                    ],
                    source_status="unknown",
                ),
            )
        )
        req = request(
            "帮我看看现在几点。",
            language="zh-CN",
        )
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "determine the current local time",
                        "bindings": {"time": "now"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                )
            }
        )

        normalized, dropped = (
            GoalAssociationResolver._drop_ungrounded_resource_query_locations(
                raw,
                request=req,
            )
        )

        query_scope = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ]
        self.assertEqual([item["name"] for item in query_scope], ["time"])
        self.assertEqual(dropped[0]["value"], "current location")

    def test_goal_prompts_distinguish_body_action_from_physical_resource(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        req = request(
            "Run forward for 15 seconds while singing.",
            language="en-US",
            responsibility_outcomes=[
                "run forward for 15 seconds",
                "sing while running",
            ],
        )
        primary_prompt = resolver._build_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        coverage_system = resolver._responsibility_coverage_system_prompt()

        self.assertIn("distinct concrete object", primary_prompt)
        self.assertIn("non-resource body_action Goals", primary_prompt)
        self.assertIn("Responsibility conservation is strict", primary_prompt)
        self.assertIn("physical resource", coverage_system)
        self.assertIn("coverage=representation_mismatch", coverage_system)
        self.assertIn(
            "Coordination grammar never demotes a positive effect to a constraint",
            coverage_system,
        )
        self.assertIn(
            "cross-check the JSON against reason_summary",
            coverage_system,
        )

        coverage_prompt = resolver._build_responsibility_coverage_prompt(
            request=req,
            raw=create_goals(
                goal("run forward for 15 seconds", "body_action"),
                goal(
                    "sing while running",
                    "singing",
                    source_responsibility_refs=["r2"],
                ),
            ),
        )
        self.assertIn(
            "each positive effect remains in responsibility_items",
            coverage_prompt,
        )
        self.assertIn(
            "each positive effect entailed by the final turn needs a "
            "role=responsibility owner",
            coverage_prompt,
        )
        self.assertIn("Authoritative Responsibility cross-check list", coverage_prompt)
        self.assertIn('"local_ref":"r2"', coverage_prompt)
        self.assertIn(
            "The structured arrays, role, and coverage must express the same "
            "conclusion as reason_summary",
            coverage_prompt,
        )

    def test_no_candidate_segmentation_prompt_fits_qualified_8k_preflight(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        req = request("你往前走 10 秒。")

        layered = resolver._layered_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        input_chars = len(layered.render()) + len(
            resolver._system_prompt(GoalSegmentationModelOutput)
        )

        # The deployed fail-closed estimate is two characters per token.  An
        # 8,192-token request reserving 512 output and 2,048 safety tokens may
        # therefore admit at most 11,264 input characters.
        self.assertLessEqual(input_chars, 11_264)
        prompt = layered.render()
        self.assertIn("Responsibility conservation is strict", prompt)
        self.assertIn("distinct concrete object", prompt)
        self.assertIn("non-resource body_action Goals", prompt)
        self.assertIn("FINAL AUTHORITATIVE USER TURN", prompt)

        coverage_prompt = resolver._build_responsibility_coverage_prompt(
            request=req,
            raw=create_goals(
                goal(
                    "move forward for 10 seconds",
                    "body_action",
                    bindings=[
                        binding("distance_duration", "duration", "10 秒")
                    ],
                )
            ),
        )
        coverage_input_chars = len(coverage_prompt) + len(
            resolver._responsibility_coverage_system_prompt()
        )
        self.assertLessEqual(coverage_input_chars, 11_264)
        self.assertIn("Duration is never a second outcome", coverage_prompt)
        self.assertIn(
            "a constraint belongs on the same candidate as the responsibility",
            coverage_prompt,
        )
        self.assertIn(
            "typed bindings as authoritative candidate evidence",
            coverage_prompt,
        )
        self.assertIn(
            "do not call it a representation mismatch merely because the modifier",
            resolver._responsibility_coverage_system_prompt(),
        )

    def test_existing_goal_association_prompt_fits_qualified_8k_preflight(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        req = request(
            "刚才那个事情继续。",
            active_goals=[active_goal("goal-walk", "往前走十秒")],
        )
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "continue moving forward for ten seconds",
                        "bindings": {
                            "direction": "forward",
                            "distance_duration": "10 秒",
                        },
                        "output_mode": "body_action",
                        "relationship": "continue",
                        "target_goal_ids": ["goal-walk"],
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": False,
                        "confidence": 1.0,
                    }
                ),
                "context": {
                    **req.context,
                    "history": [
                        {
                            "role": "user",
                            "text": "你往前走 10 秒。",
                            "metadata": {
                                "turn_envelope": "runtime transport must not leak"
                            },
                        },
                        {
                            "role": "assistant",
                            "text": "好，我这就往前走十秒。",
                        },
                    ],
                },
            }
        )
        candidates = resolver._candidate_goals(req)
        layered = resolver._layered_prompt(
            req,
            candidates,
            output_type=GoalAssociationModelOutput,
        )
        input_chars = len(layered.render()) + len(
            resolver._system_prompt(GoalAssociationModelOutput)
        )

        self.assertLessEqual(input_chars, 11_264)
        prompt = layered.render()
        self.assertIn("Verify GI relationship", prompt)
        self.assertIn('"relationship":"continue"', prompt)
        self.assertIn('"goal_id":"goal-walk"', prompt)
        self.assertIn("好，我这就往前走十秒。", prompt)
        self.assertNotIn("runtime transport must not leak", prompt)
        self.assertNotIn("Owner-approved Personality Expression JSON", prompt)

        schema = resolver._response_schema(
            GoalAssociationModelOutput,
            candidates,
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={
                "r1": {"direction": "forward", "distance_duration": "10 秒"}
            },
        )
        association_schema = schema["$defs"]["GoalAssociationModelAssociation"]
        self.assertIn("confidence", association_schema["required"])
        self.assertIn("target_goal_ids", association_schema["required"])



class GoalAssociationTransactionTests(unittest.TestCase):
    def _resolve(self, ollama, req: CognitiveWorkRequest) -> GoalAssociationResolution:
        return asyncio.run(GoalAssociationResolver(ollama).resolve(req))

    def assert_transaction(
        self,
        result: GoalAssociationResolution,
        ollama: ScriptedOllama | FakeOllama,
        *,
        terminal: str,
        families: list[str],
    ) -> None:
        transaction = result.metadata["goal_semantic_transaction"]
        self.assertEqual(result.resolution_status, terminal)
        self.assertEqual(transaction["terminal_state"], terminal if terminal == "fail_closed" else "commit")
        self.assertEqual(transaction["logical_invocation_count"], len(families))
        self.assertEqual(transaction["logical_invocation_budget"], 5)
        self.assertEqual(transaction["prompt_families"], families)
        self.assertEqual(
            [kwargs["prompt_family"] for _, kwargs in ollama.prompts],
            families,
        )

    def test_weather_material_modifier_and_planner_progress_recover_to_one_goal(self):
        req = request("你好，我在重庆，今天晚上有大雨吗？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
{
                        "local_ref": "weather_1",
                        # Simulate the retained live GI defect: the fast proposal
                        # generalized 大雨 to rain. GA coverage must not commit it.
                        "outcome": "确认重庆今晚是否下雨",
                        "bindings": {"location": "重庆", "time": "今天晚上"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                ),
                "context": {
                    **req.context,
                    "fast_planner_advance": {
                        "covered_responsibility_refs": ["weather_1"],
                        "continuations": ["goal_association"],
                        "immediate_vocal_activity": {
                            "activity_id": "vocal_1",
                            "role": "progress",
                            "response_text": "我看看今晚会不会有大雨～",
                            "source_responsibility_refs": ["weather_1"],
                        },
                        "confidence": 0.95,
                    },
                }
            }
        )
        initial = create_goals(
            goal(
                "Confirm whether it rains in Chongqing tonight.",
                "capability_work",
                source_responsibility_refs=["weather_1"],
                resource=resource_responsibility(
                    kind="information",
                    description="Chongqing rain tonight",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("time", "day_part", "evening"),
                    ],
                    source_status="provider_resolved",
                ),
            ),
        )
        rejected_coverage = certificate(
            coverage_item(
                "你好", role="framing", independently_satisfiable=False
            ),
            coverage_item(
                "我在重庆", role="context", independently_satisfiable=False
            ),
            # Retained live malformed shape: missing plus candidate index.
            coverage_item(
                "今天晚上有大雨吗？",
                0,
                coverage="missing",
                independently_satisfiable=True,
                required_goal_shape="information_resource",
            ),
        )
        corrected = create_goals(
            goal(
                "确认重庆今天晚上是否有大雨。",
                "capability_work",
                source_responsibility_refs=["weather_1"],
                resource=resource_responsibility(
                    kind="information",
                    description="重庆今晚大雨情况",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("date", "date", "today"),
                        binding("time", "day_part", "evening"),
                        binding(
                            "precipitation_severity",
                            "severity",
                            "heavy",
                        ),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        final_coverage = certificate(
            coverage_item(
                "你好", role="framing", independently_satisfiable=False
            ),
            coverage_item(
                "我在重庆", role="context", independently_satisfiable=False
            ),
            coverage_item(
                "今天晚上有大雨吗？",
                0,
                required_goal_shape="information_resource",
            ),
        )
        ollama = ScriptedOllama(
            [initial, rejected_coverage, corrected, final_coverage]
        )

        result = self._resolve(ollama, req)

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.new_goals), 1)
        resource = result.new_goals[0].resource_responsibility.resource
        self.assertEqual(
            resource.attributes["precipitation_severity"]["value"],
            "heavy",
        )
        self.assertEqual(resource.attributes["date"]["value"], "today")
        self.assertEqual(resource.attributes["time"]["value"], "evening")
        families = [kwargs["prompt_family"] for _, kwargs in ollama.prompts]
        self.assertEqual(
            families,
            [
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )
        primary_prompt = str(ollama.prompts[0][0])
        self.assertNotIn("我看看今晚会不会有大雨～", primary_prompt)
        self.assertIn("emit separate query_scope bindings for both", primary_prompt)
        coverage_prompt = str(ollama.prompts[1][0])
        self.assertIn("date_and_day_part", coverage_prompt)
        self.assertIn("both typed bindings", coverage_prompt)
        fresh_prompt = str(ollama.prompts[2][0])
        self.assertIn("restore that source-grounded WHAT", fresh_prompt)
        self.assertIn("Planner Activity metadata is never a Responsibility source", fresh_prompt)

    def test_bundle_tonight_contract_repair_splits_date_and_night(self):
        invalid_primary = create_goals(
            goal(
                "确认重庆今晚是否下雨。",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="重庆今晚降雨情况",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("date", "date", "tonight"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        repaired = create_goals(
            goal(
                "确认重庆今晚是否下雨。",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="重庆今晚降雨情况",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("date", "date", "today"),
                        binding("day_part", "day_part", "night"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        accepted = certificate(
            coverage_item(
                "今晚",
                0,
                role="constraint",
                independently_satisfiable=False,
                temporal_dimensions=["date", "day_part"],
            ),
            coverage_item(
                "重庆会不会下雨",
                0,
                required_goal_shape="information_resource",
            ),
        )
        ollama = ScriptedOllama([invalid_primary, repaired, accepted])
        req = request("今晚重庆会不会下雨哦？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "确认重庆今晚是否下雨",
                        "bindings": {"location": "重庆", "time": "tonight"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                )
            }
        )

        result = self._resolve(ollama, req)

        self.assertEqual(result.resolution_status, "resolved")
        attributes = result.new_goals[0].resource_responsibility.resource.attributes
        self.assertEqual(attributes["date"]["value"], "today")
        self.assertEqual(attributes["day_part"]["value"], "night")
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.contract_repair",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_ordinary_conversation_commits_after_required_coverage(self):
        ollama = ScriptedOllama(
            [
                create_goals(goal("Acknowledge the greeting.", "speech")),
                certificate(coverage_item("Hello", 0)),
            ]
        )
        result = self._resolve(ollama, request("Hello", language="en-US"))

        self.assertEqual(len(result.new_goals), 1)
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_effectful_goal_requires_one_immutable_coverage_certificate(self):
        ollama = ScriptedOllama(
            [
                create_goals(goal("Blink twice.", "body_action")),
                certificate(coverage_item("Blink twice.", 0)),
            ]
        )
        result = self._resolve(
            ollama,
            request(
                "Blink twice.",
                language="en-US",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        self.assertNotIn("decision", result.metadata["responsibility_coverage"]["certificate"])
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_body_actions_miscast_as_physical_resources_are_reconsidered(self):
        req = request(
            "Run forward for 15 seconds, then blink.",
            language="en-US",
        )
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "Run forward for 15 seconds.",
                        "bindings": {
                            "direction": "forward",
                            "duration": "15 seconds",
                        },
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "Blink.",
                        "bindings": {"action": "blink"},
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    },
                ),
            }
        )
        mistaken = create_goals(
            goal(
                "Run forward for 15 seconds.",
                "body_action",
                resource=resource_responsibility(
                    description="forward running motion",
                    quantity="",
                ),
            ),
            goal(
                "Blink.",
                "body_action",
                source_responsibility_refs=["r2"],
                resource=resource_responsibility(
                    description="eye blinking motion",
                    quantity="",
                ),
            ),
        )
        rejected = certificate(
            coverage_item(
                "Run forward for 15 seconds",
                0,
                coverage="representation_mismatch",
            ),
            coverage_item(
                "blink",
                1,
                coverage="representation_mismatch",
            ),
        )
        corrected = create_goals(
            goal(
                "Run forward for 15 seconds.",
                "body_action",
                bindings=[
                    binding("direction", "direction", "forward"),
                    binding("duration", "duration", "15 seconds"),
                ],
            ),
            goal(
                "Blink.",
                "body_action",
                source_responsibility_refs=["r2"],
                bindings=[binding("action", "action", "blink")],
            ),
        )
        accepted = certificate(
            coverage_item("Run forward for 15 seconds", 0),
            coverage_item("blink", 1),
        )
        ollama = ScriptedOllama([mistaken, rejected, corrected, accepted])

        result = self._resolve(ollama, req)

        self.assertEqual(len(result.new_goals), 2)
        self.assertEqual(
            [item.metadata["output_mode"] for item in result.new_goals],
            ["body_action", "body_action"],
        )
        self.assertTrue(
            all(item.resource_responsibility is None for item in result.new_goals)
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_ordinary_coverage_cannot_certify_a_physical_resource_wrapper(self):
        req = request("Walk forward.", language="en-US")
        mistaken = GoalAssociationModelGoal.model_validate(
            goal(
                "Walk forward.",
                "body_action",
                resource=resource_responsibility(
                    description="walking motion",
                    quantity="",
                ),
            )
        )

        result = GoalAssociationResolver._validate_coverage_certificate(
            certificate(coverage_item("Walk forward.", 0)),
            request=req,
            goal_count=1,
            candidate_goals=[mistaken],
        )

        self.assertEqual(
            result.responsibility_items[0].coverage,
            "representation_mismatch",
        )

    def test_primary_dto_gets_exactly_one_contract_repair(self):
        invalid = create_goals(goal("Blink twice.", "invalid_mode"))
        valid = create_goals(goal("Blink twice.", "body_action"))
        ollama = ScriptedOllama(
            [invalid, valid, certificate(coverage_item("Blink twice.", 0))]
        )
        result = self._resolve(
            ollama,
            request("Blink twice.", language="en-US"),
        )

        self.assertTrue(
            result.metadata["goal_semantic_transaction"]["contract_repair_attempted"]
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.contract_repair",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_primary_cannot_drop_direct_gi_binding_into_goal_prose(self):
        missing = create_goals(
            goal("Move forward for 10 seconds.", "body_action")
        )
        rejected = certificate(
            coverage_item("Move forward for 10 seconds", 0)
        )
        reconsidered = create_goals(
            goal(
                "Move forward for 10 seconds.",
                "body_action",
                bindings=[binding("duration", "duration", "10 seconds")],
            )
        )
        accepted = certificate(coverage_item("Move forward for 10 seconds", 0))
        ollama = ScriptedOllama([missing, rejected, reconsidered, accepted])
        req = request("Move forward for 10 seconds.", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "move forward for ten seconds",
                        "bindings": {"duration": "10 seconds"},
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "confidence": 0.95,
                    }
                )
            }
        )

        result = self._resolve(ollama, req)

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(
            result.new_goals[0].object["bindings"]["duration"]["value"],
            "10 seconds",
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )
        self.assertFalse(
            result.metadata["goal_semantic_transaction"]
            ["contract_repair_attempted"]
        )
        self.assertTrue(
            result.metadata["goal_semantic_transaction"]
            ["semantic_reconsideration_attempted"]
        )

    def test_ungrounded_initial_coverage_excerpt_triggers_fresh_interpretation(self):
        req = request("你往前走 10 秒。").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "move forward for ten seconds",
                        "bindings": {
                            "direction": "往前",
                            "duration": "10 秒",
                        },
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "confidence": 0.95,
                    }
                )
            }
        )
        mistaken = create_goals(
            goal(
                "Move forward for ten seconds.",
                "body_action",
                resource=resource_responsibility(
                    description="forward motion",
                    quantity="",
                ),
            )
        )
        ungrounded_audit = certificate(
            coverage_item("move forward for ten seconds", 0)
        )
        corrected = create_goals(
            goal(
                "你往前走 10 秒。",
                "body_action",
                bindings=[
                    binding("direction", "direction", "往前"),
                    binding("duration", "duration", "10 秒"),
                ],
            )
        )
        final_audit = certificate(coverage_item("往前走 10 秒", 0))
        ollama = ScriptedOllama(
            [mistaken, ungrounded_audit, corrected, final_audit]
        )

        result = self._resolve(ollama, req)

        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )
        coverage = result.metadata["responsibility_coverage"]
        self.assertEqual(
            coverage["initial_certificate_contract_error"],
            "source_excerpt_not_authoritative",
        )
        self.assertEqual(coverage["final_verdict"], "accept")

    def test_ungrounded_final_coverage_excerpt_still_fails_closed(self):
        req = request("你往前走 10 秒。").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "move forward for ten seconds",
                        "bindings": {"duration": "10 秒"},
                        "output_mode": "body_action",
                        "completion_requires_work": True,
                        "confidence": 0.95,
                    }
                )
            }
        )
        corrected = create_goals(
            goal(
                "你往前走 10 秒。",
                "body_action",
                bindings=[binding("duration", "duration", "10 秒")],
            )
        )
        ungrounded_audit = certificate(
            coverage_item("move forward for ten seconds", 0)
        )
        ollama = ScriptedOllama(
            [corrected, ungrounded_audit, corrected, ungrounded_audit]
        )

        result = self._resolve(ollama, req)

        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_response_schema_requires_source_grounded_ordinary_bindings(self):
        schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={"r1": {"duration": "10 秒"}},
        )

        ordinary_branch = schema["$defs"]["GoalAssociationModelGoal"]["oneOf"][0]
        bindings = ordinary_branch["properties"]["bindings"]
        self.assertEqual(bindings["minItems"], 1)
        self.assertEqual(
            bindings["allOf"][0]["contains"]["properties"],
            {
                "name": {"const": "duration"},
                "value": {"const": "10 秒"},
            },
        )
        self.assertEqual(bindings["minItems"], 1)
        self.assertEqual(bindings["maxItems"], 1)
        self.assertEqual(
            bindings["items"]["oneOf"][0]["properties"]["value"],
            {"const": "10 秒"},
        )

    def test_invalid_contract_repair_fails_closed_without_third_call(self):
        invalid = create_goals(goal("Blink twice.", "invalid_mode"))
        ollama = ScriptedOllama([invalid, invalid])
        result = self._resolve(
            ollama,
            request("Blink twice.", language="en-US"),
        )

        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.associations, [])
        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.contract_repair",
            ],
        )

    def test_invalid_coverage_certificate_fails_closed_without_repair(self):
        ollama = ScriptedOllama(
            [
                create_goals(goal("Blink twice.", "body_action")),
                {"decision": "accept", "items": []},
            ]
        )
        result = self._resolve(
            ollama,
            request("Blink twice.", language="en-US"),
        )

        self.assertEqual(result.new_goals, [])
        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_semantic_reject_allows_one_fresh_interpretation_and_final_audit(self):
        collapsed = create_goals(
            goal(
                "Walk, blink, and sing.",
                "body_action",
                source_responsibility_refs=["r1", "r2", "r3"],
            )
        )
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("blink", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("Blink.", "body_action", source_responsibility_refs=["r2"]),
            goal("Sing.", "singing", source_responsibility_refs=["r3"]),
        )
        accepted = certificate(
            coverage_item("Walk", 0),
            coverage_item("blink", 1),
            coverage_item("sing", 2),
        )
        ollama = ScriptedOllama([collapsed, rejected, corrected, accepted])
        result = self._resolve(
            ollama,
            request(
                "Walk, blink, and sing.",
                language="en-US",
                responsibility_outcomes=["Walk.", "Blink.", "Sing."],
            ),
        )

        self.assertEqual(
            [item.metadata["output_mode"] for item in result.new_goals],
            ["body_action", "body_action", "singing"],
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_ungrounded_reference_commits_provisional_goal_for_planner(self):
        initial = create_goals(
            goal("Turn off the unresolved referenced device.", "body_action")
        )
        provisional = certificate(
            coverage_item(
                "Turn it off",
                0,
                role="responsibility",
                coverage="clarification_required",
                independently_satisfiable=False,
            )
        )
        ollama = ScriptedOllama([initial, provisional])
        result = self._resolve(
            ollama,
            request(
                "Turn it off.",
                language="en-US",
                interpretation_unresolved=["which device the user means"],
            ),
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(
            result.metadata["responsibility_coverage"]["final_verdict"],
            "accept",
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
            ],
        )

    def test_maximum_semantic_dag_is_five_calls(self):
        invalid = create_goals(
            goal(
                "Walk and sing.",
                "invalid_mode",
                source_responsibility_refs=["r1", "r2"],
            )
        )
        collapsed = create_goals(
            goal(
                "Walk and sing.",
                "body_action",
                source_responsibility_refs=["r1", "r2"],
            )
        )
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("sing.", "singing", source_responsibility_refs=["r2"]),
        )
        accepted = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 1),
        )
        ollama = ScriptedOllama(
            [invalid, collapsed, rejected, corrected, accepted]
        )
        result = self._resolve(
            ollama,
            request(
                "Walk and sing.",
                language="en-US",
                responsibility_outcomes=["Walk.", "Sing."],
            ),
        )

        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.contract_repair",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_fresh_interpretation_has_no_semantic_dto_repair(self):
        first = create_goals(
            goal(
                "Walk and sing.",
                "body_action",
                source_responsibility_refs=["r1", "r2"],
            )
        )
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        invalid_fresh = create_goals(goal("Walk.", "invalid_mode"))
        ollama = ScriptedOllama([first, rejected, invalid_fresh])
        result = self._resolve(
            ollama,
            request(
                "Walk and sing.",
                language="en-US",
                responsibility_outcomes=["Walk.", "Sing."],
            ),
        )

        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
            ],
        )

    def test_fresh_interpretation_allows_one_checked_temporal_dto_repair(self):
        first = create_goals(
            goal(
                "Check Chongqing weather this morning.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="Chongqing weather this morning",
                    attributes=[
                        binding("location", "location", "重庆"),
                        binding("date", "date", "today"),
                        binding("day_part", "day_part", "morning"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        rejected = certificate(
            coverage_item(
                "重庆会不会下雨",
                0,
                required_goal_shape="information_resource",
            ),
            coverage_item(
                "今天上午",
                0,
                role="constraint",
                coverage="representation_mismatch",
                independently_satisfiable=False,
                temporal_dimensions=["date", "day_part"],
            )
        )
        invalid_fresh = create_goals(
            goal(
                "Check Chongqing weather this morning.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="Chongqing weather this morning",
                    attributes=[
                        binding("location", "location", "重庆"),
                        binding("date", "date", "今天"),
                        binding("day_part", "day_part", "morning"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        repaired = {
            "repairs": [
                {
                    "path": (
                        "$.new_goals[0].resource_responsibility."
                        "query_scope[1].value"
                    ),
                    "value": "today",
                }
            ]
        }
        accepted = certificate(
            coverage_item(
                "今天上午重庆会不会下雨",
                0,
                required_goal_shape="information_resource",
            )
        )
        ollama = ScriptedOllama(
            [first, rejected, invalid_fresh, repaired, accepted]
        )

        result = self._resolve(
            ollama,
            request("哎，今天上午重庆会不会下雨？"),
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(
            result.new_goals[0]
            .resource_responsibility.resource.attributes["date"]["value"],
            "today",
        )
        self.assertEqual(
            result.metadata["fresh_temporal_contract_repair"],
            {
                "strategy": "bounded_same_stage_dto_repair",
                "changed_fields": [
                    "$.new_goals[0].resource_responsibility.query_scope[1].value"
                ],
                "semantic_fields_unchanged": True,
            },
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.fresh_temporal_contract_repair",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_fresh_temporal_repair_rejects_any_unauthorized_path(self):
        first = create_goals(
            goal(
                "Check Chongqing weather this morning.",
                "capability_work",
                bindings=[binding("date", "date", "today")],
            )
        )
        rejected = certificate(
            coverage_item("重庆会不会下雨", 0),
            coverage_item(
                "今天上午",
                0,
                role="constraint",
                coverage="representation_mismatch",
                independently_satisfiable=False,
            )
        )
        invalid_fresh = create_goals(
            goal(
                "Check Chongqing weather this morning.",
                "capability_work",
                bindings=[binding("date", "date", "今天")],
            )
        )
        changed = {
            "repairs": [
                {
                    "path": "$.new_goals[0].bindings[0].value",
                    "value": "today",
                },
                {
                    "path": "$.new_goals[0].description",
                    "value": "A changed responsibility.",
                },
            ]
        }
        ollama = ScriptedOllama([first, rejected, invalid_fresh, changed])

        result = self._resolve(
            ollama,
            request("哎，今天上午重庆会不会下雨？"),
        )

        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.fresh_temporal_contract_repair",
            ],
        )

    def test_final_coverage_reject_fails_closed(self):
        first = create_goals(
            goal(
                "Walk and sing.",
                "body_action",
                source_responsibility_refs=["r1", "r2"],
            )
        )
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("Sing.", "singing", source_responsibility_refs=["r2"]),
        )
        still_rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        ollama = ScriptedOllama([first, rejected, corrected, still_rejected])
        result = self._resolve(
            ollama,
            request(
                "Walk and sing.",
                language="en-US",
                responsibility_outcomes=["Walk.", "Sing."],
            ),
        )

        self.assertEqual(result.new_goals, [])
        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
                "goal_association.responsibility_coverage_final",
            ],
        )

    def test_model_transport_failure_is_formal_fail_closed(self):
        ollama = FakeOllama(
            OllamaGenerationError(
                "unavailable",
                failure_class="provider_unavailable",
                failure_domain="transport",
                architecture_attribution="not_evaluated",
                retryable=True,
            )
        )
        result = self._resolve(ollama, request("Hello", language="en-US"))

        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(result.new_goals, [])

    def test_user_answerable_ambiguity_commits_provisional_goal(self):
        ollama = ScriptedOllama(
            [
                create_goals(
                    goal("Bring the unresolved referenced cup.", "body_action")
                ),
                certificate(
                    coverage_item(
                        "Bring me that cup",
                        0,
                        coverage="clarification_required",
                    )
                ),
            ]
        )
        result = self._resolve(
            ollama,
            request(
                "Bring me that cup.",
                language="en-US",
                interpretation_unresolved=["which cup the user means"],
            ),
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(len(ollama.prompts), 2)


class GoalAssociationOutcomeRegressionTests(unittest.TestCase):
    def _resolve(self, payloads, req: AgentRunRequest) -> GoalAssociationResolution:
        return asyncio.run(
            GoalAssociationResolver(ScriptedOllama(payloads)).resolve(req)
        )

    def test_instrumental_navigation_is_owned_by_resource_source(self):
        resource = resource_responsibility(
            source_status="known",
            source_description="前方100米处",
            source_bindings=[
                binding("distance", "distance", "100"),
                binding("direction", "direction", "前方"),
            ],
        )
        result = self._resolve(
            [
                create_goals(
                    goal(
                        "从前方100米处拿一杯水并送给用户。",
                        "body_action",
                        resource=resource,
                    )
                ),
                certificate(
                    coverage_item("去往前走个100米", 0, role="constraint"),
                    coverage_item(
                        "帮我拿杯水过来",
                        0,
                        required_goal_shape="physical_resource",
                    ),
                ),
            ],
            request(
                "去往前走个100米，帮我拿杯水过来。",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        semantic = result.new_goals[0]
        self.assertEqual(semantic.metadata["output_mode"], "body_action")
        self.assertEqual(semantic.resource_responsibility.resource.quantity, "1")
        self.assertEqual(semantic.object, {})
        self.assertEqual(
            set(resource_semantic_bindings(semantic.resource_responsibility)),
            {"distance", "direction", "quantity"},
        )
        self.assertNotIn("resource_grounding_projection", semantic.metadata)

    def test_user_water_probe_preserves_one_resource_goal_and_source_constraint(self):
        resource = resource_responsibility(
            description="a bottle of water",
            source_status="known",
            source_description="100 meters ahead",
            source_bindings=[
                binding("distance", "distance", "100"),
                binding("direction", "direction", "ahead"),
            ],
            recipient="requester",
        )
        result = self._resolve(
            [
                create_goals(
                    goal(
                        "Bring the requester one bottle of water from 100 meters ahead.",
                        "body_action",
                        resource=resource,
                    )
                ),
                certificate(
                    coverage_item(
                        "bring me a bottle of water",
                        0,
                        required_goal_shape="physical_resource",
                    ),
                    coverage_item(
                        "the water is 100 meters ahead of you",
                        0,
                        role="constraint",
                    ),
                ),
            ],
            request(
                "bring me a bottle of water, the water is 100 meters ahead of you",
                language="en-US",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        responsibility = result.new_goals[0].resource_responsibility
        self.assertEqual(responsibility.resource.quantity, "1")
        self.assertEqual(
            set(responsibility.source.bindings),
            {"distance", "direction"},
        )
        self.assertNotIn("distance", responsibility.resource.attributes)

    def test_independent_walk_and_resource_delivery_remain_separate(self):
        result = self._resolve(
            [
                create_goals(
                    goal(
                        "Walk 100 meters for exercise.",
                        "body_action",
                        bindings=[binding("distance", "distance", "100")],
                    ),
                    goal(
                        "Bring the bottle from the table to me.",
                        "body_action",
                        source_responsibility_refs=["r2"],
                        resource=resource_responsibility(
                            description="the bottle",
                            source_status="known",
                            source_description="the table",
                            source_bindings=[
                                binding("source_location", "place", "the table")
                            ],
                        ),
                    ),
                ),
                certificate(
                    coverage_item("Walk 100 meters for exercise", 0),
                    coverage_item(
                        "bring the bottle from the table to me",
                        1,
                        required_goal_shape="physical_resource",
                    ),
                ),
            ],
            request(
                "Walk 100 meters for exercise, then bring the bottle from the table to me.",
                language="en-US",
                responsibility_outcomes=[
                    "Walk 100 meters for exercise.",
                    "Bring the bottle from the table to me.",
                ],
            ),
        )

        self.assertEqual(len(result.new_goals), 2)
        self.assertIsNone(result.new_goals[0].resource_responsibility)
        self.assertIsNotNone(result.new_goals[1].resource_responsibility)

    def test_information_scope_is_canonical_resource_attribute(self):
        weather = resource_responsibility(
            kind="information",
            description="重庆明天的天气",
            quantity="",
            attributes=[
                binding("location", "location", "重庆"),
                binding("date", "date", "tomorrow"),
            ],
            source_status="provider_resolved",
        )
        result = self._resolve(
            [
                create_goals(
                    goal("查询并解释重庆明天的天气。", "capability_work", resource=weather)
                ),
                certificate(
                    coverage_item(
                        "查重庆明天天气",
                        0,
                        required_goal_shape="information_resource",
                    )
                ),
            ],
            request(
                "帮我查重庆明天天气。",
            ),
        )

        canonical = result.new_goals[0].resource_responsibility
        self.assertEqual(canonical.resource.kind, "information")
        self.assertEqual(
            set(canonical.resource.attributes),
            {"location", "date", "information_domain"},
        )
        self.assertEqual(
            canonical.resource.attributes["information_domain"]["value"],
            "weather_forecast",
        )
        self.assertEqual(canonical.resource.attributes["date"]["value"], "tomorrow")
        self.assertEqual(canonical.source.status, "provider_resolved")
        self.assertEqual(canonical.source.bindings, {})

    def test_user_weather_probe_is_one_information_responsibility(self):
        weather = resource_responsibility(
            kind="information",
            description="whether it will rain and be cold in Chongqing tonight",
            quantity="",
            attributes=[
                binding("location", "location", "chongqing"),
                binding("time", "time", "tonight"),
                binding("aspects", "list", "rain, temperature"),
            ],
            source_status="provider_resolved",
        )
        result = self._resolve(
            [
                create_goals(
                    goal(
                        "Check whether it will rain and be cold in Chongqing tonight.",
                        "capability_work",
                        resource=weather,
                    )
                ),
                certificate(
                    coverage_item("I am in chongqing now", role="context"),
                    coverage_item(
                        "please help me check whether it will rain tonight and whether it it cold",
                        0,
                        independently_satisfiable=False,
                        required_goal_shape="information_resource",
                    ),
                ),
            ],
            request(
                "I am in chongqing now, please help me check whether it will rain tonight and whether it it cold",
                language="en-US",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        semantic = result.new_goals[0]
        self.assertEqual(semantic.metadata["output_mode"], "capability_work")
        self.assertTrue(semantic.metadata["completion_requires_work"])
        self.assertFalse(semantic.metadata["completion_requires_fresh_evidence"])
        self.assertEqual(
            set(semantic.resource_responsibility.resource.attributes),
            {"location", "time", "aspects", "information_domain"},
        )

    def test_user_joke_probe_acknowledges_tired_context_without_goal_ownership(self):
        result = self._resolve(
            [
                create_goals(goal("Tell the user a joke.", "speech")),
                certificate(
                    coverage_item(
                        "I am a litlle tired",
                        role="context",
                        independently_satisfiable=False,
                    ),
                    coverage_item("can you tell me a joke", 0),
                ),
            ],
            request(
                "I am a litlle tired, can you tell me a joke?",
                language="en-US",
            ),
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].metadata["output_mode"], "speech")

    def test_existing_goal_continuity_commits_without_creation_or_audit(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "associate",
                    "associations": [
                        {
                            "relationship": "continue",
                            "source_responsibility_refs": ["r1"],
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.95,
                            "reason_summary": "Continue the unfinished task.",
                        }
                    ],
                    "confidence": 0.95,
                }
            ]
        )
        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Continue.", active_goals=[active_goal("goal-a", "Do A")])
            )
        )

        self.assertEqual(result.associations[0].target_goal_ids, ["goal-a"])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(len(ollama.prompts), 1)

    def test_associate_discriminant_mechanically_drops_inactive_new_goal_branch(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "associate",
                    "associations": [
                        {
                            "relationship": "continue",
                            "source_responsibility_refs": ["r1"],
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.95,
                            "reason_summary": "Continue the unfinished task.",
                        }
                    ],
                    "new_goals": [
                        goal(
                            "Inactive decoder branch must not double-map r1.",
                            "speech",
                        )
                    ],
                    "confidence": 0.95,
                }
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Continue.", active_goals=[active_goal("goal-a", "Do A")])
            )
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(result.new_goals, [])
        self.assertEqual(len(ollama.prompts), 1)

    def test_explicit_location_preserves_referent_provenance(self):
        payload = create_goals(
            goal(
                "Check 重庆 weather.",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="重庆 weather",
                    attributes=[binding("location", "location", "重庆")],
                    source_status="provider_resolved",
                ),
            )
        )
        payload["referent_updates"] = [
            {
                "operation": "introduce",
                "entity_type": "location",
                "canonical_value": "重庆",
                "scope_kind": "goal",
                "confidence": 1.0,
            }
        ]
        result = self._resolve(
            [
                payload,
                certificate(
                    coverage_item(
                        "Check 重庆 weather",
                        0,
                        required_goal_shape="information_resource",
                    )
                ),
            ],
            request("Check 重庆 weather.", language="en-US"),
        )

        referent = result.referent_updates[0].referent
        self.assertIsNotNone(referent)
        self.assertEqual(
            result.new_goals[0]
            .resource_responsibility.resource.attributes["location"]["referent_id"],
            referent.referent_id,
        )


class GoalAssociationResolutionContractTests(unittest.TestCase):
    def test_goal_association_dto_has_no_work_replanning_authority(self):
        self.assertNotIn(
            "requires_replan",
            GoalAssociationModelAssociation.model_json_schema()["properties"],
        )
        parsed = GoalAssociationModelAssociation.model_validate(
            {
                "relationship": "modify",
                "source_responsibility_refs": ["weather"],
                "target_goal_ids": ["goal-weather"],
                "updated_description": "Check a corrected location.",
                # Transport-noise compatibility must not restore authority that
                # the decoder schema and canonical DTO deliberately removed.
                "requires_replan": True,
            }
        )
        self.assertNotIn("requires_replan", parsed.model_dump())

    def test_fail_closed_is_the_only_empty_terminal_resolution(self):
        failed = GoalAssociationResolution(
            turn_id="turn-1",
            resolution_status="fail_closed",
        )
        self.assertEqual(failed.prompt_projection()["resolution_status"], "fail_closed")
        with self.assertRaises(ValueError):
            GoalAssociationResolution(turn_id="turn-1")
        self.assertTrue(
            GoalAssociationResolution.model_fields["resolution_status"].is_required()
        )

    def test_goal_association_cannot_author_clarification(self):
        with self.assertRaises(ValidationError):
            GoalAssociationResolution(
                resolution_status="needs_clarification",
                turn_id="turn-1",
                clarification="Which one?",
            )




if __name__ == "__main__":
    unittest.main()
