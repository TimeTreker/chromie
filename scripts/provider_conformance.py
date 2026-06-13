#!/usr/bin/env python3
"""Verify Soridormi named-skill provider conformance in no-motion-safe modes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.tool_invocation import (
    AsyncToolInvoker,
    ToolCallOutcome,
    ToolInvocationContext,
)
from orchestrator.runtime.interaction_coordinator import build_soridormi_invoker
from shared.chromie_contracts.interaction import reject_forbidden_low_level_fields

CONFORMANCE_VERSION = "1.1"
TRACE_VERSION = "1.0"
SAFE_MODES = {"sim", "hardware_shadow", "hardware_dry_run"}


@dataclass(frozen=True)
class ConformanceCheck:
    name: str
    passed: bool
    detail: str


class TracingInvoker:
    """Retain replayable high-level calls without exposing device controls."""

    def __init__(self, delegate: AsyncToolInvoker) -> None:
        self.delegate = delegate
        self.entries: list[dict[str, Any]] = []

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        outcome = await self.delegate.invoke(tool_name, args, context=context)
        self.entries.append(
            {
                "sequence": len(self.entries) + 1,
                "tool_name": tool_name,
                "args": args,
                "authorization": (
                    context.model_dump(mode="json")
                    if context is not None
                    else ToolInvocationContext().model_dump(mode="json")
                ),
                "outcome": outcome.model_dump(mode="json"),
            }
        )
        return outcome


class NoMotionProviderStub:
    """Minimal provider skeleton used to prove mode-independent contracts."""

    def __init__(self, mode: str) -> None:
        if mode not in SAFE_MODES:
            raise ValueError(f"unsupported no-motion provider mode: {mode}")
        self.mode = mode

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": self.mode,
                    "skills": [
                        {
                            "skill_id": "nod_yes",
                            "version": "0.1.0",
                            "available": True,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "count": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 3,
                                    }
                                },
                                "additionalProperties": False,
                            },
                            "interruptible": True,
                        }
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success(
                {
                    "plan_id": "conformance-plan",
                    "skill_id": args.get("skill_id"),
                    "mode": self.mode,
                }
            )
        if tool_name == "soridormi.safety.monitor_motion":
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            if not context or not (
                context.allow_side_effects
                and context.confirmed
                and context.safety_monitor_active
            ):
                return ToolCallOutcome.failed("missing execution authorization")
            return ToolCallOutcome.success(
                {
                    "completed": True,
                    "skill_id": "nod_yes",
                    "mode": self.mode,
                    "no_motion": self.mode != "sim",
                    "recommendation_only": self.mode == "hardware_shadow",
                }
            )
        if tool_name == "soridormi.motion.cancel":
            if not context or not context.allow_safety_controls:
                return ToolCallOutcome.failed("missing safety-control authorization")
            return ToolCallOutcome.success({"cancelled": True})
        if tool_name == "soridormi.robot.get_status":
            return ToolCallOutcome.success(
                {
                    "mode": self.mode,
                    "active_task": None,
                    "emergency_stop": False,
                }
            )
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


def record_outcome(
    checks: list[ConformanceCheck],
    name: str,
    outcome: ToolCallOutcome,
) -> bool:
    passed = outcome.status == "success"
    checks.append(
        ConformanceCheck(
            name,
            passed,
            "success" if passed else (outcome.error or outcome.status),
        )
    )
    return passed


def record_abstraction(
    checks: list[ConformanceCheck],
    name: str,
    output: dict[str, Any],
) -> None:
    try:
        reject_forbidden_low_level_fields(output)
    except ValueError as exc:
        checks.append(ConformanceCheck(name, False, str(exc)))
    else:
        checks.append(ConformanceCheck(name, True, "no forbidden low-level fields"))


def report(
    mode: str,
    checks: Sequence[ConformanceCheck],
    trace: Sequence[dict[str, Any]] = (),
    *,
    evidence_source: str,
) -> dict[str, Any]:
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "trace_version": TRACE_VERSION,
        "evidence_source": evidence_source,
        "mode": mode,
        "passed": all(check.passed for check in checks),
        "check_count": len(checks),
        "checks": [asdict(check) for check in checks],
        "trace": list(trace),
    }


def trace_signature(profile: dict[str, Any]) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for entry in profile.get("trace", []):
        tool_name = entry.get("tool_name")
        args = dict(entry.get("args") or {})
        if tool_name == "soridormi.skill.execute_plan" and "plan_id" in args:
            args["plan_id"] = "<opaque-plan-id>"
        signature.append(
            {
                "tool_name": tool_name,
                "args": args,
                "authorization": entry.get("authorization"),
                "status": entry.get("outcome", {}).get("status"),
            }
        )
    return signature


def compare_profiles(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) < 2:
        return {
            "passed": True,
            "compared_modes": [report["mode"] for report in reports],
            "mismatches": [],
        }
    ignored_checks = {
        "safe provider mode",
        "shadow no-motion proof",
        "dry-run no-motion proof",
    }
    baseline = reports[0]
    baseline_checks = {
        check["name"]: check["passed"]
        for check in baseline["checks"]
        if check["name"] not in ignored_checks
    }
    mismatches: list[str] = []
    for candidate in reports[1:]:
        candidate_checks = {
            check["name"]: check["passed"]
            for check in candidate["checks"]
            if check["name"] not in ignored_checks
        }
        if candidate_checks.keys() != baseline_checks.keys():
            missing = sorted(baseline_checks.keys() - candidate_checks.keys())
            extra = sorted(candidate_checks.keys() - baseline_checks.keys())
            mismatches.append(
                f"{candidate['mode']} check set differs: missing={missing} extra={extra}"
            )
            continue
        for name, baseline_passed in baseline_checks.items():
            candidate_passed = candidate_checks[name]
            if candidate_passed != baseline_passed:
                mismatches.append(
                    f"{candidate['mode']} check {name!r}={candidate_passed} "
                    f"differs from {baseline['mode']}={baseline_passed}"
                )
        if trace_signature(candidate) != trace_signature(baseline):
            mismatches.append(
                f"{candidate['mode']} high-level trace differs from "
                f"{baseline['mode']}"
            )
    return {
        "passed": not mismatches,
        "compared_modes": [report["mode"] for report in reports],
        "ignored_profile_specific_checks": sorted(ignored_checks),
        "mismatches": mismatches,
    }


def compare_evidence(paths: Sequence[Path]) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    seen_modes: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("conformance_version") != CONFORMANCE_VERSION:
            raise ValueError(
                f"{path} uses conformance version "
                f"{payload.get('conformance_version')!r}, expected "
                f"{CONFORMANCE_VERSION!r}"
            )
        if payload.get("trace_version") != TRACE_VERSION:
            raise ValueError(
                f"{path} uses trace version {payload.get('trace_version')!r}, "
                f"expected {TRACE_VERSION!r}"
            )
        items = payload.get("profiles")
        if not isinstance(items, list) or not items:
            raise ValueError(f"{path} contains no provider profiles")
        for profile in items:
            if not isinstance(profile, dict) or profile.get("mode") not in SAFE_MODES:
                raise ValueError(f"{path} contains an invalid provider profile")
            mode = str(profile["mode"])
            if mode in seen_modes:
                raise ValueError(f"duplicate provider profile mode: {mode}")
            seen_modes.add(mode)
            profiles.append(profile)
    parity = compare_profiles(profiles)
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "trace_version": TRACE_VERSION,
        "passed": all(profile.get("passed") is True for profile in profiles)
        and parity["passed"],
        "profile_parity": parity,
        "profiles": profiles,
        "source_files": [str(path) for path in paths],
    }


async def run_conformance(
    invoker: AsyncToolInvoker,
    *,
    expected_mode: str,
    evidence_source: str = "local_stub",
) -> dict[str, Any]:
    if expected_mode not in SAFE_MODES:
        raise ValueError(
            "Provider conformance execution is restricted to sim, "
            "hardware_shadow, or hardware_dry_run"
        )
    traced = TracingInvoker(invoker)
    checks: list[ConformanceCheck] = []
    catalog = await traced.invoke("soridormi.skill.list", {})
    if not record_outcome(checks, "catalog call", catalog):
        return report(
            expected_mode,
            checks,
            traced.entries,
            evidence_source=evidence_source,
        )
    record_abstraction(checks, "catalog abstraction", catalog.output)
    actual_mode = catalog.output.get("mode")
    checks.append(
        ConformanceCheck(
            "safe provider mode",
            actual_mode == expected_mode and actual_mode in SAFE_MODES,
            f"expected={expected_mode} actual={actual_mode}",
        )
    )
    skills = catalog.output.get("skills")
    skill_items = skills if isinstance(skills, list) else []
    nod = next(
        (
            item
            for item in skill_items
            if isinstance(item, dict) and item.get("skill_id") == "nod_yes"
        ),
        None,
    )
    checks.append(
        ConformanceCheck(
            "named skill catalog",
            isinstance(nod, dict)
            and nod.get("available") is True
            and isinstance(nod.get("parameters_schema"), dict)
            and bool(nod.get("version")),
            "nod_yes is versioned, available, and schema-backed",
        )
    )
    if not isinstance(nod, dict):
        return report(
            expected_mode,
            checks,
            traced.entries,
            evidence_source=evidence_source,
        )

    planned = await traced.invoke(
        "soridormi.skill.create_plan",
        {"skill_id": "nod_yes", "parameters": {"count": 2}},
    )
    if not record_outcome(checks, "plan call", planned):
        return report(
            expected_mode,
            checks,
            traced.entries,
            evidence_source=evidence_source,
        )
    record_abstraction(checks, "plan abstraction", planned.output)
    plan_id = planned.output.get("plan_id")
    checks.append(
        ConformanceCheck(
            "opaque plan identity",
            isinstance(plan_id, str)
            and bool(plan_id)
            and planned.output.get("skill_id") == "nod_yes",
            "plan_id is opaque and bound to nod_yes",
        )
    )
    if not isinstance(plan_id, str) or not plan_id:
        return report(
            expected_mode,
            checks,
            traced.entries,
            evidence_source=evidence_source,
        )

    monitored = await traced.invoke(
        "soridormi.safety.monitor_motion",
        {"during_node_id": "conformance-request"},
        context=ToolInvocationContext(allow_safety_controls=True),
    )
    if not record_outcome(checks, "monitor call", monitored):
        return report(
            expected_mode,
            checks,
            traced.entries,
            evidence_source=evidence_source,
        )
    record_abstraction(checks, "monitor abstraction", monitored.output)
    checks.append(
        ConformanceCheck(
            "monitor ready",
            monitored.output.get("ok") is True,
            "safety monitor explicitly returned ok=true",
        )
    )

    executed = await traced.invoke(
        "soridormi.skill.execute_plan",
        {"plan_id": plan_id},
        context=ToolInvocationContext(
            allow_side_effects=True,
            confirmed=True,
            safety_monitor_active=True,
        ),
    )
    if record_outcome(checks, "execute call", executed):
        record_abstraction(checks, "execution abstraction", executed.output)
        checks.append(
            ConformanceCheck(
                "explicit matching completion",
                executed.output.get("completed") is True
                and executed.output.get("skill_id") == "nod_yes",
                "completed=true and skill_id=nod_yes",
            )
        )
        if expected_mode == "hardware_shadow":
            checks.append(
                ConformanceCheck(
                    "shadow no-motion proof",
                    executed.output.get("no_motion") is True
                    and executed.output.get("recommendation_only") is True,
                    "hardware_shadow is no-motion and recommendation-only",
                )
            )
        if expected_mode == "hardware_dry_run":
            checks.append(
                ConformanceCheck(
                    "dry-run no-motion proof",
                    executed.output.get("no_motion") is True,
                    "hardware_dry_run declares no_motion=true",
                )
            )

    cancelled = await traced.invoke(
        "soridormi.motion.cancel",
        {},
        context=ToolInvocationContext(allow_safety_controls=True),
    )
    if record_outcome(checks, "cancel call", cancelled):
        record_abstraction(checks, "cancel abstraction", cancelled.output)
        checks.append(
            ConformanceCheck(
                "idempotent cancellation",
                cancelled.output.get("cancelled") is True,
                "cancelled=true",
            )
        )
    status = await traced.invoke("soridormi.robot.get_status", {})
    if record_outcome(checks, "status call", status):
        record_abstraction(checks, "status abstraction", status.output)
        checks.append(
            ConformanceCheck(
                "safe idle",
                status.output.get("mode") == expected_mode
                and status.output.get("active_task") is None
                and status.output.get("emergency_stop") is False,
                "provider mode matches and status is explicitly safe idle",
            )
        )
    return report(
        expected_mode,
        checks,
        traced.entries,
        evidence_source=evidence_source,
    )


async def run_profiles(profiles: Sequence[str]) -> dict[str, Any]:
    reports = [
        await run_conformance(NoMotionProviderStub(profile), expected_mode=profile)
        for profile in profiles
    ]
    parity = compare_profiles(reports)
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "trace_version": TRACE_VERSION,
        "passed": all(item["passed"] for item in reports) and parity["passed"],
        "profile_parity": parity,
        "profiles": reports,
    }


async def run_live(manifest: Path, expected_mode: str) -> dict[str, Any]:
    if not os.environ.get("SORIDORMI_MCP_URL"):
        raise ValueError("SORIDORMI_MCP_URL is required for --live")
    conformance = await run_conformance(
        build_soridormi_invoker(manifest_path=manifest),
        expected_mode=expected_mode,
        evidence_source="live",
    )
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "trace_version": TRACE_VERSION,
        "passed": conformance["passed"],
        "profiles": [conformance],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("all", "sim", "hardware_shadow", "hardware_dry_run"),
        default="all",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--compare",
        nargs="+",
        type=Path,
        help="Compare retained conformance JSON files without provider calls.",
    )
    parser.add_argument("--manifest", default="capabilities/soridormi.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.compare and args.live:
        parser.error("--compare cannot be combined with --live")
    if args.compare and args.profile != "all":
        parser.error("--compare cannot be combined with --profile")
    if args.live and args.profile == "all":
        parser.error("--live requires one explicit safe --profile")
    profiles = (
        ["sim", "hardware_shadow", "hardware_dry_run"]
        if args.profile == "all"
        else [args.profile]
    )
    try:
        if args.compare:
            payload = compare_evidence(args.compare)
        else:
            payload = (
                asyncio.run(run_live(Path(args.manifest), profiles[0]))
                if args.live
                else asyncio.run(run_profiles(profiles))
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
