from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .models import CapabilityRegistry

McpToolSchemas = dict[str, dict[str, Any]]
McpToolLister = Callable[[str, float], Awaitable[McpToolSchemas]]
McpToolPage = tuple[McpToolSchemas, str | None]
McpToolPageLister = Callable[[str | None], Awaitable[McpToolPage]]


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
            if not _schema_satisfies_contract(
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


def _schema_satisfies_contract(
    actual: Any,
    expected: Any,
    *,
    field_name: str | None = None,
) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual
            and _schema_satisfies_contract(
                actual[key],
                value,
                field_name=key,
            )
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        if field_name in {"enum", "required", "type"}:
            return _unordered_equal(actual, expected)
        return (
            len(actual) == len(expected)
            and all(
                _schema_satisfies_contract(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected)
            )
        )
    return actual == expected


def _unordered_equal(actual: list[Any], expected: list[Any]) -> bool:
    unmatched = list(actual)
    for expected_item in expected:
        for index, actual_item in enumerate(unmatched):
            if actual_item == expected_item:
                unmatched.pop(index)
                break
        else:
            return False
    return not unmatched


async def _collect_tool_pages(list_page: McpToolPageLister) -> McpToolSchemas:
    schemas: McpToolSchemas = {}
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        page, next_cursor = await list_page(cursor)
        duplicates = schemas.keys() & page.keys()
        if duplicates:
            raise ValueError(
                f"MCP tools/list returned duplicate tools across pages: {sorted(duplicates)}"
            )
        schemas.update(page)
        if not next_cursor:
            return schemas
        if next_cursor in seen_cursors:
            raise ValueError(f"MCP tools/list repeated pagination cursor {next_cursor!r}")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


async def _list_tools_with_sdk(url: str, timeout_s: float) -> McpToolSchemas:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.types import PaginatedRequestParams

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        trust_env=False,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def list_page(cursor: str | None) -> McpToolPage:
                    params = (
                        PaginatedRequestParams(cursor=cursor)
                        if cursor is not None
                        else None
                    )
                    response = await session.list_tools(params=params)
                    return (
                        {tool.name: tool.inputSchema for tool in response.tools},
                        response.nextCursor,
                    )

                return await _collect_tool_pages(list_page)
