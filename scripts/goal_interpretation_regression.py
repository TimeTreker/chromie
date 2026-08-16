"""Dependency-light evaluation helpers for Goal Interpretation regression cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    reasons: tuple[str, ...] = ()


def _capability_id(item: Mapping[str, Any]) -> str:
    capability_id = str(item.get("capability_id") or "").strip()
    if capability_id:
        return capability_id
    intent = str(item.get("intent") or "").strip()
    if intent.startswith("capability:"):
        return intent.split(":", 1)[1].strip()
    return ""


def selected_capabilities(response: Mapping[str, Any]) -> list[str]:
    actions = response.get("actions")
    selected: list[str] = []
    if isinstance(actions, list) and actions:
        for action in actions:
            if isinstance(action, Mapping):
                capability_id = _capability_id(action)
                if capability_id:
                    selected.append(capability_id)
        return selected
    intent = str(response.get("intent") or "").strip()
    if intent.startswith("capability:"):
        return [intent.split(":", 1)[1].strip()]
    return []


def candidate_capabilities(response: Mapping[str, Any]) -> list[str]:
    candidates = response.get("candidate_capabilities")
    if not isinstance(candidates, list):
        return []
    result: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            capability_id = _capability_id(candidate)
            if capability_id:
                result.append(capability_id)
    return result


def evaluate_case(case: Mapping[str, Any], response: Mapping[str, Any]) -> EvaluationResult:
    reasons: list[str] = []
    expected_route = case.get("expected_route")
    if expected_route and response.get("route") != expected_route:
        reasons.append(f"route {response.get('route')!r}, expected {expected_route!r}")
    expected = list(case.get("expected_capabilities") or [])
    selected = selected_capabilities(response)
    if expected and selected != expected:
        reasons.append(f"selected capabilities {selected!r}, expected {expected!r}")
    if case.get("require_ordered_actions") and not response.get("actions"):
        reasons.append("expected a non-empty actions list for ordered compound execution")
    required_candidates = list(case.get("required_candidates") or [])
    candidates = candidate_capabilities(response)
    missing = [item for item in required_candidates if item not in candidates]
    if missing:
        reasons.append(f"missing candidate capabilities {missing!r}")
    return EvaluationResult(passed=not reasons, reasons=tuple(reasons))
