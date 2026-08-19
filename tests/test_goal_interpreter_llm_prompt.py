from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from agent.app.cognitive_core.goal_interpreter.engine import interpret_goal
from agent.app.cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _extract_json_object,
    _payload_message_texts,
    _reject_canonical_goal_identity_refs,
    _reject_planner_shaped_goal_interpretation,
    _reject_untyped_coordination_bindings,
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
                "output_mode": "capability_work",
                "completion_requires_work": True,
                "completion_requires_fresh_evidence": True,
                "confidence": 0.95,
            }
        ],
        "unresolved": [],
    }


class GoalInterpreterContractTests(unittest.TestCase):
    def test_responsibility_rejects_planner_owned_information_gap(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
            CognitiveResponsibilityProposal(
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
                confidence=0.95,
            )

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
        decision = GoalInterpretationDecision.model_validate(
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
                        "completion_requires_work": True,
                        "completion_requires_fresh_evidence": True,
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        self.assertTrue(decision.responsibilities[0].completion_requires_fresh_evidence)
        self.assertEqual(decision.unresolved, [])

    def test_already_bound_values_are_not_top_level_uncertainty(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "already-bound semantic values are not unresolved",
        ):
            GoalInterpretationDecision.model_validate(
                {
                    **_valid_output(),
                    "responsibilities": [
                        {
                            **_valid_output()["responsibilities"][0],
                            "bindings": {"location": "重庆", "time": "今天上午"},
                        }
                    ],
                    "unresolved": ["重庆", "今天上午"],
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

        schema = self._interpreter()._goal_interpretation_response_schema()
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        self.assertIn(
            "Never combine coordinated positive effects",
            responsibility["properties"]["outcome"]["description"],
        )

    def test_system_prompt_preserves_speaker_and_immediate_conversation_boundaries(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("downstream work beyond the immediate ordinary conversational response", prompt)
        self.assertIn("Preserve speaker, experiencer, actor, addressee", prompt)
        self.assertIn("most recent accepted assistant/Chromie utterance", prompt)
        self.assertIn("does not continue, resume, or modify the old Goal", prompt)
        self.assertIn("Coordination does not merge independently observable effects", prompt)
        self.assertIn("Chinese `边…边…`", prompt)
        self.assertIn("singing is output_mode=singing", prompt)
        self.assertIn("Each outcome describes only its own effect", prompt)
        self.assertIn("exactly one canonical JSON token", prompt)
        self.assertIn("`new`, `continue`, `modify`", prompt)
        self.assertIn("never inflect, pluralize, conjugate", prompt)
        self.assertNotIn("new or continues, modifies", prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN")
        )
        self.assertIn("whole Latest user input", turn_prompt)
        self.assertIn("not semantic bindings", turn_prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="你刚才说什么？",
                language="zh-CN",
                context={
                    "history": [
                        {"role": "user", "text": "你好，Chromie。"},
                        {"role": "assistant", "text": "你好呀！"},
                    ]
                },
            )
        )
        self.assertIn("most recent accepted assistant utterance", turn_prompt)
        self.assertIn("not continuation of the prior utterance's Goal", turn_prompt)
        self.assertIn("Most recent accepted Chromie/assistant utterance JSON", turn_prompt)
        self.assertIn('"role":"assistant"', turn_prompt)
        self.assertIn('"text":"你好呀！"', turn_prompt)

    def test_system_prompt_preserves_direct_entity_surface_and_rejects_provider_time_uncertainty(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("exact contiguous surface", prompt)
        self.assertIn("Never translate, transliterate", prompt)
        self.assertIn("deictic spatial language", prompt)
        self.assertIn("inside/outside", prompt)
        self.assertIn("Chinese `重庆` stays `重庆`, never `Chongqing`", prompt)
        self.assertIn("`外面` stays `外面`, never `outside`", prompt)
        self.assertIn("emit a `date` binding and a `day_part` binding", prompt)
        self.assertIn("contextual WHAT normalization only", prompt)
        self.assertIn("provider timezone", prompt)
        self.assertIn("never an unresolved WHAT question", prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="今天晚上重庆热不热？",
                language="zh-CN",
            )
        )
        self.assertIn("literal surface audit", turn_prompt)
        self.assertIn('authoritative input is "今天晚上重庆热不热？"', turn_prompt)
        self.assertIn("translated equivalent", turn_prompt)

    def test_system_prompt_preserves_requested_judgment_without_asserting_the_answer(self) -> None:
        prompt = self._interpreter().load_system_prompt().casefold()
        self.assertIn("preserve the requested judgment", prompt)
        self.assertIn("whether the proposition is true", prompt)
        self.assertIn("must not become an assertion", prompt)
        self.assertIn("does not become unresolved merely because its answer is unknown", prompt)
        self.assertIn("reasoning from facts already supplied by the user", prompt)
        self.assertIn("do not create or resolve an informationgap", prompt)
        self.assertIn("external or changing facts", prompt)
        self.assertIn("declarative statement", prompt)
        self.assertIn("states a future plan is context", prompt)
        self.assertIn("do not invent a responsibility to confirm", prompt)

    def test_current_turn_prompt_distinguishes_missing_binding_from_requested_evidence(self) -> None:
        prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="哎，今天上午重庆会不会下雨？",
                language="zh-CN",
            )
        )

        self.assertIn("Missing execution inputs belong to Fast Planner", prompt)
        self.assertIn("External Evidence is fresh Evidence", prompt)

    def test_deep_payload_reasons_from_source_without_prior_dto(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="fast-model",
            deep_model="deep-model",
            timeout_ms=800,
        )
        payload = interpreter.build_deep_interpretation_payload(
            GoalInterpretationRequest(
                text="哎，今天上午重庆会不会下雨？",
                language="zh-CN",
            )
        )

        system_text, user_text, all_text = _payload_message_texts(payload)
        self.assertFalse(payload["think"])
        self.assertEqual(payload["model"], "deep-model")
        self.assertIn("Deep Goal Interpretation", system_text)
        self.assertIn("genuine consequential ambiguity", system_text)
        self.assertIn("atomicity audit", system_text)
        self.assertIn("responsibilities must contain N sibling items", system_text)
        self.assertIn("No prior interpretation DTO is supplied", user_text)
        self.assertIn("final number of responsibilities must equal that count", user_text)
        self.assertNotIn("previous output", all_text.casefold())

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
                "output_mode",
                "completion_requires_work",
                "completion_requires_fresh_evidence",
                "confidence",
            },
        )
        responsibility_schema = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertNotIn("relationship", responsibility_schema["properties"])
        self.assertNotIn("target_goal_ids", responsibility_schema["properties"])
        self.assertNotIn("InformationGap", payload["format"]["$defs"])
        output_modes = {
            item["const"]
            for item in responsibility_schema["properties"]["output_mode"]["oneOf"]
        }
        self.assertNotIn("unspecified", output_modes)
        self.assertNotIn("other", output_modes)
        self.assertIn("singing", output_modes)
        fresh_evidence_clause = next(
            clause
            for clause in responsibility_schema["allOf"]
            if clause.get("if", {})
            .get("properties", {})
            .get("completion_requires_fresh_evidence", {})
            .get("const")
            is True
        )
        self.assertEqual(
            fresh_evidence_clause["then"]["properties"]["output_mode"],
            {"const": "capability_work"},
        )
        nonverbal = next(
            item
            for item in responsibility_schema["properties"]["output_mode"]["oneOf"]
            if item.get("const") == "nonverbal_vocalization"
        )
        self.assertIn("excludes singing", nonverbal["description"])

    def test_repair_schema_does_not_reintroduce_planning_gap_contract(self) -> None:
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

        self.assertNotIn("InformationGap", payload["format"]["$defs"])
        system_text, _, _ = _payload_message_texts(payload)
        self.assertIn("Never create/resolve an InformationGap", system_text)

    def test_goal_relationship_fields_remain_model_owned_when_goal_context_exists(self) -> None:
        interpreter = self._interpreter()
        payload = interpreter.build_interpretation_payload(
            GoalInterpretationRequest(
                text="那就继续吧",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-existing",
                            "goal": {
                                "goal_id": "goal-existing",
                                "description": "continue the existing request",
                            },
                        }
                    ]
                },
            )
        )

        responsibility = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertIn("relationship", responsibility["properties"])
        self.assertIn("target_goal_ids", responsibility["properties"])
        self.assertIn("relationship", responsibility["required"])
        self.assertIn("target_goal_ids", responsibility["required"])
        relationship = responsibility["properties"]["relationship"]
        self.assertNotIn("enum", relationship)
        self.assertEqual(
            {item["const"] for item in relationship["oneOf"]},
            {
                "continue",
                "modify",
                "clarify",
                "confirm",
                "reject",
                "cancel",
                "pause",
                "resume",
                "merge",
                "split",
                "reference",
                "new",
            },
        )
        self.assertIn("never inflect", relationship["description"])
        self.assertNotIn("continues", json.dumps(relationship))
        self.assertNotIn("resumes", json.dumps(relationship))
        self.assertEqual(
            responsibility["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-existing"],
        )
        relationship_targets = responsibility["allOf"][-1]
        self.assertEqual(
            relationship_targets["if"]["properties"]["relationship"],
            {"const": "new"},
        )
        self.assertEqual(
            relationship_targets["then"]["properties"]["target_goal_ids"][
                "maxItems"
            ],
            0,
        )
        self.assertEqual(
            relationship_targets["else"]["properties"]["target_goal_ids"][
                "minItems"
            ],
            1,
        )
        _, user_prompt, _ = _payload_message_texts(payload)
        self.assertIn("copy exactly one relationship protocol token", user_prompt)
        self.assertIn("Never inflect, conjugate, translate", user_prompt)

        repair = interpreter.build_interpretation_repair_payload(
            GoalInterpretationRequest(
                text="刚才那个事情继续。",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {"goal_id": "goal-existing", "goal": {"goal_id": "goal-existing"}}
                    ]
                },
            ),
            previous_content='{"relationship":"continues"}',
            validation_error=ValueError("invalid relationship token"),
        )
        repair_responsibility = repair["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertEqual(
            repair_responsibility["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-existing"],
        )
        self.assertIn(
            "continue",
            {
                item["const"]
                for item in repair_responsibility["properties"]["relationship"]["oneOf"]
            },
        )
        repair_system, _, _ = _payload_message_texts(repair)
        self.assertIn("copy one exact protocol token", repair_system)

    def test_recent_terminal_goal_semantics_are_available_for_continuation(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="刚才那个事情继续。",
            language="zh-CN",
            context={
                "active_goal_snapshots": [],
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "responsibility_status": "satisfied",
                        "last_user_update": "你往前走 10 秒。",
                        "goal": {
                            "goal_id": "goal-walk",
                            "description": "move forward for ten seconds",
                            "metadata": {
                                "output_mode": "body_action",
                                "completion_requires_work": True,
                                "completion_requires_fresh_evidence": False,
                            },
                        },
                    }
                ],
            },
        )

        payload = interpreter.build_interpretation_payload(request)
        _, user_prompt, _ = _payload_message_texts(payload)

        self.assertIn("Retained active/recent Goal semantics", user_prompt)
        self.assertIn('"goal_id":"goal-walk"', user_prompt)
        self.assertIn("move forward for ten seconds", user_prompt)
        self.assertEqual(
            payload["format"]["$defs"]["CognitiveResponsibilityProposal"][
                "properties"
            ]["target_goal_ids"]["items"]["enum"],
            ["goal-walk"],
        )

    def test_repair_schema_excludes_bound_values_from_unresolved(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="哎，今天上午重庆会不会下雨？",
            language="zh-CN",
        )
        try:
            GoalInterpretationDecision.model_validate(
                {
                    **_valid_output(),
                    "responsibilities": [
                        {
                            **_valid_output()["responsibilities"][0],
                            "bindings": {"location": "重庆", "time": "今天上午"},
                        }
                    ],
                    "unresolved": ["重庆", "今天上午"],
                }
            )
        except ValidationError as exc:
            payload = interpreter.build_interpretation_repair_payload(
                request,
                previous_content="rejected",
                validation_error=exc,
            )
        else:  # pragma: no cover - protects the regression setup itself
            self.fail("bound unresolved values unexpectedly passed validation")

        unresolved_items = payload["format"]["properties"]["unresolved"]["items"]
        self.assertEqual(
            set(unresolved_items["not"]["enum"]),
            {"重庆", "今天上午"},
        )
        system_text, _, _ = _payload_message_texts(payload)
        self.assertIn("already-resolved binding values", system_text)

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

    def test_prompt_exposes_retained_goal_completion_modality_for_continuation(self) -> None:
        prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                sid="continue-walk",
                text="刚才那个事情继续。",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-walk",
                            "goal": {
                                "goal_id": "goal-walk",
                                "description": "move forward 10 seconds",
                                "metadata": {
                                    "output_mode": "body_action",
                                    "provider_required": True,
                                    "completion_requires_work": True,
                                    "completion_requires_fresh_evidence": False,
                                },
                            },
                        }
                    ]
                },
            )
        )

        self.assertIn('"output_mode":"body_action"', prompt)
        self.assertIn('"completion_requires_work":true', prompt)
        self.assertIn(
            "continues or resumes one supplied Goal must preserve", prompt
        )

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

    async def test_provider_key_value_bindings_are_mechanically_normalized(self) -> None:
        interpreter = self._interpreter()
        output = {
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for ten seconds",
                    "bindings": [
                        {"name": "direction", "value": "forward"},
                        {"key": "duration", "value": "10 秒"},
                    ],
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(output)}}
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(
            result.responsibilities[0].bindings,
            {"direction": "forward", "duration": "10 秒"},
        )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_rewritten_explicit_number_escalates_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for ten seconds",
                    "bindings": [
                        {"name": "direction", "value": "forward"},
                        {"name": "duration", "value": "ten seconds"},
                    ],
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        repaired = copy.deepcopy(invalid)
        repaired["responsibilities"][0]["bindings"][1]["value"] = "10 秒"
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(repaired)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertEqual(result.responsibilities[0].bindings["duration"], "10 秒")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        system_text, user_text, _all_text = _payload_message_texts(deep_payload)
        self.assertIn("Audit declarative context before counting outcomes", system_text)
        self.assertIn("states a future plan is context", user_text)

    def test_body_action_completion_is_not_fresh_information(self) -> None:
        with self.assertRaisesRegex(
            ValidationError, "not a fresh-information Responsibility"
        ):
            CognitiveResponsibilityProposal.model_validate(
                {
                    "local_ref": "walk",
                    "outcome": "move forward for ten seconds",
                    "bindings": {"duration": "10 seconds"},
                    "output_mode": "body_action",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                }
            )

    async def test_continuation_cannot_turn_retained_body_work_into_speech(self) -> None:
        interpreter = self._interpreter()
        wrong = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "continue the previous action",
                    "bindings": {"previous_action": "你往前走 10 秒。"},
                    "output_mode": "speech",
                    "relationship": "continue",
                    "target_goal_ids": ["goal-walk"],
                    "completion_requires_work": False,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        corrected = copy.deepcopy(wrong)
        corrected["responsibilities"][0]["output_mode"] = "body_action"
        corrected["responsibilities"][0]["completion_requires_work"] = True
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(wrong, ensure_ascii=False)}},
                {
                    "message": {
                        "content": json.dumps(corrected, ensure_ascii=False)
                    }
                },
            ]
        )
        request = GoalInterpretationRequest(
            sid="continue-walk",
            text="刚才那个事情继续。",
            language="zh-CN",
            context={
                "active_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "goal": {
                            "goal_id": "goal-walk",
                            "description": "move forward 10 seconds",
                            "metadata": {
                                "output_mode": "body_action",
                                "provider_required": True,
                                "completion_requires_work": True,
                                "completion_requires_fresh_evidence": False,
                            },
                        },
                    }
                ]
            },
        )

        result = await interpreter.interpret_goal(request)

        responsibility = result.responsibilities[0]
        self.assertEqual(responsibility.output_mode, "body_action")
        self.assertTrue(responsibility.completion_requires_work)
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_bundle_beijing_translation_escalates_from_source(self) -> None:
        interpreter = self._interpreter()
        translated = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "determine whether it will rain in Beijing tomorrow",
                    "bindings": {"location": "Beijing", "date": "tomorrow"},
                }
            ],
        }
        corrected = {
            **translated,
            "responsibilities": [
                {
                    **translated["responsibilities"][0],
                    "bindings": {"location": "北京", "date": "tomorrow"},
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
                text="明天北京下雨吗？我明天要去北京出差。",
                language="zh-CN",
            )
        )
        self.assertEqual(result.responsibilities[0].bindings["location"], "北京")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        _system_text, user_text, all_text = _payload_message_texts(deep_payload)
        self.assertIn("No prior interpretation DTO is supplied", user_text)
        self.assertNotIn(json.dumps(translated), all_text)
        location_contract = deep_payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]["properties"]["location"]
        self.assertIn("北京", location_contract["enum"])
        self.assertNotIn("Beijing", location_contract["enum"])

    async def test_multiple_fresh_evidence_claims_escalate_from_source(self) -> None:
        interpreter = self._interpreter()
        weather = _valid_output()
        oversegmented = {
            **weather,
            "responsibilities": [
                weather["responsibilities"][0],
                {
                    **weather["responsibilities"][0],
                    "local_ref": "r2",
                    "outcome": "confirm the user's travel plan",
                },
            ],
        }
        corrected = {
            **weather,
            "responsibilities": [weather["responsibilities"][0]],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(oversegmented)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="Will it rain in Chongqing tomorrow? I am traveling for work.",
                language="en-US",
            )
        )

        self.assertEqual(len(result.responsibilities), 1)
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_planner_gap_fields_escalate_once_from_source(self) -> None:
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
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
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
        self.assertFalse(hasattr(responsibility, "information_gaps"))
        self.assertTrue(responsibility.completion_requires_fresh_evidence)
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_genuine_semantic_ambiguity_escalates_once_to_deep(self) -> None:
        interpreter = self._interpreter()
        fast = {
            "confidence": 0.72,
            "responsibilities": [
                {
                    "local_ref": "device_action",
                    "outcome": "turn off the referenced device",
                    "bindings": {},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.72,
                }
            ],
            "unresolved": ["which device the user means"],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(fast, ensure_ascii=False)}},
                {"message": {"content": json.dumps(fast, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="把它关掉。",
                language="zh-CN",
            )
        )

        self.assertFalse(hasattr(result.responsibilities[0], "information_gaps"))
        self.assertEqual(result.unresolved, ["which device the user means"])
        self.assertEqual(interpreter._chat.await_count, 2)
        deep_call = interpreter._chat.await_args_list[1]
        self.assertEqual(deep_call.kwargs["stage"], "goal_interpretation_deep")
        self.assertFalse(deep_call.args[0]["think"])

    async def test_missing_execution_location_stays_out_of_gi_uncertainty(self) -> None:
        interpreter = self._interpreter()
        missing_location = {
            "confidence": 0.9,
            "responsibilities": [
                {
                    "local_ref": "weather",
                    "outcome": "provide today's weather for the requested location",
                    "bindings": {"date": "today"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.9,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(missing_location)}}
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather today?")
        )

        self.assertFalse(hasattr(result.responsibilities[0], "information_gaps"))
        self.assertEqual(result.unresolved, [])
        self.assertEqual(interpreter._chat.await_count, 1)

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
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "describe today's daytime weather in Chongqing",
                    "bindings": {
                        "location": "重庆",
                        "time": "today",
                        "time_of_day": "daytime",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
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
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        self.assertNotIn("InformationGap", deep_payload["format"]["$defs"])
        system_text, _, _ = _payload_message_texts(deep_payload)
        self.assertIn("Do not create or resolve an InformationGap", system_text)

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

    async def test_runtime_session_identity_in_binding_escalates_from_source(self) -> None:
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
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_transport_echo_bindings_escalate_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "combined",
                    "outcome": "walk while singing",
                    "bindings": {
                        "language": "zh-CN",
                        "text": "边走边唱歌",
                    },
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "walk",
                    "outcome": "walk forward",
                    "bindings": {},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                },
                {
                    "local_ref": "sing",
                    "outcome": "sing audibly while walking",
                    "bindings": {"coordinate_with": "walk"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": True,
                    "confidence": 0.95,
                },
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
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN")
        )

        self.assertEqual(
            [item.local_ref for item in result.responsibilities],
            ["walk", "sing"],
        )
        self.assertEqual(interpreter._chat.await_count, 2)
        deep_call = interpreter._chat.await_args_list[1]
        self.assertEqual(deep_call.kwargs["stage"], "goal_interpretation_deep")
        self.assertIn("No prior interpretation DTO", deep_call.args[0]["messages"][1]["content"])

    async def test_free_form_coordination_effect_escalates_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "walk ahead",
                    "bindings": {},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "sing simultaneously",
                    "bindings": {"simultaneously": "with blinking eyes"},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "walk ahead",
                    "bindings": {"coordinate_with": ["r2", "r3"]},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "sing",
                    "bindings": {"coordinate_with": ["r1", "r3"]},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r3",
                    "outcome": "blink eyes",
                    "bindings": {"coordinate_with": ["r1", "r2"]},
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="walk ahead, singing and blinking eyes simultaneously"
            )
        )

        self.assertEqual(len(result.responsibilities), 3)
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_valid_atomic_compound_meaning_proceeds_without_deep_pass(self) -> None:
        interpreter = self._interpreter()
        primary = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "walk",
                    "outcome": "walk",
                    "bindings": {"mode": "simultaneous"},
                    "output_mode": "body_action",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
                {
                    "local_ref": "sing",
                    "outcome": "sing",
                    "bindings": {"simultaneously": "simultaneously"},
                    "output_mode": "singing",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(primary)}}
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="walk and sing simultaneously")
        )

        self.assertEqual(
            [item.output_mode for item in result.responsibilities],
            ["body_action", "singing"],
        )
        self.assertEqual(interpreter._chat.await_count, 1)
        self.assertEqual(
            interpreter._chat.await_args_list[0].kwargs["stage"],
            "goal_interpretation",
        )

    def test_self_referential_action_combination_is_structural_loss(self) -> None:
        parsed = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "combined request",
                    "bindings": {"action_combination": ["r1"]},
                    "output_mode": "capability_work",
                    "completion_requires_work": True,
                    "completion_requires_fresh_evidence": False,
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        with self.assertRaisesRegex(ValueError, "sibling local_ref"):
            _reject_untyped_coordination_bindings(parsed)

    async def test_route_output_escalates_once_from_source(self) -> None:
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
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_invalid_authority_output_after_deep_pass_is_unavailable(self) -> None:
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

    async def test_llm_budget_failure_is_typed_interpretation_unavailable(self) -> None:
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

        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "structured output budget exhausted",
        ):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(text="What's the weather today?")
            )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_engine_rejects_empty_admitted_input(self) -> None:
        with self.assertRaisesRegex(InterpretationUnavailableError, "empty admitted input"):
            await interpret_goal(GoalInterpretationRequest(text="   "))
