from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.cognitive_core.goal_interpreter.engine import interpret_goal
from agent.app.cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _GoalInterpretationAuthorityViolation,
    _GoalInterpretationSemanticStructureViolation,
    _extract_json_object,
    _normalize_model_interpretation_projection,
    _payload_message_texts,
    _reject_canonical_goal_identity_refs,
    _reject_hidden_effect_or_how_bindings,
    _reject_noncanonical_count_bindings,
    _reject_planner_shaped_goal_interpretation,
    _reject_unavailable_or_mismatched_prior_assistant_utterance,
    _reject_unprovenanced_location_bindings,
    _reject_unprovenanced_duration_bindings,
    _reject_unprovenanced_speed_bindings,
    _source_tokens,
    _without_goal_interpretation_authority,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    GoalInterpretationRequest,
)


def _valid_output(
    text: str = "What's the weather in Chongqing today?",
    *,
    local_ref: str = "r1",
    unresolved: list[str] | None = None,
) -> dict[str, object]:
    tokens = _source_tokens(text)
    return {
        "confidence": 0.93,
        "responsibilities": [
            {
                "local_ref": local_ref,
                "outcome": "provide today's weather for Chongqing",
                "bindings": {"location": "Chongqing", "time": "today"},
                "output_mode": "information",
                "relationship": "new",
                "target_goal_ids": [],
                "confidence": 0.95,
                "source_evidence": {
                    "source_start_token_ref": tokens[0]["ref"],
                    "source_end_token_ref": tokens[-1]["ref"],
                },
            }
        ],
        "unresolved": unresolved or [],
    }


def _compound_output() -> dict[str, object]:
    def responsibility(
        ref: str, outcome: str, source_ref: str, relation: dict[str, str]
    ) -> dict[str, object]:
        return {
            "local_ref": ref,
            "outcome": outcome,
            "bindings": relation,
            "output_mode": "body_action",
            "relationship": "new",
            "target_goal_ids": [],
            "confidence": 1.0,
            "source_evidence": {
                "source_start_token_ref": source_ref,
                "source_end_token_ref": source_ref,
            },
        }

    return {
        "confidence": 1.0,
        "responsibilities": [
            responsibility("r1", "nod", "t0", {"before": "r2"}),
            responsibility("r2", "blink", "t2", {"after": "r1"}),
        ],
        "unresolved": [],
    }


def test_model_interpretation_projection_lowers_typed_relations_and_numbers() -> None:
    parsed = _compound_output()
    parsed["responsibilities"][0].pop("bindings")
    parsed["responsibilities"][0]["binding_items"] = {}
    parsed["responsibilities"][1].pop("bindings")
    parsed["responsibilities"][1]["binding_items"] = {"count": 2}
    parsed["coordination"] = [{"kind": "sequence", "refs": ["r1", "r2"]}]

    _normalize_model_interpretation_projection(parsed)

    assert "coordination" not in parsed
    assert parsed["responsibilities"][0]["bindings"] == {}
    assert parsed["responsibilities"][1]["bindings"] == {
        "after": ["r1"],
        "count": 2,
    }
