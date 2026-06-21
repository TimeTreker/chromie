from __future__ import annotations

from typing import Any

from .models import ExecutionTrace, NodeResult

_SUCCESS_STATUSES = {"success", "skipped"}


def build_trace_outcome_summary(trace: ExecutionTrace) -> str:
    """Return a deterministic one-line summary for reports and speech."""

    problem = next(
        (result for result in trace.node_results if result.status not in _SUCCESS_STATUSES),
        None,
    )
    if problem is None:
        if trace.status == "success":
            return "TaskGraph completed successfully."
        return f"TaskGraph ended with status={trace.status}."

    prefix = _problem_prefix(trace, problem)
    details = _problem_details(problem)
    if details:
        return f"{prefix}; " + "; ".join(details) + "."
    return f"{prefix}."


def _problem_prefix(trace: ExecutionTrace, result: NodeResult) -> str:
    status_text = {
        "blocked": "was blocked",
        "cancelled": "was cancelled",
        "failed_fatal": "failed",
        "failed_retryable": "failed retryably",
        "safety_interrupted": "was interrupted for safety",
        "timeout": "timed out",
    }.get(result.status, f"ended with status={result.status}")
    tool = f" ({result.tool})" if result.tool else ""
    return f"TaskGraph {trace.status}: node {result.node_id}{tool} {status_text}"


def _problem_details(result: NodeResult) -> list[str]:
    output = result.output
    details: list[str] = []
    reason_code = _clean_text(output.get("reason_code"))
    if reason_code:
        details.append(f"reason code: {reason_code}")
    reason = _clean_text(output.get("reason"))
    if reason:
        details.append(f"reason: {reason}")

    blocked = _clean_text_list(output.get("blocked_subsystems"))
    if blocked:
        details.append("blocked subsystems: " + ", ".join(blocked))

    recommended = _format_recommended_actions(output.get("recommended_next_actions"))
    if recommended:
        details.append("recommended next actions: " + "; ".join(recommended))

    if not details:
        error = _clean_text(result.error)
        if error:
            details.append(f"error: {error}")
    return details


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def _clean_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return [text for item in value if (text := _clean_text(item))]
    text = _clean_text(value)
    return [text] if text else []


def _format_recommended_actions(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list | tuple):
        return _clean_text_list(value)

    formatted: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            text = _clean_text(item)
            if text:
                formatted.append(text)
            continue

        action = _clean_text(item.get("action"))
        reason_code = _clean_text(item.get("reason_code"))
        detail = _clean_text(item.get("message") or item.get("reason"))
        if action and reason_code:
            text = f"{action} ({reason_code})"
        else:
            text = action or reason_code
        if text and detail:
            text = f"{text}: {detail}"
        elif detail:
            text = detail
        if text:
            formatted.append(text)
    return formatted
