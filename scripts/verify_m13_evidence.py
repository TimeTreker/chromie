#!/usr/bin/env python3
"""Verify the structure and pass state of an M13 acceptance evidence bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REQUIRED_CASES = {
    "speech-only",
    "speech-skill",
    "refusal",
    "barge-in",
    "body-cancel",
    "stop",
    "follow-up",
}
REQUIRED_FILES = {
    "metadata.json",
    "cases.json",
    "summary.md",
    "events.jsonl",
    "orchestrator.log",
    "runtime.env.redacted",
    "audio-devices.log",
    "acceptance-overrides.env",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_bundle(
    evidence_dir: Path,
    *,
    require_clean: bool = False,
    allow_automated: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not evidence_dir.is_dir():
        return {
            "passed": False,
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
    cases: list[dict[str, Any]] = []
    try:
        metadata = load_json(evidence_dir / "metadata.json")
    except Exception as exc:
        errors.append(f"metadata.json is invalid: {exc}")
    try:
        loaded_cases = load_json(evidence_dir / "cases.json")
        if isinstance(loaded_cases, list):
            cases = [item for item in loaded_cases if isinstance(item, dict)]
        else:
            errors.append("cases.json must contain a list")
    except Exception as exc:
        errors.append(f"cases.json is invalid: {exc}")

    if metadata.get("status") != "passed":
        errors.append(f"Acceptance status is not passed: {metadata.get('status')!r}")
    runner = metadata.get("runner") or {}
    mode = str(runner.get("mode") or "supervised")
    if mode not in {"synthetic", "virtual-mic", "supervised"}:
        errors.append(f"Unknown acceptance mode: {mode!r}")
    if mode != "supervised" and not allow_automated:
        errors.append(
            f"Acceptance mode {mode!r} is automated evidence and cannot close M13; "
            "run --mode supervised for release-closing evidence"
        )
    if runner.get("dry_run"):
        errors.append("Dry-run evidence cannot close M13")
    if int(metadata.get("event_count") or 0) <= 0:
        errors.append("metadata.json reports no structured session events")

    chromie = metadata.get("chromie") or {}
    if not chromie.get("revision") or chromie.get("revision") == "unknown":
        errors.append("Chromie revision is missing")
    if chromie.get("dirty"):
        message = "Chromie worktree was dirty during acceptance"
        if require_clean:
            errors.append(message)
        else:
            warnings.append(message)

    manifest = metadata.get("soridormi_manifest") or {}
    if not manifest.get("upstream_commit"):
        errors.append("Pinned Soridormi upstream revision is missing")
    if metadata.get("soridormi_mcp_url") in {None, "", "not-configured"}:
        errors.append("Soridormi MCP endpoint is missing from metadata")

    by_id = {
        str(item.get("case_id")): item
        for item in cases
        if item.get("case_id")
    }
    missing_cases = sorted(REQUIRED_CASES - set(by_id))
    extra_cases = sorted(set(by_id) - REQUIRED_CASES)
    if missing_cases:
        errors.append("Missing required cases: " + ", ".join(missing_cases))
    if extra_cases:
        warnings.append("Additional cases present: " + ", ".join(extra_cases))

    for case_id in sorted(REQUIRED_CASES & set(by_id)):
        item = by_id[case_id]
        verdict = item.get("operator_verdict")
        expected_verdicts = {"pass"} if mode == "supervised" else {"automated"}
        if verdict not in expected_verdicts:
            errors.append(
                f"Case {case_id} verdict is {verdict!r}; expected one of "
                f"{sorted(expected_verdicts)} for mode {mode!r}"
            )
        checks = item.get("checks")
        if not isinstance(checks, list) or not checks:
            errors.append(f"Case {case_id} has no automated checks")
        else:
            failed = [
                str(check.get("name") or "unnamed")
                for check in checks
                if not isinstance(check, dict) or not check.get("passed")
            ]
            if failed:
                errors.append(
                    f"Case {case_id} has failed checks: " + ", ".join(failed)
                )
        if int(item.get("event_count") or 0) <= 0:
            errors.append(f"Case {case_id} has no correlated events")
        if not item.get("session_ids"):
            errors.append(f"Case {case_id} has no correlated session IDs")

    override_text = ""
    try:
        override_text = (evidence_dir / "acceptance-overrides.env").read_text(
            encoding="utf-8"
        )
    except Exception:
        pass
    required_overrides = {
        "ORCH_ENABLE_INTERACTION_RESPONSE=1",
        "ORCH_ENABLE_SORIDORMI_SKILLS=1",
        "AGENT_INTERACTION_OUTPUT_MODE=native",
        "AGENT_NATIVE_INTERACTION_FALLBACK=0",
    }
    if mode == "synthetic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE=stdin",
                "ORCH_AUDIO_OUTPUT_MODE=discard",
            }
        )
    elif mode == "virtual-mic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE=device",
                "ORCH_AUDIO_OUTPUT_MODE=discard",
                "PULSE_SOURCE=",
            }
        )
    else:
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE=device",
                "ORCH_AUDIO_OUTPUT_MODE=device",
            }
        )
    for value in sorted(required_overrides):
        if value not in override_text:
            errors.append(f"Acceptance override is missing: {value}")

    if mode in {"synthetic", "virtual-mic"}:
        generated_dir = evidence_dir / "generated-input"
        manifest_path = generated_dir / "manifest.json"
        if not manifest_path.is_file():
            errors.append("Automated evidence is missing generated-input/manifest.json")
        if not any(generated_dir.glob("*.wav")):
            errors.append("Automated evidence contains no generated input WAV files")

    return {
        "schema_version": 1,
        "evidence_dir": str(evidence_dir),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "acceptance_id": metadata.get("acceptance_id"),
        "chromie_revision": chromie.get("revision"),
        "chromie_version": chromie.get("version"),
        "soridormi_revision": manifest.get("upstream_commit"),
        "case_count": len(by_id),
        "mode": mode,
        "release_eligible": mode == "supervised" and not errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument(
        "--allow-automated",
        action="store_true",
        help="Validate synthetic/virtual-mic evidence without treating it as M13-closing.",
    )
    parser.add_argument("--write-report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_bundle(
        args.evidence_dir,
        require_clean=args.require_clean,
        allow_automated=args.allow_automated,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
