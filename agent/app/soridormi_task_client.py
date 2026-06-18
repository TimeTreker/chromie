from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .tool_invocation import AsyncToolInvoker, ToolCallOutcome, ToolInvocationContext

_MAX_CLIENT_TASK_REF_LENGTH = 128
_UNSAFE_REF_CHARS = re.compile(r"[^A-Za-z0-9_.:-]+")

Sleep = Callable[[float], Awaitable[None]]
_UNSUCCESSFUL_TASK_STATUSES = {"cancelled", "failed", "refused"}


class SoridormiTaskClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        outcome: ToolCallOutcome | None = None,
    ) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.outcome = outcome


class SoridormiTaskMonitorTimeout(SoridormiTaskClientError):
    def __init__(self, message: str, *, last_events: dict[str, Any] | None = None) -> None:
        super().__init__(message, tool_name="soridormi.task.events")
        self.last_events = last_events


def soridormi_client_task_ref(graph_id: str, node_id: str) -> str:
    """Return Chromie's stable idempotency key for one Soridormi task node."""

    if not graph_id.strip():
        raise ValueError("graph_id is required")
    if not node_id.strip():
        raise ValueError("node_id is required")
    raw = f"chromie:{graph_id}:{node_id}"
    safe = _UNSAFE_REF_CHARS.sub("-", raw).strip("-")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    if safe == raw and len(safe) <= _MAX_CLIENT_TASK_REF_LENGTH:
        return safe

    suffix = f":{digest}"
    prefix_budget = _MAX_CLIENT_TASK_REF_LENGTH - len(suffix)
    prefix = safe[:prefix_budget].rstrip("._:-") or "chromie"
    return f"{prefix}{suffix}"


def with_client_task_ref(
    payload: dict[str, Any],
    *,
    graph_id: str,
    node_id: str,
) -> dict[str, Any]:
    """Copy a submit payload and attach Chromie's retry-safe task reference."""

    copied = dict(payload)
    explicit_ref = copied.get("client_task_ref")
    if explicit_ref is not None:
        if not str(explicit_ref).strip():
            raise ValueError("client_task_ref must be non-empty when provided")
        return copied
    copied["client_task_ref"] = soridormi_client_task_ref(graph_id, node_id)
    return copied


