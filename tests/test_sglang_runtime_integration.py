from __future__ import annotations

import asyncio
import os
import unittest

import pytest
from unittest.mock import AsyncMock, Mock, patch

from agent.app.cognitive_core.user_meaning_interpreter.model_interpreter import OllamaUserMeaningInterpreter
from agent.app.clients.model_client_factory import build_model_client
from agent.app.clients.ollama_client import OllamaClient
from agent.app.clients.sglang_client import SGLangClient, SGLangGenerationError
from agent.app.clients.sglang_protocol import (
    build_sglang_chat_payload,
    candidate_compatible_schema,
    sglang_priority,
    sglang_stream_delta,
)
from agent.app.inference_compute import CognitionComputeClass
from agent.app.settings import Settings
from orchestrator.runtime.presentation_compute_lease import PresentationComputeLease


@pytest.mark.parametrize("stage", ["responsibility_order", "stream_constraints", "intersections", "unique_items"])
def test_schema_passes_visit_shared_nodes_once_without_changing_the_wire(stage):
    import json
    from collections import Counter
    from jsonschema import Draft202012Validator
    from agent.app.planner_native_schema import _responsibility_refs_first
    from agent.app.clients.sglang_protocol import _stream_decoder_constraints
    from shared.chromie_contracts.json_schema import expose_intersection_shapes

    visits = []

    class ObservedSchema(dict):
        def values(self):
            visits.append(id(self))
            return super().values()

        def items(self):
            visits.append(id(self))
            return super().items()

    leaf = ObservedSchema(type="array", minItems=1, maxItems=1, uniqueItems=True,
                          allOf=[{"contains": {"enum": ["r1"]}}])
    activity = ObservedSchema(type="object", properties={
        "payload": leaf, "source_responsibility_refs": {"type": "array"},
        "role": {"enum": ["capability"]},
    })
    shared = {"allOf": [activity] * 32}
    independent = json.loads(json.dumps(shared))

    def apply(schema):
        if stage == "unique_items":
            return candidate_compatible_schema(schema)[0]
        transform = {"responsibility_order": _responsibility_refs_first,
                     "stream_constraints": _stream_decoder_constraints,
                     "intersections": expose_intersection_shapes}[stage]
        transform(schema)
        return schema

    expected = apply(independent)
    visits.clear()
    actual = apply(shared)
    assert max(Counter(visits).values()) <= 2  # One copy and one transform, at most.
    assert json.dumps(actual) == json.dumps(expected)
    validator = Draft202012Validator(actual)
    assert validator.is_valid({"role": "capability", "payload": ["r1"]})
    assert not validator.is_valid({"role": "capability", "payload": ["different"]})


