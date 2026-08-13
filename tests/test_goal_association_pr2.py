from __future__ import annotations

import asyncio
import unittest

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import (
    GoalAssociationModelGoal,
    GoalAssociationResolver,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
)
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.resource import (
    AcquireAndDeliverResource,
    ResourceDescriptor,
    ResourceRecipient,
    ResourceSource,
    project_resource_grounding,
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
    return {
        "resource": {
            "kind": kind,
            "description": description,
            "quantity": quantity,
            "attributes": list(attributes or []),
        },
        "source": {
            "status": source_status,
            "description": source_description,
            "bindings": list(source_bindings or []),
        },
        "recipient": recipient_payload,
        "delivery_mode": delivery_mode
        or ("physical_handover" if kind == "physical_object" else "spoken_explanation"),
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


def request(
    text: str,
    *,
    active_goals=None,
    language: str = "zh-CN",
    route: str = "chat",
    intent: str = "conversation",
    discourse_referents=None,
    progress_candidates=None,
) -> AgentRunRequest:
    return AgentRunRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        route_decision=RouteDecision(
            route=route,
            intent=intent,
            confidence=0.9,
            source="llm",
        ),
        context={
            "active_goal_snapshots": active_goals or [],
            "recent_goal_snapshots": [],
            "history": [],
            "discourse_referents": discourse_referents or [],
            "discourse_focus": [],
            "recent_tool_evidence": [],
            "progress_candidates": progress_candidates or [],
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

    def test_resource_contract_is_nested_and_top_level_bindings_are_read_only(self):
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
        self.assertEqual(parsed.resource_responsibility.resource.quantity, "1")
        self.assertEqual(
            [item.name for item in parsed.resource_responsibility.source.bindings],
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

    def test_resource_attributes_cannot_duplicate_canonical_quantity(self):
        with self.assertRaisesRegex(ValueError, "duplicate canonical resource"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring one bottle.",
                    "body_action",
                    resource=resource_responsibility(
                        attributes=[binding("quantity", "quantity", "1")]
                    ),
                )
            )

    def test_known_resource_source_requires_typed_source_bindings(self):
        with self.assertRaisesRegex(ValueError, "source.bindings"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the water from 100 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        attributes=[binding("distance", "distance", "100")],
                        source_status="known",
                        source_description="100 meters ahead",
                    ),
                )
            )

    def test_source_summary_cannot_supply_an_unbound_numeric_fact(self):
        with self.assertRaisesRegex(ValueError, "numeric facts.*source.bindings"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the water from 100 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        attributes=[binding("distance", "distance", "100m")],
                        source_status="known",
                        source_description="100 meters ahead",
                        source_bindings=[
                            binding("location_direction", "direction", "ahead")
                        ],
                    ),
                )
            )

    def test_typed_resource_fact_cannot_have_two_writable_owners(self):
        with self.assertRaisesRegex(ValueError, "both resource attributes and source"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the water from 100 meters ahead.",
                    "body_action",
                    resource=resource_responsibility(
                        attributes=[
                            binding("distance_to_source", "distance", "100m")
                        ],
                        source_status="known",
                        source_description="100 meters ahead",
                        source_bindings=[
                            binding("location_offset", "distance", "100m")
                        ],
                    ),
                )
            )

    def test_equivalent_measurement_cannot_escape_cross_owner_check(self):
        with self.assertRaisesRegex(
            ValueError,
            "equivalent typed measurement.*resource attributes and source",
        ):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Retrieve the measurement from the supplied source.",
                    "capability_work",
                    resource=resource_responsibility(
                        kind="information",
                        description="the requested measurement",
                        quantity="",
                        attributes=[binding("distance", "measurement", "100m")],
                        source_status="known",
                        source_bindings=[
                            binding(
                                "location_description",
                                "location_instruction",
                                "100 meters ahead",
                            )
                        ],
                    ),
                )
            )

    def test_physical_resource_attributes_are_structurally_unwritable(self):
        with self.assertRaisesRegex(
            ValueError,
            "physical resource.attributes must be empty",
        ):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Bring the red bottle from the table.",
                    "body_action",
                    resource=resource_responsibility(
                        description="the red bottle",
                        attributes=[binding("color", "color", "red")],
                        source_status="known",
                        source_bindings=[
                            binding("source_location", "place", "the table")
                        ],
                    ),
                )
            )

    def test_resource_kind_requires_its_semantic_completion_mode(self):
        information = resource_responsibility(
            kind="information",
            description="tonight's Chongqing weather",
            quantity="",
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

    def test_vocal_goal_cannot_claim_resource_authority(self):
        with self.assertRaisesRegex(ValueError, "output_mode=body_action"):
            GoalAssociationModelGoal.model_validate(
                goal(
                    "Sing a song.",
                    "singing",
                    resource=resource_responsibility(),
                )
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

        typed_physical_attribute = create_goals(
            goal(
                "Bring the red bottle from the table.",
                "body_action",
                resource=resource_responsibility(
                    description="the red bottle",
                    attributes=[binding("color", "color", "red")],
                    source_status="known",
                    source_bindings=[
                        binding("source_location", "place", "the table")
                    ],
                ),
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
            route="tool",
            intent="capability:chromie.weather.lookup",
        )

        interpretation_prompt = resolver._build_prompt(
            req,
            [],
            output_type=GoalSegmentationModelOutput,
        )
        self.assertIn(
            "put a resolved place in resource.attributes as a binding named location",
            interpretation_prompt,
        )
        self.assertIn(
            "requested time and result aspects there as their own typed attributes",
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
            "resource.attributes",
            coverage_prompt,
        )

    def test_deterministic_resource_projection_is_frozen(self):
        canonical = AcquireAndDeliverResource(
            resource=ResourceDescriptor(
                kind="physical_object",
                description="一杯水",
                quantity="1",
                attributes={"temperature": binding("temperature", "temperature", "cold")},
            ),
            source=ResourceSource(
                status="known",
                description="前方100米处",
                bindings={"distance": binding("distance", "distance", "100")},
            ),
            recipient=ResourceRecipient(description="用户"),
            delivery_mode="physical_handover",
        )
        projection = project_resource_grounding(canonical)

        self.assertEqual(
            set(projection.bindings),
            {"temperature", "distance", "quantity"},
        )
        self.assertEqual(
            projection.provenance["distance"],
            "resource_responsibility.source.bindings.distance",
        )
        with self.assertRaises(ValidationError):
            projection.bindings = {}

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


class GoalAssociationTransactionTests(unittest.TestCase):
    def _resolve(self, ollama, req: AgentRunRequest) -> GoalAssociationResolution:
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
                route="robot_action",
                intent="blink",
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

    def test_primary_dto_gets_exactly_one_contract_repair(self):
        invalid = create_goals(goal("Blink twice.", "invalid_mode"))
        valid = create_goals(goal("Blink twice.", "body_action"))
        ollama = ScriptedOllama(
            [invalid, valid, certificate(coverage_item("Blink twice.", 0))]
        )
        result = self._resolve(
            ollama,
            request("Blink twice.", language="en-US", route="robot_action"),
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
            request("Blink twice.", language="en-US", route="robot_action"),
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
            request("Blink twice.", language="en-US", route="robot_action"),
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
                route="robot_action",
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
            request("Walk and sing.", language="en-US", route="robot_action"),
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
            request("Walk and sing.", language="en-US", route="robot_action"),
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
            request("Walk and sing.", language="en-US", route="robot_action"),
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
            request("Bring me that cup.", language="en-US", route="robot_action"),
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
                route="robot_action",
                intent="resource_delivery",
            ),
        )

        self.assertEqual(len(result.new_goals), 1)
        semantic = result.new_goals[0]
        self.assertEqual(semantic.metadata["output_mode"], "body_action")
        self.assertEqual(semantic.resource_responsibility.resource.quantity, "1")
        self.assertEqual(
            set(semantic.object["bindings"]),
            {"distance", "direction", "quantity"},
        )
        self.assertEqual(
            semantic.metadata["resource_grounding_projection"]["authority"],
            "derived_read_only",
        )

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
                route="robot_action",
                intent="capability:soridormi.acquire_and_deliver_resource",
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
                route="robot_action",
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
                route="tool",
                intent="weather.lookup",
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
                route="tool",
                intent="capability:chromie.weather.lookup",
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
                route="chat",
                intent="tell_a_joke",
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

    def test_legacy_clarification_infers_explicit_status(self):
        resolution = GoalAssociationResolution(
            turn_id="turn-1",
            clarification="Which one?",
        )
        self.assertEqual(resolution.resolution_status, "needs_clarification")

    def test_clarification_cannot_mix_with_goal_changes(self):
        with self.assertRaises(ValueError):
            GoalAssociationResolution(
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


class OrchestratorGoalAssociationTests(unittest.TestCase):
    def test_report_only_schedules_without_changing_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision

        class Client:
            async def resolve_goal_association(self, *args, **kwargs):
                return GoalAssociationResolution(
                    turn_id="turn-report",
                    associations=[
                        {
                            "association_id": "assoc-report",
                            "relationship": "continue",
                            "target_goal_ids": ["goal-a"],
                            "confidence": 0.9,
                        }
                    ],
                    confidence=0.9,
                )

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.goal_association_mode = "report_only"
            assistant.goal_association_timeout_ms = 1000
            assistant.enable_agent = True
            assistant.agent_client = Client()
            assistant.goal_association_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None
            decision = OrchestratorRouteDecision(
                route="chat",
                intent="conversation",
                confidence=0.8,
                source="llm",
            )
            reviewed = assistant._schedule_goal_association_report(
                object(),
                user_text="继续。",
                session_id="sid",
                context={
                    "history": [],
                    "active_goal_snapshots": [active_goal("goal-a", "Do A")],
                },
                decision=decision,
            )
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(
                reviewed.metadata["goal_association_resolution"]["status"],
                "scheduled",
            )
            pending = list(assistant.goal_association_report_tasks)
            if pending:
                await asyncio.gather(*pending)

        asyncio.run(run())

    def test_off_is_noop(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.goal_association_mode = "off"
        assistant.enable_agent = True
        decision = OrchestratorRouteDecision(
            route="chat",
            intent="conversation",
            confidence=0.8,
            source="llm",
        )
        reviewed = assistant._schedule_goal_association_report(
            object(),
            user_text="hello",
            session_id="sid",
            context={"active_goal_snapshots": []},
            decision=decision,
        )
        self.assertIs(reviewed, decision)


if __name__ == "__main__":
    unittest.main()
