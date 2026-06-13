#!/usr/bin/env python3
"""Prepare a reproducible Chromie alpha release bundle after M13 acceptance."""

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
    from verify_m13_evidence import verify_bundle
except ImportError:  # imported as scripts.prepare_alpha_release in tests/tools
    from scripts.verify_m13_evidence import verify_bundle

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


def prepare_release(args: argparse.Namespace) -> Path:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION is empty")
    notes_path = ROOT / "release" / f"v{version}.md"
    if not notes_path.is_file():
        raise FileNotFoundError(f"Missing release notes: {notes_path}")

    compatibility = read_json(ROOT / "release" / "compatibility.json")
    declared_version = compatibility.get("chromie", {}).get("version")
    if declared_version != version:
        raise ValueError(
            f"Compatibility version {declared_version!r} does not match VERSION {version!r}"
        )
    blockers = compatibility.get("release_gate_blockers")
    if blockers is None:
        blockers = compatibility.get("m13_closure_blockers") or []
    if blockers and not args.preview:
        raise RuntimeError(
            "Release candidate still has tracked blockers:\n- "
            + "\n- ".join(str(item) for item in blockers)
            + "\nUse --preview only for a non-publishable packaging rehearsal."
        )

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    evidence_report = verify_bundle(evidence_dir, require_clean=args.require_clean_evidence)
    if not evidence_report["passed"] and not args.preview:
        raise RuntimeError(
            "Alpha evidence verification failed:\n- "
            + "\n- ".join(evidence_report["errors"])
        )

    revision = git_output("rev-parse", "HEAD")
    short_revision = revision[:12]
    status = git_output("status", "--porcelain")
    dirty = bool(status)
    if dirty and not args.allow_dirty and not args.preview:
        raise RuntimeError(
            "Worktree is dirty. Commit the accepted source before preparing a release, "
            "or use --preview for a non-publishable bundle."
        )

    output_dir = Path(args.output_root).expanduser() / f"v{version}" / short_revision
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Release output already exists: {output_dir}")
    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_tests:
        run_logged(["./scripts/run_tests.sh"], output_dir / "tests.log")

    source_archive = output_dir / f"chromie-{version}.tar.gz"
    create_source_archive(revision, version, source_archive)
    shutil.copy2(notes_path, output_dir / "release-notes.md")
    shutil.copy2(ROOT / "release" / "compatibility.json", output_dir / "compatibility.json")
    shutil.copy2(evidence_dir / "summary.md", output_dir / "m13-acceptance-summary.md")

    publishable = (
        evidence_report["passed"]
        and not dirty
        and not args.preview
        and not blockers
    )
    manifest = {
        "schema_version": 1,
        "generated_utc": utc_now(),
        "version": version,
        "tag": f"v{version}",
        "publishable": publishable,
        "preview": bool(args.preview),
        "chromie": {
            "revision": revision,
            "short_revision": short_revision,
            "dirty": dirty,
            "branch": git_output("branch", "--show-current"),
        },
        "compatibility": compatibility,
        "m13_evidence": evidence_report,
        "artifacts": {
            "source_archive": source_archive.name,
            "release_notes": "release-notes.md",
            "compatibility": "compatibility.json",
            "acceptance_summary": "m13-acceptance-summary.md",
            "tests_log": None if args.skip_tests else "tests.log",
        },
        "publication_steps": [
            f"git tag -s v{version} {revision}",
            f"git push origin v{version}",
            "Create a GitHub prerelease and attach the generated artifacts.",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksum_targets = [
        source_archive,
        output_dir / "release-notes.md",
        output_dir / "compatibility.json",
        output_dir / "m13-acceptance-summary.md",
        output_dir / "manifest.json",
    ]
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
    parser.add_argument("--preview", action="store_true")
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
