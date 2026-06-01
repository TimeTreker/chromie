from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

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
