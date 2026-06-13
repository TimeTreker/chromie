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

CONFORMANCE_VERSION = "1.0"
SAFE_MODES = {"sim", "hardware_dry_run"}


@dataclass(frozen=True)
class ConformanceCheck:
    name: str
    passed: bool
    detail: str


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
                    "no_motion": self.mode == "hardware_dry_run",
                }
            )
        if tool_name == "soridormi.motion.cancel":
            if not context or not context.allow_safety_controls:
                return ToolCallOutcome.failed("missing safety-control authorization")
            return ToolCallOutcome.success({"cancelled": True})
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


def report(mode: str, checks: Sequence[ConformanceCheck]) -> dict[str, Any]:
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "mode": mode,
        "passed": all(check.passed for check in checks),
        "check_count": len(checks),
        "checks": [asdict(check) for check in checks],
    }


def compare_profiles(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) < 2:
        return {
            "passed": True,
            "compared_modes": [report["mode"] for report in reports],
            "mismatches": [],
        }
    ignored_checks = {"safe provider mode", "no-motion proof"}
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
    return {
        "passed": not mismatches,
        "compared_modes": [report["mode"] for report in reports],
        "ignored_profile_specific_checks": sorted(ignored_checks),
        "mismatches": mismatches,
    }


async def run_conformance(
    invoker: AsyncToolInvoker,
    *,
    expected_mode: str,
) -> dict[str, Any]:
    if expected_mode not in SAFE_MODES:
        raise ValueError(
            "Provider conformance execution is restricted to sim or "
            "hardware_dry_run"
        )
    checks: list[ConformanceCheck] = []
    catalog = await invoker.invoke("soridormi.skill.list", {})
    if not record_outcome(checks, "catalog call", catalog):
        return report(expected_mode, checks)
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
        return report(expected_mode, checks)

    planned = await invoker.invoke(
        "soridormi.skill.create_plan",
        {"skill_id": "nod_yes", "parameters": {"count": 2}},
    )
    if not record_outcome(checks, "plan call", planned):
        return report(expected_mode, checks)
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
        return report(expected_mode, checks)

    monitored = await invoker.invoke(
        "soridormi.safety.monitor_motion",
        {"during_node_id": "conformance-request"},
        context=ToolInvocationContext(allow_safety_controls=True),
    )
    if not record_outcome(checks, "monitor call", monitored):
        return report(expected_mode, checks)
    record_abstraction(checks, "monitor abstraction", monitored.output)
    checks.append(
        ConformanceCheck(
            "monitor ready",
            monitored.output.get("ok") is True,
            "safety monitor explicitly returned ok=true",
        )
    )

    executed = await invoker.invoke(
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
        if expected_mode == "hardware_dry_run":
            checks.append(
                ConformanceCheck(
                    "no-motion proof",
                    executed.output.get("no_motion") is True,
                    "hardware_dry_run execution declares no_motion=true",
                )
            )

    cancelled = await invoker.invoke(
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
    return report(expected_mode, checks)


async def run_profiles(profiles: Sequence[str]) -> dict[str, Any]:
    reports = [
        await run_conformance(NoMotionProviderStub(profile), expected_mode=profile)
        for profile in profiles
    ]
    parity = compare_profiles(reports)
    return {
        "conformance_version": CONFORMANCE_VERSION,
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
    )
    return {
        "conformance_version": CONFORMANCE_VERSION,
        "passed": conformance["passed"],
        "profiles": [conformance],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("all", "sim", "hardware_dry_run"),
        default="all",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--manifest", default="capabilities/soridormi.json")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.live and args.profile == "all":
        parser.error("--live requires one explicit safe --profile")
    profiles = (
        ["sim", "hardware_dry_run"]
        if args.profile == "all"
        else [args.profile]
    )
    try:
        payload = (
            asyncio.run(run_live(Path(args.manifest), profiles[0]))
            if args.live
            else asyncio.run(run_profiles(profiles))
        )
    except ValueError as exc:
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
