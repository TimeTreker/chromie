from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .capabilities.models import CapabilityRegistry, ToolCapability

try:
    _BASE_EXCEPTION_GROUP = BaseExceptionGroup
except NameError:  # pragma: no cover - exercised on Python < 3.11
    _BASE_EXCEPTION_GROUP = None

ToolOutcomeStatus = Literal[
    "success",
    "failed_retryable",
    "failed_fatal",
    "timeout",
    "safety_interrupted",
]


class ToolCallOutcome(BaseModel):
    """Normalized result returned by a callable tool backend.

    This is intentionally transport-agnostic: a future MCP client, a local
    Python function registry, or a test double can all return the same shape to
    the DAG executor.
    """

    status: ToolOutcomeStatus = "success"
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def success(cls, output: dict[str, Any] | None = None) -> "ToolCallOutcome":
        return cls(status="success", output=output or {})

    @classmethod
    def failed(cls, error: str, *, retryable: bool = False, output: dict[str, Any] | None = None) -> "ToolCallOutcome":
        return cls(status="failed_retryable" if retryable else "failed_fatal", output=output or {}, error=error)


ToolHandler = Callable[[dict[str, Any]], dict[str, Any] | ToolCallOutcome]


class ToolInvoker(Protocol):
    """Transport-neutral callable interface used by the DAG executor."""

    def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolCallOutcome:
        ...


class ToolInvocationContext(BaseModel):
    """Proof supplied by the execution coordinator for guarded side effects."""

    allow_side_effects: bool = False
    confirmed: bool = False
    safety_monitor_active: bool = False
    allow_safety_controls: bool = False
    task_graph_id: str | None = None
    task_node_id: str | None = None


class AsyncToolInvoker(Protocol):
    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        ...


