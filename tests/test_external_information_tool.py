from __future__ import annotations

import unittest
from unittest import mock

from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.capabilities.models import CapabilityRegistry
from agent.app.clients.external_information_client import (
    ExternalInformationError,
    HttpExternalInformationClient,
)
from agent.app.local_tool_execution import LocalToolExecutor
from agent.app.settings import agent_service_settings
from shared.chromie_contracts.tool_result import ToolExecutionRequest


class _ExternalInformationClient:
    def __init__(self) -> None:
        self.queries = []

    async def retrieve(self, query):
        self.queries.append(query)
        return {
            "query": query.payload(),
            "summary": "Two nearby restaurants match the request.",
            "items": [
                {"name": "Family Noodles", "reason": "nearby and open now"},
                {"name": "Garden Kitchen", "reason": "quiet and child-friendly"},
            ],
            "sources": [
                {
                    "title": "Provider place record",
                    "url": "https://example.invalid/place",
                    "published_at": None,
                    "retrieved_at": "2026-08-04T02:20:00Z",
                }
            ],
            "retrieved_at": "2026-08-04T02:20:00Z",
            "provider": "test-external-information",
        }


class ExternalInformationToolTests(unittest.IsolatedAsyncioTestCase):
    def _registry(self) -> CapabilityRegistry:
        with (
            mock.patch.object(
                agent_service_settings,
                "external_information_enabled",
                True,
            ),
            mock.patch.object(
                agent_service_settings,
                "external_information_url",
                "http://example.invalid/retrieve",
            ),
        ):
            return CapabilityRegistry.from_bundles([chromie_capability_bundle()])

    async def test_provider_returns_evidence_not_final_personality_speech(self) -> None:
        client = _ExternalInformationClient()
        result = await LocalToolExecutor(
            self._registry(),
            external_information_client=client,  # type: ignore[arg-type]
        ).execute(
            ToolExecutionRequest(
                request_id="external-info-1",
                tool_id="chromie.external_information.retrieve",
                args={
                    "question": "Recommend good restaurants near me.",
                    "request_kind": "restaurant_search",
                    "location": "Chongqing Longxing Tianjie",
                    "freshness": "current",
                    "max_results": 5,
                },
                language="en-US",
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["provider"], "test-external-information")
        self.assertEqual(len(result.output["sources"]), 1)
        self.assertNotIn("speech", result.output)
        self.assertEqual(client.queries[0].request_kind, "restaurant_search")
        self.assertEqual(client.queries[0].location, "Chongqing Longxing Tianjie")
        scope = self._registry().get_tool(
            "chromie.external_information.retrieve"
        ).llm_hints["semantic_scope"]
        self.assertEqual(scope["responsibility_type"], "acquire_and_deliver_resource")
        self.assertEqual(scope["resource_kinds"], ["information"])

    def test_provider_result_requires_source_evidence_and_retrieval_time(self) -> None:
        with self.assertRaises(ExternalInformationError) as missing_source:
            HttpExternalInformationClient._normalize_result(
                {
                    "summary": "A result without evidence.",
                    "sources": [],
                    "retrieved_at": "2026-08-04T02:20:00Z",
                },
                query={"question": "What is nearby?"},
            )
        self.assertEqual(missing_source.exception.reason_code, "ungrounded_result")

        with self.assertRaises(ExternalInformationError) as missing_time:
            HttpExternalInformationClient._normalize_result(
                {
                    "summary": "A sourced result.",
                    "sources": [{"title": "Source", "url": "https://example.invalid"}],
                },
                query={"question": "What is nearby?"},
            )
        self.assertEqual(
            missing_time.exception.reason_code,
            "retrieval_time_missing",
        )

    async def test_capability_is_unavailable_until_provider_is_configured(self) -> None:
        registry = CapabilityRegistry.from_bundles([chromie_capability_bundle()])
        tool = registry.get_tool("chromie.external_information.retrieve")
        self.assertFalse(tool.availability.available)

        result = await LocalToolExecutor(registry).execute(
            ToolExecutionRequest(
                request_id="external-info-disabled",
                tool_id="chromie.external_information.retrieve",
                args={"question": "What is nearby?"},
            )
        )
        self.assertEqual(result.status, "refused")
        self.assertEqual(result.reason_code, "tool_unavailable")


if __name__ == "__main__":
    unittest.main()
