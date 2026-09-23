from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from jsonschema import Draft202012Validator
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.cognitive_core.user_meaning_interpreter.engine import interpret_user_meaning
from agent.app.cognitive_core.user_meaning_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import (
    OllamaUserMeaningInterpreter,
    _UserMeaningInterpretationSemanticStructureViolation,
    _extract_json_object,
    _payload_message_texts,
    _source_tokens,
    _without_user_meaning_interpretation_authority,
)
from agent.app.cognitive_core.user_meaning_interpreter.schema import (
    UserMeaningInterpretationRequest,
)


def _cognitive_requests(*refs: str) -> list[dict[str, object]]:
    scope = list(refs)
    return [
        {
            "authority": "goal_association",
            "responsibility_refs": scope,
            "reason_summary": "Check canonical continuity for the accepted meaning.",
        },
        {
            "authority": "planner",
            "responsibility_refs": scope,
            "reason_summary": "The accepted meaning is ready for HOW reasoning.",
        },
    ]


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
                "output_mode": "information",
                "continuity_scope": "goal",
                "confidence": 0.95,
                "source_evidence": {
                    "source_start_token_ref": tokens[0]["ref"],
                    "source_end_token_ref": tokens[-1]["ref"],
                },
            }
        ],
        "cognitive_requests": _cognitive_requests(local_ref),
        "meaning_uncertainties": [
            {
                "local_ref": f"u{index}",
                "kind": "other",
                "description": value,
                "responsibility_refs": [local_ref],
            }
            for index, value in enumerate(unresolved or [], start=1)
        ],
    }


def _compound_output() -> dict[str, object]:
    def responsibility(
        ref: str, outcome: str, source_ref: str, relation: dict[str, str]
    ) -> dict[str, object]:
        return {
            "local_ref": ref,
            "outcome": outcome,
            "output_mode": "body_action",
            "body_effect_family": "social_expression",
            "continuity_scope": "goal",
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
        "cognitive_requests": _cognitive_requests("r1", "r2"),
        "meaning_uncertainties": [],
    }


