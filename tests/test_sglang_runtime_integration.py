from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from agent.app.clients.model_client_factory import build_model_client
from agent.app.clients.ollama_client import OllamaClient
from agent.app.clients.sglang_client import SGLangClient
from agent.app.clients.sglang_protocol import (
    build_sglang_chat_payload,
    candidate_compatible_schema,
    sglang_priority,
    sglang_stream_delta,
)
from agent.app.inference_compute import CognitionComputeClass
from agent.app.settings import Settings
from orchestrator.runtime.presentation_compute_lease import PresentationComputeLease


class SGLangProtocolTests(unittest.TestCase):
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
        self.assertEqual(payload["priority"], 300)
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