class SGLangProtocolTests(unittest.TestCase):
    def test_planner_and_skill_wire_preserve_shapes_and_original_validation(self) -> None:
        import copy
        from jsonschema import Draft202012Validator

        for title in (
            "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput", "SocialCognitionOutput",
        ):
            with self.subTest(title=title):
                schema = {
                    "title": title, "type": "object",
                    "properties": {
                        "decision": {"enum": ["select", "none"]},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["decision", "items"], "additionalProperties": False,
                    "allOf": [{
                        "if": {"properties": {"decision": {"const": "none"}}},
                        "then": {"properties": {"items": {"maxItems": 0}}},
                    }],
                }
                original = copy.deepcopy(schema)
                payload = build_sglang_chat_payload(
                    model="fixed", messages=[],
                    compute_class=CognitionComputeClass.DELIBERATIVE,
                    options={}, response_format=schema, stream=False, priority_step=100,
                )
                wire = payload["response_format"]["json_schema"]["schema"]
                self.assertEqual(wire["anyOf"][0]["required"], schema["required"])
                self.assertFalse(wire["anyOf"][0]["additionalProperties"])
                self.assertEqual(schema, original)
                for value, expected in (
                    ({"decision": "none", "items": []}, True),
                    ({"decision": "select", "items": ["a"]}, True),
                    ({"decision": "none", "items": ["a"]}, False),
                    ({"decision": "none"}, False),
                    ({"decision": "none", "selected_items": []}, False),
                ):
                    self.assertEqual(Draft202012Validator(wire).is_valid(value), expected)
                    self.assertEqual(Draft202012Validator(schema).is_valid(value), expected)

    def test_mixed_intersections_preserve_decision_branches_and_array_defaults(self) -> None:
        import copy
        from jsonschema import Draft202012Validator

        for combinator in ("anyOf", "oneOf"):
            schema = {
                "title": "FastPlannerModelOutput", "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "outcomes": {"type": "object", "required": ["goal"],
                                 "properties": {"goal": {"type": "string"}},
                                 "additionalProperties": False},
                },
                "required": ["steps", "outcomes"], "additionalProperties": False,
                "allOf": [{}],
                combinator: [
                    {"properties": {"steps": {"type": "array", "minItems": 1, "maxItems": 2}}},
                    {"properties": {"steps": {"type": "array", "maxItems": 0}}},
                ],
            }
            original = copy.deepcopy(schema)
            payload = build_sglang_chat_payload(
                model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
                options={}, response_format=schema, stream=False, priority_step=100,
            )
            wire = payload["response_format"]["json_schema"]["schema"]
            self.assertEqual(schema, original)
            self.assertEqual(wire["required"], ["steps", "outcomes"])
            self.assertEqual(len(wire[combinator]), 2)
            self.assertEqual(wire["allOf"], [{}])
            alternative = wire[combinator][0]["properties"]["steps"]
            self.assertEqual(alternative["items"], {})
            for steps in ([], ["fetch"], ["fetch", "deliver"], ["a", "b", "c"], [1]):
                for outcomes in ({"goal": "pending"}, [], {}, {"goal": 1}):
                    value = {"steps": steps, "outcomes": outcomes}
                    with self.subTest(combinator=combinator, value=value):
                        self.assertEqual(
                            Draft202012Validator(original).is_valid(value),
                            Draft202012Validator(wire).is_valid(value),
                        )

    def test_streaming_json_keeps_schema_authority_and_decoder_compatible_shapes(self) -> None:
        import copy
        from jsonschema import Draft202012Validator

        schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "pattern": "^[^?？]*$"},
                "duration": {"type": "number", "minimum": 0.05, "maximum": 0.5},
            },
            "required": ["text", "duration"], "additionalProperties": False,
            "allOf": [{"properties": {"text": {"minLength": 1}}}],
        }
        original = copy.deepcopy(schema)
        declared = {"title": "FastPlannerWorkAdvanceOutput", **schema}
        payload = build_sglang_chat_payload(
            model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
            options={}, response_format=declared, stream=True, priority_step=100,
        )
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        wire_schema = payload["response_format"]["json_schema"]["schema"]
        self.assertEqual(wire_schema["x-guidance"], {"whitespace_flexible": False})
        self.assertEqual(wire_schema["required"], ["text", "duration"])
        self.assertFalse(wire_schema["additionalProperties"])
        self.assertIn("anyOf", wire_schema)
        self.assertNotIn("pattern", wire_schema["properties"]["text"])
        self.assertNotIn("minimum", wire_schema["properties"]["duration"])
        self.assertEqual(schema, original)
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid({"text": "checking", "duration": 0.12}))
        self.assertFalse(validator.is_valid({"text": "checking?", "duration": 0.12}))
        self.assertFalse(validator.is_valid({"text": "checking", "duration": 0.9}))

    def test_social_wire_decision_alternatives_enforce_silent_need_state(self) -> None:
        from jsonschema import Draft202012Validator
        from agent.app.social_cognition import social_cognition_response_schema
        from shared.chromie_contracts.social_cognition import (
            SocialCognitionRequest, SocialCommunicationNeed,
        )

        request = SocialCognitionRequest(
            request_id="completed-greeting", trigger="work_state", source_refs=["plan:1"],
            goal_ids=["goal:1"], communication_needs=[SocialCommunicationNeed(
                need_id="answer:1", owner="planner", kind="answer", reference_id="plan:1",
                source_goal_ids=["goal:1"],
            )],
        )
        schema = social_cognition_response_schema(request, [])
        payload = build_sglang_chat_payload(
            model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
            options={}, response_format=schema, stream=False, priority_step=100,
        )
        wire = payload["response_format"]["json_schema"]["schema"]
        # Exercise the decoder-visible alternatives independently of allOf and
        # conditional support. Logical equivalence alone missed the live failure.
        native = {"$defs": wire["$defs"], "oneOf": wire["oneOf"]}
        for outcome, expected in (("covered", False), ("pending", True)):
            value = {"need_outcomes": {"answer:1": outcome}, "disposition": "silence",
                     "activities": [], "reason_summary": "The greeting was already delivered."}
            self.assertEqual(Draft202012Validator(native).is_valid(value), expected)
            self.assertEqual(Draft202012Validator(schema).is_valid(value), expected)

    def test_readiness_and_need_first_preserve_primary_planner_decoder_contract(self) -> None:
        from jsonschema import Draft202012Validator
        from agent.app.planner_model_contract import need_first_response_schema
        from agent.app.planner_schema import (
            canonical_plan_response_schema,
            planner_readiness_response_schema,
        )

        base = canonical_plan_response_schema(
            expected_goal_ids=["goal:water"],
            allowed_capability_ids=["resource.deliver"], requires_execution=True,
        )
        schema = need_first_response_schema(
            planner_readiness_response_schema(base, ["goal:water"]), ["resource.deliver"],
        )
        payload = build_sglang_chat_payload(
            model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
            options={}, response_format=schema, stream=False, priority_step=100,
        )
        wire = payload["response_format"]["json_schema"]["schema"]
        self.assertEqual(wire["title"], base["title"])
        self.assertEqual(wire["x-guidance"], {"whitespace_flexible": False})
        arrays = []

        def visit(node):
            if isinstance(node, dict):
                if node.get("type") == "array" and "prefixItems" not in node:
                    arrays.append(node)
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(wire)
        self.assertTrue(arrays)
        self.assertTrue(all("items" in item for item in arrays))
        shapes = [shape for shape in (wire, *wire.get("oneOf", []), *wire.get("anyOf", []))
                  if isinstance(shape, dict) and "properties" in shape]
        self.assertTrue(shapes)
        for shape in shapes:
            self.assertEqual(next(iter(shape["properties"])), "ability_needs")
            self.assertIn("ability_needs", shape["required"])
            reference = shape["properties"]["ability_needs"]["$ref"]
            closest = wire["$defs"][reference.rsplit("/", 1)[1]]["items"]["properties"]["closest_loaded"]
            self.assertEqual(closest["enum"], ["resource.deliver", "none"])
        need = {"need": "bring water to the person", "closest_loaded": "resource.deliver",
                "closest_loaded_does": "Deliver a resource", "fits": True}
        item_schema = {"$defs": wire["$defs"], **shapes[0]["properties"]["ability_needs"]}
        for value, expected in (([need], True), ([{**need, "closest_loaded": "invented"}], False), ([need] * 5, False)):
            self.assertEqual(Draft202012Validator(item_schema).is_valid(value), expected)

    def test_compact_formatting_is_scoped_without_mutating_contract(self) -> None:
        for title in (
            "GoalSegmentationModelOutput", "GoalAssociationModelOutput",
            "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput", "SocialCognitionOutput",
            "CognitiveActivationDecision",
            "UserMeaningInterpretationModelOutput", "FastPlannerOutput", "OtherOutput",
        ):
            with self.subTest(title=title):
                schema = {"title": title, "type": "object", "properties": {}}
                payload = build_sglang_chat_payload(
                    model="chromie-gemma4-12b", messages=[],
                    compute_class=CognitionComputeClass.INTERACTIVE,
                    options={}, response_format=schema, stream=False,
                    priority_step=100,
                )
                wire = payload["response_format"]["json_schema"]["schema"]
                expected = dict(schema)
                if title in {
                    "GoalSegmentationModelOutput", "GoalAssociationModelOutput",
                    "AgentSkillSelectionModelOutput",
                    "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput", "SocialCognitionOutput",
                    "CognitiveActivationDecision",
                }:
                    expected["x-guidance"] = {"whitespace_flexible": False}
                self.assertEqual(wire, expected)
                self.assertNotIn("x-guidance", schema)

    def test_actual_umi_schema_bounds_formatting_without_changing_meaning(self) -> None:
        import copy
        from jsonschema import Draft202012Validator
        from tests.test_user_meaning_interpreter_llm_prompt import _valid_output

        text = "What's the weather in Chongqing today?"
        schema = OllamaUserMeaningInterpreter._user_meaning_interpretation_response_schema(
            admitted_turn=text,
        )
        original = copy.deepcopy(schema)
        payload = build_sglang_chat_payload(
            model="fixed", messages=[], compute_class=CognitionComputeClass.INTERACTIVE,
            options={}, response_format=schema, stream=False, priority_step=100,
        )
        wire = payload["response_format"]["json_schema"]["schema"]
        compatible, _ = candidate_compatible_schema(schema)
        self.assertEqual(wire, {**compatible, "x-guidance": {"max_whitespace_cnt": 16}})
        self.assertEqual(schema, original)
        for contract in (schema, wire):
            Draft202012Validator(contract).validate(_valid_output(text))

    def test_priority_preserves_provider_neutral_compute_order(self) -> None:
        self.assertGreater(
            sglang_priority(CognitionComputeClass.REALTIME),
            sglang_priority(CognitionComputeClass.INTERACTIVE),
        )
        self.assertGreater(
            sglang_priority(CognitionComputeClass.INTERACTIVE),
            sglang_priority(CognitionComputeClass.DELIBERATIVE),
        )

    def test_payload_uses_qualified_thinking_and_priority_controls(self) -> None:
        payload = build_sglang_chat_payload(
            model="chromie-qwen35-9b-sglang",
            messages=[{"role": "user", "content": "hello"}],
            compute_class=CognitionComputeClass.INTERACTIVE,
            options={"num_ctx": 32768, "num_predict": 123},
            response_format="text",
            stream=True,
            priority_step=100,
        )
        self.assertEqual(payload["priority"], 200)
        self.assertEqual(payload["max_tokens"], 123)
        self.assertEqual(
            payload["chat_template_kwargs"],
            {"enable_thinking": False},
        )
        self.assertNotIn("num_ctx", payload)

    def test_schema_projection_matches_qualified_unique_items_removal(self) -> None:
        original = {
            "type": "object",
            "properties": {
                "refs": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                }
            },
            "additionalProperties": False,
        }
        translated, removed = candidate_compatible_schema(original)
        self.assertEqual(removed, ["$.properties.refs.uniqueItems"])
        self.assertNotIn("uniqueItems", translated["properties"]["refs"])
        self.assertTrue(original["properties"]["refs"]["uniqueItems"])

    def test_non_qwen_model_does_not_receive_qwen_template_control(self) -> None:
        payload = build_sglang_chat_payload(
            model="some-gemma-model",
            messages=[{"role": "user", "content": "hello"}],
            compute_class=CognitionComputeClass.DELIBERATIVE,
            options={"num_predict": 32},
            response_format="text",
            stream=False,
            priority_step=100,
        )
        self.assertNotIn("chat_template_kwargs", payload)
        self.assertEqual(payload["priority"], 100)

    def test_stream_rejects_reasoning_output(self) -> None:
        with self.assertRaises(ValueError):
            sglang_stream_delta(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "answer",
                                "reasoning_content": "hidden",
                            },
                            "finish_reason": None,
                        }
                    ]
                }
            )

    def test_factory_keeps_ollama_default_and_allows_explicit_sglang(self) -> None:
        with patch.dict(os.environ, {"AGENT_LLM_PROVIDER": "ollama"}, clear=False):
            configured = Settings()
            client = build_model_client(
                model="test",
                timeout_ms=1000,
                purpose="fast_planner",
                service_settings=configured,
            )
            self.assertIs(type(client), OllamaClient)

        with patch.dict(
            os.environ,
            {
                "AGENT_LLM_PROVIDER": "sglang",
                "AGENT_SGLANG_URL": "http://example.invalid/v1",
                "AGENT_SGLANG_PRIORITY_STEP": "100",
            },
            clear=False,
        ):
            configured = Settings()
            client = build_model_client(
                model="test",
                timeout_ms=1000,
                purpose="fast_planner",
                service_settings=configured,
            )
            self.assertIsInstance(client, SGLangClient)
            self.assertEqual(client.base_url, "http://example.invalid/v1")
            self.assertEqual(client.compute_class, CognitionComputeClass.INTERACTIVE)



class SGLangStreamEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_budget_count_uses_nonstream_tokenizer_without_changing_generation(self) -> None:
        import httpx

        for count, limit, fits in ((500, 1024, True), (972, 1024, True),
                                   (973, 1024, False), (950, 1000, False)):
            with self.subTest(count=count, limit=limit):
                class StreamResponse:
                    status_code = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        return None

                    async def aiter_lines(self):
                        yield 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'

                async def tokenize(url, *, json):
                    # Pinned SGLang's tokenize handler supports only non-streaming.
                    return httpx.Response(
                        501 if json.get("stream") else 200,
                        json={"count": count, "tokens": [1] * count, "max_model_len": limit},
                        request=httpx.Request("POST", url),
                    )

                transport = Mock()
                transport.post = AsyncMock(side_effect=tokenize)
                transport.stream.return_value = StreamResponse()
                context = AsyncMock()
                context.__aenter__.return_value = transport
                client = SGLangClient("http://fast.invalid/v1", "fixed", timeout_ms=1000,
                    purpose="fast_planner", service_settings=Settings(
                        llm_prompt_chars_per_token_estimate=2, llm_context_safety_margin_tokens=20))
                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=context), patch(
                    "agent.app.clients.sglang_client.log_llm_call_evidence"
                ) as evidence:
                    if fits:
                        self.assertEqual([part async for part in client.generate_stream(
                            "x" * 3000, options={"num_ctx": 1024, "num_predict": 32},
                        )], ["ok"])
                    else:
                        with self.assertRaises(SGLangGenerationError) as caught:
                            async for _ in client.generate_stream(
                                "x" * 3000, options={"num_ctx": 1024, "num_predict": 32},
                            ):
                                self.fail("overflow emitted a model token")
                        self.assertEqual(caught.exception.failure_class, "prompt_budget_exceeded")
                        transport.stream.assert_not_called()
                request = evidence.call_args.kwargs["request"]
                self.assertIs(request["stream"], True)
                transport.post.assert_awaited_once_with(
                    "http://fast.invalid/v1/tokenize", json={**request, "stream": False},
                )
                if fits:
                    self.assertEqual(transport.stream.call_args.kwargs["json"], request)

    async def test_exact_serving_tokens_resolve_estimate_overflow_without_prompt_loss(self) -> None:
        import httpx

        prompt = "Evidence and shared task state. " * 100
        for count, limit, expected in ((500, 1024, True), (972, 1024, True),
                                       (973, 1024, False), (950, 1000, False)):
            with self.subTest(count=count, limit=limit):
                tokenized = httpx.Response(200, json={
                    "count": count, "tokens": [1] * count, "max_model_len": limit,
                }, request=httpx.Request("POST", "http://fast.invalid/v1/tokenize"))
                completion = httpx.Response(200, json={"choices": [{
                    "message": {"content": "ok"}, "finish_reason": "stop",
                }]}, request=httpx.Request("POST", "http://fast.invalid/v1/chat/completions"))
                http_client = AsyncMock()
                http_client.post.side_effect = [tokenized, completion]
                http_client.__aenter__.return_value = http_client
                configured = Settings(llm_prompt_chars_per_token_estimate=2,
                                      llm_context_safety_margin_tokens=20)
                client = SGLangClient("http://fast.invalid/v1", "qwen3.5-test",
                                      timeout_ms=1000, purpose="social_cognition",
                                      service_settings=configured)
                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=http_client), patch(
                    "agent.app.clients.sglang_client.log_llm_call_evidence"
                ) as evidence:
                    if expected:
                        result = await client._generate(prompt, options={"num_ctx": 1024, "num_predict": 32})
                        self.assertEqual(result, "ok")
                        self.assertEqual(http_client.post.call_args_list[0].kwargs["json"],
                                         http_client.post.call_args_list[1].kwargs["json"])
                    else:
                        with self.assertRaises(SGLangGenerationError) as caught:
                            await client._generate(prompt, options={"num_ctx": 1024, "num_predict": 32})
                        self.assertEqual(caught.exception.failure_class, "prompt_budget_exceeded")
                    self.assertEqual(http_client.post.call_count, 2 if expected else 1)
                    self.assertEqual(evidence.call_args.kwargs["request"]["messages"][-1]["content"], prompt)
                    self.assertEqual(evidence.call_args.kwargs["status"], "accepted" if expected else "failed")

    async def test_unverifiable_tokenizer_fails_closed_and_retains_stream_request(self) -> None:
        import httpx

        for data, status in (({"count": True, "tokens": [1], "max_model_len": 1024}, 200),
                             ({"count": 2, "tokens": [1], "max_model_len": 1024}, 200),
                             ({"count": 1, "tokens": [1], "max_model_len": 0}, 200),
                             ({}, 503), ([], 200)):
            with self.subTest(data=data, status=status):
                response = httpx.Response(status, json=data,
                    request=httpx.Request("POST", "http://fast.invalid/v1/tokenize"))
                http_client = AsyncMock()
                http_client.post.return_value = response
                http_client.__aenter__.return_value = http_client
                client = SGLangClient("http://fast.invalid/v1", "qwen3.5-test", timeout_ms=1000,
                    purpose="fast_planner", service_settings=Settings(
                        llm_prompt_chars_per_token_estimate=2, llm_context_safety_margin_tokens=20))
                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=http_client), patch(
                    "agent.app.clients.sglang_client.log_llm_call_evidence"
                ) as evidence:
                    with self.assertRaises(SGLangGenerationError) as caught:
                        async for _ in client.generate_stream("x" * 3000, options={"num_ctx": 1024, "num_predict": 32}):
                            self.fail("unverified request emitted a model token")
                    self.assertEqual(caught.exception.failure_class, "prompt_budget_unverified")
                    http_client.stream.assert_not_called()
                    self.assertEqual(evidence.call_args.kwargs["status"], "failed")

    async def test_nonstream_failures_retain_request_and_available_response(self) -> None:
        import httpx

        for mode in ("stop", "nested_stop", "length", "invalid_json", "http_error", "invalid_response", "nonobject_response", "timeout", "cancel"):
            with self.subTest(mode=mode):
                data = {"choices": [{"message": {"content": "broken" if mode == "invalid_json" else '{"ok":true}'},
                                     "finish_reason": "length" if mode == "length" else "stop"}]}
                response = Mock(status_code=503 if mode == "http_error" else 200,
                                text="provider body")
                response.json.return_value = [1, 2] if mode == "nonobject_response" else data
                if mode == "invalid_response":
                    response.json.side_effect = ValueError("invalid provider JSON")
                transport = AsyncMock()
                transport.__aenter__.return_value = transport
                transport.post.return_value = response
                if mode == "timeout":
                    transport.post.side_effect = httpx.ReadTimeout("test timeout")
                elif mode == "cancel":
                    transport.post.side_effect = asyncio.CancelledError()
                client = SGLangClient("http://sglang.invalid/v1", "fixed", timeout_ms=1000,
                                      purpose="agent_skill_selection")
                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=transport), \
                     patch("agent.app.clients.sglang_client.log_llm_call_evidence") as evidence:
                    call = client._generate("exact prompt", response_format="json",
                                            prefix_probe_call_id="test-call",
                                            evidence_context={"turn_id": "test-turn", "attempt": 1})
                    if mode == "nested_stop":
                        try:
                            raise ValueError("caller already handling an unrelated error")
                        except ValueError:
                            self.assertEqual(await call, {"ok": True})
                    elif mode == "stop":
                        self.assertEqual(await call, {"ok": True})
                    else:
                        error_type = asyncio.CancelledError if mode == "cancel" else (ValueError if mode in {"invalid_json", "invalid_response", "nonobject_response"} else SGLangGenerationError)
                        with self.assertRaises(error_type):
                            await call
                evidence.assert_called_once()
                record = evidence.call_args.kwargs
                self.assertEqual(record["request"], transport.post.call_args.kwargs["json"])
                expected_response = (None if mode in {"timeout", "cancel"} else
                                     {"http_status": response.status_code, "body": "provider body"}
                                     if mode in {"http_error", "invalid_response", "nonobject_response"} else data)
                self.assertEqual(record["response"], expected_response)
                self.assertEqual(record["status"], "accepted" if mode in {"stop", "nested_stop"} else "cancelled" if mode == "cancel" else "failed")
                self.assertEqual(record["correlations"], {"turn_id": "test-turn", "attempt": 1})
                transport.post.assert_called_once()
                self.assertEqual(record["error"] is None, mode in {"stop", "nested_stop"})
                if mode in {"timeout", "length"}:
                    self.assertEqual(record["error"]["failure_class"], "timeout" if mode == "timeout" else "output_truncated")

    async def test_each_stream_exit_retains_one_exact_request_and_partial_output(self) -> None:
        import hashlib
        import json
        import httpx
        from agent.app.clients.sglang_client import _PREFIX_CACHE_TRACKER

        for mode in ("stop", "length", "eof", "timeout", "cancel", "close"):
            with self.subTest(mode=mode):
                class StreamResponse:
                    status_code = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *args):
                        return None

                    async def aiter_lines(self):
                        yield "data: " + json.dumps({"choices": [{
                            "delta": {"content": "<terminal_plan>{"}, "finish_reason": None,
                        }]})
                        if mode == "timeout":
                            raise httpx.ReadTimeout("test timeout")
                        if mode == "cancel":
                            raise asyncio.CancelledError()
                        if mode != "eof":
                            yield "data: " + json.dumps({"choices": [{
                                "delta": {}, "finish_reason": mode,
                            }]})

                http_client = Mock()
                http_client.stream.return_value = StreamResponse()
                client_context = AsyncMock()
                client_context.__aenter__.return_value = http_client
                client = SGLangClient("http://sglang.invalid/v1", "fixed", timeout_ms=1000,
                                      purpose="fast_planner")

                async def consume():
                    return [delta async for delta in client.generate_stream(
                        "exact prompt", response_format="text", turn_id="turn-evidence", attempt=1,
                    )]

                with patch("agent.app.clients.sglang_client.httpx.AsyncClient", return_value=client_context), \
                     patch("agent.app.clients.sglang_client.log_llm_call_evidence") as evidence, \
                     patch.object(_PREFIX_CACHE_TRACKER, "begin", wraps=_PREFIX_CACHE_TRACKER.begin) as probe_start, \
                     patch.object(_PREFIX_CACHE_TRACKER, "finish", wraps=_PREFIX_CACHE_TRACKER.finish) as probe_finish:
                    if mode == "stop":
                        try:
                            raise ValueError("caller already handling an unrelated error")
                        except ValueError:
                            self.assertEqual(await consume(), ["<terminal_plan>{"])
                    elif mode == "close":
                        stream = client.generate_stream("exact prompt", response_format="text",
                                                        turn_id="turn-evidence", attempt=1)
                        self.assertEqual(await anext(stream), "<terminal_plan>{")
                        await stream.aclose()
                    else:
                        expected = asyncio.CancelledError if mode == "cancel" else SGLangGenerationError
                        with self.assertRaises(expected):
                            await consume()
                evidence.assert_called_once()
                record = evidence.call_args.kwargs
                self.assertEqual(record["request"], http_client.stream.call_args.kwargs["json"])
                self.assertEqual(record["response"]["choices"][0]["message"]["content"], "<terminal_plan>{")
                self.assertEqual(record["correlations"], {"turn_id": "turn-evidence", "attempt": 1})
                self.assertEqual(record["status"], "accepted" if mode == "stop" else
                                 "cancelled" if mode in {"cancel", "close"} else "failed")
                self.assertEqual(record["error"] is None, mode == "stop")
                contract_digest = "sha256:" + hashlib.sha256(json.dumps({
                    "options": client._effective_options(None),
                    "response_format": record["request"].get("response_format"),
                    "stream": True, "provider": "sglang",
                }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
                self.assertEqual(probe_start.call_args.kwargs["request_contract_digest"], contract_digest)
                probe_finish.assert_called_once()
                self.assertEqual(probe_finish.call_args.kwargs["status"], "completed" if mode == "stop" else
                                 "cancelled" if mode in {"cancel", "close"} else "failed")
                if mode == "length":
                    self.assertEqual(record["error"]["failure_class"], "output_truncated")
                if mode == "close":
                    self.assertEqual(record["error"]["error_type"], "GeneratorExit")


class SGLangUserMeaningInterpreterWarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_gi_primary_and_designated_deep_share_engine_and_interpretation_priority(self) -> None:
        import httpx

        interpreter = OllamaUserMeaningInterpreter(ollama_url="http://unused.invalid", model="qwen3.5-fast",
            deep_model="gemma-deep", inference_provider="sglang", sglang_url="http://fast.invalid/v1",
            timeout_ms=1000)
        http_client = AsyncMock()
        http_client.__aenter__.return_value = http_client
        http_client.post.return_value = httpx.Response(200, json={"choices": [{
            "message": {"content": "{}"}, "finish_reason": "stop",
        }]}, request=httpx.Request("POST", "http://test.invalid"))
        for stage, model, endpoint in (("user_meaning_interpretation_fast", "qwen3.5-fast", "fast"),
                                       ("user_meaning_interpretation_deep", "gemma-deep", "fast")):
            with self.subTest(stage=stage), patch(
                "agent.app.cognitive_core.user_meaning_interpreter.model_interpreter.httpx.AsyncClient",
                return_value=http_client,
            ), patch.object(interpreter, "_validate_completion"):
                await interpreter._chat({"model": model, "messages": [{"role": "user", "content": "source"}],
                    "options": {"num_ctx": 4096, "num_predict": 32}, "format": "json"}, stage=stage)
                self.assertEqual(http_client.post.call_args.args[0], f"http://{endpoint}.invalid/v1/chat/completions")
                self.assertEqual(http_client.post.call_args.kwargs["json"]["model"], model)
                self.assertEqual(http_client.post.call_args.kwargs["json"]["priority"], 400)

    async def test_warm_probe_reserves_terminal_completion_headroom(self) -> None:
        interpreter = OllamaUserMeaningInterpreter(
            ollama_url="http://ollama.invalid",
            model="chromie-qwen35-9b-sglang",
            inference_provider="sglang",
            sglang_url="http://sglang.invalid/v1",
            timeout_ms=1000,
        )
        logged = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "ready"},
                "done": True,
                "done_reason": "stop",
            }
        )

        with patch.object(interpreter, "_chat_logged", logged):
            await interpreter.warm_model()

        logged.assert_awaited_once()
        payload = logged.await_args.args[0]
        self.assertEqual(logged.await_args.kwargs["stage"], "startup_warm")
        self.assertEqual(payload["stream"], False)
        self.assertGreater(payload["options"]["num_predict"], 1)
        self.assertEqual(payload["options"]["num_predict"], 8)