class SoridormiTaskClient:
    """Small Chromie-side adapter for Soridormi's task-level MCP contract."""

    def __init__(
        self,
        invoker: AsyncToolInvoker,
        *,
        default_poll_interval_s: float = 0.5,
        max_polls: int = 120,
        sleep: Sleep | None = None,
    ) -> None:
        if default_poll_interval_s < 0:
            raise ValueError("default_poll_interval_s must be >= 0")
        if max_polls <= 0:
            raise ValueError("max_polls must be > 0")
        self._invoker = invoker
        self._default_poll_interval_s = default_poll_interval_s
        self._max_polls = max_polls
        self._sleep = sleep or asyncio.sleep

    async def submit(
        self,
        payload: dict[str, Any],
        *,
        graph_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        args = with_client_task_ref(payload, graph_id=graph_id, node_id=node_id)
        outcome = await self._invoker.invoke("soridormi.task.submit", args)
        return self._output_or_raise("soridormi.task.submit", outcome)

    async def status(
        self,
        *,
        task_id: str | None = None,
        client_task_ref: str | None = None,
    ) -> dict[str, Any]:
        outcome = await self._invoker.invoke(
            "soridormi.task.status",
            self._lookup_args(task_id=task_id, client_task_ref=client_task_ref),
        )
        return self._output_or_raise("soridormi.task.status", outcome)

    async def events(
        self,
        *,
        task_id: str | None = None,
        client_task_ref: str | None = None,
        after_sequence: int = 0,
    ) -> dict[str, Any]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be >= 0")
        args = self._lookup_args(task_id=task_id, client_task_ref=client_task_ref)
        args["after_sequence"] = after_sequence
        outcome = await self._invoker.invoke("soridormi.task.events", args)
        return self._output_or_raise("soridormi.task.events", outcome)

    async def monitor_until_terminal(
        self,
        *,
        task_id: str | None = None,
        client_task_ref: str | None = None,
        after_sequence: int = 0,
        max_polls: int | None = None,
    ) -> dict[str, Any]:
        poll_limit = self._max_polls if max_polls is None else max_polls
        if poll_limit <= 0:
            raise ValueError("max_polls must be > 0")

        cursor = after_sequence
        last_events: dict[str, Any] | None = None
        for _ in range(poll_limit):
            last_events = await self.events(
                task_id=task_id,
                client_task_ref=client_task_ref,
                after_sequence=cursor,
            )
            cursor = int(last_events.get("next_after_sequence", cursor))
            recommendation = last_events.get("poll_recommendation")
            action = recommendation.get("action") if isinstance(recommendation, dict) else None
            if bool(last_events.get("terminal")) or action == "stop_polling":
                return last_events

            interval_s = self._recommended_poll_interval_s(last_events)
            if interval_s > 0:
                await self._sleep(interval_s)

        raise SoridormiTaskMonitorTimeout(
            "Soridormi task did not reach a terminal state before monitor poll limit",
            last_events=last_events,
        )

    async def cancel(
        self,
        *,
        task_id: str | None = None,
        client_task_ref: str | None = None,
        reason: str = "Cancelled by Chromie task monitor.",
    ) -> dict[str, Any]:
        args = self._lookup_args(task_id=task_id, client_task_ref=client_task_ref)
        args["reason"] = reason
        outcome = await self._invoker.invoke(
            "soridormi.task.cancel",
            args,
            context=ToolInvocationContext(allow_safety_controls=True),
        )
        return self._output_or_raise("soridormi.task.cancel", outcome)

    @staticmethod
    def _lookup_args(
        *,
        task_id: str | None,
        client_task_ref: str | None,
    ) -> dict[str, Any]:
        if task_id and client_task_ref:
            raise ValueError("provide either task_id or client_task_ref, not both")
        if task_id:
            return {"task_id": task_id}
        if client_task_ref:
            return {"client_task_ref": client_task_ref}
        raise ValueError("task_id or client_task_ref is required")

    @staticmethod
    def _output_or_raise(tool_name: str, outcome: ToolCallOutcome) -> dict[str, Any]:
        if outcome.status != "success":
            detail = outcome.error or outcome.status
            raise SoridormiTaskClientError(
                f"{tool_name} failed: {detail}",
                tool_name=tool_name,
                outcome=outcome,
            )
        if not isinstance(outcome.output, dict):
            raise SoridormiTaskClientError(
                f"{tool_name} returned {type(outcome.output).__name__}, expected dict",
                tool_name=tool_name,
                outcome=outcome,
            )
        return outcome.output

    def _recommended_poll_interval_s(self, events: dict[str, Any]) -> float:
        recommendation = events.get("poll_recommendation")
        if isinstance(recommendation, dict):
            raw = recommendation.get("recommended_poll_interval_s")
            if isinstance(raw, int | float):
                return max(0.0, float(raw))
        return self._default_poll_interval_s


class SoridormiTaskMonitoringInvoker:
    """Wrap planning invocation with Soridormi task submit/monitor semantics."""

    def __init__(
        self,
        invoker: AsyncToolInvoker,
        *,
        monitor_until_terminal: bool = True,
        default_poll_interval_s: float = 0.5,
        max_polls: int = 120,
        sleep: Sleep | None = None,
    ) -> None:
        self._invoker = invoker
        self._monitor_until_terminal = monitor_until_terminal
        self._client = SoridormiTaskClient(
            invoker,
            default_poll_interval_s=default_poll_interval_s,
            max_polls=max_polls,
            sleep=sleep,
        )

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        if tool_name != "soridormi.task.submit":
            return await self._invoker.invoke(tool_name, args, context=context)

        submit_args = self._submit_args(args, context)
        outcome = await self._invoker.invoke(tool_name, submit_args, context=context)
        if outcome.status != "success":
            return outcome

        output = dict(outcome.output)
        failure = self._task_failure_message(output)
        if failure is not None:
            return ToolCallOutcome.failed(failure, output=output)

        if not self._monitor_until_terminal or output.get("terminal") is True:
            return ToolCallOutcome.success(output)

        task_id = output.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return ToolCallOutcome.failed(
                "soridormi.task.submit did not return a task_id",
                output=output,
            )

        try:
            events = await self._client.monitor_until_terminal(task_id=task_id)
        except SoridormiTaskMonitorTimeout as exc:
            if exc.last_events is not None:
                output["monitoring"] = exc.last_events
            return ToolCallOutcome(
                status="timeout",
                output=output,
                error=str(exc),
            )
        except SoridormiTaskClientError as exc:
            return ToolCallOutcome.failed(str(exc), retryable=True, output=output)

        output = self._merge_monitoring(output, events)
        failure = self._task_failure_message(output)
        if failure is not None:
            if output.get("expired") is True:
                return ToolCallOutcome(status="timeout", output=output, error=failure)
            return ToolCallOutcome.failed(failure, output=output)
        return ToolCallOutcome.success(output)

    @staticmethod
    def _submit_args(
        args: dict[str, Any],
        context: ToolInvocationContext | None,
    ) -> dict[str, Any]:
        if args.get("client_task_ref") is not None:
            return dict(args)
        if context is None or not context.task_graph_id or not context.task_node_id:
            return dict(args)
        return with_client_task_ref(
            args,
            graph_id=context.task_graph_id,
            node_id=context.task_node_id,
        )

    @staticmethod
    def _merge_monitoring(
        output: dict[str, Any],
        events: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(output)
        merged["monitoring"] = events
        for key in (
            "status",
            "phase",
            "terminal",
            "safe_idle",
            "deadline_at",
            "expired",
            "timeout_elapsed_s",
            "reason_code",
        ):
            if key in events:
                merged[key] = events[key]
        return merged

    @staticmethod
    def _task_failure_message(output: dict[str, Any]) -> str | None:
        status = str(output.get("status") or "")
        if output.get("accepted") is False or status in _UNSUCCESSFUL_TASK_STATUSES:
            reason_code = output.get("reason_code")
            reason = output.get("reason")
            parts = [part for part in (status or "task_failed", reason_code, reason) if part]
            return "Soridormi task did not complete successfully: " + " / ".join(
                str(part) for part in parts
            )
        return None