class FunctionToolInvoker:
    """In-process tool registry for tests and local Chromie tools.

    Real MCP transports can implement ToolInvoker later without changing the
    TaskGraph schema or executor. Handlers receive already-resolved node args.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        if tool_name in self._handlers:
            raise ValueError(f"duplicate tool handler: {tool_name}")
        self._handlers[tool_name] = handler

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._handlers

    def invoke(self, tool_name: str, args: dict[str, Any]) -> ToolCallOutcome:
        try:
            handler = self._handlers[tool_name]
        except KeyError:
            return ToolCallOutcome.failed(f"no handler registered for {tool_name!r}", retryable=False)
        try:
            raw = handler(args)
        except TimeoutError as exc:
            return ToolCallOutcome(status="timeout", error=str(exc) or "tool timeout")
        except Exception as exc:  # pragma: no cover - defensive normalization
            return ToolCallOutcome.failed(str(exc) or exc.__class__.__name__, retryable=False)
        if isinstance(raw, ToolCallOutcome):
            return raw
        if not isinstance(raw, dict):
            return ToolCallOutcome.failed(f"handler {tool_name!r} returned {type(raw).__name__}, expected dict")
        return ToolCallOutcome.success(raw)


McpCall = Callable[[str, str, dict[str, Any], float], Awaitable[Any]]
McpCallStarted = Callable[[str], None]


class McpStreamableHttpInvoker:
    """Invoke registry-approved tools through MCP Streamable HTTP."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        timeout_s: float = 30.0,
        trust_env: bool = False,
        call: McpCall | None = None,
        call_started: McpCallStarted | None = None,
    ) -> None:
        self.registry = registry
        self.timeout_s = timeout_s
        self.trust_env = trust_env
        self.call_started = call_started
        self._uses_sdk_call = call is None
        self._call = call or self._call_with_sdk

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        try:
            capability = self.registry.get_tool(tool_name)
            agent = self.registry.get_agent(capability.agent_id)
        except KeyError:
            return ToolCallOutcome.failed(f"unknown registered tool {tool_name!r}")

        error = self._policy_error(capability, context or ToolInvocationContext())
        if error:
            return ToolCallOutcome.failed(error)

        transport = agent.transport
        if transport.kind not in {"mcp_streamable_http", "streamable_http"}:
            return ToolCallOutcome.failed(
                f"tool {tool_name!r} uses unsupported transport {transport.kind!r}"
            )
        if not transport.url:
            return ToolCallOutcome.failed(f"tool {tool_name!r} has no MCP transport URL")

        timeout_s = capability.execution.timeout_s or self.timeout_s
        try:
            if not self._uses_sdk_call and self.call_started is not None:
                self.call_started(tool_name)
            raw = await self._call(transport.url, tool_name, args, timeout_s)
        except TimeoutError as exc:
            return ToolCallOutcome(status="timeout", error=str(exc) or "MCP tool timeout")
        except Exception as exc:
            return ToolCallOutcome.failed(
                self._exception_message(exc),
                retryable=True,
            )
        return self._normalize_result(raw)

    @classmethod
    def _exception_message(cls, exc: BaseException) -> str:
        if _BASE_EXCEPTION_GROUP is not None and isinstance(exc, _BASE_EXCEPTION_GROUP):
            nested = "; ".join(
                cls._exception_message(item)
                for item in exc.exceptions
            )
            return f"{exc.__class__.__name__}: {nested}"
        return str(exc) or exc.__class__.__name__

    def _policy_error(
        self,
        capability: ToolCapability,
        context: ToolInvocationContext,
    ) -> str | None:
        if not capability.availability.available:
            return capability.availability.reason or f"tool {capability.name!r} is unavailable"
        if capability.safety_class == "restricted":
            return f"restricted tool {capability.name!r} cannot be invoked"
        if capability.safety_class == "safety_critical":
            if not context.allow_safety_controls:
                return f"safety-critical tool {capability.name!r} requires explicit safety-control authorization"
            return None
        if capability.safety_class in {"low_risk_action", "physical_motion"} and not context.allow_side_effects:
            return f"tool {capability.name!r} requires explicit side-effect authorization"
        if capability.confirmation.required and not context.confirmed:
            return f"tool {capability.name!r} requires confirmed user approval"
        if capability.monitoring.requires_safety_monitor and not context.safety_monitor_active:
            return f"tool {capability.name!r} requires an active safety monitor"
        return None

    async def _call_with_sdk(
        self,
        url: str,
        tool_name: str,
        args: dict[str, Any],
        timeout_s: float,
    ) -> Any:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            trust_env=self.trust_env,
        ) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    if self.call_started is not None:
                        self.call_started(tool_name)
                    return await session.call_tool(tool_name, args)

    def _normalize_result(self, raw: Any) -> ToolCallOutcome:
        is_error = bool(self._field(raw, "isError", "is_error", default=False))
        structured = self._field(raw, "structuredContent", "structured_content")
        content = self._field(raw, "content", default=[]) or []
        text_parts = [
            str(self._field(item, "text"))
            for item in content
            if self._field(item, "type") == "text" and self._field(item, "text") is not None
        ]
        message = "\n".join(text_parts).strip()

        if is_error:
            error = message or "MCP tool returned an error"
            lowered = error.lower()
            if "timeout" in lowered or "timed out" in lowered:
                return ToolCallOutcome(status="timeout", error=error)
            retryable = any(
                marker in lowered
                for marker in (
                    "connection",
                    "disconnect",
                    "restart",
                    "status drop",
                    "status_drop",
                    "dropped status",
                )
            )
            return ToolCallOutcome.failed(error, retryable=retryable)
        if isinstance(structured, dict):
            return ToolCallOutcome.success(structured)
        if message:
            try:
                parsed = json.loads(message)
            except json.JSONDecodeError:
                return ToolCallOutcome.success({"text": message})
            if isinstance(parsed, dict):
                return ToolCallOutcome.success(parsed)
        return ToolCallOutcome.success({"content": self._jsonable(content)})

    def _field(self, value: Any, *names: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            for name in names:
                if name in value:
                    return value[name]
            return default
        for name in names:
            if hasattr(value, name):
                return getattr(value, name)
        return default

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: self._jsonable(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value
