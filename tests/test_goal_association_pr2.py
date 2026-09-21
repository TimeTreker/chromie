from __future__ import annotations

from agent.app import goal_association_schema as ga_schema
from agent.app import goal_association_validation as ga_validation
from agent.app import goal_association_prompt as ga_prompt

import asyncio
import copy
import json
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
    return {
        "decision": "create_goals",
        "new_goals": list(goals),
        "cognitive_requests": [],
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



    def test_decoder_forbids_associate_and_supersede_same_retained_goal(self):
        retained = active_goal("goal-weather", "Provide weather information to the user.")
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput, [retained], [],
            responsibility_count=2,
            responsibility_refs=["r1", "r2"],
            responsibility_output_modes={"r1": "body_action", "r2": "body_action"},
        )
        validator = Draft202012Validator(schema)
        illegal = {
            "associations": [{
                "relationship": "continue",
                "source_responsibility_refs": ["r1"],
                "target_goal_ids": ["goal-weather"],
                "confidence": 1.0,
            }],
            "new_goals": [{
                "source_responsibility_refs": ["r2"],
                "related_goal_ids": [],
                "supersedes_goal_ids": ["goal-weather"],
            }],
            "referent_updates": [],
            "resolved_references": [],
            "cognitive_requests": [],
            "confidence": 1.0,
            "reason_summary": "Contradictory continuity result.",
        }
        assert not validator.is_valid(illegal)
        independent = copy.deepcopy(illegal)
        independent["new_goals"][0]["supersedes_goal_ids"] = []
        assert validator.is_valid(independent)

    def test_ga_prompt_declares_responsibility_refs_turn_local(self):
        req = request(
            "Walk ahead and wave.",
            language="en-US",
            active_goals=[active_goal("goal-weather", "Provide weather information to the user.")],
            responsibility_outcomes=["Walk ahead.", "Wave your hands."],
        )
        rendered = ga_prompt.system_prompt(GoalAssociationModelOutput)
        assert "turn-local identifiers" in rendered
        assert "same spelling" in rendered
        assert "only open candidate" in rendered

    def test_decoder_array_alternative_preserves_item_shape_and_cardinality(self):
        schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput, [], [],
            responsibility_count=2, responsibility_refs=["r1", "r2"],
            responsibility_output_modes={"r1": "body_action", "r2": "speech"},
        )
        array = schema["properties"]["new_goals"]
        exposed = Draft202012Validator({
            "$defs": schema["$defs"], **array["anyOf"][0],
        })
        full = Draft202012Validator({"$defs": schema["$defs"], **array})
        complete = Draft202012Validator(schema)
        values = [
            intent_goal("Blink twice.", "body_action"),
            intent_goal("Tell a joke.", "speech", source_responsibility_refs=["r2"]),
        ]
        # The body Work is mandatory; ordinary speech may either become a Goal
        # or be classified non_goal by GA. The array shape therefore permits one
        # or two Goals, while top-level conservation still owns r2 exactly once.
        for valid in (values, list(reversed(values)), values[:1]):
            self.assertTrue(exposed.is_valid(valid))
            self.assertTrue(full.is_valid(valid))
        complete_payload = {
            **create_goals(*values),
            "referent_updates": [], "resolved_references": [],
        }
        if "non_goal_responsibility_refs" in schema["required"]:
            complete_payload["non_goal_responsibility_refs"] = []
        self.assertTrue(complete.is_valid(complete_payload))
        social_only_r2 = {
            **create_goals(values[0]),
            "non_goal_responsibility_refs": ["r2"],
            "referent_updates": [], "resolved_references": [],
        }
        self.assertTrue(complete.is_valid(social_only_r2))
        self.assertFalse(complete.is_valid({
            **create_goals(values[0]),
            "referent_updates": [], "resolved_references": [],
        }))
        for invalid in ([], values + values[:1], [False, values[1]]):
            with self.subTest(invalid=invalid):
                self.assertFalse(exposed.is_valid(invalid))
                self.assertFalse(full.is_valid(invalid))
        for field in ("source_responsibility_refs", "related_goal_ids", "supersedes_goal_ids"):
            missing = copy.deepcopy(values)
            del missing[0][field]
            with self.subTest(missing=field):
                self.assertFalse(exposed.is_valid(missing))
        duplicate = {
            **create_goals(values[0], values[0]),
            "non_goal_responsibility_refs": ["r2"],
            "referent_updates": [], "resolved_references": [],
        }
        self.assertFalse(complete.is_valid(duplicate))

    def test_decoder_object_alternative_requires_complete_association_result(self):
        for refs in (["r1"], ["r1", "r2"]):
            schema = ga_schema.goal_association_response_schema(
                GoalAssociationModelOutput, [{"goal_id": "goal-a"}], [],
                responsibility_refs=refs, responsibility_count=len(refs),
            )
            payload = {
                "associations": [{
                    "relationship": "continue", "source_responsibility_refs": refs,
                    "target_goal_ids": ["goal-a"], "confidence": 1.0,
                }],
                "new_goals": [], "referent_updates": [], "resolved_references": [],
                "cognitive_requests": [],
                "confidence": 1.0, "reason_summary": "Continue retained work.",
            }
            complete = Draft202012Validator(schema)
            # The pinned decoder chooses this alternative before sibling
            # intersections. Exercise its accepted objects, not source text.
            exposed = Draft202012Validator({
                "$defs": schema["$defs"], **schema["anyOf"][0],
            })
            self.assertTrue(complete.is_valid(payload))
            self.assertTrue(exposed.is_valid(payload))
            for field in payload:
                with self.subTest(refs=refs, missing=field):
                    missing = copy.deepcopy(payload)
                    del missing[field]
                    self.assertFalse(exposed.is_valid(missing))
            duplicate = copy.deepcopy(payload)
            duplicate["associations"] *= 2
            self.assertFalse(complete.is_valid(duplicate))
            omitted = copy.deepcopy(payload)
            omitted["associations"] = []
            self.assertFalse(complete.is_valid(omitted))

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

    def test_decoder_multi_goal_array_enforces_items_and_cardinality(self):
        for count in (2, 8):
            for mode in ("speech", "body_action"):
                refs = [f"r{index}" for index in range(1, count + 1)]
                schema = ga_schema.goal_association_response_schema(
                    GoalSegmentationModelOutput, [], [],
                    responsibility_count=count, responsibility_refs=refs,
                    responsibility_output_modes={ref: mode for ref in refs},
                )
                goals = [
                    intent_goal("Accepted responsibility.", mode, source_responsibility_refs=[ref])
                    for ref in refs
                ]
                payload = {
                    **create_goals(*goals), "referent_updates": [], "resolved_references": [],
                }
                if "non_goal_responsibility_refs" in schema["required"]:
                    payload["non_goal_responsibility_refs"] = []
                complete = Draft202012Validator(schema)
                self.assertTrue(complete.is_valid(payload))
                array = schema["properties"]["new_goals"]
                with self.subTest(count=count, mode=mode):
                    if mode == "body_action":
                        self.assertIn("anyOf", array)
                        exposed = Draft202012Validator({
                            "$defs": schema["$defs"], **array["anyOf"][0],
                        })
                        for valid in (goals, list(reversed(goals))):
                            self.assertTrue(exposed.is_valid(valid))
                            self.assertTrue(complete.is_valid({**payload, "new_goals": valid}))
                        for invalid in (
                            {}, None, [], goals[:-1], goals + [goals[0]],
                            [None, *goals[1:]], [7, *goals[1:]], [{}, *goals[1:]],
                            [{**goals[0], "output_mode": "unknown"}, *goals[1:]],
                            [{**goals[0], "source_responsibility_refs": ["unknown"]}, *goals[1:]],
                            [{**goals[0], "bindings": "invalid"}, *goals[1:]],
                        ):
                            with self.subTest(invalid=invalid):
                                self.assertFalse(exposed.is_valid(invalid))
                                self.assertFalse(complete.is_valid({**payload, "new_goals": invalid}))
                        duplicate = [goals[0], *goals[:-1]]
                        self.assertFalse(complete.is_valid({**payload, "new_goals": duplicate}))
                    else:
                        # Speech is allowed to remain a Goal when continuity requires
                        # one, but GA may instead classify any relation-free subset as
                        # non_goal. The schema must not hard-force a Goal count.
                        self.assertEqual(array["minItems"], 0)
                        no_goal = {
                            "decision": "no_goal",
                            "new_goals": [],
                            "non_goal_responsibility_refs": refs,
                            "referent_updates": [],
                            "resolved_references": [],
                            "cognitive_requests": [],
                            "confidence": 1.0,
                            "reason_summary": "Conversation is complete without Goal state.",
                        }
                        self.assertTrue(complete.is_valid(no_goal))
                        mixed = {
                            **create_goals(goals[0]),
                            "non_goal_responsibility_refs": refs[1:],
                            "referent_updates": [],
                            "resolved_references": [],
                        }
                        self.assertTrue(complete.is_valid(mixed))




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
                        "bindings": {"count": "1 次"},
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

    def test_unknown_physical_source_grounding_is_rejected_without_deletion(self):
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

        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(ValueError, "inactive physical source"):
            ga_validation.normalize_resource_binding_branches(raw)
        self.assertEqual(raw, before)

    def test_invalid_optional_resource_quantity_is_rejected_without_deletion(self):
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

        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(ValidationError, "resource quantity"):
            GoalSegmentationModelOutput.model_validate(raw)
        self.assertEqual(raw, before)

    def test_new_goal_inherits_source_outcome_and_forbids_reauthored_description(self):
        req = request("Tell me whether this is correct.", language="en-US")
        raw = create_goals(intent_goal("fixture label", "speech"))
        model = ScriptedOllama([raw])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        self.assertEqual(result.new_goals[0].description, req.responsibilities[0].outcome)
        self.assertEqual(result.new_goals[0].success_criteria, [req.responsibilities[0].outcome])
        self.assertEqual(len(model.prompts), 1)
        raw["new_goals"][0]["description"] = "Tell the user this is correct."
        with self.assertRaises(ValidationError):
            GoalSegmentationModelOutput.model_validate(raw)
        parsed = GoalAssociationModelGoal.model_validate(intent_goal("label", "speech", source_responsibility_refs=["unknown"]))
        with self.assertRaisesRegex(ValueError, "exact unique UMI"):
            ga_validation.inherited_goal_outcomes(parsed, req)

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
        self.assertIn("Every supplied Responsibility ref must occur exactly once", prompt)
        self.assertIn("Planner decomposes Activities", prompt)
        self.assertIn("Host inherits UMI", prompt)
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
        self.assertIn("you own that judgment", prompt)
        self.assertNotIn('"relationship":"continue"', prompt)
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
        goal_schema = schema["$defs"]["GoalAssociationModelGoal"]
        self.assertEqual(
            list(schema["properties"]),
            [
                "associations",
                "new_goals",
                "referent_updates",
                "resolved_references",
                "cognitive_requests",
                "confidence",
                "reason_summary",
            ],
        )
        self.assertEqual(list(goal_schema["properties"]),
                         ["source_responsibility_refs", "related_goal_ids", "supersedes_goal_ids"])
        self.assertIn("confidence", association_schema["required"])
        self.assertIn("target_goal_ids", association_schema["required"])
        self.assertNotIn("decision", schema["properties"])
        self.assertNotIn("description", goal_schema["properties"])

        validator = Draft202012Validator(schema)
        contradictory_replacement = {
            "associations": [],
            "new_goals": [intent_goal("unused", "body_action", related_goal_ids=["goal-walk"], supersedes_goal_ids=["goal-walk"])],
            "referent_updates": [], "resolved_references": [], "cognitive_requests": [],
            "confidence": 1.0, "reason_summary": "Replace the retained Goal.",
        }
        self.assertTrue(list(validator.iter_errors(contradictory_replacement)))
        contradictory_replacement["new_goals"][0]["related_goal_ids"] = []
        self.assertEqual(
            list(validator.iter_errors(contradictory_replacement)),
            [],
        )


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
        valid = create_goals(intent_goal("Blink twice.", "body_action"))
        invalid = copy.deepcopy(valid)
        invalid["new_goals"] = invalid["new_goals"][0]
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

    def test_semantic_dto_errors_never_start_mechanical_repair(self):
        valid = create_goals(goal("Walk slowly.", "body_action", bindings=[
            binding("speed", "speed", "slow")
        ]))
        cases = []
        for speed in ("走边", "quickly"):
            invalid = copy.deepcopy(valid)
            invalid["new_goals"][0]["bindings"][0]["value"] = speed
            cases.append((f"semantic_speed_{speed}", invalid))
        mixed = copy.deepcopy(cases[0][1])
        mixed["unexpected_transport_field"] = "structural error too"
        cases.append(("mixed_structural_and_semantic", mixed))
        for name, value in (("output_mode", "unsupported_mode"),
                            ("source_responsibility_refs", [])):
            invalid = copy.deepcopy(valid)
            invalid["new_goals"][0][name] = value
            cases.append((name, invalid))
        missing = copy.deepcopy(valid)
        del missing["new_goals"][0]["output_mode"]
        cases.append(("missing_semantic_field", missing))
        out_of_range = copy.deepcopy(valid)
        out_of_range["confidence"] = 1.5
        cases.append(("invalid_confidence", out_of_range))
        for name, invalid in cases:
            with self.subTest(case=name):
                ollama = ScriptedOllama([invalid, valid])
                result = self._resolve(ollama, request("Walk slowly."))

                self.assert_transaction(
                    result, ollama, terminal="fail_closed",
                    families=["goal_association.primary"],
                )
                self.assertEqual(result.new_goals, [])
                self.assertEqual(result.associations, [])
                self.assertFalse(result.metadata["retryable"])
                self.assertEqual(result.metadata["failure_class"],
                                 "structured_output_validation")
                self.assertFalse(result.metadata["goal_semantic_transaction"]
                                 ["contract_repair_attempted"])








    def test_decoder_reduction_preserves_independent_and_unresolved_constraints(self):
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput, [{"goal_id": "g1"}], [],
            responsibility_refs=["r1", "r2"],
            responsibility_output_modes={"r1": "body_action", "r2": "speech"},
        )
        self.assertEqual(len(schema["allOf"]), 3)
        # Two Responsibility-conservation constraints plus one retained-Goal
        # continuity-fate exclusivity constraint.
        goal_schema = schema["$defs"]["GoalAssociationModelGoal"]
        # An ID still cannot be both retained and superseded.
        self.assertEqual(len(goal_schema["allOf"]), 1)
        self.assertIn("not", goal_schema["allOf"][0])
        schema = ga_schema.goal_association_response_schema(
            GoalSegmentationModelOutput, [], [], responsibility_refs=["r1", "r2"],
        )
        self.assertEqual(len(schema["properties"]["new_goals"]["allOf"]), 2)
        valid = create_goals(intent_goal("A", "body_action"), intent_goal("B", "speech", source_responsibility_refs=["r2"]))
        valid.update(referent_updates=[], resolved_references=[])
        self.assertTrue(Draft202012Validator(schema).is_valid(valid))
        for field in ("bindings", "output_mode", "resource_kind"):
            invalid = copy.deepcopy(valid)
            invalid["new_goals"][0][field] = "forbidden authoring"
            self.assertFalse(Draft202012Validator(schema).is_valid(invalid))

    def test_invalid_contract_repair_fails_closed_without_third_call(self):
        invalid = create_goals(intent_goal("Blink twice.", "body_action"))
        invalid["new_goals"] = invalid["new_goals"][0]
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

    def test_decoder_excludes_terminal_goal_from_association_targets(self):
        terminal = active_goal("goal-weather", "Check Chongqing weather.")
        terminal["responsibility_status"] = "satisfied"
        terminal["work_status"] = "done"
        terminal["goal"]["responsibility_status"] = "satisfied"
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput,
            [terminal],
            [],
            responsibility_count=1,
            responsibility_refs=["r1"],
        )
        self.assertEqual(schema["properties"]["associations"]["maxItems"], 0)
        association = schema["$defs"]["GoalAssociationModelAssociation"]
        self.assertEqual(
            association["properties"]["target_goal_ids"]["items"]["enum"],
            [],
        )
        goal = schema["$defs"]["GoalAssociationModelGoal"]
        self.assertEqual(
            goal["properties"]["related_goal_ids"]["items"]["enum"],
            ["goal-weather"],
        )

    def test_terminal_history_exposes_new_goal_only_ownership_to_decoder(self):
        terminal = active_goal("goal-weather", "Check Chongqing weather.")
        terminal["responsibility_status"] = "satisfied"
        terminal["work_status"] = "done"
        terminal["goal"]["responsibility_status"] = "satisfied"
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput,
            [terminal],
            [],
            responsibility_count=2,
            responsibility_refs=["walk", "gesture"],
            responsibility_output_modes={
                "walk": "body_action",
                "gesture": "body_action",
            },
        )

        self.assertEqual(schema["properties"]["associations"]["maxItems"], 0)
        new_goals = schema["properties"]["new_goals"]
        self.assertEqual(new_goals["minItems"], 2)
        self.assertEqual(new_goals["maxItems"], 2)
        self.assertEqual(len(new_goals["prefixItems"]), 2)
        self.assertEqual(
            new_goals["prefixItems"][0]["properties"]
            ["source_responsibility_refs"]["items"]["enum"],
            ["walk"],
        )
        self.assertEqual(
            new_goals["prefixItems"][1]["properties"]
            ["source_responsibility_refs"]["items"]["enum"],
            ["gesture"],
        )
        payload = {
            "associations": [],
            "new_goals": [
                intent_goal("Walk.", "body_action", source_responsibility_refs=["walk"]),
                intent_goal("Gesture.", "body_action", source_responsibility_refs=["gesture"]),
            ],
            "referent_updates": [],
            "resolved_references": [],
            "cognitive_requests": [],
            "confidence": 1.0,
            "reason_summary": "Both new embodied outcomes require new Goal ownership.",
        }
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(payload))
        reversed_payload = {**payload, "new_goals": list(reversed(payload["new_goals"]))}
        self.assertFalse(validator.is_valid(reversed_payload))

    def test_decoder_associations_target_only_open_goals_while_terminal_remains_related_context(self):
        open_goal = active_goal("goal-open", "Walk forward.")
        terminal = active_goal("goal-done", "Check Chongqing weather.")
        terminal["responsibility_status"] = "satisfied"
        terminal["work_status"] = "done"
        terminal["goal"]["responsibility_status"] = "satisfied"
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput, [open_goal, terminal], [],
            responsibility_count=1, responsibility_refs=["r1"],
        )
        association = schema["$defs"]["GoalAssociationModelAssociation"]
        self.assertEqual(
            association["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-open"],
        )
        goal = schema["$defs"]["GoalAssociationModelGoal"]
        self.assertEqual(
            goal["properties"]["related_goal_ids"]["items"]["enum"],
            ["goal-open", "goal-done"],
        )

    def test_terminal_history_cannot_be_replaced_or_both_related_and_replaced(self):
        for status in ("satisfied", "cancelled", "refused", "superseded"):
            terminal = active_goal("goal-weather", "Check Chongqing weather.")
            terminal["responsibility_status"] = status
            terminal["goal"]["responsibility_status"] = status
            for related in ([], ["goal-weather"]):
                with self.subTest(status=status, related=related):
                    raw = {
                        "associations": [],
                        "new_goals": [intent_goal(
                            "Will it rain today?", "information",
                            related_goal_ids=related,
                            supersedes_goal_ids=["goal-weather"],
                        )],
                        "referent_updates": [], "resolved_references": [],
                        "cognitive_requests": [], "confidence": 1.0,
                        "reason_summary": "Follow up on the previous weather result.",
                    }
                    schema = ga_schema.goal_association_response_schema(
                        GoalAssociationModelOutput, [terminal], [],
                        responsibility_count=1, responsibility_refs=["r1"],
                        responsibility_output_modes={"r1": "information"},
                    )
                    self.assertFalse(Draft202012Validator(schema).is_valid(raw))
                    req = request("Will it rain today?", active_goals=[terminal])
                    result = self._resolve([raw], req)
                    self.assertEqual(result.resolution_status, "fail_closed")
                    self.assertEqual(result.new_goals, [])
                    valid = copy.deepcopy(raw)
                    valid["new_goals"][0]["supersedes_goal_ids"] = []
                    self.assertTrue(Draft202012Validator(schema).is_valid(valid))
                    self.assertEqual(self._resolve([valid], req).resolution_status, "resolved")

    def test_mixed_candidates_allow_only_open_replacement_targets(self):
        current = active_goal("goal-open", "An unfinished lookup.")
        terminal = active_goal("goal-done", "A completed lookup.")
        terminal["responsibility_status"] = "satisfied"
        terminal["goal"]["responsibility_status"] = "satisfied"
        schema = ga_schema.goal_association_response_schema(
            GoalAssociationModelOutput, [current, terminal], [],
            responsibility_count=1, responsibility_refs=["r1"],
            responsibility_output_modes={"r1": "information"},
        )
        raw = {
            "associations": [],
            "new_goals": [intent_goal(
                "Replace the unfinished lookup.", "information",
                related_goal_ids=["goal-done"], supersedes_goal_ids=["goal-open"],
            )],
            "referent_updates": [], "resolved_references": [],
            "cognitive_requests": [], "confidence": 1.0, "reason_summary": "Replace.",
        }
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(raw))
        raw["new_goals"][0]["related_goal_ids"] = []
        raw["new_goals"][0]["supersedes_goal_ids"] = ["goal-done"]
        self.assertFalse(validator.is_valid(raw))

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
                        intent_goal(
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
                    "new_goals": [intent_goal("Duplicate responsibility.", "speech")],
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
    def test_minimal_ga_new_goal_inherits_umi_bindings_without_reauthoring(self):
        cases = (
            (
                "what's the weather today in chongqing?",
                {"location": "chongqing", "time_reference": "today"},
                "information",
                {"location": "location", "time_reference": "temporal_scope"},
            ),
            (
                "nod your head 5 times, please",
                {"count": 5},
                "body_action",
                {"count": "count"},
            ),
        )
        for text, bindings, output_mode, entity_types in cases:
            with self.subTest(text=text):
                req = request(text, language="en-US").model_copy(
                    update={
                        "responsibilities": typed_responsibilities(
                            {
                                "local_ref": "r1",
                                "outcome": text.rstrip("?., "),
                                "bindings": bindings,
                                "output_mode": output_mode,
                                "confidence": 1.0,
                            }
                        )
                    }
                )
                raw = create_goals(intent_goal("unused", output_mode))
                model = ScriptedOllama([raw])

                result = asyncio.run(GoalAssociationResolver(model).resolve(req))

                self.assertEqual(result.resolution_status, "resolved", result.metadata)
                inherited = result.new_goals[0].object["bindings"]
                self.assertEqual(set(inherited), set(bindings))
                for name, value in bindings.items():
                    self.assertEqual(inherited[name]["value"], value)
                    self.assertEqual(inherited[name]["entity_type"], entity_types[name])
                self.assertEqual(result.new_goals[0].metadata["output_mode"], output_mode)

                # The live GA decoder still has no writable semantic-binding
                # surface: the Host inheritance above is not GA re-authoring.
                schema = model.prompts[0][1]["response_format"]
                forged = copy.deepcopy(raw)
                forged["new_goals"][0]["bindings"] = []
                self.assertFalse(Draft202012Validator(schema).is_valid(forged))

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

    def test_bilingual_new_goal_preserves_polarity_freshness_and_historical_scope(self):
        for outcome in (
            "Tell me whether the result is correct.",
            "Measure the value again, preserving the new observation requirement.",
            "Report the previous measurement, without replacing it with a new one.",
            "告诉我这个结果是否正确。",
            "重新测量一次，必须使用新的观察。",
            "告诉我上一次的测量结果，不要用新的结果替代。",
        ):
            with self.subTest(outcome=outcome):
                req = request(outcome)
                model = ScriptedOllama([create_goals(intent_goal("unused label", "speech"))])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "resolved")
                inherited = result.new_goals[0]
                self.assertEqual(inherited.description, outcome)
                self.assertEqual(inherited.success_criteria, [outcome])
                self.assertEqual(inherited.metadata["requirement_sources"][0]["responsibility"],
                                 req.responsibilities[0].model_dump(mode="json"))
                from agent.app.planner_context import goal_association_prompt_projection
                projection = result.prompt_projection()
                dictionary_projection = goal_association_prompt_projection({
                    "goal_association_resolution": result.model_dump(mode="json")})
                for packet in (projection, dictionary_projection):
                    self.assertEqual(packet["new_goals"][0]["metadata"]["requirement_sources"],
                                     inherited.metadata["requirement_sources"])
                self.assertEqual(len(model.prompts), 1)
                schema = model.prompts[0][1]["response_format"]
                forged = create_goals(intent_goal("unused label", "speech"))
                forged["new_goals"][0]["description"] = "An independently authored interpretation."
                self.assertFalse(Draft202012Validator(schema).is_valid(forged))

    def test_partial_goal_change_retains_sources_evidence_and_survives_restart(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from orchestrator.runtime.conversation_state import ConversationStateManager
        from shared.chromie_contracts.semantic_task import SemanticGoal

        with TemporaryDirectory() as directory:
            store = Path(directory) / "goals.json"
            manager = ConversationStateManager(base_conversation_id="inheritance", task_store_enabled=True,
                                               task_store_path=store)
            original = SemanticGoal(
                goal_id="goal-retained", description="Keep A; Do B three times.",
                source_text="Original admitted source.", success_criteria=["Keep A", "Do B three times."],
                source_responsibility_refs=["r-old"], related_goal_ids=["goal-context"],
                object={"bindings": {"count": {"name": "count", "entity_type": "count", "value": "3"}}},
                constraints={"style": "quiet"},
                resource_responsibility=AcquireAndDeliverResource(
                    resource=ResourceDescriptor(kind="physical_object", description="retained bottle"),
                    source=ResourceSource(status="unknown"), recipient=ResourceRecipient(description="user"),
                    delivery_mode="physical_handover"),
                metadata={"output_mode": "body_action"},
            )
            manager.apply_goal_association_resolution(
                GoalAssociationResolution(turn_id="turn-original", resolution_status="resolved", new_goals=[original]),
                sid="sid-original", user_text=original.source_text, atomic=True)
            context = manager._task_contexts[0]
            context["evidence_summary"] = {"retained_execution_outcomes": [{"outcome_id": "observed-old"}]}
            context["plan_version"] = 2
            context["plan_status"] = "proposed"
            req = request("Do B five times.", active_goals=manager.active_goal_snapshots()).model_copy(update={
                "responsibilities": typed_responsibilities({"local_ref": "r1", "outcome": "Do B five times.",
                    "bindings": {"count": "5"}, "output_mode": "body_action", "confidence": 1.0})})
            raw = {"associations": [{"relationship": "modify", "source_responsibility_refs": ["r1"],
                "target_goal_ids": ["goal-retained"], "confidence": 1.0,
                "requirement_changes": [{"target_goal_id": "goal-retained", "replace_requirement_indices": [1],
                    "source_responsibility_refs": ["r1"], "binding_changes": [{
                        "path": ["object", "bindings", "count", "value"],
                        "source_responsibility_ref": "r1", "source_binding": "count"}]}]}],
                "new_goals": [], "referent_updates": [], "resolved_references": [], "cognitive_requests": [],
                "reason_summary": "Refine the second retained requirement.", "confidence": 1.0}
            model = ScriptedOllama([raw])
            resolution = asyncio.run(GoalAssociationResolver(model).resolve(req))
            self.assertEqual(resolution.resolution_status, "resolved")
            self.assertEqual([error.message for error in Draft202012Validator(model.prompts[0][1]["response_format"]).iter_errors(raw)], [])
            applied = manager.apply_goal_association_resolution(resolution, sid=req.sid, user_text=req.text, atomic=True)
            self.assertTrue(all(item.get("applied") for item in applied), applied)
            after = manager._task_contexts[0]
            current = after["semantic_goal"]
            self.assertEqual(current["success_criteria"], ["Keep A", "Do B five times."])
            self.assertEqual(current["description"], "Keep A; Do B five times.")
            self.assertEqual(current["object"]["bindings"]["count"]["value"], "5")
            for field in ("constraints", "resource_responsibility", "related_goal_ids", "source_text"):
                self.assertEqual(current[field], original.model_dump(mode="json", exclude_none=True)[field])
            self.assertEqual(current["source_responsibility_refs"], ["r-old", "r1"])
            self.assertEqual(after["evidence_summary"]["retained_execution_outcomes"], [{"outcome_id": "observed-old"}])
            self.assertEqual(after["plan_version"], 2)
            self.assertEqual(after["plan_status"], "proposed")
            self.assertEqual(after["goal_revision_history"][0]["prior_goal"]["success_criteria"], original.success_criteria)
            self.assertEqual(len(model.prompts), 1)
            for forged_update in (
                {"by_goal_id": {"goal-retained": {"description": "Unattributed overwrite"}}},
                {"by_goal_id": {"goal-retained": {**resolution.associations[0].goal_update["by_goal_id"]["goal-retained"],
                                                  "source_turn_id": "foreign-turn"}}},
            ):
                forged = resolution.model_copy(deep=True)
                forged.associations[0].association_id += "-forged"
                forged.associations[0].goal_update = forged_update
                rejected = manager.apply_goal_association_resolution(forged, sid="forged", user_text=req.text, atomic=True)
                self.assertTrue(any(item.get("reason") == "source_bound_goal_update_required" for item in rejected))
                self.assertEqual(manager._task_contexts[0]["semantic_goal"], current)
            replay = resolution.model_copy(deep=True)
            replay.associations[0].association_id += "-stale"
            rejected = manager.apply_goal_association_resolution(replay, sid="stale", user_text=req.text, atomic=True)
            self.assertTrue(any(item.get("applied") is False for item in rejected))
            self.assertEqual(manager._task_contexts[0]["semantic_goal"], current)
            restored = ConversationStateManager(base_conversation_id="inheritance", task_store_enabled=True,
                                                task_store_path=store)
            self.assertEqual(restored._task_contexts[0]["semantic_goal"], current)
            self.assertEqual(restored._task_contexts[0]["goal_revision_history"], after["goal_revision_history"])

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

    def test_structured_umi_binding_is_referenced_without_reauthoring(self):
        retained = active_goal("goal-region", "Arrange the items in the specified region.")
        retained["goal"]["constraints"] = {"region": {"room": "desk", "offset": [0, 0]}}
        structured_value = {"room": "desk", "offset": [1, 2]}
        req = request("Arrange them in this region.", active_goals=[retained]).model_copy(update={
            "responsibilities": typed_responsibilities({"local_ref": "r1", "outcome": "Arrange the items in the specified region.",
                "bindings": {"region": structured_value}, "output_mode": "body_action", "confidence": 1.0})})
        raw = {"associations": [{"relationship": "modify", "source_responsibility_refs": ["r1"],
            "target_goal_ids": ["goal-region"], "confidence": 1.0, "requirement_changes": [{
                "target_goal_id": "goal-region", "replace_requirement_indices": [0],
                "source_responsibility_refs": ["r1"], "binding_changes": [{"path": ["constraints", "region"],
                    "source_responsibility_ref": "r1", "source_binding": "region"}]}]}],
            "new_goals": [], "referent_updates": [], "resolved_references": [], "cognitive_requests": [],
            "confidence": 1.0, "reason_summary": "Apply the accepted region to the retained requirement."}
        model = ScriptedOllama([raw])
        result = asyncio.run(GoalAssociationResolver(model).resolve(req))
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual([e.message for e in Draft202012Validator(model.prompts[0][1]["response_format"]).iter_errors(raw)], [])
        from shared.chromie_contracts.semantic_task import SemanticGoal, apply_goal_meaning_update
        changed = apply_goal_meaning_update(SemanticGoal.model_validate(retained["goal"]),
                    result.associations[0].goal_update["by_goal_id"]["goal-region"])
        self.assertEqual(changed.constraints["region"], structured_value)
        self.assertEqual(len(model.prompts), 1)


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

    def test_invalid_optional_semantics_are_not_deleted_before_validation(self):
        req = request("Bring the bottle from ahead.", language="en-US")
        base = create_goals(goal("label", "body_action"))
        cases = []
        for update in (
            {"operation": "introduce", "confidence": 1.0},
            {"operation": "correct", "entity_type": "person", "canonical_value": "Dad", "confidence": 1.0},
        ):
            raw = copy.deepcopy(base); raw["referent_updates"] = [update]; cases.append(raw)
        bad_quantity = create_goals(goal("label", "body_action", resource=resource_responsibility(
            description="bottle", quantity=",", source_status="known", source_description="ahead",
            source_bindings=[binding("direction", "direction", "ahead")],
        )))
        cases.append(bad_quantity)
        wrong_decision = copy.deepcopy(base); wrong_decision["decision"] = "cancel"; cases.append(wrong_decision)
        for raw in cases:
            with self.subTest(raw=raw):
                before = copy.deepcopy(raw)
                model = ScriptedOllama([raw])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "fail_closed")
                self.assertEqual(result.new_goals, [])
                self.assertEqual(raw, before)
                self.assertEqual(len(model.prompts), 1)

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

    def test_shape_repair_cannot_change_new_goal_values_or_cardinality(self):
        req = request("点头1次。")
        valid = create_goals(intent_goal("label", "body_action"))
        malformed = copy.deepcopy(valid)
        malformed["new_goals"] = malformed["new_goals"][0]
        changed = copy.deepcopy(valid); changed["new_goals"][0]["source_responsibility_refs"] = ["r2"]
        omitted = copy.deepcopy(valid); omitted["new_goals"].clear()
        added = copy.deepcopy(valid); added["new_goals"].append(copy.deepcopy(added["new_goals"][0]))
        for repaired, accepted in ((valid, True), (changed, False), (omitted, False), (added, False)):
            with self.subTest(repaired=repaired):
                model = ScriptedOllama([malformed, repaired])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(len(model.prompts), 2)
                self.assertEqual(result.resolution_status, "resolved" if accepted else "fail_closed")
                if accepted:
                    self.assertEqual(result.new_goals[0].description, "点头1次。")
                else:
                    self.assertEqual(result.new_goals, [])
                    self.assertIn("semantic_preservation", result.metadata.get("repair_rejection", ""))

    def test_malformed_active_resource_branch_is_not_overwritten(self):
        resource = resource_responsibility(kind="information", description="package status",
            attributes=[binding("tracking_number", "identifier", "ABC123")], source_status="provider_resolved")
        resource["query_scope"] = {"authored_but_malformed": "ABC123"}
        raw = create_goals(goal("label", "information", resource=resource,
            bindings=[binding("carrier", "organization", "ParcelCo")]))
        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(ValueError, "malformed active resource"):
            ga_validation.normalize_resource_binding_branches(raw)
        self.assertEqual(raw, before)

    def test_resource_binding_move_requires_an_unambiguous_destination(self):
        resources = []
        information = resource_responsibility(kind="information", source_status="provider_resolved")
        information["query_scope"] = None
        resources.append(information)
        for source in (None, "unknown"):
            physical = resource_responsibility()
            physical["source"] = source
            resources.append(physical)
        missing_source = resource_responsibility()
        del missing_source["source"]
        resources.append(missing_source)
        for resource in resources:
            with self.subTest(resource=resource):
                raw = create_goals(goal("label", "body_action", resource=resource,
                    bindings=[binding("location", "location", "ahead")]))
                before = copy.deepcopy(raw)
                with self.assertRaises(ValueError):
                    ga_validation.normalize_resource_binding_branches(raw)
                self.assertEqual(raw, before)

    def test_malformed_new_goal_references_cannot_be_deleted(self):
        req = request("Tell a joke.", active_goals=[active_goal("goal-a", "Old task.")], language="en-US")
        for field in ("related_goal_ids", "supersedes_goal_ids"):
            with self.subTest(field=field):
                raw = create_goals(goal("label", "speech"))
                raw.pop("decision", None)
                raw["new_goals"][0][field] = {"goal_id": "goal-a"}
                before = copy.deepcopy(raw)
                model = ScriptedOllama([raw])
                result = asyncio.run(GoalAssociationResolver(model).resolve(req))
                self.assertEqual(result.resolution_status, "fail_closed")
                self.assertEqual(result.new_goals, [])
                self.assertEqual(len(model.prompts), 1)
                self.assertEqual(raw, before)
