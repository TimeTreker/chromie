#!/usr/bin/env python3
"""Validate a reference-robot candidate without authorizing physical motion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

STATES = {"draft", "ready_for_no_motion_review", "selected"}
PLACEHOLDERS = {"replace-me", "todo", "tbd", "unknown", "not-configured"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOP_LEVEL_KEYS = {
    "schema_version",
    "candidate_id",
    "candidate_state",
    "identity",
    "host",
    "network",
    "power_constraints",
    "revisions",
    "initial_low_risk_skill",
    "unsupported",
    "safety",
    "calibration_artifacts",
    "procedures",
    "approvals",
}


def _nonempty(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().lower() not in PLACEHOLDERS
    )


def _timestamp(value: Any) -> bool:
    if not _nonempty(value):
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _mapping(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be an object")
        return {}
    return value


def _check_keys(
    value: dict[str, Any],
    label: str,
    allowed: set[str],
    errors: list[str],
) -> None:
    missing = sorted(allowed - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        errors.append(f"{label} is missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{label} contains unknown fields: {', '.join(unknown)}")


def _string_list(
    value: Any,
    label: str,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{label} must be an array of strings")
        return []
    return value


def _resolve_file_reference(
    path_value: Any,
    label: str,
    evidence_root: Path,
    blockers: list[str],
) -> Path | None:
    if not _nonempty(path_value):
        return None
    path = Path(str(path_value))
    if path.is_absolute():
        blockers.append(f"{label} must be relative to the evidence root")
        return None
    evidence_root_resolved = evidence_root.resolve()
    resolved = (evidence_root / path).resolve()
    if not resolved.is_relative_to(evidence_root_resolved):
        blockers.append(f"{label} must stay within the evidence root: {path}")
        return None
    return resolved


def _check_file_reference(
    path_value: Any,
    label: str,
    evidence_root: Path,
    blockers: list[str],
) -> Path | None:
    path = _resolve_file_reference(path_value, label, evidence_root, blockers)
    if path is None:
        return None
    if not path.is_file():
        blockers.append(f"{label} file does not exist: {path}")
        return None
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_provider_manifest(
    path: Path,
    expected_soridormi_revision: Any,
    blockers: list[str],
) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        blockers.append(f"revisions.provider_manifest is not valid JSON: {exc}")
        return
    if not isinstance(manifest, dict):
        blockers.append("revisions.provider_manifest must contain a JSON object")
        return
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        blockers.append("revisions.provider_manifest metadata is required")
        return
    upstream_commit = metadata.get("upstream_commit")
    if upstream_commit != expected_soridormi_revision:
        blockers.append(
            "revisions.provider_manifest metadata.upstream_commit must match "
            "revisions.soridormi"
        )


def verify_candidate(
    payload: dict[str, Any],
    *,
    evidence_root: Path | None = None,
    verify_evidence_files: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    evidence_root = evidence_root or Path.cwd()

    _check_keys(payload, "manifest", TOP_LEVEL_KEYS, errors)
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    state = payload.get("candidate_state")
    if state not in STATES:
        errors.append(
            "candidate_state must be draft, ready_for_no_motion_review, or selected"
        )
    candidate_id = payload.get("candidate_id")
    if not _nonempty(candidate_id):
        blockers.append("candidate_id must replace the template placeholder")

    identity = _mapping(payload, "identity", errors)
    _check_keys(
        identity,
        "identity",
        {"vendor", "model", "serial_number", "controller", "firmware", "sensors"},
        errors,
    )
    for field in ("vendor", "model", "serial_number", "controller", "firmware"):
        if not _nonempty(identity.get(field)):
            blockers.append(f"identity.{field} is required")
    sensors = _string_list(identity.get("sensors"), "identity.sensors", errors)
    if not sensors or any(not _nonempty(item) for item in sensors):
        blockers.append("identity.sensors must name at least one sensor")

    host = _mapping(payload, "host", errors)
    _check_keys(host, "host", {"os", "os_version", "architecture"}, errors)
    for field in ("os", "os_version", "architecture"):
        if not _nonempty(host.get(field)):
            blockers.append(f"host.{field} is required")

    network = _mapping(payload, "network", errors)
    _check_keys(
        network,
        "network",
        {"topology", "isolated_control_network"},
        errors,
    )
    if not _nonempty(network.get("topology")):
        blockers.append("network.topology is required")
    if not isinstance(network.get("isolated_control_network"), bool):
        errors.append("network.isolated_control_network must be boolean")
    elif network.get("isolated_control_network") is not True:
        warnings.append("control network is not declared isolated")
    if not _nonempty(payload.get("power_constraints")):
        blockers.append("power_constraints is required")

    revisions = _mapping(payload, "revisions", errors)
    _check_keys(
        revisions,
        "revisions",
        {
            "chromie",
            "soridormi",
            "provider_manifest",
            "provider_configuration_sha256",
        },
        errors,
    )
    for field in ("chromie", "soridormi"):
        value = revisions.get(field)
        if not isinstance(value, str) or not SHA40.fullmatch(value):
            blockers.append(f"revisions.{field} must be a full 40-character SHA")
    if not _nonempty(revisions.get("provider_manifest")):
        blockers.append("revisions.provider_manifest is required")
    elif verify_evidence_files:
        provider_manifest_path = _check_file_reference(
            revisions.get("provider_manifest"),
            "revisions.provider_manifest",
            evidence_root,
            blockers,
        )
        if provider_manifest_path is not None:
            _check_provider_manifest(
                provider_manifest_path,
                revisions.get("soridormi"),
                blockers,
            )
    provider_sha = revisions.get("provider_configuration_sha256")
    if not isinstance(provider_sha, str) or not SHA256.fullmatch(provider_sha):
        blockers.append(
            "revisions.provider_configuration_sha256 must be a 64-character SHA-256"
        )

    skill = _mapping(payload, "initial_low_risk_skill", errors)
    _check_keys(
        skill,
        "initial_low_risk_skill",
        {
            "skill_id",
            "workspace",
            "max_speed",
            "max_payload",
            "supervision",
            "abort_conditions",
        },
        errors,
    )
    for field in ("skill_id", "workspace", "max_speed", "max_payload"):
        if not _nonempty(skill.get(field)):
            blockers.append(f"initial_low_risk_skill.{field} is required")
    if skill.get("supervision") != "direct_operator":
        blockers.append(
            "initial_low_risk_skill.supervision must be direct_operator"
        )
    abort_conditions = _string_list(
        skill.get("abort_conditions"),
        "initial_low_risk_skill.abort_conditions",
        errors,
    )
    if not abort_conditions or any(not _nonempty(item) for item in abort_conditions):
        blockers.append(
            "initial_low_risk_skill.abort_conditions must not be empty"
        )

    unsupported = _mapping(payload, "unsupported", errors)
    _check_keys(
        unsupported,
        "unsupported",
        {"skills", "configurations", "operating_conditions"},
        errors,
    )
    for field in ("skills", "configurations", "operating_conditions"):
        values = _string_list(
            unsupported.get(field),
            f"unsupported.{field}",
            errors,
        )
        if not values or any(not _nonempty(item) for item in values):
            blockers.append(f"unsupported.{field} must name explicit exclusions")

    safety = _mapping(payload, "safety", errors)
    _check_keys(
        safety,
        "safety",
        {
            "physical_motion_enabled",
            "emergency_stop_independently_tested",
            "emergency_stop_procedure",
            "emergency_stop_evidence",
            "emergency_stop_tested_at",
            "emergency_stop_operator",
        },
        errors,
    )
    if safety.get("physical_motion_enabled") is not False:
        errors.append(
            "safety.physical_motion_enabled must remain false; this manifest "
            "cannot authorize motion"
        )
    if safety.get("emergency_stop_independently_tested") is not True:
        blockers.append("independent emergency-stop evidence is required")
    for field in (
        "emergency_stop_procedure",
        "emergency_stop_evidence",
        "emergency_stop_operator",
    ):
        if not _nonempty(safety.get(field)):
            blockers.append(f"safety.{field} is required")
    if verify_evidence_files:
        for field in ("emergency_stop_procedure", "emergency_stop_evidence"):
            _check_file_reference(
                safety.get(field),
                f"safety.{field}",
                evidence_root,
                blockers,
            )
    if not _timestamp(safety.get("emergency_stop_tested_at")):
        blockers.append(
            "safety.emergency_stop_tested_at must be an ISO-8601 timestamp"
        )

    artifacts = payload.get("calibration_artifacts")
    if not isinstance(artifacts, list):
        errors.append("calibration_artifacts must be an array")
        artifacts = []
    if not artifacts:
        blockers.append("at least one calibration artifact is required")
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"calibration_artifacts[{index}] must be an object")
            continue
        _check_keys(
            artifact,
            f"calibration_artifacts[{index}]",
            {"name", "path", "sha256", "captured_at"},
            errors,
        )
        for field in ("name", "path"):
            if not _nonempty(artifact.get(field)):
                blockers.append(
                    f"calibration_artifacts[{index}].{field} is required"
                )
        if not isinstance(artifact.get("sha256"), str) or not SHA256.fullmatch(
            artifact["sha256"]
        ):
            blockers.append(
                f"calibration_artifacts[{index}].sha256 must be a SHA-256"
            )
        elif verify_evidence_files:
            artifact_path = _check_file_reference(
                artifact.get("path"),
                f"calibration_artifacts[{index}].path",
                evidence_root,
                blockers,
            )
            if artifact_path is not None:
                observed_sha256 = _sha256(artifact_path)
                if observed_sha256 != artifact["sha256"]:
                    blockers.append(
                        f"calibration_artifacts[{index}].sha256 does not match "
                        f"{artifact_path}"
                    )
        if not _timestamp(artifact.get("captured_at")):
            blockers.append(
                f"calibration_artifacts[{index}].captured_at must be ISO-8601"
            )

    procedures = _mapping(payload, "procedures", errors)
    _check_keys(
        procedures,
        "procedures",
        {"stop", "recovery", "communication_loss", "observable_safe_idle"},
        errors,
    )
    for field in ("stop", "recovery", "communication_loss", "observable_safe_idle"):
        if not _nonempty(procedures.get(field)):
            blockers.append(f"procedures.{field} is required")
    if verify_evidence_files:
        for field in ("stop", "recovery", "communication_loss"):
            _check_file_reference(
                procedures.get(field),
                f"procedures.{field}",
                evidence_root,
                blockers,
            )

    approvals = _mapping(payload, "approvals", errors)
    _check_keys(
        approvals,
        "approvals",
        {"responsible_operator", "safety_reviewer", "reviewed_at"},
        errors,
    )
    for field in ("responsible_operator", "safety_reviewer"):
        if not _nonempty(approvals.get(field)):
            blockers.append(f"approvals.{field} is required")
    if not _timestamp(approvals.get("reviewed_at")):
        blockers.append("approvals.reviewed_at must be an ISO-8601 timestamp")

    core_blocker_prefixes = (
        "candidate_id",
        "identity.",
        "host.",
        "network.",
        "power_constraints",
        "revisions.",
        "initial_low_risk_skill.",
        "unsupported.",
    )
    core_blockers = [
        blocker
        for blocker in blockers
        if blocker.startswith(core_blocker_prefixes)
    ]
    ready_for_no_motion_review = not errors and not core_blockers
    selected_for_pilot = (
        ready_for_no_motion_review
        and not blockers
        and state == "selected"
    )
    if state == "ready_for_no_motion_review" and not ready_for_no_motion_review:
        errors.append(
            "candidate_state claims ready_for_no_motion_review but core blockers remain"
        )
    if state == "selected" and not selected_for_pilot:
        errors.append("candidate_state claims selected but commissioning blockers remain")

    return {
        "schema_version": 1,
        "valid": not errors,
        "ready_for_no_motion_review": ready_for_no_motion_review,
        "selected_for_pilot": selected_for_pilot,
        "physical_motion_authorized": False,
        "candidate_id": candidate_id,
        "candidate_state": state,
        "evidence_files_verified": verify_evidence_files,
        "evidence_root": str(evidence_root) if verify_evidence_files else None,
        "errors": errors,
        "blockers": blockers,
        "warnings": warnings,
    }


def load_candidate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candidate manifest root must be an object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="Exit zero for a structurally valid draft even when blockers remain.",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help=(
            "Resolve relative evidence paths from this directory when "
            "--verify-evidence-files is set. Defaults to the manifest directory."
        ),
    )
    parser.add_argument(
        "--verify-evidence-files",
        action="store_true",
        help=(
            "Require referenced provider, safety, procedure, and calibration "
            "files to exist and require calibration SHA-256 values to match."
        ),
    )
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args(argv)
    try:
        evidence_root = args.evidence_root or args.manifest.parent
        report = verify_candidate(
            load_candidate(args.manifest),
            evidence_root=evidence_root,
            verify_evidence_files=args.verify_evidence_files,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schema_version": 1,
            "valid": False,
            "ready_for_no_motion_review": False,
            "selected_for_pilot": False,
            "physical_motion_authorized": False,
            "errors": [str(exc)],
            "blockers": [],
            "warnings": [],
        }
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.allow_draft:
        return 0 if report["valid"] else 1
    return 0 if report["selected_for_pilot"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
