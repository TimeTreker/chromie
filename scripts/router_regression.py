#!/usr/bin/env python3
"""Run deterministic assertions against a live Chromie Router HTTP endpoint."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_URL = "http://127.0.0.1:8091/route"
DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tests" / "router_cases.json"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    reasons: tuple[str, ...]
    route: str
    selected_capabilities: tuple[str, ...]
    response: dict[str, Any]


def _capability_from_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    prefix = "capability:"
    if value.startswith(prefix):
        value = value[len(prefix) :].strip()
    return value or None


def selected_capabilities(response: dict[str, Any]) -> list[str]:
    """Return explicitly selected capabilities in execution order.

    Ordered actions take precedence. The top-level ``intent`` is retained as a
    backwards-compatible single-capability representation.
    """

    selected: list[str] = []
    actions = response.get("actions")
    if isinstance(actions, list):
        for action in actions:
            if not isinstance(action, dict):
                continue
            candidate = (
                action.get("capability_id")
                or action.get("skill_id")
                or action.get("intent")
            )
            capability_id = _capability_from_value(candidate)
            if capability_id and capability_id not in selected:
                selected.append(capability_id)

    if not selected:
        capability_id = _capability_from_value(response.get("intent"))
        if capability_id and str(response.get("intent", "")).startswith("capability:"):
            selected.append(capability_id)

    return selected


def candidate_capabilities(response: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    raw_candidates = response.get("candidate_capabilities")
    if not isinstance(raw_candidates, list):
        return candidates
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        capability_id = _capability_from_value(item.get("capability_id"))
        if capability_id and capability_id not in candidates:
            candidates.append(capability_id)
    return candidates


def evaluate_case(case: dict[str, Any], response: dict[str, Any]) -> CaseResult:
    reasons: list[str] = []
    case_id = str(case.get("id") or "unnamed")
    route = str(response.get("route") or "")
    expected_route = str(case.get("expected_route") or "")
    selected = selected_capabilities(response)
    candidates = candidate_capabilities(response)
    expected = [str(item) for item in case.get("expected_capabilities", [])]
    required_candidates = [str(item) for item in case.get("required_candidates", [])]

    if route != expected_route:
        reasons.append(f"route={route!r}; expected {expected_route!r}")

    if case.get("require_ordered_actions"):
        actions = response.get("actions")
        if not isinstance(actions, list) or not actions:
            reasons.append("compound route must use a non-empty actions list")
        if selected != expected:
            reasons.append(f"selected sequence={selected!r}; expected {expected!r}")
    elif selected != expected:
        reasons.append(f"selected capabilities={selected!r}; expected {expected!r}")

    missing_candidates = [item for item in required_candidates if item not in candidates]
    if missing_candidates:
        reasons.append(f"candidate list missing {missing_candidates!r}")

    return CaseResult(
        case_id=case_id,
        passed=not reasons,
        reasons=tuple(reasons),
        route=route,
        selected_capabilities=tuple(selected),
        response=response,
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"case file must contain a JSON list: {path}")
    cases = [item for item in payload if isinstance(item, dict)]
    if len(cases) != len(payload):
        raise ValueError(f"every case must be a JSON object: {path}")
    return cases


def post_route(url: str, case: dict[str, Any], *, timeout_s: float, run: int) -> dict[str, Any]:
    case_id = str(case.get("id") or "unnamed")
    body = {
        "sid": f"router-regression-{case_id}-{run}",
        "text": str(case.get("text") or ""),
        "language": str(case.get("language") or "en-US"),
        "context": {
            "conversation_id": f"router_regression_{case_id}",
            "router_regression_case": case_id,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"router request failed: {exc.reason}") from exc

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("router response must be a JSON object")
    return payload


def _filter_cases(cases: Iterable[dict[str, Any]], selected_ids: set[str]) -> list[dict[str, Any]]:
    if not selected_ids:
        return list(cases)
    filtered = [case for case in cases if str(case.get("id")) in selected_ids]
    missing = selected_ids - {str(case.get("id")) for case in filtered}
    if missing:
        raise ValueError(f"unknown case IDs: {sorted(missing)}")
    return filtered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Router POST /route URL")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", default=[], help="Run one case ID; repeatable")
    parser.add_argument("--repeat", type=int, default=1, help="Run every selected case N times")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--show-response", action="store_true", help="Print every JSON response")
    args = parser.parse_args(argv)

    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    cases = _filter_cases(load_cases(args.cases), set(args.case))
    failures = 0
    total = 0

    for case in cases:
        for run in range(1, args.repeat + 1):
            total += 1
            case_id = str(case.get("id") or "unnamed")
            try:
                response = post_route(args.url, case, timeout_s=args.timeout, run=run)
                result = evaluate_case(case, response)
            except Exception as exc:  # the runner must report all cases
                failures += 1
                print(f"FAIL {case_id} run={run}: {type(exc).__name__}: {exc}")
                continue

            selected_text = ",".join(result.selected_capabilities) or "<none>"
            if result.passed:
                print(f"PASS {case_id} run={run}: route={result.route} selected={selected_text}")
            else:
                failures += 1
                print(f"FAIL {case_id} run={run}: {'; '.join(result.reasons)}")

            if args.show_response or not result.passed:
                print(json.dumps(result.response, indent=2, sort_keys=True))

    print(f"SUMMARY total={total} passed={total - failures} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
