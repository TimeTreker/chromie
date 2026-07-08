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
            if _schema_contract_violations(
                self.advertised_schemas[name],
                self.expected_schemas[name],
            )
        )

    @property
    def schema_mismatch_details(self) -> dict[str, tuple[str, ...]]:
        return {
            name: tuple(
                _schema_contract_violations(
                    self.advertised_schemas[name],
                    self.expected_schemas[name],
                )
            )
            for name in sorted(self.expected_schemas.keys() & self.advertised_schemas.keys())
            if _schema_contract_violations(
                self.advertised_schemas[name],
                self.expected_schemas[name],
            )
        }

    @property
    def schema_warnings(self) -> dict[str, tuple[str, ...]]:
        return {
            name: tuple(
                _schema_contract_warnings(
                    self.advertised_schemas[name],
                    self.expected_schemas[name],
                )
            )
            for name in sorted(self.expected_schemas.keys() & self.advertised_schemas.keys())
            if _schema_contract_warnings(
                self.advertised_schemas[name],
                self.expected_schemas[name],
            )
        }

    @property
    def ok(self) -> bool:
        return not self.missing_tools and not self.schema_mismatches


async def probe_mcp_capabilities(
    registry: CapabilityRegistry,
    *,
    timeout_s: float = 10.0,
    list_tools: McpToolLister | None = None,
    excluded_effects: frozenset[str] = frozenset(),
) -> list[CapabilityProbeResult]:
    endpoints: dict[str, McpToolSchemas] = defaultdict(dict)
    for agent in registry.list_agents():
        if agent.transport.kind not in {"mcp_streamable_http", "streamable_http"}:
            continue
        if not agent.transport.url:
            raise ValueError(f"MCP agent {agent.agent_id!r} has no transport URL")
        endpoints[agent.transport.url].update(
            {
                tool.name: tool.input_schema
                for tool in agent.tools
                if excluded_effects.isdisjoint(tool.effects)
            }
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
    return not _schema_contract_violations(
        actual,
        expected,
        field_name=field_name,
    )


def _schema_contract_violations(
    actual: Any,
    expected: Any,
    *,
    field_name: str | None = None,
    path: str = "input_schema",
) -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        return _dict_schema_violations(
            actual,
            expected,
            field_name=field_name,
            path=path,
        )

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected list, got {type(actual).__name__}"]
        if field_name in {"enum", "required", "type"}:
            if _unordered_equal(actual, expected):
                return []
            return [f"{path}: expected unordered {expected!r}, got {actual!r}"]
        if len(actual) != len(expected):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}"]
        violations: list[str] = []
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            violations.extend(
                _schema_contract_violations(
                    actual_item,
                    expected_item,
                    path=f"{path}[{index}]",
                )
            )
        return violations

    if actual == expected:
        return []
    return [f"{path}: expected {expected!r}, got {actual!r}"]


def _dict_schema_violations(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    field_name: str | None,
    path: str,
) -> list[str]:
    violations: list[str] = []

    for key, value in expected.items():
        if key == "properties" and isinstance(value, dict):
            continue
        if key not in actual:
            if key == "additionalProperties" and value is True:
                # JSON Schema defaults additionalProperties to true when omitted.
                continue
            violations.append(f"{path}.{key}: missing")
            continue
        violations.extend(
            _schema_contract_violations(
                actual[key],
                value,
                field_name=key,
                path=f"{path}.{key}",
            )
        )

    if "properties" in expected and isinstance(expected["properties"], dict):
        actual_properties = actual.get("properties", {})
        if not isinstance(actual_properties, dict):
            violations.append(f"{path}.properties: expected object")
            return violations

        required = _required_names(expected)
        allows_extra = actual.get("additionalProperties", True) is not False
        for property_name, property_schema in expected["properties"].items():
            property_path = f"{path}.properties.{property_name}"
            if property_name in actual_properties:
                violations.extend(
                    _schema_contract_violations(
                        actual_properties[property_name],
                        property_schema,
                        path=property_path,
                    )
                )
            elif property_name in required or not allows_extra:
                violations.append(f"{property_path}: missing")

    return violations


def _schema_contract_warnings(
    actual: Any,
    expected: Any,
    *,
    path: str = "input_schema",
) -> list[str]:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return []

    warnings: list[str] = []
    if "properties" in expected and isinstance(expected["properties"], dict):
        actual_properties = actual.get("properties", {})
        if isinstance(actual_properties, dict):
            required = _required_names(expected)
            allows_extra = actual.get("additionalProperties", True) is not False
            for property_name in expected["properties"]:
                if (
                    property_name not in actual_properties
                    and property_name not in required
                    and allows_extra
                ):
                    warnings.append(
                        f"{path}.properties.{property_name}: optional manifest property "
                        "is not advertised; accepting because additionalProperties "
                        "is not false"
                    )

            for property_name, property_schema in expected["properties"].items():
                if property_name in actual_properties:
                    warnings.extend(
                        _schema_contract_warnings(
                            actual_properties[property_name],
                            property_schema,
                            path=f"{path}.properties.{property_name}",
                        )
                    )

    for key, value in expected.items():
        if key == "properties":
            continue
        if key in actual:
            warnings.extend(
                _schema_contract_warnings(
                    actual[key],
                    value,
                    path=f"{path}.{key}",
                )
            )
    return warnings


def _required_names(schema: dict[str, Any]) -> frozenset[str]:
    required = schema.get("required", [])
    if not isinstance(required, list):
        return frozenset()
    return frozenset(item for item in required if isinstance(item, str))


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
