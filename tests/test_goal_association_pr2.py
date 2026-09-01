from __future__ import annotations

from agent.app import goal_association_schema as ga_schema
from agent.app import goal_association_validation as ga_validation
from agent.app import goal_association_prompt as ga_prompt

import asyncio
import copy
import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import GoalAssociationResolver
from agent.app.goal_association_contract import (
    GoalAssociationModelAssociation,
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelInformationResourceResponsibility,
    GoalAssociationModelOutput,
    GoalAssociationModelPhysicalResourceResponsibility,
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
        "resource_kind": resource.get("kind", "none") if resource else "none",
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


    def test_goal_association_preserves_what_without_execution_projection(self):
        item = GoalAssociationModelGoal.model_validate(
            goal("Check tomorrow's weather.", "information")
        )

        self.assertEqual(item.output_mode, "information")
        self.assertFalse(hasattr(item, "responsibility_kind"))
        self.assertFalse(hasattr(item, "execution_lane"))
        self.assertFalse(hasattr(item, "provider_required"))

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
            goal("Check Chongqing weather tonight.", "information", resource=information)
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
                    "information",
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
                goal("Check 重庆 weather.", "information", resource=payload)
            )

    def test_resource_kind_requires_its_semantic_completion_mode(self):
        information = resource_responsibility(
            kind="information",
            description="tonight's Chongqing weather",
            quantity="",
            attributes=[binding("location", "location", "Chongqing")],
            source_status="provider_resolved",
        )
        with self.assertRaisesRegex(ValueError, "output_mode=information"):
            GoalAssociationModelGoal.model_validate(
                goal("Check tonight's weather.", "speech", resource=information)
            )

        parsed = GoalAssociationModelGoal.model_validate(
            goal("Check tonight's weather.", "information", resource=information)
        )
        self.assertEqual(parsed.output_mode, "information")

    def test_information_resource_requires_typed_query_scope_not_description_only(self):
        information = resource_responsibility(
            kind="information",
            description="Chongqing current weather",
            quantity="",
            source_status="provider_resolved",
        )
        with self.assertRaisesRegex(ValueError, "query_scope"):
            GoalAssociationModelGoal.model_validate(
                goal("Check Chongqing weather.", "information", resource=information)
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

    def test_resource_and_responsibility_conservation_invariants_are_in_decoder_schema(self):
        goal_schema = ga_schema.goal_association_response_schema(
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
        weather["new_goals"][0]["output_mode"] = "information"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather["new_goals"][0]["bindings"] = [
            binding("location", "location", "Chongqing")
        ]
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather["new_goals"][0]["bindings"] = []

        weather_scope = weather["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ]
        weather_scope.append(
            binding("temporal_scope", "temporal_scope", "tonight")
        )
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])

        bounded_goal_schema = ga_schema.goal_association_response_schema(
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
            self.assertEqual(branch["type"], "object")
            self.assertFalse(branch["additionalProperties"])
            self.assertIn("description", branch["required"])
            self.assertIn("output_mode", branch["required"])
            self.assertIn("bindings", branch["required"])
            self.assertIn("resource_kind", branch["required"])
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
            body_branches[0]["properties"]["resource_kind"]["const"],
            "none",
        )
        self.assertEqual(
            body_branches[0]["properties"]["resource_responsibility"]["type"],
            "null",
        )
        self.assertEqual(
            body_branches[1]["properties"]["resource_responsibility"]["properties"][
                "kind"
            ]["const"],
            "physical_object",
        )
        self.assertEqual(
            body_branches[1]["properties"]["resource_kind"]["const"],
            "physical_object",
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
            vocal_branches[0]["properties"]["resource_responsibility"]["type"],
            "null",
        )
        self.assertNotIn(
            "GoalAssociationModelInformationResourceResponsibility",
            bounded_goal_schema["$defs"],
        )
        fresh_evidence_schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["weather"],
            responsibility_output_modes={"weather": "information"},
            responsibility_information_refs={"weather"},
        )
        fresh_evidence_branches = fresh_evidence_schema["$defs"][
            "GoalAssociationModelGoal"
        ]["oneOf"]
        self.assertEqual(len(fresh_evidence_branches), 1)
        self.assertEqual(
            fresh_evidence_branches[0]["properties"][
                "resource_responsibility"
            ]["properties"]["kind"]["const"],
            "information",
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
        duplicated_provenance = copy.deepcopy(two_body_actions)
        duplicated_provenance["new_goals"][1]["source_responsibility_refs"] = ["r1"]
        self.assertTrue(
            list(bounded_goal_validator.iter_errors(duplicated_provenance))
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

        constrained_goal_schema = bounded_goal_schema["$defs"][
            "GoalAssociationModelGoal"
        ]
        body_action_branches = [
            branch
            for branch in constrained_goal_schema["oneOf"]
            if branch["properties"]["output_mode"].get("const") == "body_action"
        ]
        ordinary_body_branch = next(
            branch
            for branch in body_action_branches
            if branch["properties"]["resource_responsibility"].get("type")
            == "null"
        )
        ordinary_property_order = list(ordinary_body_branch["properties"])
        self.assertLess(
            ordinary_property_order.index("resource_kind"),
            ordinary_property_order.index("bindings"),
        )
        physical_body_branch = next(
            branch
            for branch in body_action_branches
            if branch["properties"]["resource_responsibility"]
            .get("properties", {})
            .get("kind", {})
            .get("const")
            == "physical_object"
        )
        self.assertIn(
            "locomotion",
            ordinary_body_branch["properties"]["resource_responsibility"][
                "description"
            ],
        )
        self.assertIn(
            "distinct concrete object",
            physical_body_branch["properties"]["resource_responsibility"][
                "description"
            ],
        )

    def test_physical_resource_schema_preserves_entity_recipient_and_source(self):
        schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={
                "r1": {
                    "entity": "bottle of milk",
                    "recipient": "me",
                    "location": "ahead of you about 50 meters",
                    "distance": 50,
                }
            },
        )
        Draft202012Validator.check_schema(schema)
        physical_branch = next(
            branch
            for branch in schema["$defs"]["GoalAssociationModelGoal"]["oneOf"]
            if branch["properties"]["resource_kind"].get("const")
            == "physical_object"
        )
        physical = physical_branch["properties"]["resource_responsibility"]

        self.assertEqual(
            physical["properties"]["description"],
            {"const": "bottle of milk"},
        )
        self.assertEqual(
            physical["properties"]["recipient"]["properties"]["description"],
            {"const": "me"},
        )
        source_bindings = physical["properties"]["source"]["properties"][
            "acquisition_bindings"
        ]
        self.assertEqual(source_bindings["minItems"], 2)
        self.assertEqual(
            [
                item["properties"]["name"]["const"]
                for item in source_bindings["prefixItems"]
            ],
            ["location", "distance"],
        )

        valid = create_goals(
            goal(
                "bring a bottle of milk to me",
                "body_action",
                resource=resource_responsibility(
                    description="bottle of milk",
                    source_status="known",
                    source_description="ahead of you about 50 meters",
                    source_bindings=[
                        binding(
                            "location",
                            "relative_location",
                            "ahead of you about 50 meters",
                        ),
                        binding("distance", "distance", "50"),
                    ],
                    recipient="me",
                ),
            )
        )
        valid.update(referent_updates=[], resolved_references=[])
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(valid)), [])

        wrong_recipient = copy.deepcopy(valid)
        wrong_recipient["new_goals"][0]["resource_responsibility"]["recipient"][
            "description"
        ] = "user"
        self.assertTrue(list(validator.iter_errors(wrong_recipient)))

    def test_primary_prompt_owns_information_and_effect_semantics(self):
        req = request(
            "I am in chongqing now, please help me check whether it will rain "
            "tonight and whether it it cold",
            language="en-US",
        )

        interpretation_prompt = ga_prompt.build_prompt(
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
        self.assertIn(
            "never decompose one GI-owned composite binding",
            interpretation_prompt,
        )

        execution_contract = ga_prompt.build_prompt(
            request(
                "Set a reminder for later.",
                language="en-US",
            ),
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn("stateful_effect", execution_contract)
        self.assertIn("durable or future state change", execution_contract)
        self.assertIn("does not decide whether a Capability", execution_contract)
        self.assertIn("ordinary typed bindings", execution_contract)
        self.assertIn("local/private/runtime source", execution_contract)
        self.assertIn("source.status=unknown", execution_contract)

    def test_unscoped_optional_referent_correction_is_dropped(self):
        normalized, dropped = (
            ga_validation.normalize_optional_referent_updates(
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












    def test_goal_candidate_must_conserve_interpreted_output_mode(self):
        req = request("sing a song", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "sing a song",
                        "bindings": {},
                        "output_mode": "singing",
                        "confidence": 0.98,
                    }
                )
            }
        )
        wrong = GoalSegmentationModelOutput.model_validate(
            create_goals(goal("Sing a song.", "body_action"))
        )

        conflicts = ga_validation.responsibility_output_mode_conflicts(
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

        conflicts = ga_validation.source_grounded_binding_conservation_conflicts(
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
            ga_validation.source_grounded_binding_conservation_conflicts(
                grounded_source,
                request=req,
            ),
            [],
        )

    def test_physical_resource_entity_binding_is_conserved_by_description(self):
        req = request(
            "bring the bottle of milk to me",
            language="en-US",
            responsibility_outcomes=["bring the bottle of milk to me"],
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "bring the bottle of milk to me",
                        "bindings": {
                            "entity": "bottle of milk",
                            "recipient": "me",
                        },
                        "output_mode": "body_action",
                        "confidence": 1.0,
                    }
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "bring the bottle of milk to me",
                    "body_action",
                    resource=resource_responsibility(
                        description="bottle of milk",
                        recipient="me",
                    ),
                )
            )
        )

        self.assertEqual(
            ga_validation.source_grounded_binding_conservation_conflicts(
                output,
                request=req,
            ),
            [],
        )

    def test_physical_resource_preserves_one_composite_gi_location_binding(self):
        location = "ahead of you about 50 meters"
        req = request(
            f"there is a bottle of milk {location}, please bring it to me",
            language="en-US",
            responsibility_outcomes=["bring a bottle of milk to me"],
        ).model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "bring a bottle of milk to me",
                        "bindings": {
                            "location": location,
                            "object": "bottle of milk",
                        },
                        "output_mode": "body_action",
                        "confidence": 0.98,
                    }
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "bring a bottle of milk to me",
                    "body_action",
                    resource=resource_responsibility(
                        description="bottle of milk",
                        source_status="known",
                        source_description=location,
                        source_bindings=[
                            binding("location", "relative_location", location),
                        ],
                    ),
                )
            )
        )

        self.assertEqual(
            ga_validation.source_grounded_binding_conservation_conflicts(
                output,
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
            ga_validation.source_grounded_binding_conservation_conflicts(
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
            ga_validation.source_grounded_binding_conservation_conflicts(
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
            ga_validation.source_grounded_binding_conservation_conflicts(
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
            ga_validation.binding_semantic_contract_conflicts(output),
            ["new_goals[0].bindings[0]=distance/measurement"],
        )

    def test_ordinary_binding_pair_cannot_relabel_duration_as_distance(self):
        req = request("你往前走 10 秒。").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "往前走 10 秒",
                        "bindings": {"direction": "往前", "duration": "10 秒"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                )
            }
        )
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "往前走 10 秒",
                    "body_action",
                    bindings=[
                        binding("direction", "direction", "往前"),
                        binding("distance", "distance", "10 秒"),
                    ],
                )
            )
        )

        self.assertEqual(
            ga_validation.source_grounded_binding_conservation_conflicts(
                output,
                request=req,
            ),
            ["new_goals[0] source_refs=r1 missing='10 秒'"],
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
            ga_validation.resource_source_binding_contract_conflicts(
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
            ga_validation.non_verbatim_explicit_location_bindings(
                output,
                request=request("bring the milk from ahead of you", language="en-US"),
            ),
            [],
        )

    def test_verbatim_geographic_query_scope_is_valid_location_provenance(self):
        output = GoalSegmentationModelOutput.model_validate(
            create_goals(
                goal(
                    "河南省内乡县今天的天气怎么样？",
                    "information",
                    resource=resource_responsibility(
                        kind="information",
                        information_domain="weather_forecast",
                        description="河南省内乡县今天的天气怎么样？",
                        attributes=[
                            binding("location", "geographic", "河南省内乡县"),
                        ],
                    ),
                )
            )
        )

        self.assertEqual(
            ga_validation.non_verbatim_explicit_location_bindings(
                output,
                request=request("河南省内乡县今天的天气怎么样？"),
            ),
            [],
        )

    def test_location_name_cannot_hide_non_location_query_semantics(self):
        payload = create_goals(
            goal(
                "Determine the current local time.",
                "information",
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

        rejected = ga_validation.non_verbatim_explicit_location_bindings(
            model_output,
            request=request("帮我看看现在几点。"),
        )

        self.assertEqual(len(rejected), 1)
        self.assertIn("non_location_semantics", rejected[0])

    def test_grounded_generic_location_type_is_mechanically_normalized(self):
        payload = create_goals(
            goal(
                "Determine whether someone is outside.",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="direct_environment_perception",
                    description="whether someone is outside",
                    attributes=[binding("location", "string", "外面")],
                ),
            )
        )

        normalized, repairs = (
            ga_validation.normalize_grounded_binding_types(
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

    def test_grounded_relative_location_pair_is_mechanically_canonicalized(self):
        payload = create_goals(
            goal(
                "Bring the milk from ahead of you.",
                "body_action",
                resource=resource_responsibility(
                    description="bottle of milk",
                    source_status="known",
                    source_bindings=[
                        binding(
                            "location_relative",
                            "location_relative",
                            "ahead of you",
                        )
                    ],
                ),
            )
        )

        normalized, repairs = (
            ga_validation.normalize_grounded_binding_types(
                payload,
                request=request("Bring the milk from ahead of you."),
            )
        )

        location = normalized["new_goals"][0]["resource_responsibility"][
            "source"
        ]["acquisition_bindings"][0]
        self.assertEqual(location["name"], "location")
        self.assertEqual(location["entity_type"], "relative_location")
        self.assertEqual(location["value"], "ahead of you")
        self.assertEqual(
            repairs[0]["from"], "location_relative/location_relative"
        )
        self.assertTrue(repairs[0]["value_unchanged"])

    def test_grounded_information_time_type_remains_human_temporal_scope(self):
        payload = create_goals(
            goal(
                "查询今天北京是否下雨",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="查询今天北京是否下雨",
                    attributes=[
                        binding("location", "location", "北京"),
                        binding("time", "time", "今天"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )

        normalized, repairs = ga_validation.normalize_grounded_binding_types(
            payload,
            request=request("今天北京下雨了没有？"),
        )

        time_binding = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ][1]
        self.assertEqual(time_binding["name"], "time")
        self.assertEqual(time_binding["entity_type"], "temporal_scope")
        self.assertEqual(time_binding["value"], "今天")
        self.assertEqual(repairs[-1]["from"], "time")
        self.assertEqual(repairs[-1]["to"], "temporal_scope")
        self.assertTrue(repairs[-1]["value_unchanged"])

    def test_grounded_information_time_period_alias_remains_human_temporal_scope(self):
        payload = create_goals(
            goal(
                "查询今天白天重庆的天气",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="查询今天白天重庆的天气",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("time", "time_period", "今天白天"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )

        normalized, repairs = ga_validation.normalize_grounded_binding_types(
            payload,
            request=request("今天白天重庆天气怎么样？"),
        )

        time_binding = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ][1]
        self.assertEqual(time_binding["name"], "time")
        self.assertEqual(time_binding["entity_type"], "temporal_scope")
        self.assertEqual(time_binding["value"], "今天白天")
        self.assertEqual(repairs[-1]["from"], "time_period")
        self.assertEqual(repairs[-1]["to"], "temporal_scope")
        self.assertTrue(repairs[-1]["value_unchanged"])

    def test_grounded_information_time_scope_alias_remains_human_temporal_scope(self):
        payload = create_goals(
            goal(
                "查询今天上午重庆是否下雨",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    information_domain="weather_forecast",
                    description="查询今天上午重庆是否下雨",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("time_scope", "time_scope", "今天上午"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )

        normalized, repairs = ga_validation.normalize_grounded_binding_types(
            payload,
            request=request("哎，今天上午重庆会不会下雨？"),
        )

        time_binding = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ][1]
        self.assertEqual(time_binding["name"], "time_scope")
        self.assertEqual(time_binding["entity_type"], "temporal_scope")
        self.assertEqual(time_binding["value"], "今天上午")
        self.assertEqual(repairs[-1]["from"], "time_scope")
        self.assertEqual(repairs[-1]["to"], "temporal_scope")
        self.assertTrue(repairs[-1]["value_unchanged"])

    def test_grounded_ordinary_binding_type_aliases_are_mechanically_normalized(self):
        req = request("往前走 10 秒，同时眨一下眼睛。").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "往前走 10 秒",
                        "bindings": {"direction": "往前", "duration": "10 秒"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "眨一下眼睛",
                        "bindings": {"action": "眨眼", "count": "1 次"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                )
            }
        )
        payload = create_goals(
            goal(
                "往前走 10 秒",
                "body_action",
                bindings=[
                    binding("direction", "string", "往前"),
                    binding("duration", "temporal_scope", "10 秒"),
                ],
            ),
            goal(
                "眨一下眼睛",
                "body_action",
                bindings=[binding("count", "integer", "1 次")],
                source_responsibility_refs=["r2"],
            ),
        )

        normalized, repairs = ga_validation.normalize_grounded_binding_types(
            payload,
            request=req,
        )

        first_bindings = normalized["new_goals"][0]["bindings"]
        second_binding = normalized["new_goals"][1]["bindings"][0]
        self.assertEqual(
            [item["entity_type"] for item in first_bindings],
            ["direction", "duration"],
        )
        self.assertEqual(second_binding["entity_type"], "count")
        self.assertEqual(len(repairs), 3)
        self.assertTrue(all(item["source_pair_grounded"] for item in repairs))






    def test_primary_result_preserves_two_responsibilities_without_a_reviewer(self):
        candidates = create_goals(
            goal("Look at me", "body_action", source_responsibility_refs=["r1"]),
            goal(
                "blink twice",
                "body_action",
                source_responsibility_refs=["r2"],
                bindings=[
                    binding("after", "sequence_ref", "r1"),
                    binding("count", "count", "2"),
                ],
            ),
        )
        ollama = ScriptedOllama([candidates])
        req = request("Look at me, then blink twice.", language="en-US")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "Look at me",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.99,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "blink twice",
                        "bindings": {"after": "r1", "count": 2},
                        "output_mode": "body_action",
                        "confidence": 0.99,
                    },
                )
            }
        )

        result = asyncio.run(GoalAssociationResolver(ollama).resolve(req))

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.new_goals), 2)
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(
            result.metadata["responsibility_conservation"]["mapped_refs"],
            ["r1", "r2"],
        )



    def test_goal_association_projection_omits_fast_planner_response_wording(self):
        req = request("今天晚上有大雨吗？")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
{
                        "local_ref": "weather_1",
                        "outcome": "确认今晚是否有大雨",
                        "bindings": {"precipitation_severity": "heavy"},
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
        prompt = ga_prompt.build_prompt(
            req, [], output_type=GoalSegmentationModelOutput
        )

        self.assertNotIn("这句 Planner 文案绝不能进入 GA。", prompt)
        self.assertNotIn("Planner HOW, not Goal meaning.", prompt)
        self.assertNotIn('"activity_id":"vocal_1"', prompt)
        self.assertNotIn('"role":"progress"', prompt)
        self.assertIn("authored concurrently", prompt)
        self.assertIn("must never become, justify, or be copied", prompt)



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
                "information",
                bindings=list(resource["query_scope"]),
                resource=resource,
            )
        )

        normalized, dropped = (
            ga_validation.normalize_resource_binding_branches(raw)
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
                "information",
                bindings=[binding("carrier", "organization", "ParcelCo")],
                resource=resource,
            )
        )

        normalized, dropped = (
            ga_validation.normalize_resource_binding_branches(raw)
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
            ga_validation.normalize_resource_binding_branches(raw)
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
            ga_validation.normalize_optional_resource_quantity(raw)
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
                        "confidence": 0.98,
                    }
                )
            }
        )
        raw = create_goals(goal("discarded", "singing", source_responsibility_refs=["sing"]))
        raw["new_goals"][0].pop("description")

        normalized, recovered = (
            ga_validation.restore_missing_goal_descriptions(
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
            ga_validation.restore_missing_goal_descriptions(
                ambiguous,
                request=req,
            )
        )
        self.assertNotIn("description", unchanged["new_goals"][0])
        self.assertEqual(recovered, [])



    def test_unentailed_resource_query_location_is_dropped_without_replacement(self):
        raw = create_goals(
            goal(
                "Report the current local time.",
                "information",
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
                        "confidence": 0.95,
                    }
                )
            }
        )

        normalized, dropped = (
            ga_validation.drop_ungrounded_resource_query_locations(
                raw,
                request=req,
            )
        )

        query_scope = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ]
        self.assertEqual([item["name"] for item in query_scope], ["time"])
        self.assertEqual(dropped[0]["value"], "current location")

    def test_unique_gi_time_value_repairs_corrupted_query_location_label(self):
        raw = create_goals(
            goal(
                "Report the current local time.",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    description="current local time",
                    attributes=[binding("location", "unknown", "现在")],
                    source_status="unknown",
                ),
            )
        )
        req = request("帮我看看现在几点。", language="zh-CN")
        req = req.model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "现在是几点",
                        "bindings": {"time": "现在"},
                        "output_mode": "information",
                        "confidence": 0.99,
                    }
                )
            }
        )

        normalized, repaired = ga_validation.normalize_grounded_binding_types(
            raw,
            request=req,
        )

        query_scope = normalized["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ]
        self.assertEqual(query_scope[0]["name"], "time")
        self.assertEqual(query_scope[0]["entity_type"], "temporal_scope")
        self.assertEqual(query_scope[0]["value"], "现在")
        self.assertTrue(repaired[0]["source_pair_grounded"])

    def test_goal_association_prompt_uses_gateway_original_user_wording(self):
        req = request("今晚，重庆热不热？")
        context = dict(req.context)
        context["user_turn_envelope"] = {
            "original_input": {"text": "  今晚，重庆热不热？  "}
        }
        req = req.model_copy(update={"context": context})

        self.assertEqual(req.text, "今晚，重庆热不热？")
        self.assertEqual(req.original_user_text, "  今晚，重庆热不热？  ")
        self.assertEqual(
            req.source_turn_provenance["authority"],
            "read_only_source_provenance",
        )
        prompt = ga_prompt.build_prompt(
            req, [], output_type=GoalSegmentationModelOutput
        )
        self.assertIn("IMMUTABLE SOURCE TURN JSON", prompt)
        self.assertIn('"original_text":"  今晚，重庆热不热？  "', prompt)
        self.assertIn("GI Responsibilities own current-turn WHAT", prompt)
        self.assertIn("never silent semantic repair", prompt)

    def test_primary_goal_prompt_distinguishes_body_action_from_physical_resource(self):
        req = request(
            "Run forward for 15 seconds while singing.",
            language="en-US",
            responsibility_outcomes=[
                "run forward for 15 seconds",
                "sing while running",
            ],
        )
        primary_prompt = ga_prompt.build_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn("distinct concrete object", primary_prompt)
        self.assertIn("non-resource body_action Goals", primary_prompt)
        self.assertIn("Responsibility conservation is strict", primary_prompt)

    def test_no_candidate_segmentation_prompt_fits_qualified_8k_preflight(self):
        req = request("你往前走 10 秒。")

        layered = ga_prompt.layered_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        input_chars = len(layered.render()) + len(
            ga_prompt.system_prompt(GoalSegmentationModelOutput)
        )

        # The deployed fail-closed estimate is two characters per token.  An
        # 8,192-token request reserving 512 output and 2,048 safety tokens may
        # therefore admit at most 11,264 input characters.
        self.assertLessEqual(input_chars, 11_264)
        prompt = layered.render()
        self.assertIn("Responsibility conservation is strict", prompt)
        self.assertIn("distinct concrete object", prompt)
        self.assertIn("non-resource body_action Goals", prompt)
        self.assertIn("IMMUTABLE SOURCE TURN JSON", prompt)

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
        layered = ga_prompt.layered_prompt(
            req,
            candidates,
            output_type=GoalAssociationModelOutput,
        )
        input_chars = len(layered.render()) + len(
            ga_prompt.system_prompt(GoalAssociationModelOutput)
        )

        self.assertLessEqual(input_chars, 11_264)
        prompt = layered.render()
        self.assertIn("Verify GI relationship", prompt)
        self.assertIn('"relationship":"continue"', prompt)
        self.assertIn('"goal_id":"goal-walk"', prompt)
        self.assertIn("好，我这就往前走十秒。", prompt)
        self.assertNotIn("runtime transport must not leak", prompt)
        self.assertNotIn("Owner-approved Personality Expression JSON", prompt)

        schema = ga_schema.goal_association_response_schema(
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
        self.assertNotIn("decision", schema["properties"])
        self.assertNotIn("decision=associate", prompt)
        self.assertIn("associations and new_goals", prompt)
        self.assertIn(
            "Association confidence measures certainty about Goal ownership",
            prompt,
        )
        self.assertIn("resolved_gap_ids empty when resolution is unproven", prompt)

        validator = Draft202012Validator(schema)
        missing_modify_update = {
            "associations": [
                {
                    "relationship": "modify",
                    "source_responsibility_refs": ["r1"],
                    "target_goal_ids": ["goal-walk"],
                    "confidence": 1.0,
                }
            ],
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "confidence": 1.0,
            "reason_summary": "The requested refinement is understood.",
        }
        self.assertTrue(list(validator.iter_errors(missing_modify_update)))
        missing_modify_update["associations"][0]["updated_description"] = (
            "Walk forward for ten seconds, then stop quietly."
        )
        self.assertEqual(list(validator.iter_errors(missing_modify_update)), [])



    def test_temporal_binding_preserves_human_semantic_surface(self):
        value = GoalAssociationModelBinding(
            name="temporal_scope",
            entity_type="temporal_scope",
            value="今晚",
            confidence=1.0,
        )
        self.assertEqual(value.value, "今晚")



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
        self.assertEqual(transaction["logical_invocation_budget"], 2)
        self.assertEqual(transaction["prompt_families"], families)
        self.assertEqual(
            [kwargs["prompt_family"] for _, kwargs in ollama.prompts],
            families,
        )







    def test_primary_dto_gets_exactly_one_contract_repair(self):
        valid = create_goals(goal("Blink twice.", "body_action"))
        invalid = copy.deepcopy(valid)
        invalid["unexpected_transport_field"] = "must be removed"
        ollama = ScriptedOllama([invalid, valid])
        req = request("Please blink exactly twice.", language="en-US")
        result = self._resolve(
            ollama,
            req,
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
            ],
        )
        repair_prompt = str(ollama.prompts[1][0])
        self.assertIn("mechanical", repair_prompt)
        self.assertNotIn(req.original_user_text, repair_prompt)

    def test_primary_binding_conservation_failure_is_terminal_without_repair(self):
        missing = create_goals(
            goal("Move forward for 10 seconds.", "body_action")
        )
        ollama = ScriptedOllama([missing])
        req = request("Move forward for 10 seconds.", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "move forward for ten seconds",
                        "bindings": {"duration": "10 seconds"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                )
            }
        )

        result = self._resolve(ollama, req)

        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(result.new_goals, [])
        self.assert_transaction(
            result,
            ollama,
            terminal="fail_closed",
            families=["goal_association.primary"],
        )
        self.assertFalse(
            result.metadata["goal_semantic_transaction"]
            ["contract_repair_attempted"]
        )



    def test_response_schema_keeps_unsupplied_recipient_pronoun_out_of_referent_id(self):
        schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={
                "r1": {"location": "ahead of you", "distance": "50 meters"}
            },
        )

        recipient = schema["$defs"]["GoalAssociationModelResourceRecipient"]
        self.assertEqual(recipient["properties"]["referent_id"], {"type": "null"})
        self.assertNotIn("referent_id", recipient.get("required", []))

    def test_response_schema_requires_source_grounded_ordinary_bindings(self):
        schema = ga_schema.goal_association_response_schema(
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
        self.assertIsInstance(bindings["items"], dict)
        self.assertNotEqual(bindings["items"], False)
        self.assertEqual(
            bindings["prefixItems"][0]["properties"]["value"],
            {"const": "10 秒"},
        )
        duration_binding = bindings["prefixItems"][0]
        self.assertFalse(
            list(
                Draft202012Validator(duration_binding).iter_errors(
                    binding("duration", "duration", "10 秒")
                )
            )
        )
        self.assertTrue(
            list(
                Draft202012Validator(duration_binding).iter_errors(
                    binding("duration", "temporal_scope", "10 秒")
                )
            )
        )

        speed_schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={"r1": {"speed": "quickly"}},
        )
        speed_branch = speed_schema["$defs"]["GoalAssociationModelGoal"][
            "oneOf"
        ][0]
        speed_binding = speed_branch["properties"]["bindings"]["prefixItems"][0]
        self.assertEqual(
            speed_binding["properties"]["value"],
            {"const": "quick"},
        )
        self.assertFalse(
            list(
                Draft202012Validator(speed_binding).iter_errors(
                    binding("speed", "speed", "quick")
                )
            )
        )
        self.assertTrue(
            list(
                Draft202012Validator(speed_binding).iter_errors(
                    binding("speed", "manner", "quick")
                )
            )
        )

        count_schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "body_action"},
            responsibility_bindings={"r1": {"count": "1 次"}},
        )
        count_binding = count_schema["$defs"]["GoalAssociationModelGoal"][
            "oneOf"
        ][0]["properties"]["bindings"]["prefixItems"][0]
        self.assertTrue(
            list(
                Draft202012Validator(count_binding).iter_errors(
                    binding("count", "integer", "1 次")
                )
            )
        )

        identity_schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "speech"},
            responsibility_bindings={
                "r1": {"name": "entity_id", "value": "chromie"}
            },
        )
        identity_bindings = identity_schema["$defs"][
            "GoalAssociationModelGoal"
        ]["oneOf"][0]["properties"]["bindings"]
        self.assertEqual(
            [
                item["properties"]["name"]["const"]
                for item in identity_bindings["prefixItems"]
            ],
            ["name", "value"],
        )
        duplicate_name_rows = [
            binding("name", "entity_id", "entity_id"),
            binding("name", "name", "entity_id"),
        ]
        self.assertTrue(
            list(
                Draft202012Validator(identity_bindings).iter_errors(
                    duplicate_name_rows
                )
            )
        )

    def test_response_schema_requires_all_source_grounded_information_scope(self):
        schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "information"},
            responsibility_information_refs={"r1"},
            responsibility_bindings={
                "r1": {"event": "下雨", "location": "北京", "time": "今天"}
            },
        )

        branch = schema["$defs"]["GoalAssociationModelGoal"]["oneOf"][0]
        information = branch["properties"]["resource_responsibility"]
        scope = information["properties"]["query_scope"]
        self.assertEqual(scope["minItems"], 3)
        self.assertEqual(scope["maxItems"], 3)
        required_pairs = {
            (
                clause["contains"]["properties"]["name"]["const"],
                clause["contains"]["properties"]["value"]["const"],
            )
            for clause in scope["allOf"]
        }
        self.assertEqual(
            required_pairs,
            {("event", "下雨"), ("location", "北京"), ("time", "今天")},
        )
        validator = Draft202012Validator(schema)
        complete = create_goals(
            goal(
                "查询今天北京是否下雨",
                "information",
                resource=resource_responsibility(
                    kind="information",
                    description="查询今天北京是否下雨",
                    attributes=[
                        binding("event", "event", "下雨"),
                        binding("location", "place", "北京"),
                        binding("time", "temporal_scope", "今天"),
                    ],
                    source_status="provider_resolved",
                ),
            )
        )
        complete.update(referent_updates=[], resolved_references=[])
        self.assertEqual(list(validator.iter_errors(complete)), [])
        incomplete = copy.deepcopy(complete)
        incomplete["new_goals"][0]["resource_responsibility"][
            "query_scope"
        ].pop(0)
        self.assertTrue(list(validator.iter_errors(incomplete)))

    def test_numeric_gi_binding_reaches_the_decoder_as_grounded_text(self):
        req = request("你往前走 10 秒。").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "往前走 10 秒",
                        "bindings": {"direction": "前", "duration_seconds": 10},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                )
            }
        )
        candidate = create_goals(
            goal(
                "往前走 10 秒",
                "body_action",
                bindings=[
                    binding("direction", "direction", "前"),
                    binding("duration_seconds", "duration", "10"),
                ],
            )
        )
        ollama = ScriptedOllama([candidate])

        result = self._resolve(ollama, req)

        self.assertEqual(result.resolution_status, "resolved")
        response_schema = ollama.prompts[0][1]["response_format"]
        ordinary_branch = response_schema["$defs"][
            "GoalAssociationModelGoal"
        ]["oneOf"][0]
        required_values = {
            item["contains"]["properties"]["value"]["const"]
            for item in ordinary_branch["properties"]["bindings"]["allOf"]
        }
        self.assertEqual(required_values, {"前", "10"})

    def test_invalid_contract_repair_fails_closed_without_third_call(self):
        invalid = create_goals(goal("Blink twice.", "body_action"))
        invalid["unexpected_transport_field"] = "must be removed"
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



    def test_ungrounded_reference_commits_provisional_goal_for_planner(self):
        initial = create_goals(
            goal("Turn off the unresolved referenced device.", "body_action")
        )
        ollama = ScriptedOllama([initial])
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
            result.metadata["responsibility_conservation"]["status"],
            "validated",
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="resolved",
            families=["goal_association.primary"],
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
                )
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
        self.assertEqual(len(ollama.prompts), 1)


