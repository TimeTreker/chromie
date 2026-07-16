#!/usr/bin/env python3
"""Prepare a reproducible Chromie release bundle after acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

try:
    from cognitive_runtime_acceptance import build_bundle as build_cognitive_bundle
    from release_provenance import collect_provenance
    from verify_voice_evidence import verify_bundle
except ImportError:  # imported as scripts.prepare_release in tests/tools
    from scripts.cognitive_runtime_acceptance import build_bundle as build_cognitive_bundle
    from scripts.release_provenance import collect_provenance
    from scripts.verify_voice_evidence import verify_bundle

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "releases"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object in {path}")
    return payload


def soridormi_manifest_revision(root: Path = ROOT) -> str:
    manifest = read_json(root / "capabilities" / "soridormi.json")
    metadata = manifest.get("metadata")
    revision = metadata.get("upstream_commit") if isinstance(metadata, dict) else None
    if not revision:
        raise ValueError(
            "capabilities/soridormi.json does not declare metadata.upstream_commit"
        )
    return str(revision)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_logged(command: Sequence[str], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(command) + "\n\n")
        handle.flush()
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}; "
            f"see {log_path}"
        )


def sanitize_release_log(
    log_path: Path,
    *,
    repository_root: Path,
    home_directory: Path | None = None,
) -> None:
    """Replace machine-local repository/home paths in a passing public test log."""

    root = repository_root.expanduser().resolve()
    home = (home_directory or Path.home()).expanduser().resolve()
    replacements = [(str(root), "<repo>")]
    if home != root and home != Path("/"):
        replacements.append((str(home), "<home>"))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)

    content = log_path.read_text(encoding="utf-8")
    for private_path, public_label in replacements:
        content = content.replace(private_path, public_label)
    log_path.write_text(content, encoding="utf-8")


def create_source_archive(revision: str, version: str, destination: Path) -> None:
    prefix = f"chromie-{version}/"
    subprocess.run(
        [
            "git",
            "archive",
            "--format=tar.gz",
            f"--prefix={prefix}",
            "-o",
            str(destination),
            revision,
        ],
        cwd=ROOT,
        check=True,
    )
    # Verify the archive is readable before publishing a checksum.
    with tarfile.open(destination, "r:gz") as archive:
        if not archive.getmembers():
            raise RuntimeError("Generated source archive is empty")


def release_tag(version: str, compatibility: dict[str, Any]) -> str:
    configured = compatibility.get("chromie", {}).get("release_tag")
    if configured:
        return str(configured)
    if version.startswith(("v", "sim-")):
        return version
    return f"v{version}"


def release_notes_path(version: str, tag: str) -> Path:
    candidates = [
        ROOT / "release" / f"{tag}.md",
        ROOT / "release" / f"{version}.md",
        ROOT / "release" / f"v{version}.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Missing release notes. Tried: "
        + ", ".join(str(path.relative_to(ROOT)) for path in candidates)
    )


def validate_compatibility(compatibility: dict[str, Any]) -> None:
    """Reject incomplete or internally contradictory release policy."""

    if compatibility.get("schema_version") != 1:
        raise ValueError("release/compatibility.json schema_version must be 1")
    release_state = compatibility.get("release_state")
    if release_state not in {"candidate", "release"}:
        raise ValueError(
            "release/compatibility.json release_state must be 'candidate' or 'release'"
        )

    chromie = compatibility.get("chromie")
    if not isinstance(chromie, dict):
        raise ValueError("release/compatibility.json requires a chromie object")
    supported_branch = chromie.get("supported_branch")
    if not isinstance(supported_branch, str) or not supported_branch.strip():
        raise ValueError("chromie.supported_branch must be a non-empty string")
    runtime_modes = chromie.get("runtime_modes")
    if (
        not isinstance(runtime_modes, list)
        or not runtime_modes
        or any(
            not isinstance(item, str) or not item.strip() or item != item.strip()
            for item in runtime_modes
        )
        or len(set(runtime_modes)) != len(runtime_modes)
    ):
        raise ValueError(
            "chromie.runtime_modes must be a non-empty, unique list of "
            "trimmed non-empty strings"
        )

    soridormi = compatibility.get("soridormi")
    if not isinstance(soridormi, dict):
        raise ValueError("release/compatibility.json requires a soridormi object")
    if soridormi.get("supported_mode") not in {"sim"}:
        raise ValueError(
            "soridormi.supported_mode must be 'sim' for the current release scope"
        )

    blockers = compatibility.get("release_gate_blockers")
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item.strip() for item in blockers
    ):
        raise ValueError(
            "release_gate_blockers must be a list of non-empty strings"
        )
    if release_state == "candidate" and not blockers:
        raise ValueError("candidate release_state requires at least one gate blocker")
    if release_state == "release" and blockers:
        raise ValueError("release release_state cannot retain gate blockers")

    evidence_policy = compatibility.get("evidence_policy")
    if not isinstance(evidence_policy, dict):
        raise ValueError("release/compatibility.json requires an evidence_policy object")
    accepted_modes = evidence_policy.get("accepted_voice_modes")
    supported_voice_modes = {"synthetic", "virtual-mic", "acoustic", "supervised"}
    if (
        not isinstance(accepted_modes, list)
        or not accepted_modes
        or any(
            not isinstance(item, str) or item not in supported_voice_modes
            for item in accepted_modes
        )
        or len(set(accepted_modes)) != len(accepted_modes)
    ):
        raise ValueError(
            "evidence_policy.accepted_voice_modes must be a non-empty, unique "
            "list of supported voice modes"
        )
    if not isinstance(
        evidence_policy.get("human_supervised_voice_device_claim"), bool
    ):
        raise ValueError(
            "evidence_policy.human_supervised_voice_device_claim must be boolean"
        )
    sim_required = evidence_policy.get("soridormi_mujoco_sim_executor_required")
    if not isinstance(sim_required, bool):
        raise ValueError(
            "evidence_policy.soridormi_mujoco_sim_executor_required must be boolean"
        )
    declares_sim_scope = (
        soridormi.get("supported_mode") == "sim"
        or "soridormi-mujoco-sim" in runtime_modes
    )
    if declares_sim_scope and sim_required is not True:
        raise ValueError(
            "simulator release scope requires "
            "evidence_policy.soridormi_mujoco_sim_executor_required=true"
        )


def release_safe_payload(value: Any, *, private_paths: Sequence[Path]) -> Any:
    """Remove machine-local absolute paths from copied release metadata."""

    replacements = [
        str(path.expanduser().resolve())
        for path in private_paths
        if str(path)
    ]

    def sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: sanitize(child)
                for key, child in item.items()
                if key not in {"evidence_dir", "summary_path"}
            }
        if isinstance(item, list):
            return [sanitize(child) for child in item]
        if isinstance(item, str):
            cleaned = item
            for path in replacements:
                cleaned = cleaned.replace(path, "<external-evidence>")
            return cleaned
        return item

    return sanitize(value)


def render_release_voice_summary(evidence_report: dict[str, Any]) -> str:
    """Render a path- and operator-free summary for public release artifacts."""

    return "\n".join(
        [
            "# Voice Acceptance Summary",
            "",
            f"- **Verified:** `{bool(evidence_report.get('passed'))}`",
            f"- **Acceptance ID:** `{evidence_report.get('acceptance_id')}`",
            f"- **Mode:** `{evidence_report.get('mode')}`",
            f"- **Cases:** `{evidence_report.get('case_count')}`",
            f"- **Chromie revision:** `{evidence_report.get('chromie_revision')}`",
            f"- **Chromie version:** `{evidence_report.get('chromie_version')}`",
            f"- **Soridormi revision:** `{evidence_report.get('soridormi_revision')}`",
            f"- **Endpoint source bound:** `{bool(evidence_report.get('endpoint_source_bound'))}`",
            f"- **Policy evaluation ready:** `{bool(evidence_report.get('policy_evaluation_ready'))}`",
            "",
            "Operator identity and machine-local evidence paths are intentionally omitted.",
            "This summary does not establish a physical voice-device claim.",
            "",
        ]
    )


def prepare_release(args: argparse.Namespace) -> Path:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION is empty")
    compatibility = read_json(ROOT / "release" / "compatibility.json")
    validate_compatibility(compatibility)
    declared_version = compatibility.get("chromie", {}).get("version")
    if declared_version != version:
        raise ValueError(
            f"Compatibility version {declared_version!r} does not match VERSION {version!r}"
        )
    compatibility_soridormi = compatibility.get("soridormi") or {}
    compatibility_soridormi_revision = compatibility_soridormi.get("upstream_commit")
    if not compatibility_soridormi_revision:
        raise ValueError(
            "release/compatibility.json does not declare soridormi.upstream_commit"
        )
    manifest_soridormi_revision = soridormi_manifest_revision(ROOT)
    if compatibility_soridormi_revision != manifest_soridormi_revision:
        raise ValueError(
            "Compatibility Soridormi revision "
            f"{compatibility_soridormi_revision!r} does not match the capability "
            f"manifest revision {manifest_soridormi_revision!r}"
        )
    revision = git_output("rev-parse", "HEAD")
    branch = git_output("branch", "--show-current")
    supported_branch = str(
        (compatibility.get("chromie") or {}).get("supported_branch") or ""
    ).strip()
    if not args.preview and supported_branch and branch != supported_branch:
        raise RuntimeError(
            f"Release policy requires branch {supported_branch!r}; current branch "
            f"is {branch or '<detached>'!r}"
        )
    tag = release_tag(version, compatibility)
    notes_path = release_notes_path(version, tag)
    blockers = compatibility.get("release_gate_blockers") or []
    if blockers and not args.preview:
        raise RuntimeError(
            "Release candidate still has tracked blockers:\n- "
            + "\n- ".join(str(item) for item in blockers)
            + "\nUse --preview only for a non-publishable packaging rehearsal."
        )
    if args.skip_tests and not args.preview:
        raise ValueError("--skip-tests is allowed only with --preview")
    if args.allow_dirty and not args.preview:
        raise ValueError("--allow-dirty is allowed only with --preview")

    skip_runtime_provenance = bool(getattr(args, "skip_runtime_provenance", False))
    if skip_runtime_provenance and not args.preview:
        raise ValueError("--skip-runtime-provenance is allowed only with --preview")

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    allow_automated_evidence = bool(getattr(args, "allow_automated_evidence", False))
    evidence_report = verify_bundle(
        evidence_dir,
        require_clean=(not args.preview or args.require_clean_evidence),
        allow_automated=allow_automated_evidence,
        expected_chromie_revision=revision,
        expected_chromie_version=version,
        expected_soridormi_revision=manifest_soridormi_revision,
    )
    if evidence_report.get("provenance_errors"):
        raise RuntimeError(
            "Acceptance evidence provenance does not match this release source:\n- "
            + "\n- ".join(evidence_report["provenance_errors"])
        )
    if not evidence_report["passed"] and not args.preview:
        raise RuntimeError(
            "Acceptance evidence verification failed:\n- "
            + "\n- ".join(evidence_report["errors"])
        )
    if not evidence_report.get("policy_evaluation_ready") and not args.preview:
        raise RuntimeError(
            "Acceptance evidence is not ready for release-policy evaluation; "
            "clean source and endpoint-reported Soridormi revision binding are required"
        )
    evidence_policy = compatibility["evidence_policy"]
    accepted_modes = evidence_policy["accepted_voice_modes"]
    mode = evidence_report.get("mode")
    if mode not in accepted_modes:
        raise RuntimeError(
            f"Evidence mode {mode!r} is not accepted by release/compatibility.json"
        )
    if allow_automated_evidence:
        if evidence_policy.get("human_supervised_voice_device_claim") is not False:
            raise RuntimeError(
                "--allow-automated-evidence requires release/compatibility.json "
                "to declare evidence_policy.human_supervised_voice_device_claim=false"
            )
    sim_executor_required = evidence_policy["soridormi_mujoco_sim_executor_required"]
    if sim_executor_required and evidence_report.get("soridormi_mode") != "sim":
        raise RuntimeError(
            "Voice evidence does not prove the required Soridormi MuJoCo sim mode"
        )

    text_mujoco_summary = getattr(args, "text_mujoco_summary", None)
    cognitive_evidence: dict[str, Any] | None = None
    if text_mujoco_summary:
        cognitive_evidence = build_cognitive_bundle(
            events_path=None,
            text_mujoco_summary=Path(text_mujoco_summary).expanduser().resolve(),
            expected_chromie_revision=revision,
            expected_soridormi_revision=manifest_soridormi_revision,
        )
        simulator_report = cognitive_evidence.get("simulator") or {}
        if simulator_report.get("provenance_errors"):
            raise RuntimeError(
                "Cognitive simulator evidence provenance does not match this release source:\n- "
                + "\n- ".join(simulator_report["provenance_errors"])
            )
    if (
        sim_executor_required
        and not args.preview
        and not (
            cognitive_evidence
            and cognitive_evidence["status_vocabulary"]["target_validated"]
        )
    ):
        raise RuntimeError(
            "A current-revision target-validated goal-driven text-MuJoCo summary "
            "is required; pass --text-mujoco-summary"
        )

    short_revision = revision[:12]
    status = git_output("status", "--porcelain")
    dirty = bool(status)
    if dirty and not args.allow_dirty and not args.preview:
        raise RuntimeError(
            "Worktree is dirty. Commit the accepted source before preparing a release, "
            "or use --preview for a non-publishable bundle."
        )

    output_dir = Path(args.output_root).expanduser() / tag / short_revision
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Release output already exists: {output_dir}")
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_tests:
        tests_log = output_dir / "tests.log"
        run_logged(["./scripts/run_tests.sh"], tests_log)
        sanitize_release_log(tests_log, repository_root=ROOT)

    provenance = collect_provenance(
        ROOT,
        require_runtime=not args.preview,
        attempt_runtime=not skip_runtime_provenance,
    )
    if not provenance["complete"] and not args.preview:
        errors = provenance["source_errors"] + provenance["runtime_errors"]
        raise RuntimeError(
            "Release build provenance is incomplete:\n- " + "\n- ".join(errors)
        )

    final_revision = git_output("rev-parse", "HEAD")
    final_branch = git_output("branch", "--show-current")
    final_status = git_output("status", "--porcelain")
    if final_revision != revision or final_branch != branch:
        raise RuntimeError(
            "Repository HEAD or branch changed while release checks were running; "
            "discard this rehearsal and rerun from a stable checkout"
        )
    dirty = bool(final_status)
    if dirty and not args.preview:
        raise RuntimeError(
            "Worktree changed while release checks were running; rerun from a "
            "clean committed checkout"
        )
    provenance_path = output_dir / "build-provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    source_archive = output_dir / f"chromie-{version}.tar.gz"
    create_source_archive(revision, version, source_archive)
    shutil.copy2(notes_path, output_dir / "release-notes.md")
    shutil.copy2(ROOT / "release" / "compatibility.json", output_dir / "compatibility.json")
    model_lock_source = ROOT / "release" / "model-lock.json"
    model_lock_artifact = None
    if model_lock_source.is_file():
        shutil.copy2(model_lock_source, output_dir / "model-lock.json")
        model_lock_artifact = "model-lock.json"
    private_paths = [evidence_dir]
    if text_mujoco_summary:
        private_paths.append(Path(text_mujoco_summary))
    public_evidence_report = release_safe_payload(
        evidence_report,
        private_paths=private_paths,
    )
    public_cognitive_evidence = release_safe_payload(
        cognitive_evidence,
        private_paths=private_paths,
    )
    (output_dir / "voice-acceptance-summary.md").write_text(
        render_release_voice_summary(public_evidence_report),
        encoding="utf-8",
    )
    cognitive_evidence_artifact = None
    if cognitive_evidence is not None:
        cognitive_evidence_artifact = "cognitive-runtime-acceptance.json"
        (output_dir / cognitive_evidence_artifact).write_text(
            json.dumps(public_cognitive_evidence, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    voice_policy_eligible = bool(
        evidence_report["passed"]
        and evidence_report.get("policy_evaluation_ready")
        and mode in accepted_modes
        and (not sim_executor_required or evidence_report.get("soridormi_mode") == "sim")
    )
    simulator_policy_eligible = bool(
        not sim_executor_required
        or (
            cognitive_evidence
            and cognitive_evidence["status_vocabulary"]["target_validated"]
        )
    )
    publishable = (
        voice_policy_eligible
        and simulator_policy_eligible
        and not dirty
        and not args.preview
        and not blockers
        and not args.skip_tests
        and provenance["complete"]
    )
    manifest = {
        "schema_version": 2,
        "generated_utc": utc_now(),
        "version": version,
        "tag": tag,
        "publishable": publishable,
        "preview": bool(args.preview),
        "chromie": {
            "revision": revision,
            "short_revision": short_revision,
            "dirty": dirty,
            "branch": branch,
        },
        "compatibility": compatibility,
        "voice_evidence": public_evidence_report,
        "cognitive_simulator_evidence": public_cognitive_evidence,
        "evidence_policy": {
            "allow_automated_voice_evidence": allow_automated_evidence,
            "voice_policy_eligible": voice_policy_eligible,
            "simulator_policy_eligible": simulator_policy_eligible,
        },
        "build_provenance": {
            "complete": provenance["complete"],
            "source_error_count": len(provenance["source_errors"]),
            "runtime_error_count": len(provenance["runtime_errors"]),
        },
        "artifacts": {
            "source_archive": source_archive.name,
            "release_notes": "release-notes.md",
            "compatibility": "compatibility.json",
            "model_lock": model_lock_artifact,
            "build_provenance": "build-provenance.json",
            "acceptance_summary": "voice-acceptance-summary.md",
            "cognitive_runtime_acceptance": cognitive_evidence_artifact,
            "tests_log": None if args.skip_tests else "tests.log",
        },
        "publication_steps": (
            [
                f"git tag -s {tag} {revision}",
                f"git push origin {tag}",
                "Create a GitHub prerelease and attach the generated artifacts.",
            ]
            if publishable
            else []
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_targets = [
        source_archive,
        output_dir / "release-notes.md",
        output_dir / "compatibility.json",
        provenance_path,
        output_dir / "voice-acceptance-summary.md",
        output_dir / "manifest.json",
    ]
    if model_lock_artifact:
        checksum_targets.append(output_dir / model_lock_artifact)
    if cognitive_evidence_artifact:
        checksum_targets.append(output_dir / cognitive_evidence_artifact)
    if not args.skip_tests:
        checksum_targets.append(output_dir / "tests.log")
    (output_dir / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in checksum_targets),
        encoding="utf-8",
    )
    return output_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--require-clean-evidence", action="store_true")
    parser.add_argument(
        "--text-mujoco-summary",
        help=(
            "Current-revision goal-driven text-MuJoCo summary.json required by "
            "sim-executor release policy."
        ),
    )
    parser.add_argument(
        "--allow-automated-evidence",
        action="store_true",
        help=(
            "Allow synthetic, virtual-mic, or acoustic voice evidence for a "
            "release whose compatibility declaration explicitly narrows the claim."
        ),
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument(
        "--skip-runtime-provenance",
        action="store_true",
        help="Preview only: omit the requirement for live Docker/Ollama provenance",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = prepare_release(args)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[release][error] {exc}", file=sys.stderr)
        return 2
    print(f"Release bundle prepared: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
