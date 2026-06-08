from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .models import CapabilityRegistry

McpToolSchemas = dict[str, dict[str, Any]]
McpToolLister = Callable[[str, float], Awaitable[McpToolSchemas]]


@dataclass(frozen=True)
class CapabilityProbeResult:
    url: str
    expected_schemas: McpToolSchemas
    advertised_schemas: McpToolSchemas

    @property
    def missing_tools(self) -> frozenset[str]:
        return frozenset(self.expected_schemas.keys() - self.advertised_schemas.keys())

    @property
    def extra_tools(self) -> frozenset[str]:
        return frozenset(self.advertised_schemas.keys() - self.expected_schemas.keys())

    @property
    def schema_mismatches(self) -> frozenset[str]:
        return frozenset(
            name
            for name in self.expected_schemas.keys() & self.advertised_schemas.keys()
            if not _contains_schema(
                self.advertised_schemas[name],
                self.expected_schemas[name],
            )
        )

    @property
    def ok(self) -> bool:
        return not self.missing_tools and not self.schema_mismatches


async def probe_mcp_capabilities(
    registry: CapabilityRegistry,
    *,
    timeout_s: float = 10.0,
    list_tools: McpToolLister | None = None,
) -> list[CapabilityProbeResult]:
    endpoints: dict[str, McpToolSchemas] = defaultdict(dict)
    for agent in registry.list_agents():
        if agent.transport.kind not in {"mcp_streamable_http", "streamable_http"}:
            continue
        if not agent.transport.url:
            raise ValueError(f"MCP agent {agent.agent_id!r} has no transport URL")
        endpoints[agent.transport.url].update(
            {tool.name: tool.input_schema for tool in agent.tools}
        )

    if not endpoints:
        raise ValueError("capability registry contains no MCP Streamable HTTP endpoints")

    tool_lister = list_tools or _list_tools_with_sdk
    results: list[CapabilityProbeResult] = []
    for url in sorted(endpoints):
        advertised_schemas = await tool_lister(url, timeout_s)
        results.append(
            CapabilityProbeResult(
                url=url,
                expected_schemas=endpoints[url],
                advertised_schemas=advertised_schemas,
            )
        )
    return results


def _contains_schema(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_schema(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _contains_schema(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected)
            )
        )
    return actual == expected


async def _list_tools_with_sdk(url: str, timeout_s: float) -> McpToolSchemas:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                return {
                    tool.name: tool.inputSchema
                    for tool in response.tools
                }