class GoalInterpreterContractTests(unittest.TestCase):
    def test_source_tokens_preserve_latin_cjk_and_punctuation(self) -> None:
        self.assertEqual(
            [(item["ref"], item["surface"]) for item in _source_tokens("Walk 前!")],
            [("t0", "Walk"), ("t1", "前"), ("t2", "!")],
        )

    def test_live_primary_validation_requires_source_evidence(self) -> None:
        parsed = _valid_output()
        del parsed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "lacks source_evidence"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(
                    text="What's the weather in Chongqing today?"
                ),
                json.dumps(parsed),
            )

    def test_primary_source_evidence_accepts_known_ordered_refs(self) -> None:
        decision = OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?"),
            json.dumps(_valid_output()),
        )
        self.assertEqual(decision.responsibilities[0].local_ref, "r1")

    def test_primary_source_evidence_rejects_unknown_refs(self) -> None:
        parsed = _valid_output()
        parsed["responsibilities"][0]["source_evidence"][  # type: ignore[index]
            "source_end_token_ref"
        ] = "t999"
        with self.assertRaisesRegex(ValueError, "unknown authoritative"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="What's the weather in Chongqing today?"),
                json.dumps(parsed),
            )

    def test_primary_source_evidence_rejects_reversed_refs(self) -> None:
        parsed = _valid_output()
        evidence = parsed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        evidence["source_start_token_ref"] = "t2"
        evidence["source_end_token_ref"] = "t0"
        with self.assertRaisesRegex(ValueError, "endpoints are reversed"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="What's the weather in Chongqing today?"),
                json.dumps(parsed),
            )

    def test_primary_source_evidence_rejects_independent_overlap(self) -> None:
        parsed = _compound_output()
        parsed["responsibilities"][1]["source_evidence"][  # type: ignore[index]
            "source_start_token_ref"
        ] = "t0"
        with self.assertRaisesRegex(
            _GoalInterpretationSemanticStructureViolation, "spans overlap"
        ):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="nod and blink"), json.dumps(parsed)
            )

    def test_primary_source_evidence_allows_disjoint_atomic_siblings(self) -> None:
        decision = OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text="nod and blink"),
            json.dumps(_compound_output()),
        )
        self.assertEqual(
            [item.local_ref for item in decision.responsibilities], ["r1", "r2"]
        )

    def test_context_backed_elliptical_clarification_keeps_whole_turn_binding(
        self,
    ) -> None:
        request = GoalInterpretationRequest(
            text="Tomorrow afternoon.",
            context={
                "active_task_snapshots": [
                    {
                        "goal_id": "goal-reminder",
                        "open_information_gaps": [
                            {
                                "gap_id": "gap-time",
                                "blocking": True,
                                "preferred_resolution": "ask_user",
                            }
                        ],
                    }
                ]
            },
        )
        parsed = {
            "confidence": 1.0,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "remind the user tomorrow afternoon",
                    "bindings": {"time_scope": "Tomorrow afternoon"},
                    "output_mode": "stateful_effect",
                    "relationship": "clarify",
                    "target_goal_ids": ["goal-reminder"],
                    "confidence": 1.0,
                    "source_evidence": {
                        "source_start_token_ref": "t0",
                        "source_end_token_ref": "t2",
                    },
                }
            ],
            "unresolved": [],
        }

        decision = OllamaGoalInterpreter._validate_interpretation_content(
            request, json.dumps(parsed)
        )

        self.assertEqual(
            decision.responsibilities[0].bindings,
            {"time_scope": "Tomorrow afternoon"},
        )

    def test_whole_turn_binding_without_pending_user_gap_remains_rejected(
        self,
    ) -> None:
        request = GoalInterpretationRequest(
            text="Tomorrow afternoon.",
            context={
                "active_task_snapshots": [
                    {
                        "goal_id": "goal-reminder",
                        "open_information_gaps": [],
                    }
                ]
            },
        )
        parsed = {
            "confidence": 1.0,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "clarify the reminder time as tomorrow afternoon",
                    "bindings": {"time_scope": "Tomorrow afternoon"},
                    "output_mode": "stateful_effect",
                    "relationship": "clarify",
                    "target_goal_ids": ["goal-reminder"],
                    "confidence": 1.0,
                    "source_evidence": {
                        "source_start_token_ref": "t0",
                        "source_end_token_ref": "t2",
                    },
                }
            ],
            "unresolved": [],
        }

        with self.assertRaisesRegex(
            _GoalInterpretationSemanticStructureViolation,
            "copied the whole admitted turn",
        ):
            OllamaGoalInterpreter._validate_interpretation_content(
                request, json.dumps(parsed)
            )

    def test_whole_turn_binding_with_non_user_gap_remains_rejected(self) -> None:
        request = GoalInterpretationRequest(
            text="Tomorrow afternoon.",
            context={
                "active_task_snapshots": [
                    {
                        "goal_id": "goal-reminder",
                        "open_information_gaps": [
                            {
                                "gap_id": "gap-weather",
                                "blocking": True,
                                "preferred_resolution": "query_trusted_service",
                            }
                        ],
                    }
                ]
            },
        )
        parsed = {
            "confidence": 1.0,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "clarify the reminder time as tomorrow afternoon",
                    "bindings": {"time_scope": "Tomorrow afternoon"},
                    "output_mode": "stateful_effect",
                    "relationship": "clarify",
                    "target_goal_ids": ["goal-reminder"],
                    "confidence": 1.0,
                    "source_evidence": {
                        "source_start_token_ref": "t0",
                        "source_end_token_ref": "t2",
                    },
                }
            ],
            "unresolved": [],
        }

        with self.assertRaisesRegex(
            _GoalInterpretationSemanticStructureViolation,
            "copied the whole admitted turn",
        ):
            OllamaGoalInterpreter._validate_interpretation_content(
                request, json.dumps(parsed)
            )

    def test_hidden_effect_and_how_binding_names_are_rejected(self) -> None:
        for binding_name in ("concurrent_action", "capability", "agent_skill"):
            with self.subTest(binding_name=binding_name):
                parsed = _valid_output()
                parsed["responsibilities"][0]["bindings"] = {binding_name: "blink"}  # type: ignore[index]
                with self.assertRaises(
                    _GoalInterpretationSemanticStructureViolation
                ):
                    _reject_hidden_effect_or_how_bindings(parsed)

    def test_duration_and_location_bindings_remain_scalar(self) -> None:
        request = GoalInterpretationRequest(text="move forward for 15 seconds")
        base = {
            "confidence": 1.0,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for 15 seconds",
                    "bindings": {"duration": "15 seconds", "location": "forward"},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 1.0,
                    "source_evidence": {
                        "source_start_token_ref": "t0",
                        "source_end_token_ref": "t4",
                    },
                }
            ],
            "unresolved": [],
        }
        nested_duration = copy.deepcopy(base)
        nested_duration["responsibilities"][0]["bindings"]["duration"] = {  # type: ignore[index]
            "value": 15,
            "unit": "seconds",
        }
        with self.assertRaisesRegex(ValueError, "duration binding must remain one scalar"):
            OllamaGoalInterpreter._validate_interpretation_content(
                request, json.dumps(nested_duration)
            )
        nested_location = copy.deepcopy(base)
        nested_location["responsibilities"][0]["bindings"]["location"] = {  # type: ignore[index]
            "value": "forward"
        }
        with self.assertRaisesRegex(ValueError, "location binding must be one exact"):
            OllamaGoalInterpreter._validate_interpretation_content(
                request, json.dumps(nested_location)
            )

    def test_location_provenance_uses_only_rendered_dialogue_text(self) -> None:
        visible = {"role": "user", "text": "这里说的那边是门口。"}
        for history, accepted in (
            ([visible], True),
            ([{**visible, "role": "assistant"}], True),
            ([{"role": "user", "text": "门口"}], True),
            ([{"role": "user", "text": "门口", "metadata": {
                "cognitive_gateway_admission": "suppress"}}], False),
            ([{"role": "user", "text": "另一个地方", "metadata": {
                "label": "门口"}}], False),
            ([{"role": "user", "content": "门口"}], False),
            ([{"role": "system", "text": "门口"}], False),
            ([{"role": "user", "text": "门口"}]
             + [{"role": "user", "text": "最近对话"}] * 6, False),
            ([{"role": "user", "text": "甲" * 270 + "门口"}], False),
            ([{"role": "user", "text": "乙" * 260, "metadata": {
                "semantic_status": "known" * 10}}] * 5
             + [{"role": "user", "text": "门口"}], False),
            ([{"role": "user", "text": "the doorway"}], False),
        ):
            with self.subTest(history=history, accepted=accepted):
                request = GoalInterpretationRequest(
                    text="去那边等我。", context={"history": history}
                )
                parsed = {"responsibilities": [{"bindings": {"location": "门口"}}]}
                if accepted:
                    _reject_unprovenanced_location_bindings(request, parsed)
                    self.assertEqual(parsed["responsibilities"][0]["bindings"],
                                     {"location": "门口"})
                else:
                    with self.assertRaisesRegex(ValueError, "no authoritative surface"):
                        _reject_unprovenanced_location_bindings(request, parsed)

    def test_speed_requires_source_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "no authoritative surface provenance"):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="run forward for 15 seconds"),
                {"responsibilities": [{"bindings": {"speed": "normal"}}]},
            )

    def test_duration_requires_source_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "no authoritative surface provenance"):
            _reject_unprovenanced_duration_bindings(
                GoalInterpretationRequest(text="move briefly"),
                {
                    "responsibilities": [
                        {"bindings": {"duration": "invented elapsed span"}}
                    ]
                },
            )

    def test_duration_accepts_gi_owned_number_word_normalization(self) -> None:
        _reject_unprovenanced_duration_bindings(
            GoalInterpretationRequest(text="持续三秒", language="zh-CN"),
            {"responsibilities": [{"bindings": {"duration": 3}}]},
        )

    def test_spatial_surface_cannot_be_retyped_as_speed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Direction/location is never speed"):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN"),
                {"responsibilities": [{"bindings": {"location": "往前", "speed": "往前"}}]},
            )

    def test_unprovenanced_numeric_speed_is_rejected_without_mutation(self) -> None:
        parsed = {"responsibilities": [{"bindings": {"count": 2, "speed": 1}}]}
        original = copy.deepcopy(parsed)
        with self.assertRaisesRegex(ValueError, "no authoritative surface provenance"):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="Nod twice."), parsed
            )
        self.assertEqual(parsed, original)

    def test_explicit_numeric_speed_survives_provenance_validation(self) -> None:
        request = GoalInterpretationRequest(text="move at speed 0.35")
        parsed = {"responsibilities": [{"bindings": {"speed": 0.35}}]}

        _reject_unprovenanced_speed_bindings(request, parsed)

        self.assertEqual(
            parsed["responsibilities"][0]["bindings"],
            {"speed": 0.35},
        )

    def test_typed_count_contract_is_canonical(self) -> None:
        for value in ("2", 0, -1, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "canonical positive"):
                    _reject_noncanonical_count_bindings(
                        {"responsibilities": [{"bindings": {"count": value}}]}
                    )

    def test_planner_fields_are_authority_violations(self) -> None:
        for field, value in (("route", "tool"), ("intent", "weather"), ("plan", [])):
            with self.subTest(field=field):
                with self.assertRaises(_GoalInterpretationAuthorityViolation):
                    _reject_planner_shaped_goal_interpretation({**_valid_output(), field: value})

    def test_local_ref_cannot_reuse_canonical_goal_identity(self) -> None:
        request = GoalInterpretationRequest(
            text="continue",
            context={"active_goal_snapshots": [{"goal_id": "goal-previous"}]},
        )
        with self.assertRaises(_GoalInterpretationAuthorityViolation):
            _reject_canonical_goal_identity_refs(
                request, _valid_output("continue", local_ref="goal-previous")
            )

    def test_bound_unresolved_duplicate_fails_closed(self) -> None:
        parsed = _valid_output()
        parsed["unresolved"] = ["Chongqing", "which forecast provider"]
        with self.assertRaisesRegex(ValueError, "already-bound semantic values"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(
                    text="What's the weather in Chongqing today?"
                ),
                json.dumps(parsed),
            )

    def test_prior_assistant_binding_requires_exact_evidence(self) -> None:
        request = GoalInterpretationRequest(
            text="repeat that",
            context={"history": [{"role": "assistant", "content": "Hello there."}]},
        )
        parsed = {"responsibilities": [{"bindings": {"prior_assistant_utterance": "Hello."}}]}
        with self.assertRaises(_GoalInterpretationAuthorityViolation):
            _reject_unavailable_or_mismatched_prior_assistant_utterance(request, parsed)

    def test_context_projection_removes_downstream_authority(self) -> None:
        projected = _without_goal_interpretation_authority(
            {"goal_id": "goal-1", "route": "tool", "nested": {"capability_id": "weather", "outcome": "weather"}}
        )
        self.assertEqual(projected, {"goal_id": "goal-1", "nested": {"outcome": "weather"}})

    def test_extract_json_object_accepts_fenced_json(self) -> None:
        self.assertEqual(_extract_json_object("```json\n{\"confidence\":1}\n```"), {"confidence": 1})