class UserMeaningInterpreterContractTests(unittest.TestCase):
    def test_source_tokens_preserve_latin_cjk_and_punctuation(self) -> None:
        self.assertEqual(
            [(item["ref"], item["surface"]) for item in _source_tokens("Walk 前!")],
            [("t0", "Walk"), ("t1", "前"), ("t2", "!")],
        )

    def test_live_primary_validation_requires_source_evidence(self) -> None:
        parsed = _valid_output()
        del parsed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "lacks source_evidence"):
            OllamaUserMeaningInterpreter._validate_interpretation_content(
                UserMeaningInterpretationRequest(
                    text="What's the weather in Chongqing today?"
                ),
                json.dumps(parsed),
            )

    def test_primary_source_evidence_accepts_known_ordered_refs(self) -> None:
        decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
            UserMeaningInterpretationRequest(text="What's the weather in Chongqing today?"),
            json.dumps(_valid_output()),
        )
        self.assertEqual(decision.responsibilities[0].local_ref, "r1")

    def test_primary_planner_activation_does_not_require_model_authored_sc(self) -> None:
        parsed = _valid_output()
        parsed["cognitive_requests"] = [
            {
                "authority": "planner",
                "responsibility_refs": ["r1"],
                "reason_summary": "The accepted meaning is ready for HOW reasoning.",
            },
        ]

        decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
            UserMeaningInterpretationRequest(
                text="What's the weather in Chongqing today?"
            ),
            json.dumps(parsed),
        )

        self.assertEqual(
            [item.authority for item in decision.cognitive_requests],
            ["planner"],
        )

    def test_primary_validation_accepts_empty_non_standing_cognitive_requests(self) -> None:
        request = UserMeaningInterpretationRequest(
            text="What's the weather in Chongqing today?"
        )
        parsed = _valid_output()
        parsed["cognitive_requests"] = []

        decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
            request, json.dumps(parsed),
        )

        self.assertEqual(decision.cognitive_requests, [])

    def test_primary_source_evidence_rejects_unknown_refs(self) -> None:
        parsed = _valid_output()
        parsed["responsibilities"][0]["source_evidence"][  # type: ignore[index]
            "source_end_token_ref"
        ] = "t999"
        with self.assertRaisesRegex(ValueError, "unknown authoritative"):
            OllamaUserMeaningInterpreter._validate_interpretation_content(
                UserMeaningInterpretationRequest(text="What's the weather in Chongqing today?"),
                json.dumps(parsed),
            )

    def test_mixed_greeting_and_work_requires_turn_wide_ga_and_scoped_planner(self) -> None:
        request = UserMeaningInterpretationRequest(text="Hi. Turn left.")
        parsed = _compound_output()
        parsed["responsibilities"][0].update(
            outcome="Respond to the greeting", output_mode="speech", body_effect_family=None, continuity_scope="turn",
            source_evidence={"source_start_token_ref": "t0", "source_end_token_ref": "t1"},
        )
        parsed["responsibilities"][1].update(
            outcome="Turn left", body_effect_family="task_physical_effect", continuity_scope="goal",
            source_evidence={"source_start_token_ref": "t2", "source_end_token_ref": "t4"},
        )
        parsed["cognitive_requests"][1]["responsibility_refs"] = ["r2"]
        for omitted_scope in (["r1"], ["r2"]):
            with self.subTest(ga_refs=omitted_scope):
                parsed["cognitive_requests"][0]["responsibility_refs"] = omitted_scope
                with self.assertRaisesRegex(ValueError, "turn-wide"):
                    OllamaUserMeaningInterpreter._validate_interpretation_content(
                        request, json.dumps(parsed),
                    )
        parsed["cognitive_requests"][0]["responsibility_refs"] = ["r1", "r2"]
        decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
            request, json.dumps(parsed),
        )
        self.assertEqual(
            {item.authority: item.responsibility_refs for item in decision.cognitive_requests},
            {"goal_association": ["r1", "r2"], "planner": ["r2"]},
        )

    def test_primary_source_evidence_rejects_reversed_refs(self) -> None:
        parsed = _valid_output()
        evidence = parsed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        evidence["source_start_token_ref"] = "t2"
        evidence["source_end_token_ref"] = "t0"
        with self.assertRaisesRegex(ValueError, "endpoints are reversed"):
            OllamaUserMeaningInterpreter._validate_interpretation_content(
                UserMeaningInterpretationRequest(text="What's the weather in Chongqing today?"),
                json.dumps(parsed),
            )

    def test_primary_source_evidence_rejects_independent_overlap(self) -> None:
        parsed = _compound_output()
        parsed["responsibilities"][1]["source_evidence"][  # type: ignore[index]
            "source_start_token_ref"
        ] = "t0"
        with self.assertRaisesRegex(
            _UserMeaningInterpretationSemanticStructureViolation, "spans overlap"
        ):
            OllamaUserMeaningInterpreter._validate_interpretation_content(
                UserMeaningInterpretationRequest(text="nod and blink"), json.dumps(parsed)
            )

    def test_primary_source_evidence_allows_disjoint_atomic_siblings(self) -> None:
        decision = OllamaUserMeaningInterpreter._validate_interpretation_content(
            UserMeaningInterpretationRequest(text="nod and blink"),
            json.dumps(_compound_output()),
        )
        self.assertEqual(
            [item.local_ref for item in decision.responsibilities], ["r1", "r2"]
        )




















    def test_context_projection_removes_downstream_authority(self) -> None:
        projected = _without_user_meaning_interpretation_authority(
            {"goal_id": "goal-1", "route": "tool", "nested": {"capability_id": "weather", "outcome": "weather"}}
        )
        self.assertEqual(projected, {"goal_id": "goal-1", "nested": {"outcome": "weather"}})

    def test_extract_json_object_accepts_fenced_json(self) -> None:
        self.assertEqual(_extract_json_object("```json\n{\"confidence\":1}\n```"), {"confidence": 1})




def test_umi_system_prompt_preserves_information_delivery_as_terminal_what() -> None:
    prompt = (
        Path(__file__).parents[1]
        / "agent/app/cognitive_core/user_meaning_interpreter/prompts/user_meaning_interpreter_system.txt"
    ).read_text(encoding="utf-8")
    assert "made available to the intended recipient" in prompt
    assert "Acquiring or checking the source alone is not" in prompt
    assert "the complete WHAT" in prompt

