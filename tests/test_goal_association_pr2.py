from __future__ import annotations

from agent.app import goal_association_schema as ga_schema
from agent.app import goal_association_validation as ga_validation
from agent.app import goal_association_prompt as ga_prompt

import asyncio
import copy
import json
import unittest

import pytest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import GoalAssociationResolver
from agent.app.goal_association_contract import (
    GoalAssociationModelAssociation,
    GoalAssociationModelBinding,
    GoalAssociationModelGoal,
    GoalAssociationModelInformationResourceResponsibility,
    GoalAssociationModelInformationSource,
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

        "output_mode": output_mode,
        "bindings": list(bindings or []),
        "resource_kind": resource.get("kind", "none") if resource else "none",
        "resource_responsibility": resource,
        **extra,
    }
    return payload


def intent_goal(description: str, output_mode: str, **extra) -> dict:
    """GA fixture selects intent identities; descriptions/types come from UMI."""
    return {"source_responsibility_refs": ["r1"], "related_goal_ids": [],
            "supersedes_goal_ids": [], **extra}


def create_goals(*goals: dict) -> dict:
    refs = [
        ref
        for goal_payload in goals
        for ref in goal_payload.get("source_responsibility_refs", [])
    ]
    return {
        "decision": "create_goals",
        "unassociated_responsibility_refs": list(dict.fromkeys(refs)),
        "cognitive_requests": [],
        "confidence": 1.0,
        "reason_summary": "No retained Goal matches the current Responsibility.",
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
    meaning_uncertainties: list[str] | None = None,
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
        meaning_uncertainties=[
            {
                "local_ref": f"u{index}",
                "kind": "other",
                "description": description,
                "responsibility_refs": ["r1"],
            }
            for index, description in enumerate(meaning_uncertainties or [], start=1)
        ],
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

    def test_information_resource_allows_query_in_inherited_complete_outcome(self):
        information = resource_responsibility(
            kind="information",
            description="Chongqing current weather",
            quantity="",
            source_status="provider_resolved",
        )
        parsed = GoalAssociationModelGoal.model_validate(
            goal("Check Chongqing weather.", "information", resource=information)
        )
        self.assertEqual(parsed.resource_responsibility.query_scope, [])

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







    def test_decoder_nested_association_preserves_types_and_conditional_contract(self):
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput, [{"goal_id": "goal-a"}], [],
            responsibility_refs=["r1"],
        )
        association = schema["$defs"]["GoalAssociationModelAssociation"]
        exposed = Draft202012Validator(association["anyOf"][0])
        valid = {
            "relationship": "continue", "source_responsibility_refs": ["r1"],
            "target_goal_ids": ["goal-a"], "confidence": 1.0,
        }
        self.assertTrue(exposed.is_valid(valid))
        for field in valid:
            with self.subTest(missing=field):
                missing = copy.deepcopy(valid)
                del missing[field]
                self.assertFalse(exposed.is_valid(missing))
        for field, value in (
            ("relationship", "invented"), ("source_responsibility_refs", [False]),
            ("target_goal_ids", ["unknown-goal"]), ("confidence", "high"),
        ):
            with self.subTest(field=field, value=value):
                self.assertFalse(exposed.is_valid({**valid, field: value}))
        modify = {**valid, "relationship": "modify"}
        self.assertFalse(Draft202012Validator({"$defs": schema["$defs"], **association}).is_valid(modify))
        modify["requirement_changes"] = [{"target_goal_id": "goal-a", "replace_requirement_indices": [0], "source_responsibility_refs": ["r1"]}]
        self.assertTrue(Draft202012Validator({"$defs": schema["$defs"], **association}).is_valid(modify))





    def test_unscoped_optional_referent_correction_is_rejected(self):
        raw = create_goals(goal("label", "speech"))
        raw["referent_updates"] = [{"operation": "correct", "entity_type": "person",
            "canonical_value": "Dad", "target_referent_ids": [], "confidence": 1.0}]
        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(ValidationError, "requires target_referent_ids"):
            GoalSegmentationModelOutput.model_validate(raw)
        self.assertEqual(raw, before)

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
                        "bindings": {},
                        "output_mode": "singing",
                        "confidence": 0.98,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "blinking eyes simultaneously",
                        "bindings": {"simultaneously": "simultaneously"},
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













    def test_primary_result_preserves_two_responsibilities_without_a_reviewer(self):
        candidates = create_goals(
            intent_goal("Look at me", "body_action", source_responsibility_refs=["r1"]),
            intent_goal(
                "blink twice",
                "body_action",
                source_responsibility_refs=["r2"],
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
                        "bindings": {},
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










    def test_goal_segmentation_prompt_preserves_all_authoritative_responsibilities(self):
        outcomes = [
            f"responsibility {index}: " + ("material semantic detail " * 10)
            for index in range(1, 9)
        ]
        req = request(
            "Handle all eight independent responsibilities.",
            language="en-US",
            responsibility_outcomes=outcomes,
        )

        prompt = ga_prompt.build_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )

        label = "UMI Responsibilities JSON:\n"
        payload, end = json.JSONDecoder().raw_decode(prompt.split(label, 1)[1])
        payload_text = prompt.split(label, 1)[1][:end]
        self.assertGreater(len(payload_text), 2600)
        self.assertEqual(
            [item["local_ref"] for item in payload],
            [f"r{index}" for index in range(1, 9)],
        )
        self.assertIn(outcomes[-1].strip(), prompt)

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
        self.assertIn("UMI Responsibilities own current-turn WHAT", prompt)
        self.assertIn("never silent semantic repair", prompt)





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




















    def test_ungrounded_reference_commits_provisional_goal_for_planner(self):
        initial = create_goals(
            intent_goal("Turn off the unresolved referenced device.", "body_action")
        )
        ollama = ScriptedOllama([initial])
        result = self._resolve(
            ollama,
            request(
                "Turn it off.",
                language="en-US",
                meaning_uncertainties=["which device the user means"],
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

    def test_user_answerable_ambiguity_commits_provisional_intent_goal(self):
        ollama = ScriptedOllama(
            [
                create_goals(
                    intent_goal("Bring the unresolved referenced cup.", "body_action")
                )
            ]
        )
        result = self._resolve(
            ollama,
            request(
                "Bring me that cup.",
                language="en-US",
                meaning_uncertainties=["which cup the user means"],
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








    def test_terminal_goal_cannot_absorb_fresh_responsibility(self):
        terminal = active_goal("goal-weather", "Check Chongqing weather.")
        terminal["responsibility_status"] = "satisfied"
        terminal["work_status"] = "done"
        terminal["goal"]["responsibility_status"] = "satisfied"
        payload = {
            "associations": [{
                "relationship": "continue",
                "source_responsibility_refs": ["r1"],
                "target_goal_ids": ["goal-weather"],
                "confidence": 1.0,
                "reason_summary": "Wrongly reuse the completed weather Goal.",
            }],
            "new_goals": [],
            "referent_updates": [],
            "resolved_references": [],
            "confidence": 1.0,
            "reason_summary": "Wrong continuity decision.",
        }

        result = self._resolve(
            [payload],
            request("Nod your head five times.", active_goals=[terminal], language="en-US"),
        )

        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(result.associations, [])
        self.assertEqual(
            result.metadata["rejected_associations"][0]["reason"],
            "terminal_goal_history_only",
        )






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



    def test_duplicate_new_goal_responsibility_fails_closed_without_repair(self):
        ollama = ScriptedOllama([
            create_goals(
                intent_goal("Tell me a joke.", "speech"),
                intent_goal("Tell me another joke.", "speech"),
            )
        ])
        result = asyncio.run(
            GoalAssociationResolver(ollama).resolve(
                request(
                    "Tell me a joke and greet me.", language="en-US",
                    responsibility_outcomes=["Tell me a joke.", "Greet me."],
                )
            )
        )
        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(result.associations, [])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(len(ollama.prompts), 1)
        self.assertFalse(
            result.metadata["goal_semantic_transaction"]["contract_repair_attempted"]
        )



class GoalAssociationResolutionContractTests(unittest.TestCase):
    def test_goal_association_dto_has_no_work_replanning_authority(self):
        self.assertNotIn(
            "requires_replan",
            GoalAssociationModelAssociation.model_json_schema()["properties"],
        )
        with self.assertRaisesRegex(ValidationError, "requires_replan"):
            GoalAssociationModelAssociation.model_validate({
                "relationship": "modify", "source_responsibility_refs": ["weather"],
                "target_goal_ids": ["goal-weather"],
                "requirement_changes": [{"target_goal_id": "goal-weather", "replace_requirement_indices": [0], "source_responsibility_refs": ["weather"]}],
                "requires_replan": True,
            })

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


class GoalMeaningInheritanceTests(unittest.TestCase):

    def test_body_effect_family_is_preserved_into_goal_metadata(self):
        req = request("bring the milk to me", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities({
                    "local_ref": "r1",
                    "outcome": "bring the milk to me",
                    "bindings": {"entity": "milk", "recipient": "me"},
                    "output_mode": "body_action",
                    "body_effect_family": "task_physical_effect",
                    "confidence": 1.0,
                })
            }
        )
        raw = create_goals(intent_goal("unused", "body_action"))
        result = asyncio.run(GoalAssociationResolver(ScriptedOllama([raw])).resolve(req))
        self.assertEqual(
            result.new_goals[0].metadata["body_effect_families"],
            ["task_physical_effect"],
        )

    def test_minimal_ga_new_goal_preserves_structured_umi_binding_losslessly(self):
        structured = {"room": "desk", "offset": [1, 2]}
        req = request("Arrange them in this region.", language="en-US").model_copy(
            update={
                "responsibilities": typed_responsibilities(
                    {
                        "local_ref": "r1",
                        "outcome": "Arrange them in this region.",
                        "bindings": {"region": structured},
                        "output_mode": "body_action",
                        "confidence": 0.97,
                    }
                )
            }
        )
        model = ScriptedOllama([create_goals(intent_goal("unused", "body_action"))])

        result = asyncio.run(GoalAssociationResolver(model).resolve(req))

        self.assertEqual(result.resolution_status, "resolved", result.metadata)
        inherited = result.new_goals[0].object["bindings"]["region"]
        self.assertEqual(inherited["value"], structured)
        self.assertEqual(inherited["entity_type"], "region")
        self.assertEqual(inherited["confidence"], 0.97)



    def test_source_bound_changes_reject_missing_requirement_binding_or_snapshot(self):
        from shared.chromie_contracts.semantic_task import SemanticGoal, apply_goal_meaning_update, semantic_goal_fingerprint
        original = SemanticGoal(goal_id="g", source_text="original", description="A; B", success_criteria=["A", "B"])
        update = {"base_goal_fingerprint": semantic_goal_fingerprint(original), "replace_requirement_indices": [],
                  "source_turn_id": "turn-current", "source_responsibilities": [{"local_ref": "r1", "outcome": "C"}],
                  "binding_changes": []}
        self.assertEqual(apply_goal_meaning_update(original, update).success_criteria, ["A", "B", "C"])
        invalid_updates = [
            {**update, "base_goal_fingerprint": "stale"},
            {**update, "replace_requirement_indices": [2]},
            {**update, "replace_requirement_indices": [0, 0]},
            {**update, "source_responsibilities": []},
            {**update, "description": "unattributed change"},
            {**update, "binding_changes": [{"path": ["constraints", "count"],
              "source_responsibility_ref": "r1", "source_binding": "missing"}]},
            {**update, "binding_changes": [{"path": ["metadata", "output_mode"],
              "source_responsibility_ref": "r1", "source_binding": "missing"}]},
        ]
        for invalid in invalid_updates:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                apply_goal_meaning_update(original, invalid)
        self.assertEqual(original.success_criteria, ["A", "B"])
        typed = original.model_copy(update={"object": {"bindings": {"count": {"value": "3"}}}})
        conflicting = {**update, "base_goal_fingerprint": semantic_goal_fingerprint(typed),
                       "source_responsibilities": [{"local_ref": "r1", "outcome": "B five times.",
                                                     "bindings": {"count": "5"}}]}
        with self.assertRaisesRegex(ValueError, "conflicts with its accepted UMI"):
            apply_goal_meaning_update(typed, conflicting)

    def test_association_cannot_hide_what_rewrite_or_drop_a_source(self):
        base = {"relationship": "modify", "source_responsibility_refs": ["a", "b"], "target_goal_ids": ["g"],
                "requirement_changes": [{"target_goal_id": "g", "replace_requirement_indices": [0],
                                         "source_responsibility_refs": ["a", "b"]}]}
        self.assertEqual(len(GoalAssociationModelAssociation.model_validate(base).requirement_changes), 1)
        for change in ({**base, "updated_description": "new prose"},
                       {**base, "requirement_changes": [{**base["requirement_changes"][0], "source_responsibility_refs": ["a"]}]},
                       {**base, "relationship": "continue"}):
            with self.assertRaises(ValidationError):
                GoalAssociationModelAssociation.model_validate(change)



class GoalAssociationRepairPreservationTests(unittest.TestCase):
    @staticmethod
    def candidate_case():
        req = request("Continue the existing task.", language="en-US", active_goals=[
            active_goal("goal-a", "Prepare the report."),
            active_goal("goal-b", "Prepare another report."),
        ])
        valid = {
            "associations": [{"relationship": "continue", "source_responsibility_refs": ["r1"],
                              "target_goal_ids": ["goal-a"], "confidence": 1.0}],
            "new_goals": [], "referent_updates": [], "resolved_references": [],
            "confidence": 1.0, "reason_summary": "Continue the same goal.",
        }
        malformed = copy.deepcopy(valid)
        malformed["associations"] = malformed["associations"][0]
        return req, valid, malformed

    def test_shape_repair_cannot_change_existing_goal_decisions(self):
        req, valid, malformed = self.candidate_case()
        for field, replacement in (
            ("relationship", "cancel"), ("target_goal_ids", ["goal-b"]),
            ("confidence", 0.9), ("source_responsibility_refs", ["r2"]),
        ):
            with self.subTest(field=field):
                repaired = copy.deepcopy(valid)
                repaired["associations"][0][field] = replacement
                model = ScriptedOllama([malformed, repaired])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "fail_closed")
                self.assertEqual(result.associations, [])
                self.assertEqual(len(model.prompts), 2)
                self.assertFalse(result.metadata["retryable"])
                self.assertIn("semantic_preservation", result.metadata.get("repair_rejection", ""))

    def test_shape_only_repair_preserves_complete_primary_result(self):
        req, valid, malformed = self.candidate_case()
        before = copy.deepcopy(malformed)
        model = ScriptedOllama([malformed, valid])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(result.associations[0].relationship, "continue")
        self.assertTrue(result.metadata["goal_semantic_transaction"]["repair_semantics_verified"])
        self.assertEqual(malformed, before)
        self.assertEqual(len(model.prompts), 2)

    def test_shape_repair_cannot_change_requirement_replacement_scope(self):
        req, valid, _ = self.candidate_case()
        req.context["active_goal_snapshots"][0]["goal"]["success_criteria"] = ["Requirement A", "Requirement B"]
        item = valid["associations"][0]
        item["relationship"] = "modify"
        item["requirement_changes"] = [{"target_goal_id": "goal-a",
            "replace_requirement_indices": [0], "source_responsibility_refs": ["r1"]}]
        malformed = copy.deepcopy(valid)
        malformed["associations"] = malformed["associations"][0]
        repaired = copy.deepcopy(valid)
        repaired["associations"][0]["requirement_changes"][0]["replace_requirement_indices"] = [1]
        model = ScriptedOllama([malformed, repaired])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(result.associations, [])
        self.assertEqual(len(model.prompts), 2)
        self.assertIn("semantic_preservation", result.metadata.get("repair_rejection", ""))

    def test_rejected_cancel_repair_preserves_retained_goal_state(self):
        from orchestrator.runtime.conversation_state import ConversationStateManager
        manager = ConversationStateManager(base_conversation_id="ga-repair-containment")
        manager.apply_goal_association_resolution({
            "turn_id": "create", "resolution_status": "resolved", "confidence": 1.0,
            "new_goals": [{"goal_id": "goal-a", "description": "Prepare the report.",
                           "source_text": "Prepare the report."}],
        }, sid="create", user_text="Prepare the report.", atomic=True)
        req, valid, malformed = self.candidate_case()
        req.context["active_goal_snapshots"] = manager.active_goal_snapshots()
        repaired = copy.deepcopy(valid); repaired["associations"][0]["relationship"] = "cancel"
        model = ScriptedOllama([malformed, repaired])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        before = copy.deepcopy(manager.active_goal_snapshots())
        applied = manager.apply_goal_association_resolution(
            result, sid="repair", user_text=req.text, atomic=True
        )
        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(applied, [])
        self.assertEqual(manager.active_goal_snapshots(), before)

    def test_unknown_fields_are_not_erased_as_transport_noise(self):
        req, valid, _ = self.candidate_case()
        for nested in (False, True):
            with self.subTest(nested=nested):
                raw = copy.deepcopy(valid)
                surface = raw["associations"][0] if nested else raw
                surface["unrecognized_goal_decision"] = "cancel goal-a"
                model = ScriptedOllama([raw, valid])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "fail_closed")
                self.assertEqual(len(model.prompts), 1)

    def test_semantic_failure_hidden_inside_wrong_container_never_retries(self):
        req, valid, malformed = self.candidate_case()
        malformed["associations"]["source_responsibility_refs"] = ["missing"]
        model = ScriptedOllama([malformed, valid])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        self.assertEqual(result.resolution_status, "fail_closed")
        self.assertEqual(len(model.prompts), 1)
        self.assertFalse(result.metadata["goal_semantic_transaction"]["contract_repair_attempted"])


    def test_unrecoverable_container_does_not_authorize_new_meaning(self):
        req, valid, _ = self.candidate_case()
        for value in (None, "continue goal-a", 1):
            with self.subTest(value=value):
                raw = copy.deepcopy(valid); raw["associations"] = value
                model = ScriptedOllama([raw, valid])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "fail_closed")
                self.assertEqual(len(model.prompts), 1)

    def test_repair_prompt_never_truncates_the_primary_result(self):
        req, _, malformed = self.candidate_case()
        malformed["associations"]["reason_summary"] = "x" * 7100
        with self.assertRaisesRegex(ValueError, "required prompt projection budget"):
            ga_prompt.build_repair_prompt(request=req, candidate_goals=[], turn_id="turn",
                output_type=GoalAssociationModelOutput, raw=malformed, validation_error="[]")










class GoalAssociationOnlyContractTests(unittest.TestCase):
    """Current GA contract: association only; trusted code owns Goal materialization."""

    def _schema(self, refs=("r1",), candidates=None):
        candidates = list(candidates or [])
        output = GoalAssociationModelOutput if candidates else GoalSegmentationModelOutput
        return ga_schema.goal_association_response_schema(
            output, candidates, [], responsibility_count=len(refs),
            responsibility_refs=list(refs),
            responsibility_output_modes={ref: "speech" for ref in refs},
        )

    def test_live_model_schema_has_no_new_goal_authorship(self):
        for schema in (self._schema(), self._schema(candidates=[{"goal_id": "goal-old", "responsibility_status": "open"}])):
            self.assertNotIn("new_goals", schema["properties"])
            self.assertIn("unassociated_responsibility_refs", schema["properties"])
            self.assertNotIn("GoalAssociationModelGoal", schema.get("$defs", {}))

    def test_no_candidate_schema_requires_every_ref_unassociated(self):
        schema = self._schema(("r1", "r2"))
        validator = Draft202012Validator(schema)
        valid = {
            "unassociated_responsibility_refs": ["r1", "r2"],
            "referent_updates": [], "resolved_references": [],
            "cognitive_requests": [], "confidence": 1.0,
            "reason_summary": "No retained Goal matches.",
        }
        self.assertTrue(validator.is_valid(valid))
        self.assertFalse(validator.is_valid({**valid, "unassociated_responsibility_refs": ["r1"]}))
        self.assertFalse(validator.is_valid({**valid, "new_goals": []}))

    def test_candidate_schema_partitions_current_refs_between_associated_and_unassociated(self):
        retained = active_goal("goal-old", "Retained task")
        schema = self._schema(("r1", "r2"), [retained])
        validator = Draft202012Validator(schema)
        valid = {
            "associations": [{
                "relationship": "continue",
                "source_responsibility_refs": ["r1"],
                "target_goal_ids": ["goal-old"],
                "confidence": 1.0,
            }],
            "unassociated_responsibility_refs": ["r2"],
            "referent_updates": [], "resolved_references": [],
            "cognitive_requests": [], "confidence": 1.0,
            "reason_summary": "Only r1 continues retained work.",
        }
        self.assertTrue(validator.is_valid(valid))
        self.assertFalse(validator.is_valid({**valid, "unassociated_responsibility_refs": ["r1", "r2"]}))
        self.assertFalse(validator.is_valid({**valid, "unassociated_responsibility_refs": []}))

    def test_terminal_goal_is_history_not_mutable_association_target(self):
        terminal = active_goal("goal-done", "Finished task")
        terminal["responsibility_status"] = "satisfied"
        terminal["goal"]["responsibility_status"] = "satisfied"
        schema = self._schema(("r1",), [terminal])
        rendered = json.dumps(schema, ensure_ascii=False)
        self.assertNotIn('"goal-done"', json.dumps(schema.get("$defs", {}).get("GoalAssociationModelAssociation", {})))
        valid = {
            "associations": [], "unassociated_responsibility_refs": ["r1"],
            "referent_updates": [], "resolved_references": [],
            "cognitive_requests": [], "confidence": 1.0,
            "reason_summary": "Terminal history cannot absorb fresh responsibility.",
        }
        self.assertTrue(Draft202012Validator(schema).is_valid(valid), rendered[:500])

    def test_prompt_makes_current_responsibility_foreground_and_ga_association_only(self):
        req = request("Tell me a joke.", active_goals=[active_goal("goal-weather", "Check weather")])
        prompt = ga_prompt.layered_prompt(
            req, GoalAssociationResolver(FakeOllama({}))._candidate_goals(req),
            output_type=GoalAssociationModelOutput,
        ).render()
        self.assertIn("GA is association-only", prompt)
        self.assertIn("current UMI Responsibility is foreground semantic truth", prompt)
        self.assertIn("retained Goals are history", prompt)
        self.assertIn("If no retained Goal actually matches", prompt)
        self.assertIn("Do not author descriptions", prompt)

    def test_live_schema_rejects_model_authored_new_goal_payload(self):
        schema = self._schema(("r1",))
        forged = {
            "unassociated_responsibility_refs": ["r1"],
            "new_goals": [goal("forged", "speech")],
            "referent_updates": [], "resolved_references": [],
            "cognitive_requests": [], "confidence": 1.0,
            "reason_summary": "forged",
        }
        self.assertFalse(Draft202012Validator(schema).is_valid(forged))

    def test_trusted_materialization_inherits_weather_what_from_umi(self):
        req = request("Will it rain tomorrow in Chongqing?")
        req = req.model_copy(update={"responsibilities": typed_responsibilities({
            "local_ref": "r1",
            "outcome": "Establish whether it will rain tomorrow in Chongqing.",
            "bindings": {"location": "Chongqing", "time": "tomorrow"},
            "output_mode": "information", "continuity_scope": "goal", "confidence": 1.0,
        })})
        output = GoalSegmentationModelOutput.model_validate({
            "decision": "create_goals", "unassociated_responsibility_refs": ["r1"],
            "referent_updates": [], "resolved_references": [], "cognitive_requests": [],
            "confidence": 1.0, "reason_summary": "No retained Goal matches.",
        })
        result = asyncio.run(GoalAssociationResolver(FakeOllama({}))._materialize_primary_output(
            output, request=req, turn_id="turn-weather"
        ))
        self.assertEqual(len(result.new_goals), 1)
        created = result.new_goals[0]
        self.assertEqual(created.description, req.responsibilities[0].outcome)
        self.assertEqual(
            {name: value["value"] for name, value in created.object["bindings"].items()},
            req.responsibilities[0].bindings,
        )
        self.assertEqual(created.metadata["output_mode"], "information")
        self.assertEqual(created.metadata["goal_lifetime"], "working")
        self.assertEqual(created.metadata["goal_materialization_owner"], "trusted_runtime_from_umi")

    def test_trusted_materialization_creates_short_lived_interaction_goal_for_joke(self):
        req = request("Tell me a joke.")
        req = req.model_copy(update={"responsibilities": typed_responsibilities({
            "local_ref": "r1", "outcome": "Tell the user a joke.",
            "bindings": {}, "output_mode": "speech", "continuity_scope": "turn", "confidence": 1.0,
        })})
        output = GoalSegmentationModelOutput.model_validate({
            "decision": "no_goal", "unassociated_responsibility_refs": ["r1"],
            "referent_updates": [], "resolved_references": [], "cognitive_requests": [],
            "confidence": 1.0, "reason_summary": "No retained Goal matches.",
        })
        result = asyncio.run(GoalAssociationResolver(FakeOllama({}))._materialize_primary_output(
            output, request=req, turn_id="turn-joke"
        ))
        self.assertEqual(result.non_goal_responsibility_refs, [])
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].metadata["goal_lifetime"], "interaction")
        self.assertEqual(result.new_goals[0].description, "Tell the user a joke.")

    def test_existing_goal_continuity_produces_no_new_goal(self):
        retained = active_goal("goal-coffee", "Bring coffee to the user")
        req = request("Add ice to it.", active_goals=[retained])
        req = req.model_copy(update={"responsibilities": typed_responsibilities({
            "local_ref": "r1", "outcome": "Add ice to the coffee being prepared.",
            "bindings": {"modifier": "ice"}, "output_mode": "body_action",
            "body_effect_family": "task_physical_effect", "continuity_scope": "goal", "confidence": 1.0,
        })})
        output = GoalAssociationModelOutput.model_validate({
            "associations": [{
                "relationship": "modify", "source_responsibility_refs": ["r1"],
                "target_goal_ids": ["goal-coffee"],
                "requirement_changes": [{"target_goal_id": "goal-coffee", "replace_requirement_indices": [0], "source_responsibility_refs": ["r1"]}],
                "confidence": 1.0,
            }],
            "unassociated_responsibility_refs": [], "referent_updates": [],
            "resolved_references": [], "cognitive_requests": [], "confidence": 1.0,
            "reason_summary": "The new responsibility modifies retained coffee work.",
        })
        result = asyncio.run(GoalAssociationResolver(FakeOllama({}))._materialize_primary_output(
            output, request=req, turn_id="turn-ice"
        ))
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.associations[0].target_goal_ids, ["goal-coffee"])

    def test_emotion_is_context_evidence_not_an_invented_goal_fact(self):
        prompt = ga_prompt.system_prompt(GoalAssociationModelOutput)
        self.assertIn("do not invent motives or internal states", prompt)