class GoalInterpreterPromptTests(unittest.TestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            deep_model="deep-test-model",
            timeout_ms=800,
        )

    def test_runtime_correlation_labels_do_not_change_model_input(self) -> None:
        interpreter = self._interpreter()
        for key in ("conversation_id", "session_id", "turn_id", "sid"):
            first = GoalInterpretationRequest(
                text="Blink twice.",
                context={key: "a-session-label", "discourse_focus": []},
            )
            second = first.model_copy(deep=True)
            second.context[key] = "an-unrelated-test-label"
            for build in (
                interpreter.build_interpretation_payload,
                interpreter.build_deep_interpretation_payload,
            ):
                with self.subTest(key=key, variant=build.__name__):
                    self.assertEqual(build(first), build(second))
                    self.assertEqual(first.context[key], "a-session-label")
                    self.assertEqual(second.context[key], "an-unrelated-test-label")

    def test_primary_prompt_owns_what_and_source_evidence(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="边走边唱歌", language="zh-CN")
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("Authoritative source tokens", user_text)
        self.assertIn("source_evidence", all_text)
        self.assertIn("one primary semantic decision", all_text)
        self.assertNotIn("Common Ability Catalog", all_text)

    def test_identity_boundary_is_lossless_in_both_interpretation_prompts(self) -> None:
        boundary = (
            "Chromie's body is robotic. Her social identity is not a claim "
            "of biological human age, birth history, or physiology."
        )
        request = GoalInterpretationRequest(
            text="Blink twice.",
            context={"mind": {"identity": {
                "name": "Chromie", "model_identity_boundary": boundary,
            }}},
        )
        interpreter = self._interpreter()
        for build in (
            interpreter.build_interpretation_payload,
            interpreter.build_deep_interpretation_payload,
        ):
            with self.subTest(variant=build.__name__):
                _, user_text, _ = _payload_message_texts(build(request))
                projection = json.loads(
                    user_text.split("Bounded Identity Context:\n", 1)[1].split("\n", 1)[0]
                )
                self.assertEqual(
                    projection["self_identity"].get("model_identity_boundary"), boundary
                )

    def test_identity_projection_overflow_fails_instead_of_dropping_truth(self) -> None:
        request = GoalInterpretationRequest(
            text="Blink twice.",
            context={"mind": {"identity": {
                "name": "Chromie", "model_identity_boundary": "x" * 1201,
            }}},
        )
        interpreter = self._interpreter()
        for build in (
            interpreter.build_interpretation_payload,
            interpreter.build_deep_interpretation_payload,
        ):
            with self.subTest(variant=build.__name__):
                with self.assertRaisesRegex(ValueError, "identity.*projection budget"):
                    build(request)

    def test_primary_prompt_matches_schema_when_no_candidate_goal_exists(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="blink twice")
        )
        system_text, _, _ = _payload_message_texts(payload)
        responsibility = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]

        self.assertNotIn("relationship", responsibility["properties"])
        self.assertNotIn("target_goal_ids", responsibility["properties"])
        self.assertNotIn("Goal continuity is exposed for this request", system_text)

    def test_primary_prompt_projects_goal_continuity_only_when_schema_exposes_it(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="continue that",
                context={
                    "active_goal_snapshots": [
                        {"goal_id": "goal-active", "outcome": "continue walking"}
                    ]
                },
            )
        )
        system_text, _, _ = _payload_message_texts(payload)
        responsibility = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]

        self.assertIn("relationship", responsibility["properties"])
        self.assertIn("target_goal_ids", responsibility["properties"])
        self.assertIn("Goal continuity is exposed for this request", system_text)
        self.assertIn("exact supplied Goal IDs", system_text)
        self.assertIn("Preserve negation and lifecycle meaning", system_text)
        self.assertIn("cancellation, cessation, pause, continuation", system_text)
        self.assertIn("preserve the target Goal's output mode", system_text)

    def test_continuity_decoder_shape_preserves_required_source_and_goal_fields(self) -> None:
        request = GoalInterpretationRequest(
            text="continue walking",
            context={"active_goal_snapshots": [
                {"goal_id": "goal-active", "outcome": "continue walking"}
            ]},
        )
        interpreter = self._interpreter()
        for build in (interpreter.build_interpretation_payload,
                      interpreter.build_deep_interpretation_payload):
            schema = build(request)["format"]
            responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
            exposed = Draft202012Validator({
                "$defs": schema["$defs"], **responsibility["anyOf"][0],
            })
            full = Draft202012Validator({"$defs": schema["$defs"], **responsibility})
            valid = _valid_output(request.text)["responsibilities"][0]
            valid.pop("bindings")
            valid.update(binding_items={}, relationship="continue",
                         target_goal_ids=["goal-active"], confidence=1.0,
                         outcome="continue walking", output_mode="body_action")
            self.assertTrue(exposed.is_valid(valid))
            self.assertTrue(full.is_valid(valid))
            for field in responsibility["required"]:
                missing = copy.deepcopy(valid)
                del missing[field]
                with self.subTest(build=build.__name__, missing=field):
                    self.assertFalse(exposed.is_valid(missing))
            for field, value in (
                ("local_ref", "res_1"), ("source_evidence", ["t0"]),
                ("target_goal_ids", ["unknown"]), ("relationship", "continued"),
                ("unexpected", True),
            ):
                with self.subTest(build=build.__name__, invalid=field):
                    self.assertFalse(exposed.is_valid({**valid, field: value}))
            # Decoder shape alone does not enforce the conditional Goal contract.
            self.assertFalse(full.is_valid({**valid, "target_goal_ids": []}))
            self.assertFalse(full.is_valid({**valid, "relationship": "new"}))
            self.assertTrue(full.is_valid({**valid, "relationship": "new",
                                           "target_goal_ids": []}))

    def test_primary_prompt_projects_prior_utterance_rule_only_when_available(
        self,
    ) -> None:
        plain = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="hello")
        )
        contextual = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="what did you say?",
                context={
                    "history": [
                        {"role": "assistant", "text": "Hello there."}
                    ]
                },
            )
        )

        plain_system, _, _ = _payload_message_texts(plain)
        contextual_system, _, _ = _payload_message_texts(contextual)
        self.assertNotIn("prior assistant utterance is available", plain_system)
        self.assertIn("prior assistant utterance is available", contextual_system)
        self.assertIn(
            "mere availability does not create any Responsibility",
            contextual_system,
        )
        self.assertIn(
            "whose cited source predicate itself asks to repeat or report",
            contextual_system,
        )
        prior_binding = contextual["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["binding_items"]["properties"]["prior_assistant_utterance"]
        self.assertIn(
            "presence in this schema never creates or implies a Responsibility",
            prior_binding["description"],
        )

    def test_primary_prompt_does_not_expose_runtime_sid(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                sid="runtime-secret-sid",
                text="What time is it now?",
                language="en-US",
            )
        )
        _, _, all_text = _payload_message_texts(payload)
        self.assertNotIn("runtime-secret-sid", all_text)

    def test_primary_prompt_does_not_expose_planner_target_realization(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="look at me",
                context={
                    "active_user_target": {
                        "target_ref": "opaque-current-speaker",
                        "relative_direction": "front",
                    },
                    "planner_auxiliary_social_context": {
                        "target_evidence": {
                            "available": True,
                            "target": {"target_ref": "opaque-current-speaker"},
                        }
                    },
                },
            )
        )

        _, _, all_text = _payload_message_texts(payload)

        self.assertNotIn("opaque-current-speaker", all_text)
        self.assertNotIn("active_user_target", all_text)
        self.assertNotIn("planner_auxiliary_social_context", all_text)

    def test_primary_prompt_exposes_semantic_identity_not_presentation_profile(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="what is your name?",
                context={
                    "mind": {
                        "profile_id": "internal-profile-id",
                        "version": "internal-version",
                        "identity": {
                            "entity_id": "internal-entity-id",
                            "name": "Chromie",
                            "kind": "girl identity",
                        },
                        "personality_expression": {
                            "owner_approved": True,
                            "spoken_style": "internal-spoken-style",
                            "maturity_boundary": "internal-maturity-boundary",
                        },
                    }
                },
            )
        )

        _, user_text, _ = _payload_message_texts(payload)

        self.assertIn('"name":"Chromie"', user_text)
        self.assertNotIn("internal-profile-id", user_text)
        self.assertNotIn("internal-version", user_text)
        self.assertNotIn("internal-entity-id", user_text)
        self.assertNotIn("internal-spoken-style", user_text)
        self.assertNotIn("internal-maturity-boundary", user_text)

    def test_primary_prompt_does_not_repeat_extracted_numeric_answer_list(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="walk forward for 15 seconds")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertNotIn("Explicit Arabic numeric values", user_text)
        self.assertNotIn("[15]", user_text)
        self.assertNotIn("Every listed explicit Arabic number", system_text)
        self.assertNotIn("speed V plus duration D", user_text)
        self.assertIn("IMMUTABLE SOURCE TURN JSON", user_text)
        self.assertIn('"original_text":"walk forward for 15 seconds"', user_text)

    def test_primary_prompt_preserves_measured_value_and_unit(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="walk forward for 15 seconds")
        )
        system_text, _, _ = _payload_message_texts(payload)
        duration = payload["format"]["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]["properties"]["duration"]

        self.assertIn("number and unit", system_text)
        self.assertIn("15 seconds", system_text)
        self.assertIn("both number and unit", duration["description"])
        self.assertNotIn("without its unit", system_text)

    def test_primary_prompt_keeps_standalone_social_acts(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="Thank you.")
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("standalone greeting, thanks", system_text)
        self.assertIn("one speech Responsibility", system_text)
        self.assertIn("politeness framing attached to a substantive request", system_text)

    def test_primary_prompt_requires_minimal_nonoverlapping_responsibility_decomposition(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="hello?")
        )
        system_text, _, _ = _payload_message_texts(payload)
        responsibilities = payload["format"]["properties"]["responsibilities"]

        self.assertIn("decomposition is minimal and source-partitioned", system_text)
        self.assertIn("same source predicate", system_text)
        self.assertIn("single conversational/social act", system_text)
        self.assertIn(
            "distinct non-overlapping positive predicate span",
            responsibilities["description"],
        )
        self.assertIn("Context may resolve", responsibilities["description"])
        self.assertIn("never creates a new one", responsibilities["description"])

    def test_primary_prompt_limits_unfamiliar_name_uncertainty_to_materiality(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="Tell Nova the meeting moved.")
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("unfamiliarity alone is not unresolved meaning", system_text)
        self.assertIn("harmless directly supplied name", system_text)

    def test_primary_prompt_preserves_exact_gateway_wording_once(self) -> None:
        exact = "  今晚，重庆热不热？  "
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                sid="turn-exact-source",
                text="今晚，重庆热不热？",
                language="zh-CN",
                context={
                    "user_turn_envelope": {
                        "turn_id": "turn-exact-source",
                        "original_input": {"text": exact},
                        "normalized_input": {
                            "text": "今晚，重庆热不热？",
                            "language": "zh-CN",
                        },
                    }
                },
            )
        )
        _, user_text, _ = _payload_message_texts(payload)

        self.assertEqual(user_text.count(exact), 1)
        self.assertIn('"authority":"read_only_source_provenance"', user_text)
        self.assertNotIn('"user_turn_envelope"', user_text)
        self.assertIn("Goal Interpretation owns current-turn WHAT", user_text)

    def test_primary_prompt_requires_sparse_non_self_relations_and_disjoint_spans(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="look at me while blinking")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertIn("at least two unique emitted sibling local_refs", system_text)
        self.assertNotIn("FINAL SPARSE-OUTPUT CHECK", user_text)
        self.assertIn("one complete schema-valid JSON decision", user_text)

    def test_primary_prompt_keeps_action_modifiers_on_one_responsibility(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="perform A with modifiers M and N")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertIn(
            "One predicate with several modifiers remains one Responsibility",
            system_text,
        )
        self.assertNotIn("never sibling effects", user_text)

    def test_primary_prompt_requires_material_unknown_name_uncertainty(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="你能查天信吗？", language="zh-CN")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertIn("consequential referent/category choice", system_text)
        self.assertIn("materially change the intended outcome", system_text)
        self.assertNotIn("unresolved must include a bare name", user_text)

    def test_primary_prompt_preflight_prioritizes_decomposition_and_binding_dimensions(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="move with two modifiers, then perform another effect"
            )
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("one responsibilities[] item for each independently", system_text)
        self.assertIn("time_scope is a calendar or relative period", system_text)
        self.assertIn("Missing tools, units, providers", system_text)
        self.assertIn("Ignore fillers, hesitation, vocatives", system_text)
        self.assertIn("politeness framing attached to a substantive request", system_text)
        self.assertIn("Use [] when meaning is clear", system_text)
        self.assertIn("outcome names exactly that requested predicate", system_text)

    def test_primary_prompt_disambiguates_full_audit_failure_boundaries(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="Please ask Lee whether the value is below 5.")
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("never interrogative/declarative mood", system_text)
        self.assertIn("proposition owns the communicated content", system_text)
        self.assertIn("including a clause-opening “please/请”", system_text)
        self.assertIn("An anaphoric continuation", system_text)
        self.assertIn("never infer actor=Chromie", system_text)
        self.assertIn("speech/vocal style or manner", system_text)
        self.assertIn(
            "Do not create proposition merely because the source is a question",
            system_text,
        )

    def test_primary_schema_disambiguates_full_audit_binding_boundaries(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="Please ask Lee whether the value is below 5.")
        )["format"]
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        bindings = responsibility["properties"]["binding_items"]["properties"]
        evidence = schema["$defs"]["ResponsibilitySourceEvidence"]["properties"]

        self.assertIn("Never infer actor=Chromie", bindings["actor"]["description"])
        self.assertIn("interrogative/declarative mood", bindings["polarity"]["description"])
        self.assertIn("proposition-internal", bindings["proposition"]["description"])
        self.assertIn(
            "Do not create proposition merely because an information source is a question",
            bindings["proposition"]["description"],
        )
        self.assertIn("authored speech or vocal style", bindings["subtype"]["description"])
        self.assertIn(
            "clause-opening modal or request marker",
            evidence["source_start_token_ref"]["description"],
        )

    def test_primary_prompt_disambiguates_iterative_audit_boundaries(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="Please help me draft a question for Lee, not Sam, in 5 minutes."
            )
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn("emit the JSON number itself", system_text)
        self.assertIn("preserve the exact contiguous source/context surface", system_text)
        self.assertIn("not a second recipient", system_text)
        self.assertIn("asking a named third party", system_text)
        self.assertIn("correction, replacement, or binding-only clause", system_text)
        self.assertIn("ordinary request to breathe", system_text)

    def test_primary_schema_disambiguates_iterative_audit_boundaries(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text="Please help me draft a question for Lee, not Sam, in 5 minutes."
            )
        )["format"]
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        bindings = responsibility["properties"]["binding_items"]["properties"]
        evidence = schema["$defs"]["ResponsibilitySourceEvidence"]["properties"]
        modes = responsibility["properties"]["output_mode"]["oneOf"]
        mode_descriptions = {item["const"]: item["description"] for item in modes}

        for name in ("duration", "speed", "distance", "threshold"):
            self.assertIn("emit only that JSON number", bindings[name]["description"])
        self.assertIn("not a second recipient", bindings["recipient"]["description"])
        self.assertIn("speech, not information", bindings["addressee"]["description"])
        self.assertIn("later correction", evidence["source_end_token_ref"]["description"])
        self.assertIn("ordinary request to breathe", mode_descriptions["body_action"])
        self.assertIn("named third party", mode_descriptions["speech"])

    def test_primary_prompt_collects_cross_clause_bindings_without_widening_predicate_evidence(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(
                text=(
                    "A package is thirty meters behind you. "
                    "Please bring it to Morgan."
                ),
                language="en-US",
            )
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn(
            "words that request an effect and the words that bind it may occur "
            "in different clauses",
            system_text,
        )
        self.assertIn("including declarative circumstance clauses", system_text)
        self.assertIn(
            "does not need to contain binding surfaces stated in other clauses",
            system_text,
        )
        self.assertIn(
            "including any object or recipient stated inside that request clause",
            system_text,
        )
        self.assertIn(
            "source_evidence remains on the request clause and never expands to "
            "the antecedent clause",
            system_text,
        )
        self.assertIn(
            "Treat a lexical acquire-and-deliver request",
            system_text,
        )
        self.assertIn(
            "outcome: `bring the parcel to Alex`",
            system_text,
        )
        self.assertIn(
            "span starts with any modal or request-form words",
            system_text,
        )
        self.assertIn(
            "ends after every object, complement, or recipient",
            system_text,
        )
        self.assertIn(
            "start at the current turn's token ref whose surface is `Could`",
            system_text,
        )
        self.assertIn("Example token-ref numbers are never reusable", system_text)
        self.assertNotIn('"source_start_token_ref":"t', system_text)
        self.assertNotIn("bottle of water", system_text)
        self.assertNotIn("50 meters", system_text)

    def test_primary_prompt_makes_binding_semantics_and_decoder_order_visible(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="bring the parcel to me")
        )
        system_text, _, _ = _payload_message_texts(payload)

        self.assertIn(
            "Emit selected binding_items keys in lexicographic key order",
            system_text,
        )
        self.assertLess(
            system_text.index('"direction":"behind you"'),
            system_text.index('"distance":"twenty meters"'),
        )
        self.assertLess(
            system_text.index('"distance":"twenty meters"'),
            system_text.index('"entity":"A parcel"'),
        )
        self.assertLess(
            system_text.index('"entity":"A parcel"'),
            system_text.index('"recipient":"Alex"'),
        )
        for semantic_rule in (
            "actor is the performer",
            "addressee is the addressed entity",
            "experiencer is the holder",
            "quantity is a non-repetition amount",
            "severity is seriousness or impact level",
            "preference is an expressed preference",
            "attribute is an explicitly requested property",
        ):
            self.assertIn(semantic_rule, system_text)
        self.assertIn(
            "merely plausible values such as normal speed, immediate time",
            system_text,
        )
        self.assertIn(
            "remain in the source perspective instead of becoming generic role labels",
            system_text,
        )

    def test_primary_prompt_exposes_every_model_facing_binding_dimension_without_model_tuning(
        self,
    ) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="one representative request")
        )
        system_text, _, _ = _payload_message_texts(payload)
        binding_properties = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["binding_items"]["properties"]

        for binding_name in binding_properties:
            self.assertIn(binding_name, system_text)
        for model_or_provider_name in (
            "granite",
            "gemma",
            "ministral",
            "ollama",
            "llama.cpp",
        ):
            self.assertNotIn(model_or_provider_name, system_text.casefold())

    def test_primary_schema_closes_source_token_refs(self) -> None:
        text = "今天晚上重庆热不热"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text, language="zh-CN")
        )["format"]
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        self.assertIn("source_evidence", responsibility["required"])
        evidence = schema["$defs"]["ResponsibilitySourceEvidence"]
        refs = [item["ref"] for item in _source_tokens(text)]
        self.assertEqual(evidence["properties"]["source_start_token_ref"]["enum"], refs)
        self.assertEqual(evidence["properties"]["source_end_token_ref"]["enum"], refs)
        Draft202012Validator.check_schema(schema)

    def test_primary_schema_rejects_binding_relation_and_singleton_coordination(self) -> None:
        text = "continue walking"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )["format"]
        decision = _valid_output(text)
        decision["coordination"] = []
        decision["responsibilities"][0]["bindings"]["parallel_with"] = "r1"

        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(decision)

        sibling_decision = _compound_output()
        for responsibility in sibling_decision["responsibilities"]:
            responsibility.pop("relationship")
            responsibility.pop("target_goal_ids")
            responsibility.pop("bindings")
            responsibility["binding_items"] = {}
        sibling_decision["coordination"] = [
            {"kind": "sequence", "refs": ["r1", "r2"]}
        ]
        sibling_schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="nod then blink")
        )["format"]
        Draft202012Validator(sibling_schema).validate(sibling_decision)

        sibling_decision["coordination"] = [
            {"kind": "parallel", "refs": ["r1"]}
        ]
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(sibling_schema).validate(sibling_decision)

    def test_binding_decoder_order_matches_prompt_in_both_depths_and_contexts(self) -> None:
        interpreter = self._interpreter()
        for context in ({}, {"history": [{"role": "assistant", "text": "Hello there."}]}):
            request = GoalInterpretationRequest(text="what did you say?", context=context)
            for build in (interpreter.build_interpretation_payload,
                          interpreter.build_deep_interpretation_payload):
                with self.subTest(context=context, build=build.__name__):
                    properties = build(request)["format"]["$defs"][
                        "CognitiveResponsibilityProposal"
                    ]["properties"]["binding_items"]["properties"]
                    self.assertEqual(list(properties), sorted(properties))
                    self.assertLess(list(properties).index("direction"),
                                    list(properties).index("duration"))
                    if context:
                        self.assertEqual(properties["prior_assistant_utterance"]["const"],
                                         "Hello there.")

    def test_primary_schema_exposes_sparse_typed_binding_items(self) -> None:
        text = "perform one action with two material modifiers"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )["format"]
        binding_items = schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]
        names = set(binding_items["properties"])

        self.assertEqual(binding_items["type"], "object")
        self.assertFalse(binding_items["additionalProperties"])
        self.assertIn("speed", names)
        self.assertIn("duration", names)
        self.assertIn(
            "owns the complete elapsed-span meaning",
            binding_items["properties"]["duration"]["description"],
        )
        self.assertIn(
            "cutoff for a comparison or condition",
            binding_items["properties"]["threshold"]["description"],
        )
        self.assertNotIn("explicit_numeric_bindings", schema["properties"])

    def test_primary_schema_contrasts_ambiguous_binding_dimensions_and_unresolved(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="one clear request")
        )["format"]
        properties = schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]["properties"]

        self.assertIn(
            "calendar, relative-time, or interval",
            properties["time_scope"]["description"],
        )
        self.assertIn("Never place temporal scope", properties["time_scope"]["description"])
        self.assertIn("Never put elapsed length in count", properties["duration"]["description"])
        self.assertIn(
            "outcome prose alone is not binding evidence",
            properties["duration"]["description"],
        )
        self.assertIn("unknown proper-name-like referent", properties["entity"]["description"])
        self.assertIn("Never use a place", properties["recipient"]["description"])
        self.assertIn("Never list fillers", schema["properties"]["unresolved"]["description"])

    def test_primary_schema_forbids_unknown_semantic_binding_names(self) -> None:
        text = "bring the bottle from 50 meters ahead"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )["format"]
        decision = _valid_output(text)
        responsibility = decision["responsibilities"][0]  # type: ignore[index]
        responsibility.pop("bindings")
        responsibility["binding_items"] = {
            "distance": 50,
            "provider_argument": "meters",
        }
        decision["coordination"] = []

        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(decision)

    def test_prompt_requires_precise_outcome_and_person_target_typing(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="look at me, then nod")
        )
        _, user_text, all_text = _payload_message_texts(payload)

        self.assertNotIn("never classify a person target as location", user_text)
        self.assertNotIn("concrete requested predicate", user_text)
        self.assertIn("person targeted by gaze is entity, not location", all_text)
        self.assertIn("These dimensions are exclusive", all_text)

    def test_primary_schema_keeps_context_backed_location_open_to_host_validation(self) -> None:
        text = "What time is it now?"
        request = GoalInterpretationRequest(
            sid="runtime-secret-sid",
            text=text,
            context={
                "active_goal_snapshots": [
                    {"bindings": {"location": "Chongqing"}}
                ]
            },
        )
        schema = self._interpreter().build_interpretation_payload(request)["format"]
        binding_items = schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]
        location = binding_items["properties"]["location"]
        self.assertEqual(location["$ref"], "#/$defs/SourceBackedBindingString")
        self.assertNotIn("enum", location)
        self.assertNotIn("not", schema["$defs"]["SourceBackedBindingString"])
        self.assertNotIn("runtime-secret-sid", json.dumps(location))
        for name in ("duration", "speed"):
            self.assertEqual(
                binding_items["properties"][name]["anyOf"][0]["$ref"],
                "#/$defs/SourceBackedBindingString",
            )

    def test_fresh_turn_location_is_decoder_constrained_to_exact_source_surfaces(self) -> None:
        text = "今晚重庆会不会下雨哦？"
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )
        source_turn = json.loads(
            _payload_message_texts(payload)[1].split(
                "IMMUTABLE SOURCE TURN JSON (exact Gateway wording; read-only; "
                "Goal Interpretation owns current-turn WHAT):\n",
                1,
            )[1].split("\n", 1)[0]
        )
        location = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["binding_items"]["properties"]["location"]

        self.assertEqual(source_turn["speaker_role"], "user")
        self.assertEqual(source_turn["addressee"], "Chromie")
        self.assertIn("重庆", location["enum"])
        self.assertNotIn("Chongqing", location["enum"])

    def test_decoder_rejects_removed_readiness_fields(self) -> None:
        text = "weather in Chongqing"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )["format"]
        invalid = _valid_output(text)
        invalid["responsibilities"][0]["information_gaps"] = []  # type: ignore[index]
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(invalid)

    def test_fresh_measurements_preserve_source_spelling_in_decoder(self) -> None:
        for text, dimension, exact, translated in (
            ("看着我三秒。", "duration", "三秒", "three seconds"),
            ("持续大约三秒。", "duration", "大约三秒", "about three seconds"),
            ("以每秒两米移动。", "speed", "每秒两米", "two meters per second"),
            ("Move for three seconds.", "duration", "three seconds", "三秒"),
        ):
            with self.subTest(text=text, dimension=dimension):
                request = GoalInterpretationRequest(text=text)
                for build in (
                    self._interpreter().build_interpretation_payload,
                    self._interpreter().build_deep_interpretation_payload,
                ):
                    schema = build(request)["format"]
                    field = schema["$defs"]["CognitiveResponsibilityProposal"][
                        "properties"
                    ]["binding_items"]["properties"][dimension]
                    validator = Draft202012Validator({"$defs": schema["$defs"], **field})
                    validator.validate(exact)
                    validator.validate(3)
                    with self.assertRaises(JsonSchemaValidationError):
                        validator.validate(translated)

    def test_long_measurement_turn_retains_host_provenance_validation(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="Please keep moving for three seconds and then wait for my next request.")
        )["format"]
        properties = schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]["properties"]
        for dimension in ("duration", "speed"):
            self.assertEqual(
                properties[dimension]["anyOf"][0],
                {"$ref": "#/$defs/SourceBackedBindingString"},
            )

    def test_binding_schema_forbids_hidden_effect_and_how_names(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="nod and blink")
        )["format"]
        binding_items = schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["binding_items"]
        names = set(binding_items["properties"])
        for name in ("capability", "provider", "concurrent_action", "agent_skill"):
            self.assertNotIn(name, names)

    def test_goal_interpreter_exposes_no_same_stage_repair_payload(self) -> None:
        self.assertFalse(
            hasattr(self._interpreter(), "build_interpretation_repair_payload")
        )

    def test_deep_payload_is_source_based_without_prior_dto(self) -> None:
        payload = self._interpreter().build_deep_interpretation_payload(
            GoalInterpretationRequest(text="turn it off")
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertEqual(payload["model"], "deep-test-model")
        self.assertFalse(payload["think"])
        self.assertIn("No prior interpretation DTO", user_text)
        self.assertNotIn("coverage certificate", all_text.casefold())

    def test_output_budget_is_not_silently_capped(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid", model="test-model", timeout_ms=800, num_predict=1400
        )
        payload = interpreter.build_interpretation_payload(GoalInterpretationRequest(text="hello"))
        self.assertEqual(payload["options"]["num_predict"], 1400)


class GoalInterpreterExecutionTests(unittest.IsolatedAsyncioTestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid", model="test-model", deep_model="deep-test-model", timeout_ms=800
        )

    async def test_resolved_primary_result_uses_one_model_call(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_valid_output())}}
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].output_mode, "information")
        self.assertEqual(interpreter._chat.await_count, 1)
        self.assertEqual(interpreter._chat.await_args.kwargs["stage"], "goal_interpretation")

    async def test_invalid_primary_speed_is_rejected_without_deletion_or_retry(self) -> None:
        for text, bindings in (
            ("Nod twice.", {"count": 2, "speed": 1}),
            ("点两次头。", {"count": 2, "speed": "正常速度"}),
            ("Nod.", {"speed": True}),
            ("往前走。", {"location": "往前", "speed": "往前"}),
        ):
            with self.subTest(text=text, bindings=bindings):
                interpreter = self._interpreter()
                raw = _valid_output(text)
                raw["responsibilities"][0].update(  # type: ignore[index]
                    outcome=text, bindings=bindings, output_mode="body_action"
                )
                interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
                    return_value={"message": {"content": json.dumps(raw, ensure_ascii=False)}}
                )
                with self.assertRaisesRegex(
                    InterpretationUnavailableError,
                    "invalid_primary_goal_interpretation_semantics.*SpeedProvenanceViolation",
                ):
                    await interpreter.interpret_goal(GoalInterpretationRequest(text=text))
                self.assertEqual(interpreter._chat.await_count, 1)

    async def test_invalid_deep_speed_is_terminal_without_repair_or_primary_fallback(self) -> None:
        interpreter = self._interpreter()
        text = "Nod like before."
        primary = _valid_output(text, unresolved=["which earlier pace is intended"])
        primary["responsibilities"][0].update(  # type: ignore[index]
            outcome=text, bindings={}, output_mode="body_action"
        )
        deep = copy.deepcopy(primary)
        deep["unresolved"] = []
        deep["responsibilities"][0]["bindings"] = {"speed": "normal"}  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(primary)}},
                {"message": {"content": json.dumps(deep)}},
            ]
        )
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "invalid_deep_goal_interpretation.*SpeedProvenanceViolation",
        ):
            await interpreter.interpret_goal(GoalInterpretationRequest(text=text))
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            ["goal_interpretation", "goal_interpretation_deep"],
        )

    async def test_absent_or_source_backed_speed_survives_primary_validation(self) -> None:
        for text, bindings, context in (
            ("Nod twice.", {"count": 2}, {}),
            ("Nod slowly.", {"speed": "slowly"}, {}),
            ("慢慢点头。", {"speed": "慢慢"}, {}),
            ("Nod at speed 0.35", {"speed": 0.35}, {}),
            ("再点头。", {"speed": "慢慢"}, {"history": [{"role": "user", "text": "慢慢"}]}),
        ):
            with self.subTest(text=text, bindings=bindings):
                interpreter = self._interpreter()
                raw = _valid_output(text)
                raw["responsibilities"][0].update(  # type: ignore[index]
                    outcome=text, bindings=bindings, output_mode="body_action"
                )
                interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
                    return_value={"message": {"content": json.dumps(raw, ensure_ascii=False)}}
                )
                result = await interpreter.interpret_goal(
                    GoalInterpretationRequest(text=text, context=context)
                )
                self.assertEqual(result.responsibilities[0].bindings, bindings)
                self.assertEqual(interpreter._chat.await_count, 1)

    async def test_missing_source_evidence_fails_closed_without_second_call(self) -> None:
        interpreter = self._interpreter()
        malformed = _valid_output()
        del malformed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(malformed)}}
        )
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "invalid_primary_goal_interpretation_contract",
        ):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(
                    text="What's the weather in Chongqing today?"
                )
            )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_deep_location_provenance_failure_has_no_same_stage_retry(
        self,
    ) -> None:
        interpreter = self._interpreter()
        text = "今晚重庆会不会下雨？"
        primary = _valid_output(text, unresolved=["whether 重庆 is the intended place"])
        primary_item = primary["responsibilities"][0]  # type: ignore[index]
        primary_item["bindings"] = {"location": "重庆", "time_scope": "今晚"}
        primary_item["outcome"] = "determine whether it will rain in 重庆 tonight"
        deep = copy.deepcopy(primary)
        deep["responsibilities"][0]["bindings"]["location"] = "Chongqing"  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(primary, ensure_ascii=False)}},
                {"message": {"content": json.dumps(deep, ensure_ascii=False)}},
            ]
        )

        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "invalid_deep_goal_interpretation",
        ):
            await interpreter.interpret_goal(GoalInterpretationRequest(text=text))
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            ["goal_interpretation", "goal_interpretation_deep"],
        )

    async def test_semantic_source_overlap_fails_closed_without_reviewer(self) -> None:
        interpreter = self._interpreter()
        invalid = _compound_output()
        invalid["responsibilities"][1]["source_evidence"]["source_start_token_ref"] = "t0"  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaisesRegex(InterpretationUnavailableError, "invalid_primary_goal_interpretation_semantics"):
            await interpreter.interpret_goal(GoalInterpretationRequest(text="nod and blink"))
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_authority_violation_fails_closed_without_reviewer(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaisesRegex(InterpretationUnavailableError, "invalid_primary_goal_interpretation_authority"):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(text="What's the weather in Chongqing today?")
            )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_unresolved_meaning_delegates_once_to_deep(self) -> None:
        interpreter = self._interpreter()
        text = "turn it off"
        decision = _valid_output(text, unresolved=["which device the user means"])
        responsibility = decision["responsibilities"][0]  # type: ignore[index]
        responsibility.update(
            outcome="turn off the referenced device", bindings={}, output_mode="stateful_effect"
        )
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(decision)}},
                {"message": {"content": json.dumps(decision)}},
            ]
        )
        result = await interpreter.interpret_goal(GoalInterpretationRequest(text=text))
        self.assertEqual(result.unresolved, ["which device the user means"])
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            ["goal_interpretation", "goal_interpretation_deep"],
        )

    async def test_atomic_compound_skips_deep_and_audit_calls(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_compound_output())}}
        )
        result = await interpreter.interpret_goal(GoalInterpretationRequest(text="nod and blink"))
        self.assertEqual(len(result.responsibilities), 2)
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_llm_budget_failure_is_typed_unavailable(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=OllamaGenerationError(
                "structured output budget exhausted",
                failure_class="output_truncated",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
            )
        )
        with self.assertRaisesRegex(InterpretationUnavailableError, "structured output budget exhausted"):
            await interpreter.interpret_goal(GoalInterpretationRequest(text="What's the weather today?"))
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_engine_rejects_empty_admitted_input(self) -> None:
        with self.assertRaisesRegex(InterpretationUnavailableError, "empty admitted input"):
            await interpret_goal(GoalInterpretationRequest(text="   "))


if __name__ == "__main__":
    unittest.main()
