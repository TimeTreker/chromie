#!/usr/bin/env python3
"""Preflight Soridormi capabilities and verify provider-readiness evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.provider_conformance import (  # noqa: E402
    CONFORMANCE_VERSION,
    SAFE_MODES,
    TRACE_VERSION,
)
from scripts.provider_fault_matrix import MATRIX_VERSION, SCENARIOS  # noqa: E402

REQUIRED_FILES = {
    "metadata.json",
    "provider-sim.json",
    "provider-shadow.json",
    "provider-dry-run.json",
    "provider-parity.json",
    "fault-matrix.json",
    "operator-notes.md",
}
PROFILE_FILES = {
    "sim": "provider-sim.json",
    "hardware_shadow": "provider-shadow.json",
    "hardware_dry_run": "provider-dry-run.json",
}
REQUIRED_PROVIDER_TOOLS = {
    "soridormi.skill.list",
    "soridormi.skill.create_plan",
    "soridormi.safety.monitor_motion",
    "soridormi.skill.execute_plan",
    "soridormi.motion.cancel",
    "soridormi.robot.get_status",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_preflight(manifest_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        return {
            "passed": False,
            "manifest": str(manifest_path),
            "errors": [f"Manifest is invalid: {exc}"],
            "warnings": [],
        }

    tools: dict[str, dict[str, Any]] = {}
    for agent in manifest.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        for tool in agent.get("tools") or []:
            if isinstance(tool, dict) and tool.get("name"):
                tools[str(tool["name"])] = tool

    for name in sorted(REQUIRED_PROVIDER_TOOLS):
        tool = tools.get(name)
        if tool is None:
            errors.append(f"Missing required provider tool: {name}")
            continue
        modes = set((tool.get("availability") or {}).get("modes") or [])
        missing_modes = sorted(SAFE_MODES - modes)
        if missing_modes:
            errors.append(
                f"Tool {name} is missing safe modes: {', '.join(missing_modes)}"
            )

    readiness = (manifest.get("metadata") or {}).get("provider_readiness")
    if not isinstance(readiness, dict):
        errors.append("Manifest metadata.provider_readiness is missing")
    else:
        fault_injection = readiness.get("fault_injection")
        if not isinstance(fault_injection, dict):
            errors.append(
                "Manifest metadata.provider_readiness.fault_injection is missing"
            )
        else:
            configure_tool = fault_injection.get("configure_tool")
            clear_tool = fault_injection.get("clear_tool")
            for role, name in (
                ("configure_tool", configure_tool),
                ("clear_tool", clear_tool),
            ):
                if not isinstance(name, str) or not name:
                    errors.append(f"Fault injection {role} is missing")
                elif name not in tools:
                    errors.append(
                        f"Fault injection {role} references unknown tool: {name}"
                    )
                elif tools[name].get("llm_visible") is not False:
                    errors.append(
                        f"Fault injection tool {name} must be llm_visible=false"
                    )
            supported = set(fault_injection.get("supported_scenarios") or [])
            required = {scenario.scenario_id for scenario in SCENARIOS}
            missing = sorted(required - supported)
            if missing:
                errors.append(
                    "Fault injection scenarios are missing: " + ", ".join(missing)
                )

    metadata = manifest.get("metadata") or {}
    if not metadata.get("upstream_commit"):
        errors.append("Manifest upstream_commit is missing")
    if manifest.get("schema_version") != "0.1":
        warnings.append(
            f"Unexpected manifest schema version: {manifest.get('schema_version')!r}"
        )
    return {
        "schema_version": 1,
        "passed": not errors,
        "manifest": str(manifest_path),
        "upstream_commit": metadata.get("upstream_commit"),
        "safe_modes": sorted(SAFE_MODES),
        "required_scenario_count": len(SCENARIOS),
        "errors": errors,
        "warnings": warnings,
    }


def _verify_profile(
    payload: dict[str, Any],
    expected_mode: str,
    errors: list[str],
) -> None:
    label = PROFILE_FILES[expected_mode]
    if payload.get("conformance_version") != CONFORMANCE_VERSION:
        errors.append(f"{label} has wrong conformance version")
    if payload.get("trace_version") != TRACE_VERSION:
        errors.append(f"{label} has wrong trace version")
    if payload.get("passed") is not True:
        errors.append(f"{label} did not pass")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or len(profiles) != 1:
        errors.append(f"{label} must contain exactly one profile")
        return
    profile = profiles[0]
    if not isinstance(profile, dict) or profile.get("mode") != expected_mode:
        errors.append(f"{label} does not contain mode {expected_mode}")
        return
    if profile.get("evidence_source") != "live":
        errors.append(f"{label} is not live provider evidence")
    if profile.get("passed") is not True:
        errors.append(f"{label} profile did not pass")


def verify_bundle(
    evidence_dir: Path,
    *,
    require_clean: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not evidence_dir.is_dir():
        return {
            "passed": False,
            "evidence_dir": str(evidence_dir),
            "errors": [f"Evidence directory not found: {evidence_dir}"],
            "warnings": [],
        }
    for name in sorted(REQUIRED_FILES):
        path = evidence_dir / name
        if not path.is_file():
            errors.append(f"Missing required evidence file: {name}")
        elif path.stat().st_size == 0:
            errors.append(f"Required evidence file is empty: {name}")

    metadata: dict[str, Any] = {}
    try:
        metadata = load_json(evidence_dir / "metadata.json")
    except Exception as exc:
        errors.append(f"metadata.json is invalid: {exc}")
    if metadata.get("status") != "passed":
        errors.append(f"Evidence status is not passed: {metadata.get('status')!r}")
    chromie = metadata.get("chromie") or {}
    soridormi = metadata.get("soridormi") or {}
    for label, value in (
        ("Chromie revision", chromie.get("revision")),
        ("Soridormi revision", soridormi.get("revision")),
        ("Soridormi endpoint", metadata.get("soridormi_mcp_url")),
        ("target name", metadata.get("target_name")),
    ):
        if value in {None, "", "unknown", "not-configured"}:
            errors.append(f"{label} is missing")
    if chromie.get("dirty"):
        message = "Chromie worktree was dirty during provider readiness"
        (errors if require_clean else warnings).append(message)
    if soridormi.get("dirty"):
        message = "Soridormi worktree was dirty during provider readiness"
        (errors if require_clean else warnings).append(message)

    profile_payloads: dict[str, dict[str, Any]] = {}
    for mode, filename in PROFILE_FILES.items():
        try:
            payload = load_json(evidence_dir / filename)
            if not isinstance(payload, dict):
                raise ValueError("root must be an object")
            profile_payloads[mode] = payload
            _verify_profile(payload, mode, errors)
        except Exception as exc:
            errors.append(f"{filename} is invalid: {exc}")

    try:
        parity = load_json(evidence_dir / "provider-parity.json")
        if parity.get("passed") is not True:
            errors.append("provider-parity.json did not pass")
        compared = set((parity.get("profile_parity") or {}).get("compared_modes") or [])
        if compared != SAFE_MODES:
            errors.append("provider-parity.json does not compare all safe modes")
        if (parity.get("profile_parity") or {}).get("mismatches"):
            errors.append("provider-parity.json contains profile mismatches")
    except Exception as exc:
        errors.append(f"provider-parity.json is invalid: {exc}")

    try:
        matrix = load_json(evidence_dir / "fault-matrix.json")
        if matrix.get("matrix_version") != MATRIX_VERSION:
            errors.append("fault-matrix.json has wrong matrix version")
        if matrix.get("evidence_source") != "live":
            errors.append("fault-matrix.json is not live fault-injection evidence")
        if matrix.get("passed") is not True:
            errors.append("fault-matrix.json did not pass")
        results = matrix.get("results")
        if not isinstance(results, list):
            errors.append("fault-matrix.json has no result list")
        else:
            by_id = {
                str(item.get("scenario_id")): item
                for item in results
                if isinstance(item, dict) and item.get("scenario_id")
            }
            required_ids = {scenario.scenario_id for scenario in SCENARIOS}
            missing = sorted(required_ids - set(by_id))
            if missing:
                errors.append("Fault scenarios are missing: " + ", ".join(missing))
            for scenario_id in sorted(required_ids & set(by_id)):
                item = by_id[scenario_id]
                if item.get("passed") is not True:
                    errors.append(f"Fault scenario {scenario_id} did not pass")
                if item.get("safe_idle") is not True:
                    errors.append(f"Fault scenario {scenario_id} is not safe idle")
                if item.get("threshold_violations"):
                    errors.append(
                        f"Fault scenario {scenario_id} exceeded thresholds"
                    )
    except Exception as exc:
        errors.append(f"fault-matrix.json is invalid: {exc}")

    notes = evidence_dir / "operator-notes.md"
    if notes.is_file():
        text = notes.read_text(encoding="utf-8").strip()
        if len(text) < 20:
            errors.append("operator-notes.md is too short for review evidence")

    return {
        "schema_version": 1,
        "passed": not errors,
        "evidence_dir": str(evidence_dir),
        "errors": errors,
        "warnings": warnings,
        "target_name": metadata.get("target_name"),
        "chromie_revision": chromie.get("revision"),
        "soridormi_revision": soridormi.get("revision"),
        "profile_count": len(profile_payloads),
        "required_scenario_count": len(SCENARIOS),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument(
        "--manifest",
        type=Path,
        default=Path("capabilities/soridormi.json"),
    )
    verify = subparsers.add_parser("verify")
    verify.add_argument("evidence_dir", type=Path)
    verify.add_argument("--require-clean", action="store_true")
    verify.add_argument("--write-report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight":
        report = manifest_preflight(args.manifest)
    else:
        report = verify_bundle(
            args.evidence_dir,
            require_clean=args.require_clean,
        )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if getattr(args, "write_report", None):
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
