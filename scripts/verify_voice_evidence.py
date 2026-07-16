#!/usr/bin/env python3
"""Verify the structure and pass state of a voice acceptance evidence bundle."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    "cognitive-runtime.jsonl",
    "orchestrator.log",
    "runtime.env.redacted",
    "audio-devices.log",
    "acceptance-overrides.env",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_revision(root: Path = ROOT) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _version(root: Path = ROOT) -> str | None:
    path = root / "VERSION"
    if not path.is_file():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _soridormi_revisions(root: Path = ROOT) -> tuple[str | None, str | None]:
    manifest_revision: str | None = None
    compatibility_revision: str | None = None
    try:
        manifest = load_json(root / "capabilities" / "soridormi.json")
        metadata = manifest.get("metadata") if isinstance(manifest, dict) else None
        if isinstance(metadata, dict) and metadata.get("upstream_commit"):
            manifest_revision = str(metadata["upstream_commit"]).strip() or None
    except Exception:
        pass
    try:
        compatibility = load_json(root / "release" / "compatibility.json")
        soridormi = (
            compatibility.get("soridormi")
            if isinstance(compatibility, dict)
            else None
        )
        if isinstance(soridormi, dict) and soridormi.get("upstream_commit"):
            compatibility_revision = str(soridormi["upstream_commit"]).strip() or None
    except Exception:
        pass
    return manifest_revision, compatibility_revision


def verify_bundle(
    evidence_dir: Path,
    *,
    require_clean: bool = False,
    allow_automated: bool = False,
    expected_chromie_revision: str | None = None,
    expected_chromie_version: str | None = None,
    expected_soridormi_revision: str | None = None,
    source_root: Path = ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    provenance_errors: list[str] = []

    def provenance_error(message: str) -> None:
        errors.append(message)
        provenance_errors.append(message)

    def positive_event_count(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def nonempty_string_list(value: Any) -> list[str] | None:
        if not isinstance(value, list) or not value:
            return None
        if any(not isinstance(item, str) or not item.strip() for item in value):
            return None
        return [item.strip() for item in value]

    if expected_chromie_revision is None:
        expected_chromie_revision = _git_revision(source_root)
        if not expected_chromie_revision:
            provenance_error("Cannot determine the expected Chromie source revision")
    if expected_chromie_version is None:
        expected_chromie_version = _version(source_root)
        if not expected_chromie_version:
            provenance_error("Cannot determine the expected Chromie VERSION")
    if expected_soridormi_revision is None:
        manifest_revision, compatibility_revision = _soridormi_revisions(source_root)
        if not manifest_revision:
            provenance_error(
                "Cannot determine the Soridormi revision from the capability manifest"
            )
        if not compatibility_revision:
            provenance_error(
                "Cannot determine the Soridormi revision from release compatibility"
            )
        if (
            manifest_revision
            and compatibility_revision
            and manifest_revision != compatibility_revision
        ):
            provenance_error(
                "Soridormi source provenance is inconsistent: capability manifest "
                f"{manifest_revision!r} != release compatibility "
                f"{compatibility_revision!r}"
            )
        expected_soridormi_revision = manifest_revision or compatibility_revision

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
        loaded_metadata = load_json(evidence_dir / "metadata.json")
        if isinstance(loaded_metadata, dict):
            metadata = loaded_metadata
        else:
            errors.append("metadata.json must contain an object")
    except Exception as exc:
        errors.append(f"metadata.json is invalid: {exc}")
    try:
        loaded_cases = load_json(evidence_dir / "cases.json")
        if isinstance(loaded_cases, list):
            cases = [item for item in loaded_cases if isinstance(item, dict)]
            invalid_case_count = len(loaded_cases) - len(cases)
            if invalid_case_count:
                errors.append(
                    f"cases.json contains {invalid_case_count} non-object case entries"
                )
        else:
            errors.append("cases.json must contain a list")
    except Exception as exc:
        errors.append(f"cases.json is invalid: {exc}")

    if metadata.get("schema_version") != 2:
        provenance_error(
            "metadata.json must declare voice acceptance schema_version=2"
        )
    if metadata.get("status") != "passed":
        errors.append(f"Acceptance status is not passed: {metadata.get('status')!r}")
    runner = metadata.get("runner")
    if not isinstance(runner, dict):
        errors.append("metadata.json runner must be an object")
        runner = {}
    raw_mode = runner.get("mode")
    mode = str(raw_mode) if isinstance(raw_mode, str) and raw_mode else "unknown"
    if mode not in {"synthetic", "virtual-mic", "acoustic", "supervised"}:
        errors.append(f"Unknown acceptance mode: {mode!r}")
    if mode != "supervised" and not allow_automated:
        errors.append(
            f"Acceptance mode {mode!r} is automated evidence and cannot close a "
            "human-supervised voice-device release gate; run --mode supervised "
            "for human release-closing evidence or narrow the release claim"
        )
    if runner.get("dry_run") is not False:
        errors.append("Dry-run evidence cannot close a release gate")
    if not positive_event_count(metadata.get("event_count")):
        errors.append("metadata.json reports no structured session events")
    selected_cases = metadata.get("selected_cases")
    normalized_selected_cases = nonempty_string_list(selected_cases)
    if (
        normalized_selected_cases is None
        or len(normalized_selected_cases) != len(REQUIRED_CASES)
        or set(normalized_selected_cases) != REQUIRED_CASES
    ):
        errors.append(
            "metadata.json selected_cases must explicitly contain the full required matrix"
        )

    chromie_value = metadata.get("chromie")
    if isinstance(chromie_value, dict):
        chromie = chromie_value
    else:
        chromie = {}
        provenance_error("metadata.json chromie must be an object")
    if not chromie.get("revision") or chromie.get("revision") == "unknown":
        provenance_error("Chromie revision is missing")
    elif (
        expected_chromie_revision
        and str(chromie.get("revision")) != expected_chromie_revision
    ):
        provenance_error(
            f"Evidence Chromie revision {chromie.get('revision')!r} does not match "
            f"expected source revision {expected_chromie_revision!r}"
        )
    if not chromie.get("version"):
        provenance_error("Chromie version is missing")
    elif (
        expected_chromie_version
        and str(chromie.get("version")) != expected_chromie_version
    ):
        provenance_error(
            f"Evidence Chromie version {chromie.get('version')!r} does not match "
            f"expected VERSION {expected_chromie_version!r}"
        )
    chromie_dirty = chromie.get("dirty")
    if require_clean and chromie_dirty is not False:
        provenance_error(
            "Evidence does not explicitly record a clean Chromie worktree"
        )
    elif chromie_dirty is True:
        warnings.append("Chromie worktree was dirty during acceptance")

    manifest_value = metadata.get("soridormi_manifest")
    if isinstance(manifest_value, dict):
        manifest = manifest_value
    else:
        manifest = {}
        provenance_error("metadata.json soridormi_manifest must be an object")
    if not manifest.get("upstream_commit"):
        provenance_error("Pinned Soridormi upstream revision is missing")
    elif (
        expected_soridormi_revision
        and str(manifest.get("upstream_commit")) != expected_soridormi_revision
    ):
        provenance_error(
            "Evidence Soridormi manifest revision "
            f"{manifest.get('upstream_commit')!r} does not match expected revision "
            f"{expected_soridormi_revision!r}"
        )
    local_revision = metadata.get("soridormi_local_revision")
    if expected_soridormi_revision:
        if local_revision in {None, "", "not-provided", "unknown"}:
            provenance_error(
                "Evidence does not identify the declared paired Soridormi checkout revision"
            )
        elif str(local_revision) != expected_soridormi_revision:
            provenance_error(
                f"Evidence Soridormi checkout revision {local_revision!r} does not match "
                f"expected revision {expected_soridormi_revision!r}"
            )
    if metadata.get("soridormi_local_dirty") is not False:
        provenance_error(
            "Evidence does not record a clean declared paired Soridormi checkout"
        )
    source_binding = metadata.get("soridormi_source_binding")
    endpoint_revision = (
        source_binding.get("endpoint_revision")
        if isinstance(source_binding, dict)
        else None
    )
    endpoint_source_bound = bool(
        isinstance(source_binding, dict)
        and source_binding.get("kind") == "endpoint_reported_revision"
        and expected_soridormi_revision
        and endpoint_revision == expected_soridormi_revision
    )
    if not endpoint_source_bound:
        warnings.append(
            "Soridormi checkout provenance is declared but not bound to an "
            "endpoint-reported source revision; this bundle cannot enter release policy"
        )
    soridormi_mcp_url = metadata.get("soridormi_mcp_url")
    if (
        not isinstance(soridormi_mcp_url, str)
        or not soridormi_mcp_url.strip()
        or soridormi_mcp_url == "not-configured"
    ):
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
            failed: list[str] = []
            for check_index, check in enumerate(checks):
                if not isinstance(check, dict):
                    failed.append(f"invalid-check-{check_index}")
                elif check.get("passed") is not True:
                    failed.append(str(check.get("name") or "unnamed"))
            if failed:
                errors.append(
                    f"Case {case_id} has failed checks: " + ", ".join(failed)
                )
        if not positive_event_count(item.get("event_count")):
            errors.append(f"Case {case_id} has no correlated events")
        if nonempty_string_list(item.get("session_ids")) is None:
            errors.append(f"Case {case_id} has no correlated session IDs")

    override_text = ""
    try:
        override_text = (evidence_dir / "acceptance-overrides.env").read_text(
            encoding="utf-8"
        )
    except Exception:
        pass
    override_values: dict[str, str] = {}
    try:
        for line_number, raw_line in enumerate(override_text.splitlines(), 1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            tokens = shlex.split(stripped, comments=True, posix=True)
            if len(tokens) != 1 or "=" not in tokens[0]:
                raise ValueError(f"line {line_number} is not one exact assignment")
            key, value = tokens[0].split("=", 1)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(f"line {line_number} has invalid key {key!r}")
            if key in override_values:
                raise ValueError(f"line {line_number} duplicates {key}")
            override_values[key] = value
    except ValueError as exc:
        provenance_error(f"acceptance-overrides.env is invalid: {exc}")

    required_overrides = {
        "ORCH_ENABLE_INTERACTION_RESPONSE": "1",
        "ORCH_ENABLE_SORIDORMI_SKILLS": "1",
        "AGENT_INTERACTION_OUTPUT_MODE": "native",
        "AGENT_NATIVE_INTERACTION_FALLBACK": "0",
    }
    required_semantic_overrides = {
        "ORCH_COGNITIVE_RUNTIME_MODE": "apply",
        "ORCH_COGNITIVE_APPLY_LANES": "chat,robot_action",
        "ORCH_COGNITIVE_FALLBACK_POLICY": "fail_closed",
        "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED": "0",
        "ORCH_COGNITIVE_EVIDENCE_ENABLED": "1",
    }
    if mode == "synthetic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "stdin",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
            }
        )
    elif mode == "virtual-mic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "discard",
            }
        )
    elif mode == "acoustic":
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
            }
        )
    else:
        required_overrides.update(
            {
                "ORCH_AUDIO_INPUT_MODE": "device",
                "ORCH_AUDIO_OUTPUT_MODE": "device",
            }
        )
    for key, expected in sorted(required_overrides.items()):
        if override_values.get(key) != expected:
            errors.append(f"Acceptance override must set {key}={expected}")
    for key, expected in sorted(required_semantic_overrides.items()):
        if override_values.get(key) != expected:
            provenance_error(f"Acceptance override must set {key}={expected}")
    if mode == "virtual-mic" and not override_values.get("PULSE_SOURCE"):
        errors.append("Acceptance override must set a non-empty PULSE_SOURCE")
    if mode == "acoustic" and override_values.get("ORCH_AUDIO_OUTPUT_MODE") not in {
        "discard",
        "device",
    }:
        errors.append(
            "Acceptance override is missing acoustic output mode: "
            "ORCH_AUDIO_OUTPUT_MODE=discard or ORCH_AUDIO_OUTPUT_MODE=device"
        )

    if mode in {"synthetic", "virtual-mic", "acoustic"}:
        generated_dir = evidence_dir / "generated-input"
        manifest_path = generated_dir / "manifest.json"
        if not manifest_path.is_file():
            errors.append("Automated evidence is missing generated-input/manifest.json")
        if not any(generated_dir.glob("*.wav")):
            errors.append("Automated evidence contains no generated input WAV files")

    cognitive_events: list[dict[str, Any]] = []
    cognitive_path = evidence_dir / "cognitive-runtime.jsonl"
    if cognitive_path.is_file():
        try:
            for line_number, raw_line in enumerate(
                cognitive_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line)
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number} is not a JSON object")
                cognitive_events.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            provenance_error(f"cognitive-runtime.jsonl is invalid: {exc}")

    acceptance_session_ids = {
        str(session_id)
        for item in by_id.values()
        for session_id in (
            item.get("session_ids")
            if isinstance(item.get("session_ids"), list)
            else []
        )
        if session_id
    }
    runtime_events: list[dict[str, Any]] = []
    runtime_path = evidence_dir / "events.jsonl"
    if runtime_path.is_file():
        try:
            for line_number, raw_line in enumerate(
                runtime_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line)
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number} is not a JSON object")
                runtime_events.append(item)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            provenance_error(f"events.jsonl is invalid: {exc}")

    from scripts.voice_acceptance import analyze_case

    expected_lane_by_case = {
        "speech-only": "chat",
        "speech-skill": "robot_action",
        "refusal": "robot_action",
        "barge-in": "chat",
        "body-cancel": "robot_action",
        "stop": "chat",
        "follow-up": "chat",
    }
    for case_id in sorted(REQUIRED_CASES & set(by_id)):
        raw_case_session_ids = by_id[case_id].get("session_ids")
        case_session_ids = {
            str(value)
            for value in (
                raw_case_session_ids
                if isinstance(raw_case_session_ids, list)
                else []
            )
            if value
        }
        case_runtime_events = [
            item
            for item in runtime_events
            if str(item.get("sid") or "") in case_session_ids
        ]
        if not case_runtime_events:
            errors.append(f"Case {case_id} has no raw correlated runtime events")
            continue
        recomputed = analyze_case(case_id, case_runtime_events)
        recomputed_failures = [item.name for item in recomputed if not item.passed]
        if recomputed_failures:
            errors.append(
                f"Case {case_id} fails recomputed raw-event checks: "
                + ", ".join(recomputed_failures)
            )

        expected_lane = expected_lane_by_case[case_id]
        case_cognitive_events = [
            item
            for item in cognitive_events
            if str(item.get("sid") or "") in case_session_ids
        ]
        applied = [
            item
            for item in case_cognitive_events
            if item.get("mode") == "apply"
            and item.get("status") == "applied"
            and item.get("lane") == expected_lane
        ]
        minimum_applied = 2 if case_id == "follow-up" else 1
        if len(applied) < minimum_applied:
            provenance_error(
                f"Case {case_id} has {len(applied)} correlated applied "
                f"{expected_lane!r} cognitive events; expected at least {minimum_applied}"
            )
        if any(item.get("status") == "error" for item in case_cognitive_events):
            provenance_error(
                f"Case {case_id} contains a correlated cognitive runtime error"
            )

        if case_id in {"speech-skill", "body-cancel"}:
            case_provider_modes = {
                match.group(1)
                for item in case_runtime_events
                if item.get("event") == "skill_runtime_done"
                for match in [
                    re.search(
                        r"(?:^|\s)provider_mode=([^\s]+)",
                        str(item.get("message") or ""),
                    )
                ]
                if match is not None and match.group(1) != "not-used"
            }
            cancelled_sim_status = bool(
                case_id == "body-cancel"
                and any(
                    item.get("event") == "soridormi_post_status"
                    and "mode=sim" in str(item.get("message") or "")
                    and "backend=runtime" in str(item.get("message") or "")
                    for item in case_runtime_events
                )
            )
            if case_provider_modes != {"sim"} and not cancelled_sim_status:
                provenance_error(
                    f"Case {case_id} does not prove exclusive simulator provider "
                    f"execution: {sorted(case_provider_modes)!r}"
                )
    provider_modes = {
        match.group(1)
        for item in runtime_events
        if str(item.get("sid") or "") in acceptance_session_ids
        and item.get("event") == "skill_runtime_done"
        for match in [
            re.search(
                r"(?:^|\s)provider_mode=([^\s]+)",
                str(item.get("message") or ""),
            )
        ]
        if match is not None and match.group(1) != "not-used"
    }
    if provider_modes != {"sim"}:
        provenance_error(
            "Voice evidence does not prove exclusive Soridormi simulator execution; "
            f"observed provider modes: {sorted(provider_modes)!r}"
        )
    correlated_cognitive_events = [
        item
        for item in cognitive_events
        if str(item.get("sid") or "") in acceptance_session_ids
    ]
    applied_lanes = {
        str(item.get("lane") or "")
        for item in correlated_cognitive_events
        if item.get("mode") == "apply" and item.get("status") == "applied"
    }
    missing_applied_lanes = sorted({"chat", "robot_action"} - applied_lanes)
    if missing_applied_lanes:
        provenance_error(
            "Voice evidence is missing correlated applied cognitive runtime lanes: "
            + ", ".join(missing_applied_lanes)
        )
    cognitive_errors = [
        item
        for item in correlated_cognitive_events
        if item.get("status") == "error"
    ]
    if cognitive_errors:
        provenance_error(
            "Voice evidence contains cognitive runtime errors for acceptance sessions"
        )

    clean_provenance = bool(
        chromie.get("dirty") is False
        and metadata.get("soridormi_local_dirty") is False
    )
    policy_evaluation_ready = bool(
        not errors and clean_provenance and endpoint_source_bound
    )
    return {
        "schema_version": 3,
        "evidence_dir": str(evidence_dir),
        "passed": not errors,
        "errors": errors,
        "provenance_errors": provenance_errors,
        "warnings": warnings,
        "acceptance_id": metadata.get("acceptance_id"),
        "chromie_revision": chromie.get("revision"),
        "chromie_version": chromie.get("version"),
        "soridormi_revision": manifest.get("upstream_commit"),
        "expected_provenance": {
            "chromie_revision": expected_chromie_revision,
            "chromie_version": expected_chromie_version,
            "soridormi_revision": expected_soridormi_revision,
        },
        "cognitive_runtime": {
            "event_count": len(correlated_cognitive_events),
            "applied_lanes": sorted(applied_lanes),
            "error_count": len(cognitive_errors),
        },
        "soridormi_mode": "sim" if provider_modes == {"sim"} else None,
        "case_count": len(by_id),
        "mode": mode,
        "clean_provenance": clean_provenance,
        "endpoint_source_bound": endpoint_source_bound,
        "policy_evaluation_ready": policy_evaluation_ready,
        "human_voice_device_claim_eligible": (
            mode == "supervised"
            and policy_evaluation_ready
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument(
        "--allow-automated",
        action="store_true",
        help=(
            "Permit automated evidence to enter compatibility-policy evaluation; "
            "this does not establish a human physical voice-device claim."
        ),
    )
    parser.add_argument("--expected-chromie-revision")
    parser.add_argument("--expected-chromie-version")
    parser.add_argument("--expected-soridormi-revision")
    parser.add_argument("--write-report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify_bundle(
        args.evidence_dir,
        require_clean=args.require_clean,
        allow_automated=args.allow_automated,
        expected_chromie_revision=args.expected_chromie_revision,
        expected_chromie_version=args.expected_chromie_version,
        expected_soridormi_revision=args.expected_soridormi_revision,
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