class GoalAssociationOutcomeRegressionTests(unittest.TestCase):
    def _resolve(
        self, payloads, req: CognitiveWorkRequest
    ) -> GoalAssociationResolution:
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
                )
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
                )
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
                )
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
                    goal("查询并解释重庆明天的天气。", "information", resource=weather)
                )
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
                        "information",
                        resource=weather,
                    )
                )
            ],
            request(
                "I am in chongqing now, please help me check whether it will rain tonight and whether it it cold",
                language="en-US",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        semantic = result.new_goals[0]
        self.assertEqual(semantic.metadata["output_mode"], "information")
        self.assertNotIn("completion_requires_work", semantic.metadata)
        self.assertNotIn("completion_requires_fresh_evidence", semantic.metadata)
        self.assertEqual(
            set(semantic.resource_responsibility.resource.attributes),
            {"location", "time", "aspects", "information_domain"},
        )

    def test_user_joke_probe_acknowledges_tired_context_without_goal_ownership(self):
        result = self._resolve(
            [
                create_goals(goal("Tell the user a joke.", "speech"))
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

    def test_candidate_aware_result_commits_association_and_new_goal_together(self):
        ollama = ScriptedOllama(
            [
                {
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
                            "Tell the user a joke.",
                            "speech",
                            source_responsibility_refs=["r2"],
                        )
                    ],
                    "confidence": 0.95,
                }
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Continue A and tell me a joke.",
                    active_goals=[active_goal("goal-a", "Do A")],
                    language="en-US",
                    responsibility_outcomes=["Continue A.", "Tell me a joke."],
                )
            )
        )

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].source_responsibility_refs, ["r2"])
        self.assertEqual(
            result.metadata["responsibility_conservation"]["mapped_refs"],
            ["r1", "r2"],
        )
        self.assertEqual(len(ollama.prompts), 1)

    def test_cross_collection_duplicate_responsibility_fails_closed_without_repair(self):
        ollama = ScriptedOllama(
            [
                {
                    "associations": [
                        {
                            "relationship": "continue",
                            "source_responsibility_refs": ["r1"],
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.95,
                            "reason_summary": "Continue the unfinished task.",
                        }
                    ],
                    "new_goals": [goal("Duplicate responsibility.", "speech")],
                    "confidence": 0.95,
                }
            ]
        )

        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request("Continue.", active_goals=[active_goal("goal-a", "Do A")])
            )
        )

        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertFalse(
            result.metadata["goal_semantic_transaction"]
            ["contract_repair_attempted"]
        )

    def test_explicit_location_preserves_referent_provenance(self):
        payload = create_goals(
            goal(
                "Check 重庆 weather.",
                "information",
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
                payload
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