class _ObservedLease(PresentationComputeLease):
    def __init__(self) -> None:
        super().__init__(
            enabled=True,
            control_url="http://example.invalid",
            mode="in_place",
            timeout_ms=1000,
        )
        self.controls: list[tuple[str, dict[str, object]]] = []

    async def _post_control(self, action: str, payload: dict[str, object]) -> None:
        self.controls.append((action, dict(payload)))


class PresentationComputeLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrap_holds_engine_for_vocal_delivery(self) -> None:
        lease = _ObservedLease()
        observed: list[dict[str, object]] = []

        async def speech(args):
            observed.append(args)
            self.assertTrue(lease.active)
            return {"scheduled": True}

        wrapped = lease.wrap_speech_scheduler(speech)
        result = await wrapped({"text": "hi", "metadata": {}})
        self.assertEqual(result, {"scheduled": True})
        self.assertFalse(lease.active)
        self.assertEqual(
            [item[0] for item in lease.controls],
            ["pause_generation", "continue_generation"],
        )
        metadata = observed[0]["metadata"]
        self.assertIsInstance(metadata, dict)
        self.assertTrue(metadata["wait_for_voice_release"])

    async def test_revocation_invalidates_old_release_token(self) -> None:
        lease = _ObservedLease()
        old = await lease.acquire(reason="old_speech")
        self.assertTrue(await lease.revoke(reason="new_user_input"))
        new = await lease.acquire(reason="replacement_speech")
        self.assertFalse(await lease.release(old, reason="stale_old_speech"))
        self.assertTrue(lease.active)
        self.assertTrue(await lease.release(new, reason="replacement_done"))
        self.assertEqual(
            [item[0] for item in lease.controls],
            [
                "pause_generation",
                "continue_generation",
                "pause_generation",
                "continue_generation",
            ],
        )


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize('purpose', ['social_cognition', 'social_cognition_deep'])
@pytest.mark.asyncio
async def test_actual_sc_overflow_is_rejected_even_when_character_estimate_fits(purpose):
    import httpx

    transport = AsyncMock()
    transport.__aenter__.return_value = transport
    async def post(url, **kwargs):
        data = ({'count': 973, 'tokens': [1] * 973, 'max_model_len': 1024}
                if url.endswith('/tokenize') else
                {'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}]})
        return httpx.Response(200, json=data, request=httpx.Request('POST', url))
    transport.post.side_effect = post
    client = SGLangClient('http://model.invalid/v1', 'fixed', purpose=purpose, timeout_ms=1000,
        service_settings=Settings(llm_prompt_chars_per_token_estimate=2, llm_context_safety_margin_tokens=20))
    with patch('agent.app.clients.sglang_client.httpx.AsyncClient', return_value=transport):
        with pytest.raises(SGLangGenerationError) as caught:
            await client.generate('short', system='short', options={'num_ctx': 1024, 'num_predict': 32})
    assert caught.value.failure_class == 'prompt_budget_exceeded'
    assert [c.args[0] for c in transport.post.call_args_list] == ['http://model.invalid/v1/tokenize']


def test_existing_definition_source_contracts_are_shared_without_changing_admission():
    import copy
    from jsonschema import Draft202012Validator
    from agent.app.clients.sglang_protocol import share_planner_schema_contracts
    span = {'type': 'object', 'additionalProperties': False,
            'required': ['source_start_token_ref', 'source_end_token_ref'], 'properties': {
                'source_start_token_ref': {'type': 'string', 'enum': ['r1.t0']},
                'source_end_token_ref': {'type': 'string', 'enum': ['r1.t1']}}}
    branch = {'type': 'object', 'additionalProperties': False, 'required': ['argument_sources'],
              'properties': {'argument_sources': {'type': 'object', 'required': ['count'],
                  'additionalProperties': False, 'properties': {'count': span}}}}
    schema = {'type': 'object', 'required': ['first', 'second'], 'additionalProperties': False,
              'properties': {'first': {'$ref': '#/$defs/first'}, 'second': {'$ref': '#/$defs/second'}},
              '$defs': {'first': copy.deepcopy(branch), 'second': copy.deepcopy(branch)}}
    shared = copy.deepcopy(schema)
    share_planner_schema_contracts(shared)
    def source(name):
        fields = shared['$defs'][name]['properties']['argument_sources']
        while '$ref' in fields:
            fields = shared['$defs'][fields['$ref'].rsplit('/', 1)[-1]]
        return fields['properties']['count']
    first, second = source('first'), source('second')
    assert first == second and '$ref' in first
    for source, accepted in [({'source_start_token_ref': 'r1.t0', 'source_end_token_ref': 'r1.t1'}, True),
                             ({'source_start_token_ref': 'r1.t0', 'source_end_token_ref': 'r2.t1'}, False),
                             ({'source_end_token_ref': 'r1.t1'}, False),
                             ({'source_start_token_ref': 'r1.t0', 'source_end_token_ref': 'r1.t1', 'foreign': 1}, False)]:
        value = {'first': {'argument_sources': {'count': source}}, 'second': {'argument_sources': {'count': source}}}
        assert Draft202012Validator(schema).is_valid(value) is accepted
        assert Draft202012Validator(shared).is_valid(value) is accepted


@pytest.mark.parametrize('location', ['items', 'prefix', 'nested_alternative', 'definition'])
def test_activity_grammar_shares_repeated_slots_at_every_array_depth(location):
    import copy
    from jsonschema import Draft202012Validator
    from agent.app.clients.sglang_protocol import share_planner_schema_contracts

    slot = {'oneOf': [
        {'type': 'object', 'additionalProperties': False,
         'required': ['kind', 'owner'], 'properties': {
             'kind': {'const': kind}, 'owner': {'enum': ['r1', 'r2']}}}
        for kind in ['work', 'need']
    ]}
    array = {'type': 'array', 'minItems': 2, 'maxItems': 2}
    if location == 'items':
        array['items'] = copy.deepcopy(slot)
    else:
        array.update(prefixItems=[copy.deepcopy(slot), copy.deepcopy(slot)], items=False)
    if location == 'nested_alternative':
        array = {'oneOf': [array, {'type': 'array', 'maxItems': 0}]}
    owner = {'type': 'object', 'additionalProperties': False, 'required': ['activities'],
             'properties': {'activities': array}}
    schema = ({'$ref': '#/$defs/owner', '$defs': {'owner': owner}} if location == 'definition'
              else {'oneOf': [owner]})
    shared = copy.deepcopy(schema)
    share_planner_schema_contracts(shared)
    Draft202012Validator.check_schema(shared)
    # The repeated slot union must itself be shared, including nested array shapes.
    slot_definitions = [node for node in shared['$defs'].values()
                        if isinstance(node, dict) and len(node.get('oneOf', [])) == 2
                        and all('$ref' in branch for branch in node['oneOf'])]
    assert slot_definitions
    for value, accepted in [
        ({'activities': [{'kind': 'work', 'owner': 'r1'}, {'kind': 'need', 'owner': 'r2'}]}, True),
        ({'activities': []}, location == 'nested_alternative'),
        ({'activities': [{'kind': 'work', 'owner': 'foreign'}, {'kind': 'need', 'owner': 'r2'}]}, False),
        ({'activities': [{'kind': 'work', 'owner': 'r1'}]}, False),
        ({'activities': [{'kind': 'work', 'owner': 'r1', 'extra': True}, {'kind': 'need', 'owner': 'r2'}]}, False),
    ]:
        assert Draft202012Validator(schema).is_valid(value) is accepted
        assert Draft202012Validator(shared).is_valid(value) is accepted


def test_repeated_schema_projection_has_one_wire_identity_despite_allocator_churn():
    import copy
    import json
    from agent.app.clients.sglang_protocol import _openai_response_format
    from agent.app.planner_schema import fast_streaming_advance_response_schema
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal

    responsibilities = [CognitiveResponsibilityProposal(
        local_ref=f"r{i}", outcome=f"Perform requested effect {i}.", confidence=1,
    ) for i in (1, 2)]
    capabilities = [{"capability_id": f"test.effect_{i}", "effects": ["physical_motion"],
                     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}}
                    for i in range(3)]
    schema = fast_streaming_advance_response_schema(
        [item.local_ref for item in responsibilities], responsibilities=responsibilities,
        capabilities=capabilities,
    )
    original = copy.deepcopy(schema)
    wires = []
    for count in (0, 1, 31, 127, 511, 1023) * 3:
        retained = [{str(index): [index]} for index in range(count)]
        wire = _openai_response_format(schema)
        wires.append(json.dumps(wire, ensure_ascii=False, separators=(",", ":")))
        assert len(retained) == count
    assert len(set(wires)) == 1
    assert schema == original


@pytest.mark.parametrize('literal_keyword', ['const', 'enum', 'default', 'examples'])
@pytest.mark.parametrize('stage', ['sharing', 'wire'])
def test_planner_schema_sharing_keeps_schema_shaped_literal_data_opaque(literal_keyword, stage):
    import copy
    from jsonschema import Draft202012Validator
    from agent.app.clients.sglang_protocol import share_planner_schema_contracts, _openai_response_format

    literal = {'properties': {'argument_sources': {'properties': {'count': {
        'type': 'object', 'properties': {'source': {'type': 'string'}},
    }}}}, 'type': 'array', 'uniqueItems': True}
    value = literal if literal_keyword in {'const', 'default'} else [literal]
    schema = {'title': 'FastPlannerWorkAdvanceOutput', 'type': 'object', 'required': ['payload'], 'properties': {
        'payload': {literal_keyword: copy.deepcopy(value)}}}
    shared = copy.deepcopy(schema)
    if stage == 'sharing':
        share_planner_schema_contracts(shared)
    else:
        shared = _openai_response_format(shared)['json_schema']['schema']
    payload = shared['properties']['payload']
    while '$ref' in payload:
        payload = shared['$defs'][payload['$ref'].rsplit('/', 1)[-1]]
    assert payload[literal_keyword] == value
    packet = {'payload': literal}
    assert Draft202012Validator(schema).is_valid(packet)
    assert Draft202012Validator(shared).is_valid(packet)


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('cause', ['Grammar preprocessing timed out', 'backend unavailable'])
def test_provider_error_is_not_an_empty_completion_or_delta(streaming, cause):
    from agent.app.clients.sglang_protocol import sglang_completion_content, sglang_stream_delta
    read = sglang_stream_delta if streaming else sglang_completion_content
    with pytest.raises(ValueError, match=cause) as caught:
        read({'error': {'message': cause + ': req.grammar_key=PRIVATE_SCHEMA', 'code': 400}})
    assert 'PRIVATE_SCHEMA' not in str(caught.value)
