from __future__ import annotations

import asyncio
import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import (
    GoalAssociationModelGoal,
    GoalAssociationModelInformationResourceResponsibility,
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
        "description": description,
        "output_mode": output_mode,
        "bindings": list(bindings or []),
        **extra,
    }
    if resource is not None:
        payload["resource_responsibility"] = resource
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
) -> dict:
    return {
        "source_excerpt": source_excerpt,
        "role": role,
        "coverage": coverage,
        "independently_satisfiable": (
            independently_satisfiable if role == "responsibility" else False
        ),
        "candidate_goal_indices": list(goal_indices),
    }


def certificate(*items: dict) -> dict:
    return {
        "items": list(items),
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
) -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": text,
                "bindings": {},
                "completion_requires_work": True,
                "completion_requires_fresh_evidence": False,
                "confidence": 0.9,
            }
        ],
        interpretation_confidence=0.9,
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
            clarification="",
        )
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather["new_goals"][0]["output_mode"] = "capability_work"
        self.assertEqual(list(goal_validator.iter_errors(weather)), [])
        weather["new_goals"][0]["bindings"] = [
            binding("location", "location", "Chongqing")
        ]
        self.assertTrue(list(goal_validator.iter_errors(weather)))
        weather["new_goals"][0]["bindings"] = []

        bounded_goal_schema = GoalAssociationResolver._response_schema(
            GoalSegmentationModelOutput,
            [],
            [],
            responsibility_count=2,
        )
        bounded_goal_validator = Draft202012Validator(bounded_goal_schema)
        two_body_actions = create_goals(
            goal("Run forward for 15 seconds.", "body_action"),
            goal("Blink.", "body_action"),
        )
        two_body_actions.update(
            referent_updates=[],
            resolved_references=[],
            clarification="",
        )
        self.assertEqual(
            list(bounded_goal_validator.iter_errors(two_body_actions)),
            [],
        )
        three_goals = create_goals(
            *two_body_actions["new_goals"],
            goal("Say that the actions are being handled.", "speech"),
        )
        three_goals.update(
            referent_updates=[],
            resolved_references=[],
            clarification="",
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
            clarification="",
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
            clarification="",
        )
        self.assertTrue(list(goal_validator.iter_errors(typed_physical_attribute)))

        coverage_schema = GoalAssociationResolver._coverage_certificate_response_schema(
            1
        )
        Draft202012Validator.check_schema(coverage_schema)
        coverage_validator = Draft202012Validator(coverage_schema)
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
                "I am a little tired",
                role="context",
                independently_satisfiable=False,
            )
        )
        self.assertEqual(list(coverage_validator.iter_errors(valid_context)), [])

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

    def test_coverage_normalizes_clarification_with_named_candidate_by_dropping_owner(self):
        req = request("把那个拿过来")
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
        self.assertEqual(parsed.items[0].candidate_goal_indices, [])

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
        self.assertIn('"activity_id":"vocal_1"', prompt)
        self.assertIn('"role":"progress"', prompt)
        self.assertIn("Response wording is intentionally absent", prompt)
        self.assertIn("must never become or justify a sibling Goal", prompt)

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
        self.assertIn("state mutation or deferred effect", prompt)
        self.assertIn("representation_mismatch", prompt)
        self.assertIn("drops or generalizes a material qualifier", prompt)
        self.assertIn("candidate_goal_indices must be empty", prompt)

    def test_goal_prompts_distinguish_body_action_from_physical_resource(self):
        resolver = GoalAssociationResolver(FakeOllama({}))
        req = request("Run forward for 15 seconds, then blink.", language="en-US")
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
                        "bindings": {"location": "重庆", "time": "tonight"},
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
                resource=resource_responsibility(
                    kind="information",
                    description="Chongqing rain tonight",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("time", "day_part", "tonight"),
                    ],
                    source_status="provider_resolved",
                ),
            ),
            goal("我看看今晚会不会有大雨～", "capability_work"),
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
            ),
        )
        corrected = create_goals(
            goal(
                "确认重庆今天晚上是否有大雨。",
                "capability_work",
                resource=resource_responsibility(
                    kind="information",
                    description="重庆今晚大雨情况",
                    attributes=[
                        binding("location", "place", "重庆"),
                        binding("time", "day_part", "tonight"),
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
            coverage_item("今天晚上有大雨吗？", 0),
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
        fresh_prompt = str(ollama.prompts[2][0])
        self.assertIn("restore that source-grounded WHAT", fresh_prompt)
        self.assertIn("Planner Activity metadata is never a Responsibility source", fresh_prompt)

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

    def test_invalid_contract_repair_fails_closed_without_third_call(self):
        invalid = create_goals(goal("Blink twice.", "invalid_mode"))
        ollama = ScriptedOllama([invalid, invalid])
        result = self._resolve(
            ollama,
            request("Blink twice.", language="en-US"),
        )

        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.associations, [])
        self.assertEqual(result.clarification, "")
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
            goal("Walk, blink, and sing.", "body_action")
        )
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("blink", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("Blink.", "body_action"),
            goal("Sing.", "singing"),
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

    def test_ungrounded_reference_reconsideration_can_end_in_clarification(self):
        initial = create_goals(
            goal("Turn off the current device.", "body_action")
        )
        rejected = certificate(
            coverage_item(
                "Turn it off",
                role="responsibility",
                coverage="clarification_required",
                independently_satisfiable=False,
            )
        )
        clarified = {
            "decision": "clarify",
            "clarification": "Which device do you mean?",
            "confidence": 0.95,
            "reason_summary": "The device reference is unresolved.",
        }
        ollama = ScriptedOllama([initial, rejected, clarified])
        result = self._resolve(
            ollama,
            request("Turn it off.", language="en-US"),
        )

        self.assertEqual(result.resolution_status, "needs_clarification")
        self.assertEqual(result.clarification, "Which device do you mean?")
        self.assertEqual(
            ollama.prompts[2][1]["response_format"]["properties"]["decision"]["enum"],
            ["clarify"],
        )
        self.assertEqual(
            result.metadata["responsibility_coverage"]["final_verdict"],
            "clarification",
        )
        self.assert_transaction(
            result,
            ollama,
            terminal="needs_clarification",
            families=[
                "goal_association.primary",
                "goal_association.responsibility_coverage",
                "goal_association.fresh_interpretation",
            ],
        )

    def test_maximum_semantic_dag_is_five_calls(self):
        invalid = create_goals(goal("Walk and sing.", "invalid_mode"))
        collapsed = create_goals(goal("Walk and sing.", "body_action"))
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("sing.", "singing"),
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
            request("Walk and sing.", language="en-US"),
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

    def test_fresh_interpretation_has_no_dto_repair(self):
        first = create_goals(goal("Walk and sing.", "body_action"))
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        invalid_fresh = create_goals(goal("Walk.", "invalid_mode"))
        ollama = ScriptedOllama([first, rejected, invalid_fresh])
        result = self._resolve(
            ollama,
            request("Walk and sing.", language="en-US"),
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

    def test_final_coverage_reject_fails_closed(self):
        first = create_goals(goal("Walk and sing.", "body_action"))
        rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        corrected = create_goals(
            goal("Walk.", "body_action"),
            goal("Sing.", "singing"),
        )
        still_rejected = certificate(
            coverage_item("Walk", 0),
            coverage_item("sing", 0),
        )
        ollama = ScriptedOllama([first, rejected, corrected, still_rejected])
        result = self._resolve(
            ollama,
            request("Walk and sing.", language="en-US"),
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
        self.assertEqual(result.clarification, "")

    def test_user_answerable_ambiguity_is_not_fail_closed(self):
        ollama = ScriptedOllama(
            [
                {
                    "decision": "clarify",
                    "clarification": "Which cup do you mean?",
                    "confidence": 0.9,
                    "reason_summary": "The intended cup is ambiguous.",
                }
            ]
        )
        result = self._resolve(
            ollama,
            request("Bring me that cup.", language="en-US"),
        )

        self.assertEqual(result.resolution_status, "needs_clarification")
        self.assertEqual(result.clarification, "Which cup do you mean?")
        self.assertEqual(len(ollama.prompts), 1)


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
                    coverage_item("帮我拿杯水过来", 0),
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
                    coverage_item("bring me a bottle of water", 0),
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
                    coverage_item("bring the bottle from the table to me", 1),
                ),
            ],
            request(
                "Walk 100 meters for exercise, then bring the bottle from the table to me.",
                language="en-US",
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
                binding("date", "date", "明天"),
            ],
            source_status="provider_resolved",
        )
        result = self._resolve(
            [
                create_goals(
                    goal("查询并解释重庆明天的天气。", "capability_work", resource=weather)
                ),
                certificate(coverage_item("查重庆明天天气", 0)),
            ],
            request(
                "帮我查重庆明天天气。",
            ),
        )

        canonical = result.new_goals[0].resource_responsibility
        self.assertEqual(canonical.resource.kind, "information")
        self.assertEqual(set(canonical.resource.attributes), {"location", "date"})
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
        self.assertEqual(
            set(semantic.resource_responsibility.resource.attributes),
            {"location", "time", "aspects"},
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

    def test_explicit_location_preserves_referent_provenance(self):
        payload = create_goals(
            goal(
                "Check 重庆 weather.",
                "capability_work",
                bindings=[binding("location", "location", "重庆")],
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
            [payload, certificate(coverage_item("Check 重庆 weather", 0))],
            request("Check 重庆 weather.", language="en-US"),
        )

        referent = result.referent_updates[0].referent
        self.assertIsNotNone(referent)
        self.assertEqual(
            result.new_goals[0].object["bindings"]["location"]["referent_id"],
            referent.referent_id,
        )


class GoalAssociationResolutionContractTests(unittest.TestCase):
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

    def test_clarification_requires_explicit_terminal_status(self):
        resolution = GoalAssociationResolution(
            resolution_status="needs_clarification",
            turn_id="turn-1",
            clarification="Which one?",
        )
        self.assertEqual(resolution.resolution_status, "needs_clarification")

    def test_clarification_cannot_mix_with_goal_changes(self):
        with self.assertRaises(ValueError):
            GoalAssociationResolution(
                resolution_status="needs_clarification",
                turn_id="turn-1",
                clarification="Which one?",
                new_goals=[
                    {
                        "goal_id": "goal-new",
                        "description": "New goal",
                        "source_text": "New goal",
                        "beneficiary": "user",
                        "constraints": {},
                        "success_criteria": [],
                        "metadata": {},
                    }
                ],
            )




if __name__ == "__main__":
    unittest.main()
