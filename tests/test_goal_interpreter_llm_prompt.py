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
    _payload_message_texts,
    _reject_canonical_goal_identity_refs,
    _reject_hidden_effect_or_how_bindings,
    _reject_noncanonical_count_bindings,
    _reject_planner_shaped_goal_interpretation,
    _reject_unavailable_or_mismatched_prior_assistant_utterance,
    _reject_unprovenanced_speed_bindings,
    _source_token_span_surfaces,
    _source_tokens,
    _strip_bound_values_from_unresolved,
    _strip_mechanically_unprovenanced_speed_bindings,
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


class GoalInterpreterContractTests(unittest.TestCase):
    def test_source_tokens_preserve_latin_cjk_and_punctuation(self) -> None:
        self.assertEqual(
            [(item["ref"], item["surface"]) for item in _source_tokens("Walk 前!")],
            [("t0", "Walk"), ("t1", "前"), ("t2", "!")],
        )

    def test_source_token_span_surfaces_are_exact_and_exclude_whole_turn(self) -> None:
        values = _source_token_span_surfaces("Walk forward quickly.")
        self.assertIn("forward", values)
        self.assertIn("forward quickly", values)
        self.assertNotIn("Walk forward quickly.", values)

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
                    "bindings": {"duration": 15, "location": "forward"},
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

    def test_speed_requires_source_provenance(self) -> None:
        with self.assertRaisesRegex(ValueError, "no authoritative surface provenance"):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="run forward for 15 seconds"),
                {"responsibilities": [{"bindings": {"speed": "normal"}}]},
            )

    def test_spatial_surface_cannot_be_retyped_as_speed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Direction/location is never speed"):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN"),
                {"responsibilities": [{"bindings": {"location": "往前", "speed": "往前"}}]},
            )

    def test_unprovenanced_numeric_speed_is_removed(self) -> None:
        parsed = {"responsibilities": [{"bindings": {"count": 2, "speed": 1}}]}
        _strip_mechanically_unprovenanced_speed_bindings(
            GoalInterpretationRequest(text="Nod twice."), parsed
        )
        self.assertEqual(parsed["responsibilities"][0]["bindings"], {"count": 2})

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

    def test_bound_unresolved_duplicate_is_removed(self) -> None:
        parsed = _valid_output()
        parsed["unresolved"] = ["Chongqing", "which forecast provider"]
        _strip_bound_values_from_unresolved(parsed)
        self.assertEqual(parsed["unresolved"], ["which forecast provider"])

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

    def test_primary_prompt_owns_what_and_source_evidence(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="边走边唱歌", language="zh-CN")
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("Authoritative source tokens", user_text)
        self.assertIn("source_evidence", all_text)
        self.assertIn("one primary semantic decision", all_text)
        self.assertNotIn("Common Ability Catalog", all_text)

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

    def test_primary_prompt_foregrounds_explicit_numeric_bindings(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="walk forward for 15 seconds")
        )
        _, user_text, _ = _payload_message_texts(payload)
        self.assertIn("must remain as typed semantic bindings", user_text)
        self.assertIn("[15]", user_text)

    def test_primary_prompt_keeps_action_modifiers_on_one_responsibility(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="walk forward for 15 seconds quickly")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertIn("not three Responsibilities", system_text)
        self.assertIn("never sibling effects", user_text)

    def test_primary_prompt_requires_unknown_name_referent_uncertainty(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="你能查天信吗？", language="zh-CN")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertIn("a non-empty unresolved item", system_text)
        self.assertIn("unresolved must include a bare name", user_text)

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

    def test_primary_schema_closes_location_to_source_or_typed_context(self) -> None:
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
        location = schema["$defs"]["CognitiveResponsibilityProposal"]["properties"][
            "bindings"
        ]["properties"]["location"]
        self.assertIn("now", location["enum"])
        self.assertIn("Chongqing", location["enum"])
        self.assertNotIn("runtime-secret-sid", location["enum"])
        self.assertNotIn(text, location["enum"])

    def test_decoder_rejects_removed_readiness_fields(self) -> None:
        text = "weather in Chongqing"
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text=text)
        )["format"]
        invalid = _valid_output(text)
        invalid["responsibilities"][0]["information_gaps"] = []  # type: ignore[index]
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(invalid)

    def test_binding_schema_forbids_hidden_effect_and_how_names(self) -> None:
        schema = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="nod and blink")
        )["format"]
        bindings = schema["$defs"]["CognitiveResponsibilityProposal"]["properties"]["bindings"]
        self.assertFalse(bindings["additionalProperties"])
        for name in ("capability", "provider", "concurrent_action", "agent_skill"):
            self.assertNotIn(name, bindings["properties"])

    def test_repair_payload_does_not_replay_rejected_output(self) -> None:
        payload = self._interpreter().build_interpretation_repair_payload(
            GoalInterpretationRequest(text="bring water"),
            previous_content='{"capability_id":"soridormi.acquire_water"}',
            validation_error=ValueError("forbidden capability"),
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("Regenerate from the authoritative user meaning", user_text)
        self.assertNotIn("soridormi.acquire_water", all_text)
        self.assertNotIn("forbidden capability", all_text)

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

    async def test_one_dto_repair_restores_missing_source_evidence(self) -> None:
        interpreter = self._interpreter()
        malformed = _valid_output()
        del malformed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(malformed)}},
                {"message": {"content": json.dumps(_valid_output())}},
            ]
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertIsNotNone(result.responsibilities[0].source_evidence)
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            ["goal_interpretation", "goal_interpretation_contract_repair"],
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
