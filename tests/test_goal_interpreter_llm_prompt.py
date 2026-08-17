from __future__ import annotations

import json
import unittest
from unittest import mock

from pydantic import ValidationError

from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from agent.app.cognitive_core.goal_interpreter.engine import interpret_goal
from agent.app.cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _extract_json_object,
    _payload_message_texts,
    _reject_canonical_goal_identity_refs,
    _reject_planner_shaped_goal_interpretation,
    _without_goal_interpretation_authority,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    GoalInterpretationDecision,
    GoalInterpretationRequest,
)


def _valid_output(*, local_ref: str = "r1") -> dict[str, object]:
    return {
        "confidence": 0.93,
        "responsibilities": [
            {
                "local_ref": local_ref,
                "outcome": "provide today's weather for Chongqing",
                "bindings": {"location": "Chongqing", "time": "today"},
                "completion_requires_work": True,
                "completion_requires_fresh_evidence": True,
                "confidence": 0.95,
            }
        ],
        "unresolved": [],
    }


class GoalInterpreterContractTests(unittest.TestCase):
    def test_user_resolvable_gap_names_the_missing_semantic_value(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ask_user required_for entries must be unresolved semantic binding names",
        ):
            CognitiveResponsibilityProposal(
                local_ref="weather",
                outcome="report today's daytime weather in Chongqing",
                bindings={
                    "location": "重庆",
                    "date": "today",
                    "time_of_day": "白天",
                },
                information_gaps=[
                    {
                        "gap_id": "weather_result",
                        "description": "The current weather result is not known yet.",
                        "blocking": True,
                        "required_for": ["weather data for Chongqing"],
                        "preferred_resolution": "ask_user",
                    }
                ],
                completion_requires_work=True,
                completion_requires_fresh_evidence=True,
                confidence=0.95,
            )

        valid = CognitiveResponsibilityProposal(
            local_ref="weather",
            outcome="report today's weather at the user's location",
            bindings={"date": "today"},
            information_gaps=[
                {
                    "gap_id": "weather_location",
                    "description": "The requested location is missing.",
                    "blocking": True,
                    "required_for": ["location"],
                    "preferred_resolution": "ask_user",
                }
            ],
            completion_requires_work=True,
            completion_requires_fresh_evidence=True,
            confidence=0.9,
        )
        self.assertEqual(valid.information_gaps[0].required_for, ["location"])

    def test_responsibility_rejects_planner_owned_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "Planner-owned field"):
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome="provide today's Chongqing weather",
                bindings={
                    "location": "Chongqing",
                    "capability_id": "chromie.weather.lookup",
                },
                completion_requires_work=True,
                completion_requires_fresh_evidence=True,
                confidence=0.95,
            )

    def test_external_evidence_is_not_top_level_semantic_uncertainty(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "external Evidence acquisition is not unresolved semantic meaning",
        ):
            GoalInterpretationDecision.model_validate(
                {
                    "confidence": 0.95,
                    "responsibilities": [
                        {
                            "local_ref": "weather",
                            "outcome": "Describe today's daytime weather in Chongqing.",
                            "bindings": {
                                "location": "重庆",
                                "date": "today",
                                "time_of_day": "白天",
                            },
                            "information_gaps": [
                                {
                                    "gap_id": "weather_result",
                                    "description": "current weather data for Chongqing",
                                    "preferred_resolution": "query_trusted_service",
                                }
                            ],
                            "completion_requires_work": True,
                            "completion_requires_fresh_evidence": True,
                            "confidence": 0.95,
                        }
                    ],
                    "unresolved": ["current weather data for Chongqing"],
                }
            )

    def test_decision_contract_is_what_only(self) -> None:
        schema = GoalInterpretationDecision.model_json_schema()
        self.assertEqual(
            set(schema["properties"]),
            {"confidence", "responsibilities", "unresolved"},
        )
        serialized = json.dumps(schema, sort_keys=True)
        for forbidden in (
            '"route"',
            '"intent"',
            '"fast_speech"',
            '"progress"',
            '"actions"',
            '"candidate_capabilities"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_goal_interpretation_request_normalizes_text(self) -> None:
        request = GoalInterpretationRequest(text="  bring   me water  ")
        self.assertEqual(request.text, "bring me water")

    def test_route_and_how_fields_fail_closed_before_typed_validation(self) -> None:
        for field, value in (
            ("route", "tool"),
            ("intent", "weather_lookup"),
            ("actions", []),
            ("plan", {"steps": []}),
            ("capability_id", "chromie.weather.lookup"),
            ("response_text", "I'll check."),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "downstream-owned field"):
                    _reject_planner_shaped_goal_interpretation(
                        {**_valid_output(), field: value}
                    )

    def test_local_ref_cannot_reuse_canonical_goal_identity(self) -> None:
        request = GoalInterpretationRequest(
            text="Bring me the bottle.",
            context={"recent_goal_snapshots": [{"goal_id": "goal-previous"}]},
        )
        parsed = _valid_output(local_ref="goal-previous")
        with self.assertRaisesRegex(ValueError, "reused canonical Goal identity"):
            _reject_canonical_goal_identity_refs(request, parsed)

    def test_context_projection_removes_route_and_downstream_identity_recursively(self) -> None:
        projected = _without_goal_interpretation_authority(
            {
                "route": "robot_action",
                "intent": "walk_forward",
                "goal_id": "goal-1",
                "nested": {
                    "capability_id": "soridormi.walk_forward",
                    "meaning": "walk forward for ten seconds",
                },
            }
        )
        self.assertEqual(
            projected,
            {
                "goal_id": "goal-1",
                "nested": {"meaning": "walk forward for ten seconds"},
            },
        )

    def test_extract_json_object_accepts_fenced_json(self) -> None:
        self.assertEqual(
            _extract_json_object('```json\n{"confidence": 1}\n```'),
            {"confidence": 1},
        )


class GoalInterpreterPromptTests(unittest.TestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
        )

    def test_system_prompt_names_what_only_boundary(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("only authority is to understand WHAT", prompt)
        self.assertIn("provider-neutral Responsibility evidence", prompt)
        self.assertIn("route or intent labels", prompt)
        self.assertIn("ability catalog is intentionally not supplied", prompt)
        self.assertNotIn("Route Taxonomy", prompt)
        self.assertNotIn("Compatibility Framing", prompt)

    def test_system_prompt_preserves_direct_entity_surface_and_rejects_provider_time_uncertainty(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("exact contiguous surface", prompt)
        self.assertIn("Never translate, transliterate", prompt)
        self.assertIn("provider timezone", prompt)
        self.assertIn("never an unresolved WHAT question", prompt)

    def test_system_prompt_preserves_requested_judgment_without_asserting_the_answer(self) -> None:
        prompt = self._interpreter().load_system_prompt().casefold()
        self.assertIn("preserve the requested judgment", prompt)
        self.assertIn("whether the proposition is true", prompt)
        self.assertIn("must not become an assertion", prompt)
        self.assertIn("does not become unresolved merely because its answer is unknown", prompt)
        self.assertIn("reasoning from facts already supplied by the user", prompt)

    def test_decision_confidence_is_required_model_evidence(self) -> None:
        schema = GoalInterpretationDecision.model_json_schema()
        self.assertIn("confidence", schema["required"])

    def test_payload_omits_capability_catalog_and_route_contract(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            sid="weather-sid",
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the robot eyes.",
                        "route": "robot_action",
                    }
                ]
            },
        )
        payload = interpreter.build_interpretation_payload(request)
        system_text, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("今天重庆天气怎么样？", user_text)
        self.assertIn("provider-neutral", system_text)
        self.assertNotIn("soridormi.blink_eyes", all_text)
        self.assertNotIn("Common Ability Catalog", all_text)
        self.assertEqual(
            set(payload["format"]["properties"]),
            {"confidence", "responsibilities", "unresolved"},
        )
        self.assertEqual(
            set(
                payload["format"]["$defs"][
                    "CognitiveResponsibilityProposal"
                ]["required"]
            ),
            {
                "local_ref",
                "outcome",
                "bindings",
                "relationship",
                "target_goal_ids",
                "information_gaps",
                "resolved_gap_ids",
                "completion_requires_work",
                "completion_requires_fresh_evidence",
                "confidence",
            },
        )
        gap_schema = payload["format"]["$defs"]["InformationGap"]
        self.assertEqual(
            gap_schema["properties"]["required_for"]["items"]["pattern"],
            "^[a-z][a-z0-9_]{0,79}$",
        )

    def test_repair_schema_excludes_already_bound_user_gap_names(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="你好，今天重庆白天天气怎么样啊？",
            language="zh-CN",
        )
        try:
            CognitiveResponsibilityProposal(
                local_ref="weather",
                outcome="report today's daytime weather in Chongqing",
                bindings={"location": "重庆", "date": "today"},
                information_gaps=[
                    {
                        "gap_id": "weather_result",
                        "description": "Current weather has not been queried.",
                        "required_for": ["location", "date"],
                        "preferred_resolution": "ask_user",
                    }
                ],
                completion_requires_work=True,
                completion_requires_fresh_evidence=True,
                confidence=0.95,
            )
        except ValidationError as exc:
            payload = interpreter.build_interpretation_repair_payload(
                request,
                previous_content="rejected",
                validation_error=exc,
            )
        else:  # pragma: no cover - protects the regression setup itself
            self.fail("invalid ask_user gap unexpectedly passed validation")

        gap_schema = payload["format"]["$defs"]["InformationGap"]
        encoded_schema = json.dumps(gap_schema, sort_keys=True)
        self.assertIn('"enum": ["date", "location"]', encoded_schema)
        self.assertIn('"not"', encoded_schema)
        self.assertEqual(payload["format"]["properties"]["unresolved"]["maxItems"], 0)
        system_text, _, _ = _payload_message_texts(payload)
        self.assertIn("already-bound value", system_text)
        self.assertIn("open descriptive question", system_text)

    def test_prompt_keeps_semantic_continuity_with_context_goal_identity_but_no_route(self) -> None:
        prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                sid="s1",
                text="Make that one iced.",
                context={
                    "history": [
                        {
                            "role": "user",
                            "text": "Bring me a coffee.",
                            "route": "tool",
                            "intent": "coffee",
                        }
                    ],
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-coffee",
                            "responsibility_status": "open",
                            "goal": {"description": "obtain coffee for the user"},
                        }
                    ],
                },
            )
        )
        self.assertIn("Bring me a coffee", prompt)
        self.assertIn("obtain coffee for the user", prompt)
        self.assertIn("goal-coffee", prompt)
        self.assertNotIn('"route"', prompt)
        self.assertNotIn('"intent"', prompt)

    def test_repair_prompt_does_not_replay_rejected_output(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(text="Bring me water.")
        payload = interpreter.build_interpretation_repair_payload(
            request,
            previous_content='{"capability_id":"soridormi.acquire_water"}',
            validation_error=ValueError("forbidden capability"),
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("Regenerate from the authoritative user meaning", user_text)
        self.assertNotIn("soridormi.acquire_water", all_text)
        self.assertNotIn("forbidden capability", all_text)


class GoalInterpreterExecutionTests(unittest.IsolatedAsyncioTestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
        )

    async def test_interpret_goal_accepts_valid_what_only_output(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_valid_output())}}
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].local_ref, "r1")
        self.assertTrue(result.responsibilities[0].completion_requires_fresh_evidence)
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_unprovenanced_translated_location_gets_one_dto_repair(self) -> None:
        interpreter = self._interpreter()
        translated = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "provide tonight's weather for Chongqing",
                    "bindings": {"location": "Chongqing", "time": "tonight"},
                }
            ],
        }
        corrected = {
            **translated,
            "responsibilities": [
                {
                    **translated["responsibilities"][0],
                    "bindings": {"location": "重庆", "time": "tonight"},
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(translated)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="今天晚上重庆会不会下雨啊？",
                language="zh-CN",
            )
        )
        self.assertEqual(result.responsibilities[0].bindings["location"], "重庆")
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_external_weather_result_gap_gets_one_dto_repair(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "weather",
                    "outcome": "report today's daytime weather in Chongqing",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "time_of_day": "白天",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "information_gaps": [
                        {
                            "gap_id": "weather_result",
                            "description": "The current weather result is not known yet.",
                            "blocking": True,
                            "required_for": ["weather data for Chongqing"],
                            "preferred_resolution": "ask_user",
                            "candidate_values": [],
                            "resolved": False,
                            "resolution_value": None,
                            "metadata": {},
                        }
                    ],
                    "resolved_gap_ids": [],
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                }
            ],
            "unresolved": ["The current weather result is not known yet."],
        }
        corrected = {
            **invalid,
            "responsibilities": [
                {
                    **invalid["responsibilities"][0],
                    "information_gaps": [],
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="你好，今天重庆白天天气怎么样啊？",
                language="zh-CN",
            )
        )

        responsibility = result.responsibilities[0]
        self.assertEqual(responsibility.information_gaps, [])
        self.assertTrue(responsibility.completion_requires_fresh_evidence)
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_external_query_gap_cannot_be_repeated_as_semantic_uncertainty(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "determine whether Chongqing is sunny today",
                    "bindings": {
                        "location": "重庆",
                        "time": "today",
                        "time_of_day": "daytime",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "information_gaps": [
                        {
                            "gap_id": "info_gap_1",
                            "description": "current weather data for Chongqing",
                            "preferred_resolution": "query_trusted_service",
                        }
                    ],
                    "resolved_gap_ids": [],
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                }
            ],
            "unresolved": ["current weather data for Chongqing"],
        }
        corrected = {
            **invalid,
            "responsibilities": [
                {
                    **invalid["responsibilities"][0],
                    "outcome": "describe today's daytime weather in Chongqing",
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="你好，今天重庆白天天气怎么样啊？",
                language="zh-CN",
            )
        )

        self.assertEqual(
            result.responsibilities[0].outcome,
            "describe today's daytime weather in Chongqing",
        )
        self.assertEqual(result.unresolved, [])
        self.assertEqual(interpreter._chat.await_count, 2)
        repair_payload = interpreter._chat.await_args_list[1].args[0]
        system_text, _, _ = _payload_message_texts(repair_payload)
        self.assertIn("open descriptive question", system_text)

    async def test_context_backed_indirect_location_does_not_require_current_turn_surface(self) -> None:
        interpreter = self._interpreter()
        contextual = _valid_output()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(contextual)}}
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="那里今天会下雨吗？",
                language="zh-CN",
                context={
                    "discourse_referents": [
                        {"entity_type": "location", "canonical_value": "Chongqing"}
                    ]
                },
            )
        )
        self.assertEqual(result.responsibilities[0].bindings["location"], "Chongqing")
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_runtime_session_identity_in_binding_gets_one_dto_repair(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "determine whether the washing machine finished",
                    "bindings": {
                        "device": "washing machine",
                        "cycle": "turn-correlation-123",
                    },
                }
            ],
        }
        corrected = {
            **invalid,
            "responsibilities": [
                {
                    **invalid["responsibilities"][0],
                    "bindings": {"device": "washing machine"},
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                sid="turn-correlation-123",
                text="Has the washing machine finished?",
            )
        )

        self.assertEqual(
            result.responsibilities[0].bindings,
            {"device": "washing machine"},
        )
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_route_output_gets_one_mechanical_dto_repair(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool", "intent": "weather"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(_valid_output())}},
            ]
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].outcome, "provide today's weather for Chongqing")
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_invalid_output_after_repair_is_unavailable(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaises(InterpretationUnavailableError):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(text="What's the weather today?")
            )
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_engine_rejects_empty_admitted_input(self) -> None:
        with self.assertRaisesRegex(InterpretationUnavailableError, "empty admitted input"):
            await interpret_goal(GoalInterpretationRequest(text="   "))
