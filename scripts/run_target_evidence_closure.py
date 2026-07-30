#!/usr/bin/env python3
"""Coordinate Chromie's remaining source-bound target-evidence tracks.

The workflow delegates to existing specialized collectors and verifiers. It
never adds cognition, approves human review, changes runtime policy, or declares
release readiness. The default profile closes the current development evidence
scope; supervised physical evidence is a separate, stricter profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "target_evidence_closure_v1.json"
)
DEFAULT_ROOT = ROOT / ".chromie" / "acceptance" / "target-evidence"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"artifact does not exist: {resolved}")
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _git_state(root: Path = ROOT) -> dict[str, Any]:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip()
    )
    return {"revision": revision, "dirty": dirty}


def _root(value: Path | None, *, existing: bool) -> Path:
    if value is None:
        if existing:
            raise ValueError("--evidence-root is required")
        return DEFAULT_ROOT / _run_id()
    return value.expanduser().resolve()


def _state_path(root: Path) -> Path:
    return root / "closure-state.json"


def _report_path(root: Path) -> Path:
    return root / "closure-report.json"


def _manifest(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _read_json(args.manifest.expanduser().resolve())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported target-evidence closure manifest")
    if manifest.get("runtime_policy_authority") is not False:
        raise ValueError("target-evidence manifest must deny runtime policy authority")
    if manifest.get("release_qualification_automatic") is not False:
        raise ValueError("target-evidence manifest must deny automatic release qualification")
    return manifest


def _load_state(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"target-evidence closure is not initialized: {path}")
    state = _read_json(path)
    if state.get("closure_id") != manifest.get("closure_id"):
        raise ValueError("closure state belongs to a different manifest")
    return state


def _write_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    _write_json(_state_path(root), state)


def _profile(manifest: dict[str, Any], profile_id: str) -> dict[str, Any]:
    profiles = manifest.get("profiles")
    profile = profiles.get(profile_id) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        raise ValueError(f"unknown target-evidence profile {profile_id!r}")
    return profile


def _track_spec(manifest: dict[str, Any], track_id: str) -> dict[str, Any]:
    tracks = manifest.get("tracks")
    track = tracks.get(track_id) if isinstance(tracks, dict) else None
    if not isinstance(track, dict):
        raise ValueError(f"unknown target-evidence track {track_id!r}")
    return track


def _nested(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _review_checks(manifest: dict[str, Any], track_id: str) -> list[str]:
    key = f"{track_id}_review_checks"
    values = manifest.get(key)
    if not isinstance(values, list) or not all(
        isinstance(item, str) and item for item in values
    ):
        raise ValueError(f"manifest has no reviewed checks for {track_id}")
    return list(values)


def _review_valid(
    review: dict[str, Any],
    *,
    manifest: dict[str, Any],
    track_id: str,
    report_path: Path,
) -> list[str]:
    errors: list[str] = []
    if review.get("closure_id") != manifest.get("closure_id"):
        errors.append("review closure_id does not match")
    if review.get("track_id") != track_id:
        errors.append("review track_id does not match")
    if review.get("artifact_sha256") != _sha256(report_path):
        errors.append("review artifact fingerprint does not match")
    if review.get("decision") != "approved":
        errors.append("review decision is not approved")
    if not str(review.get("reviewer") or "").strip():
        errors.append("reviewer identity is missing")
    checks = review.get("checks")
    if not isinstance(checks, dict):
        errors.append("review checks must be an object")
    else:
        for check in _review_checks(manifest, track_id):
            if checks.get(check) != "approved":
                errors.append(f"review check {check!r} is not approved")
    return errors


def _track_status(
    root: Path,
    manifest: dict[str, Any],
    track_id: str,
) -> dict[str, Any]:
    spec = _track_spec(manifest, track_id)
    report = root / str(spec.get("report") or "")
    status: dict[str, Any] = {
        "track_id": track_id,
        "report": str(report),
        "present": report.is_file(),
        "eligible": False,
        "errors": [],
    }
    if not report.is_file():
        status["errors"].append("report_missing")
        return status
    try:
        payload = _read_json(report)
    except Exception as exc:
        status["errors"].append(f"report_invalid:{exc}")
        return status
    actual = _nested(payload, str(spec.get("eligibility_path") or ""))
    expected = spec.get("eligibility_value", True)
    if actual != expected:
        status["errors"].append(
            f"eligibility_mismatch:expected={expected!r}:actual={actual!r}"
        )
    review_relative = spec.get("review")
    if review_relative:
        review_path = root / str(review_relative)
        status["review"] = str(review_path)
        if not review_path.is_file():
            status["errors"].append("review_missing")
        else:
            try:
                status["errors"].extend(
                    _review_valid(
                        _read_json(review_path),
                        manifest=manifest,
                        track_id=track_id,
                        report_path=report,
                    )
                )
            except Exception as exc:
                status["errors"].append(f"review_invalid:{exc}")
    status["artifact"] = _artifact(report)
    status["eligible"] = not status["errors"]
    return status


def _refresh(root: Path, manifest: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    profile = _profile(manifest, str(state["profile"]))
    required = list(profile.get("required_tracks") or [])
    optional = list(profile.get("optional_tracks") or [])
    statuses = {
        track_id: _track_status(root, manifest, track_id)
        for track_id in dict.fromkeys([*required, *optional])
    }
    state["tracks"] = statuses
    state["qualification"] = {
        "required_tracks": required,
        "optional_tracks": optional,
        "required_complete": all(statuses[item]["eligible"] for item in required),
        "release_qualified": False,
        "human_review_required": True,
    }
    _write_state(root, state)
    return state


def _copy(source: Path, destination: Path) -> Path:
    resolved = source.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"artifact does not exist: {resolved}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved, destination)
    return destination


def init(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    profile = _profile(manifest, args.profile)
    root = _root(args.evidence_root, existing=False)
    path = _state_path(root)
    if path.exists():
        raise FileExistsError(f"closure state already exists: {path}")
    source = _git_state()
    if source["dirty"] and not args.allow_dirty:
        raise ValueError("target-evidence closure requires a clean committed checkout")
    root.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "closure_id": manifest.get("closure_id"),
        "profile": args.profile,
        "profile_description": profile.get("description"),
        "evidence_root": str(root),
        "reviewer": args.reviewer,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "source": source,
        "manifest": _artifact(args.manifest.expanduser().resolve()),
        "tracks": {},
        "qualification": {
            "required_complete": False,
            "release_qualified": False,
            "human_review_required": True,
        },
    }
    _write_state(root, state)
    plan = root / "closure-plan.md"
    plan.write_text(
        "# Target Evidence Closure Plan\n\n"
        f"Profile: `{args.profile}`\n\n"
        "Use `python scripts/run_target_evidence_closure.py status --evidence-root "
        f"{root}` after each collector or attachment. Human review is never automatic.\n",
        encoding="utf-8",
    )
    print(root)
    return 0


def _run_command(command: list[str], *, dry_run: bool) -> int:
    print("[target-evidence] " + " ".join(command))
    if dry_run:
        return 0
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def collect_core(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    command = [
        args.python,
        "scripts/run_cognitive_gateway_core_qualification.py",
        "collect",
        "--reviewer",
        str(state.get("reviewer") or args.reviewer or ""),
        "--soridormi-repo",
        str(args.soridormi_repo),
        "--agent-url",
        args.agent_url,
        "--soridormi-mcp-url",
        args.soridormi_mcp_url,
        "--evidence-root",
        str(root / "gateway-core"),
    ]
    if args.resume:
        command.append("--resume")
    if args.speaker:
        command.append("--speaker")
    result = _run_command(command, dry_run=args.dry_run)
    if result == 0 and not args.dry_run:
        _refresh(root, manifest, state)
    return result


def finalize_core(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    result = _run_command(
        [
            args.python,
            "scripts/run_cognitive_gateway_core_qualification.py",
            "finalize",
            "--evidence-root",
            str(root / "gateway-core"),
        ],
        dry_run=args.dry_run,
    )
    if result == 0 and not args.dry_run:
        _refresh(root, manifest, state)
    return result


def collect_skill_weather(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    identity = root / "gateway-core" / "runtime-identity.json"
    command = [
        args.python,
        "scripts/run_agent_skill_weather_qualification.py",
        "collect",
        "--reviewer",
        str(state.get("reviewer") or args.reviewer or ""),
        "--runtime-identity",
        str(identity),
        "--agent-url",
        args.agent_url,
        "--evidence-root",
        str(root / "agent-skill-weather"),
    ]
    if args.resume:
        command.append("--resume")
    if args.speaker:
        command.append("--speaker")
    result = _run_command(command, dry_run=args.dry_run)
    if result == 0 and not args.dry_run:
        _refresh(root, manifest, state)
    return result


def finalize_skill_weather(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    identity = root / "gateway-core" / "runtime-identity.json"
    result = _run_command(
        [
            args.python,
            "scripts/run_agent_skill_weather_qualification.py",
            "finalize",
            "--runtime-identity",
            str(identity),
            "--evidence-root",
            str(root / "agent-skill-weather"),
        ],
        dry_run=args.dry_run,
    )
    if result == 0 and not args.dry_run:
        _refresh(root, manifest, state)
    return result


def _pending_review(
    *,
    root: Path,
    manifest: dict[str, Any],
    track_id: str,
    report_path: Path,
    reviewer: str,
) -> Path:
    spec = _track_spec(manifest, track_id)
    review_relative = spec.get("review")
    if not review_relative:
        raise ValueError(f"track {track_id} has no review artifact")
    review_path = root / str(review_relative)
    payload = {
        "schema_version": 1,
        "closure_id": manifest.get("closure_id"),
        "track_id": track_id,
        "artifact_sha256": _sha256(report_path),
        "reviewer": reviewer,
        "reviewed_at": _utc_now(),
        "decision": "pending",
        "checks": {item: "pending" for item in _review_checks(manifest, track_id)},
        "findings": [],
        "notes": "Inspect the exact retained report and qualitative samples before approving.",
    }
    _write_json(review_path, payload)
    return review_path



def _social_attention_pairs(dataset_path: Path) -> list[tuple[str, str]]:
    payload = _read_json(dataset_path.expanduser().resolve())
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Social Attention dataset has no scenarios")
    pairs: set[tuple[str, str]] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("Social Attention dataset scenario must be an object")
        context = scenario.get("context")
        style = context.get("social_interaction_style") if isinstance(context, dict) else None
        mode = context.get("social_attention_mode") if isinstance(context, dict) else None
        preset = style.get("preset") if isinstance(style, dict) else None
        if mode not in {"off", "report_only", "on"} or not isinstance(preset, str) or not preset:
            raise ValueError("Social Attention scenario lacks reviewed mode/style identity")
        pairs.add((mode, preset))
    return sorted(pairs)


def collect_social(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    directory = root / "social-attention"
    inventory = directory / "inventory.json"
    coverage = directory / "coverage.json"
    normalized = directory / "normalized.json"
    reports = directory / "runs"
    commands: list[list[str]] = [
        [
            args.python,
            "-m",
            "benchmarks.inventory.core",
            "--output",
            str(inventory),
            "--coverage-output",
            str(coverage),
        ],
        [
            args.python,
            "-m",
            "benchmarks.adapters.normalize",
            "--inventory",
            str(inventory),
            "--output",
            str(normalized),
        ],
    ]
    run_reports: list[Path] = []
    for mode, style in _social_attention_pairs(args.dataset):
        run_id = f"social-attention-{mode}-{style}"
        output = reports / f"{mode}-{style}.json"
        run_reports.append(output)
        command = [
            args.python,
            "-m",
            "benchmarks.e2e.run",
            "--normalized",
            str(normalized),
            "--profile",
            "live_service_text",
            "--adapter",
            args.adapter,
            "--dataset",
            "social_attention",
            "--mode",
            mode,
            "--style",
            style,
            "--run-id",
            run_id,
            "--code-revision",
            str(state.get("source", {}).get("revision") or ""),
            "--prompt-revision",
            args.prompt_revision,
            "--provider-revision",
            args.provider_revision,
            "--hardware-profile",
            args.hardware_profile,
            "--mind-profile",
            args.mind_profile,
            "--social-style",
            style,
            "--social-attention-mode",
            mode,
            "--semantic-authority-owner",
            "goal_driven_cognitive_core",
            "--runtime-topology",
            args.runtime_topology,
            "--sample-count",
            str(args.sample_count),
            "--timeout-s",
            str(args.timeout_s),
            "--output",
            str(output),
        ]
        for lane in args.apply_lane:
            command.extend(["--apply-lane", lane])
        for model in args.effective_model:
            command.extend(["--effective-model", model])
        commands.append(command)
    qualification = directory / "qualification.json"
    qualification_command = [
        args.python,
        "-m",
        "benchmarks.social_attention",
        "--normalized",
        str(normalized),
        "--inventory",
        str(inventory),
        "--output",
        str(qualification),
    ]
    for report in run_reports:
        qualification_command.extend(["--report", str(report)])
    commands.append(qualification_command)
    for command in commands:
        result = _run_command(command, dry_run=args.dry_run)
        if result != 0:
            return result
    if not args.dry_run:
        review = directory / "human-review.json"
        if not review.exists():
            _pending_review(
                root=root,
                manifest=manifest,
                track_id="social_attention",
                report_path=qualification,
                reviewer=str(state.get("reviewer") or ""),
            )
        _refresh(root, manifest, state)
        print(review)
    return 0

def attach_social(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    destination = root / "social-attention" / "qualification.json"
    _copy(args.qualification, destination)
    report = _read_json(destination)
    if _nested(report, "qualification.state") != "human_review_required":
        raise ValueError("Social Attention qualification is not eligible for human review")
    runs = report.get("runs")
    current_revision = state.get("source", {}).get("revision")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Social Attention qualification has no source-bound runs")
    mismatched = [
        str(item.get("run_id") or "unknown")
        for item in runs
        if not isinstance(item, dict) or item.get("code_revision") != current_revision
    ]
    if mismatched:
        raise ValueError(
            "Social Attention run revisions do not match the closure source: "
            + ", ".join(mismatched)
        )
    review_path = root / "social-attention" / "human-review.json"
    if args.review:
        _copy(args.review, review_path)
    elif not review_path.exists():
        _pending_review(
            root=root,
            manifest=manifest,
            track_id="social_attention",
            report_path=destination,
            reviewer=str(state.get("reviewer") or ""),
        )
    _refresh(root, manifest, state)
    print(review_path)
    return 0


def attach_lan(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    directory = root / "lan-exposure"
    local = _copy(args.local_report, directory / "local.json")
    remote = _copy(args.remote_report, directory / "remote.json")
    report = directory / "qualification.json"
    result = _run_command(
        [
            args.python,
            "scripts/runtime_exposure_evidence.py",
            "verify",
            "--local-report",
            str(local),
            "--remote-report",
            str(remote),
            "--expected-revision",
            str(state.get("source", {}).get("revision") or ""),
            "--output",
            str(report),
        ],
        dry_run=False,
    )
    _refresh(root, manifest, state)
    return result


def attach_voice(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    directory = root / "physical-voice"
    directory.mkdir(parents=True, exist_ok=True)
    report = directory / "verification.json"
    result = _run_command(
        [
            args.python,
            "scripts/verify_voice_evidence.py",
            str(args.evidence_dir),
            "--require-clean",
            "--expected-chromie-revision",
            str(state.get("source", {}).get("revision") or ""),
            "--write-report",
            str(report),
        ],
        dry_run=False,
    )
    _refresh(root, manifest, state)
    return result


def attach_physical_robot(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    directory = root / "physical-robot"
    report_path = _copy(args.qualification, directory / "qualification.json")
    report = _read_json(report_path)
    required = {
        "evidence_type": "physical_robot_supervised",
        "passed": True,
        "physical_robot_claim_eligible": True,
        "source_clean": True,
        "provider_source_bound": True,
        "safe_state_before": True,
        "safe_state_after": True,
    }
    for key, expected in required.items():
        if report.get(key) != expected:
            raise ValueError(f"physical robot report {key} != {expected!r}")
    if report.get("chromie_revision") != state.get("source", {}).get("revision"):
        raise ValueError("physical robot report revision does not match closure source")
    if not str(report.get("operator") or "").strip():
        raise ValueError("physical robot report has no safety operator")
    review_path = directory / "human-review.json"
    if args.review:
        _copy(args.review, review_path)
    elif not review_path.exists():
        _pending_review(
            root=root,
            manifest=manifest,
            track_id="physical_robot",
            report_path=report_path,
            reviewer=str(state.get("reviewer") or ""),
        )
    _refresh(root, manifest, state)
    print(review_path)
    return 0


def status(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _refresh(root, manifest, _load_state(root, manifest))
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def finalize(args: argparse.Namespace) -> int:
    manifest = _manifest(args)
    root = _root(args.evidence_root, existing=True)
    state = _load_state(root, manifest)
    current = _git_state()
    errors: list[str] = []
    if current["dirty"]:
        errors.append("finalization requires a clean checkout")
    if current["revision"] != state.get("source", {}).get("revision"):
        errors.append("current source revision differs from the initialized closure")
    state = _refresh(root, manifest, state)
    required_complete = state.get("qualification", {}).get("required_complete") is True
    if not required_complete:
        errors.append("one or more required evidence tracks are incomplete")
    report = {
        "schema_version": 1,
        "closure_id": manifest.get("closure_id"),
        "profile": state.get("profile"),
        "source": state.get("source"),
        "reviewer": state.get("reviewer"),
        "finalized_at": _utc_now(),
        "tracks": state.get("tracks"),
        "errors": errors,
        "qualification": {
            "target_evidence_closure_eligible": not errors,
            "release_qualified": False,
            "human_review_required": True,
            "physical_support_claimed": state.get("profile") == "supervised_physical_pilot",
        },
    }
    _write_json(_report_path(root), report)
    state["final_report"] = _artifact(_report_path(root))
    state["qualification"]["target_evidence_closure_eligible"] = not errors
    _write_state(root, state)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)


def _collector_common(parser: argparse.ArgumentParser) -> None:
    _common(parser)
    parser.add_argument("--reviewer", default=os.getenv("USER", "").strip())
    parser.add_argument("--agent-url", default=os.getenv("AGENT_URL", "http://127.0.0.1:8092"))
    parser.add_argument("--speaker", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init")
    init_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    init_parser.add_argument("--evidence-root", type=Path)
    init_parser.add_argument(
        "--profile",
        choices=("source_bound_development", "supervised_physical_pilot"),
        default="source_bound_development",
    )
    init_parser.add_argument("--reviewer", default=os.getenv("USER", "").strip())
    init_parser.add_argument("--allow-dirty", action="store_true")

    core = sub.add_parser("collect-core")
    _collector_common(core)
    core.add_argument("--soridormi-repo", type=Path, default=ROOT.parent / "soridormi")
    core.add_argument(
        "--soridormi-mcp-url",
        default=os.getenv("SORIDORMI_MCP_URL", "http://127.0.0.1:8000/mcp"),
    )
    finalize_core_parser = sub.add_parser("finalize-core")
    _collector_common(finalize_core_parser)

    skill = sub.add_parser("collect-skill-weather")
    _collector_common(skill)
    finalize_skill = sub.add_parser("finalize-skill-weather")
    _collector_common(finalize_skill)

    collect_social_parser = sub.add_parser("collect-social")
    _common(collect_social_parser)
    collect_social_parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "benchmarks" / "datasets" / "social_attention" / "cases.json",
    )
    collect_social_parser.add_argument("--adapter", default="live_service_text")
    collect_social_parser.add_argument("--prompt-revision", required=True)
    collect_social_parser.add_argument("--provider-revision", required=True)
    collect_social_parser.add_argument("--hardware-profile", required=True)
    collect_social_parser.add_argument("--mind-profile", required=True)
    collect_social_parser.add_argument("--runtime-topology", required=True)
    collect_social_parser.add_argument(
        "--effective-model", action="append", default=[], metavar="COMPONENT=MODEL"
    )
    collect_social_parser.add_argument(
        "--apply-lane", action="append", default=["chat", "robot_action"]
    )
    collect_social_parser.add_argument("--sample-count", type=int, default=1)
    collect_social_parser.add_argument("--timeout-s", type=float, default=180.0)
    collect_social_parser.add_argument("--dry-run", action="store_true")

    social = sub.add_parser("attach-social")
    _common(social)
    social.add_argument("--qualification", type=Path, required=True)
    social.add_argument("--review", type=Path)

    lan = sub.add_parser("attach-lan")
    _common(lan)
    lan.add_argument("--local-report", type=Path, required=True)
    lan.add_argument("--remote-report", type=Path, required=True)

    voice = sub.add_parser("attach-voice")
    _common(voice)
    voice.add_argument("--evidence-dir", type=Path, required=True)

    physical = sub.add_parser("attach-physical-robot")
    _common(physical)
    physical.add_argument("--qualification", type=Path, required=True)
    physical.add_argument("--review", type=Path)

    status_parser = sub.add_parser("status")
    _common(status_parser)
    finalize_parser = sub.add_parser("finalize")
    _common(finalize_parser)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "init":
            if not args.reviewer:
                raise ValueError("--reviewer is required when USER is unavailable")
            return init(args)
        if args.command == "collect-core":
            return collect_core(args)
        if args.command == "finalize-core":
            return finalize_core(args)
        if args.command == "collect-skill-weather":
            return collect_skill_weather(args)
        if args.command == "finalize-skill-weather":
            return finalize_skill_weather(args)
        if args.command == "collect-social":
            return collect_social(args)
        if args.command == "attach-social":
            return attach_social(args)
        if args.command == "attach-lan":
            return attach_lan(args)
        if args.command == "attach-voice":
            return attach_voice(args)
        if args.command == "attach-physical-robot":
            return attach_physical_robot(args)
        if args.command == "status":
            return status(args)
        if args.command == "finalize":
            return finalize(args)
        raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        print(f"[target-evidence-closure][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