class UserMeaningInterpreterPromptTests(unittest.TestCase):
    def _interpreter(self) -> OllamaUserMeaningInterpreter:
        return OllamaUserMeaningInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            deep_model="deep-test-model",
            timeout_ms=800,
        )

    def test_primary_decoder_and_host_agree_on_source_span_order(self) -> None:
        text = "Give the box to Dad."
        request = UserMeaningInterpretationRequest(text=text)
        validator = Draft202012Validator(self._interpreter().build_interpretation_payload(request)["format"])
        for start in range(len(_source_tokens(text)) + 1):
            for end in range(len(_source_tokens(text)) + 1):
                parsed = _valid_output(text)
                parsed["responsibilities"][0]["source_evidence"] = {
                    "source_start_token_ref": f"t{start}", "source_end_token_ref": f"t{end}",
                }
                try:
                    OllamaUserMeaningInterpreter._validate_interpretation_content(request, json.dumps(parsed))
                    expected = True
                except ValueError:
                    expected = False
                with self.subTest(start=start, end=end):
                    self.assertEqual(validator.is_valid(parsed), expected)

    def test_primary_and_deep_keep_complete_long_turn_source_tokens(self) -> None:
        interpreter = self._interpreter()
        for text in (
            "The labelled box is beside " + "the marked shelf and " * 40 + "bring it to Dad, not me.",
            "沿着走廊经过" + "左侧标记的架子和" * 30 + "把盒子交给爸爸，不要交给我。",
        ):
            request = UserMeaningInterpretationRequest(text=text)
            expected = _source_tokens(request.text)
            self.assertGreater(len(json.dumps(expected, ensure_ascii=False)), 5000)
            for build in (interpreter.build_interpretation_payload, interpreter.build_deep_interpretation_payload):
                with self.subTest(language=text[:8], variant=build.__name__):
                    payload = build(request)
                    prompt = payload["messages"][1]["content"]
                    table, _ = json.JSONDecoder().raw_decode(prompt.split("Responsibility.source_evidence):\n", 1)[1])
                    self.assertEqual(table, expected)
                    evidence_schema = payload["format"]["$defs"]["ResponsibilitySourceEvidence"]
                    validator = Draft202012Validator(evidence_schema)
                    self.assertTrue(validator.is_valid({"source_start_token_ref": table[0]["ref"], "source_end_token_ref": table[-1]["ref"]}))

    def test_oversized_complete_source_table_fails_before_transport(self) -> None:
        import asyncio

        interpreter = self._interpreter()
        interpreter.num_ctx = 16384
        request = UserMeaningInterpretationRequest(text="word " * 2000 + "bring it to Dad, not me.")
        payload = interpreter.build_interpretation_payload(request)
        with mock.patch("agent.app.cognitive_core.user_meaning_interpreter.model_interpreter.httpx.AsyncClient") as transport:
            with self.assertRaises(OllamaGenerationError) as caught:
                asyncio.run(interpreter._chat(payload, stage="user_meaning_interpretation"))
        self.assertEqual(caught.exception.failure_class, "prompt_budget_exceeded")
        transport.assert_not_called()

    def test_runtime_correlation_labels_do_not_change_model_input(self) -> None:
        interpreter = self._interpreter()
        for key in ("conversation_id", "session_id", "turn_id", "sid"):
            first = UserMeaningInterpretationRequest(
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


    def test_identity_boundary_is_lossless_in_both_interpretation_prompts(self) -> None:
        boundary = (
            "Chromie's body is robotic. Her social identity is not a claim "
            "of biological human age, birth history, or physiology."
        )
        request = UserMeaningInterpretationRequest(
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
        request = UserMeaningInterpretationRequest(
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






    def test_working_conversational_memory_resolves_followup_without_leaking_goal_identity(self) -> None:
        interpreter = self._interpreter()
        request = UserMeaningInterpretationRequest(
            text="Please add ice to it.",
            context={
                "history": [
                    {"role": "user", "text": "Bring me a cup of coffee."},
                    {"role": "assistant", "text": "Sure."},
                ],
                "user_meaning_goal_context": [{
                    "goal_id": "goal-coffee-secret",
                    "responsibility_status": "open",
                    "goal": {
                        "goal_id": "goal-coffee-secret",
                        "description": "Bring a cup of coffee to the user.",
                        "object": {"resource": "cup of coffee"},
                        "constraints": {},
                        "metadata": {"output_mode": "body_action"},
                    },
                    "source_task_id": "task-coffee-secret",
                    "last_user_update": "Bring me a cup of coffee.",
                }],
                "discourse_referents": [{
                    "referent_id": "ref-coffee-secret",
                    "entity_type": "physical_object",
                    "canonical_value": "cup of coffee",
                    "aliases": ["coffee"],
                    "scope_kind": "goal",
                    "scope_ids": ["goal-coffee-secret"],
                    "status": "foreground",
                    "confidence": 1.0,
                    "source_turn_id": "turn-coffee-secret",
                    "source_goal_ids": ["goal-coffee-secret"],
                }],
                "discourse_focus": ["ref-coffee-secret"],
            },
        )

        payload = interpreter.build_interpretation_payload(request)
        _system, user_text, _all = _payload_message_texts(payload)

        self.assertIn("Working Conversational Memory", user_text)
        self.assertIn("Bring me a cup of coffee.", user_text)
        self.assertIn("Bring a cup of coffee to the user.", user_text)
        self.assertIn('"canonical_value":"cup of coffee"', user_text)
        self.assertIn('"salience":"focus"', user_text)
        self.assertNotIn("goal-coffee-secret", user_text)
        self.assertNotIn("task-coffee-secret", user_text)
        self.assertNotIn("ref-coffee-secret", user_text)

    def test_working_conversational_memory_supports_elliptical_constraint_followup(self) -> None:
        interpreter = self._interpreter()
        request = UserMeaningInterpretationRequest(
            text="No sugar.",
            context={
                "history": [{"role": "user", "text": "Bring me a cup of coffee."}],
                "user_meaning_goal_context": [{
                    "goal": {
                        "description": "Bring a cup of coffee to the user.",
                        "object": {"resource": "cup of coffee"},
                        "constraints": {},
                        "metadata": {"output_mode": "body_action"},
                    },
                    "responsibility_status": "open",
                }],
                "discourse_referents": [{
                    "referent_id": "ref-coffee",
                    "entity_type": "physical_object",
                    "canonical_value": "cup of coffee",
                    "aliases": ["coffee"],
                    "scope_kind": "conversation",
                    "scope_ids": [],
                    "status": "foreground",
                    "confidence": 1.0,
                    "source_turn_id": "turn-coffee",
                    "source_goal_ids": [],
                }],
                "discourse_focus": ["ref-coffee"],
            },
        )
        _system, user_text, _all = _payload_message_texts(
            interpreter.build_interpretation_payload(request)
        )
        self.assertIn("No sugar.", user_text)
        self.assertIn("cup of coffee", user_text)
        self.assertIn("omitted repeated subjects", user_text)

    def test_primary_prompt_does_not_expose_runtime_sid(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            UserMeaningInterpretationRequest(
                sid="runtime-secret-sid",
                text="What time is it now?",
                language="en-US",
            )
        )
        _, _, all_text = _payload_message_texts(payload)
        self.assertNotIn("runtime-secret-sid", all_text)

    def test_primary_prompt_does_not_expose_planner_target_realization(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            UserMeaningInterpretationRequest(
                text="look at me",
                context={
                    "active_user_target": {
                        "target_ref": "opaque-current-speaker",
                        "relative_direction": "front",
                    },
                    "planner_target_evidence_context": {
                        "target_evidence": {
                            "available": True,
                            "target": {"target_ref": "opaque-current-speaker"},
                        }
                    },
                    "planner_auxiliary_social_context": {
                        "eligible_capabilities": [{"capability_id": "legacy-social"}],
                    },
                },
            )
        )

        _, _, all_text = _payload_message_texts(payload)

        self.assertNotIn("opaque-current-speaker", all_text)
        self.assertNotIn("active_user_target", all_text)
        self.assertNotIn("planner_auxiliary_social_context", all_text)
        self.assertNotIn("planner_target_evidence_context", all_text)

    def test_primary_prompt_exposes_semantic_identity_not_presentation_profile(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            UserMeaningInterpretationRequest(
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
            UserMeaningInterpretationRequest(text="walk forward for 15 seconds")
        )
        system_text, user_text, _ = _payload_message_texts(payload)
        self.assertNotIn("Explicit Arabic numeric values", user_text)
        self.assertNotIn("[15]", user_text)
        self.assertNotIn("Every listed explicit Arabic number", system_text)
        self.assertNotIn("speed V plus duration D", user_text)
        self.assertIn("IMMUTABLE SOURCE TURN JSON", user_text)
        self.assertIn('"original_text":"walk forward for 15 seconds"', user_text)





    def test_primary_prompt_preserves_exact_gateway_wording_once(self) -> None:
        exact = "  今晚，重庆热不热？  "
        payload = self._interpreter().build_interpretation_payload(
            UserMeaningInterpretationRequest(
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
        self.assertIn("User Meaning Interpretation owns current-turn WHAT", user_text)












    def test_primary_schema_closes_source_token_refs(self) -> None:
        text = "今天晚上重庆热不热"
        schema = self._interpreter().build_interpretation_payload(
            UserMeaningInterpretationRequest(text=text, language="zh-CN")
        )["format"]
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        self.assertIn("oneOf", responsibility)
        self.assertTrue(all(
            "source_evidence" in branch["required"]
            for branch in responsibility["oneOf"]
        ))
        evidence = schema["$defs"]["ResponsibilitySourceEvidence"]
        refs = [item["ref"] for item in _source_tokens(text)]
        validator = Draft202012Validator(evidence)
        for ref in refs:
            self.assertTrue(validator.is_valid({"source_start_token_ref": ref, "source_end_token_ref": ref}))
        self.assertFalse(validator.is_valid({"source_start_token_ref": refs[0], "source_end_token_ref": "t999"}))
        Draft202012Validator.check_schema(schema)















    def test_user_meaning_interpreter_exposes_no_same_stage_repair_payload(self) -> None:
        self.assertFalse(
            hasattr(self._interpreter(), "build_interpretation_repair_payload")
        )


    def test_output_budget_is_not_silently_capped(self) -> None:
        interpreter = OllamaUserMeaningInterpreter(
            ollama_url="http://example.invalid", model="test-model", timeout_ms=800, num_predict=1400
        )
        payload = interpreter.build_interpretation_payload(UserMeaningInterpretationRequest(text="hello"))
        self.assertEqual(payload["options"]["num_predict"], 1400)







class UserMeaningInterpreterExecutionTests(unittest.IsolatedAsyncioTestCase):

    async def test_primary_rejects_lossy_representation_repairs(self) -> None:
        cases = [
            ("missing confidence", {}, {"confidence": None}),
            ("planner-owned action", {"action": "blink as well"}, {}),
            ("raw-turn replay", {"user_input": "Nod twice."}, {}),
            ("renamed binding", [{"name": " count ", "value": 2}], {}),
            ("malformed meaning uncertainty", {}, {"meaning_uncertainties": [False]}),
            ("unknown coordination", {}, {"coordination": [{"kind": "sequence", "refs": ["r1", "r2"], "unless": "cancelled"}]}),
        ]
        for label, bindings, overrides in cases:
            with self.subTest(case=label):
                text = "Nod twice."
                raw = _valid_output(text)
                raw["responsibilities"][0].update(
                    outcome="nod", bindings=bindings, output_mode="speech"
                )
                raw.update(overrides)
                if label == "missing confidence":
                    del raw["confidence"]
                if label == "unknown coordination":
                    second = copy.deepcopy(raw["responsibilities"][0])
                    second.update(local_ref="r2", outcome="blink")
                    raw["responsibilities"][0]["source_evidence"] = {"source_start_token_ref": "t0", "source_end_token_ref": "t0"}
                    second["source_evidence"] = {"source_start_token_ref": "t1", "source_end_token_ref": "t1"}
                    raw["responsibilities"].append(second)
                interpreter = self._interpreter()
                interpreter._chat = mock.AsyncMock(
                    return_value={"message": {"content": json.dumps(raw, ensure_ascii=False)}}
                )
                with self.assertRaises(InterpretationUnavailableError):
                    await interpreter.interpret_user_meaning(
                        UserMeaningInterpretationRequest(text=text, language="en-US")
                    )
                self.assertEqual(interpreter._chat.await_count, 1)


    def test_parser_rejects_discarded_or_duplicate_claims(self) -> None:
        for raw in ('prefix {"confidence":1}', '{"confidence":1} suffix',
                    '{"confidence":0,"confidence":1}', '{"confidence":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                _extract_json_object(raw)

    def _interpreter(self) -> OllamaUserMeaningInterpreter:
        return OllamaUserMeaningInterpreter(
            ollama_url="http://example.invalid", model="test-model", deep_model="deep-test-model", timeout_ms=800
        )


    async def test_resolved_primary_result_uses_one_model_call(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_valid_output())}}
        )
        result = await interpreter.interpret_user_meaning(
            UserMeaningInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].outcome, "provide today's weather for Chongqing")
        self.assertEqual(interpreter._chat.await_count, 1)
        self.assertEqual(interpreter._chat.await_args.kwargs["stage"], "user_meaning_interpretation")





    async def test_missing_source_evidence_fails_closed_without_second_call(self) -> None:
        interpreter = self._interpreter()
        malformed = _valid_output()
        del malformed["responsibilities"][0]["source_evidence"]  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(malformed)}}
        )
        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "invalid_primary_user_meaning_interpretation_contract",
        ):
            await interpreter.interpret_user_meaning(
                UserMeaningInterpretationRequest(
                    text="What's the weather in Chongqing today?"
                )
            )
        self.assertEqual(interpreter._chat.await_count, 1)


    async def test_semantic_source_overlap_fails_closed_without_reviewer(self) -> None:
        interpreter = self._interpreter()
        invalid = _compound_output()
        invalid["responsibilities"][1]["source_evidence"]["source_start_token_ref"] = "t0"  # type: ignore[index]
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaisesRegex(InterpretationUnavailableError, "invalid_primary_user_meaning_interpretation_semantics"):
            await interpreter.interpret_user_meaning(UserMeaningInterpretationRequest(text="nod and blink"))
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_authority_violation_fails_closed_without_reviewer(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaisesRegex(InterpretationUnavailableError, "invalid_primary_user_meaning_interpretation_authority"):
            await interpreter.interpret_user_meaning(
                UserMeaningInterpretationRequest(text="What's the weather in Chongqing today?")
            )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_unresolved_meaning_delegates_once_to_deep(self) -> None:
        interpreter = self._interpreter()
        text = "turn it off"
        decision = _valid_output(text, unresolved=["which device the user means"])
        responsibility = decision["responsibilities"][0]  # type: ignore[index]
        responsibility.update(
            outcome="turn off the referenced device"
        )
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(decision)}},
                {"message": {"content": json.dumps(decision)}},
            ]
        )
        result = await interpreter.interpret_user_meaning(UserMeaningInterpretationRequest(text=text))
        self.assertEqual([item.description for item in result.meaning_uncertainties], ["which device the user means"])
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            ["user_meaning_interpretation", "user_meaning_interpretation_deep"],
        )

    async def test_atomic_compound_skips_deep_and_audit_calls(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_compound_output())}}
        )
        result = await interpreter.interpret_user_meaning(UserMeaningInterpretationRequest(text="nod and blink"))
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
            await interpreter.interpret_user_meaning(UserMeaningInterpretationRequest(text="What's the weather today?"))
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_engine_rejects_empty_admitted_input(self) -> None:
        with self.assertRaisesRegex(InterpretationUnavailableError, "empty admitted input"):
            await interpret_user_meaning(UserMeaningInterpretationRequest(text="   "))


if __name__ == "__main__":
    unittest.main()


def test_user_meaning_interpreter_keeps_multi_action_physical_compounds_body_action() -> None:
    from pathlib import Path

    prompt = (
        Path("agent/app/cognitive_core/user_meaning_interpreter/prompts/user_meaning_interpreter_system.txt")
        .read_text(encoding="utf-8")
    )
    assert "do not use other merely because the compound has" in prompt
    assert "several actions or Activities" in prompt
    assert "different observable result domains" in prompt

def test_user_meaning_interpreter_scope_prompt_distinguishes_work_from_duration() -> None:
    from pathlib import Path

    prompt = (
        Path("agent/app/cognitive_core/user_meaning_interpreter/prompts/user_meaning_interpreter_system.txt")
        .read_text(encoding="utf-8")
    )
    assert "goal does\nNOT mean long-term, cross-session" in prompt
    assert "Every non-speech output_mode therefore\nuses goal" in prompt
    assert "Use turn for ordinary current-conversation\nspeech" in prompt
    assert "GA owns that continuity judgment" in prompt
