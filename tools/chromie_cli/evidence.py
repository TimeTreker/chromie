"""Evidence bundle preflight for the Chromie developer CLI."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .env import deployment_mode, load_env, selected_status_values
from .output import CommandResult, ExitCode


METADATA_FILENAMES = ("metadata.json", "summary.json", "manifest.json")


def evidence_bundle(
    root: Path,
    *,
    evidence_root: Path | None = None,
    output: Path | None = None,
) -> CommandResult:
    root = root.resolve()
    if evidence_root is None:
        evidence_root = root / ".chromie" / "acceptance"
    elif not evidence_root.is_absolute():
        evidence_root = root / evidence_root
    evidence_root = evidence_root.resolve()

    snapshot = load_env(root)
    items = _discover_evidence(evidence_root)
    payload = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "chromie": _git_metadata(root),
        "configuration": {
            "mode": deployment_mode(snapshot),
            "active_profile": snapshot.active_profile,
            "runtime_file_used": snapshot.runtime_file_used,
            "values": selected_status_values(snapshot),
        },
        "evidence_root": str(evidence_root),
        "evidence_items": items,
        "evidence_counts": _count_by_level(items),
        "claim_note": (
            "This preflight labels evidence pointers only. It does not convert "
            "automated, dry-run, no-motion, or local reachability output into "
            "target validation or release readiness."
        ),
    }
    if output is not None:
        output_path = output if output.is_absolute() else root / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        payload["written_to"] = str(output_path)

    status = "ok" if items else "warning"
    exit_code = ExitCode.OK if items else ExitCode.WARNING
    message = (
        f"Evidence bundle preflight found {len(items)} evidence item(s)."
        if items
        else "Evidence bundle preflight found no retained evidence items."
    )
    return CommandResult(
        status=status,
        message=message,
        details=payload,
        exit_code=exit_code,
    )


def _discover_evidence(evidence_root: Path) -> list[dict[str, Any]]:
    if not evidence_root.exists():
        return []
    directories: set[Path] = set()
    for filename in METADATA_FILENAMES:
        for path in evidence_root.rglob(filename):
            if path.is_file():
                directories.add(path.parent)
    return [
        _evidence_item(directory, evidence_root)
        for directory in sorted(directories)
    ]


def _evidence_item(directory: Path, evidence_root: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    metadata_file = None
    for filename in METADATA_FILENAMES:
        candidate = directory / filename
        if not candidate.is_file():
            continue
        try:
            loaded = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {"_parse_error": f"{filename} is invalid JSON"}
        if isinstance(loaded, dict):
            metadata.update(loaded)
            metadata_file = filename if metadata_file is None else metadata_file
    level, kind = _classify(directory, metadata)
    relative = directory.relative_to(evidence_root)
    return {
        "path": str(directory),
        "relative_path": str(relative),
        "metadata_file": metadata_file,
        "kind": kind,
        "evidence_level": level,
        "status": metadata.get("status") or metadata.get("result") or metadata.get("passed"),
        "acceptance_id": metadata.get("acceptance_id") or metadata.get("id"),
        "mode": _metadata_mode(metadata),
        "chromie_revision": _metadata_chromie_revision(metadata),
        "release_ready": False,
        "release_ready_reason": "preflight pointer only; use release-specific verifiers",
    }


def _classify(directory: Path, metadata: dict[str, Any]) -> tuple[str, str]:
    path_text = str(directory).lower()
    mode = _metadata_mode(metadata)
    if "text-mujoco" in path_text or "mujoco" in path_text:
        return "C", "live_simulator_or_mcp"
    if mode in {"synthetic", "virtual-mic"}:
        return "A", "automated_voice_acceptance"
    if mode == "supervised":
        return "D", "supervised_audio_acceptance_candidate"
    if "gpu" in path_text:
        return "D", "target_gpu_candidate"
    if "provider" in path_text or "soridormi" in path_text:
        return "C", "provider_contract_or_simulator"
    return "A", "automated_or_local_metadata"


def _metadata_mode(metadata: dict[str, Any]) -> str | None:
    runner = metadata.get("runner")
    if isinstance(runner, dict) and runner.get("mode"):
        return str(runner["mode"])
    mode = metadata.get("mode")
    return str(mode) if mode not in {None, ""} else None


def _metadata_chromie_revision(metadata: dict[str, Any]) -> str | None:
    chromie = metadata.get("chromie")
    if isinstance(chromie, dict) and chromie.get("revision"):
        return str(chromie["revision"])
    revision = metadata.get("chromie_revision") or metadata.get("revision")
    return str(revision) if revision not in {None, ""} else None


def _count_by_level(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for item in items:
        level = str(item.get("evidence_level") or "")
        if level in counts:
            counts[level] += 1
    return counts


def _git_metadata(root: Path) -> dict[str, Any]:
    revision = _git(root, "rev-parse", "HEAD") or "unknown"
    status = _git(root, "status", "--porcelain") or ""
    return {
        "revision": revision,
        "short_revision": revision[:12] if revision != "unknown" else "unknown",
        "branch": _git(root, "branch", "--show-current") or "",
        "dirty": bool(status.strip()),
    }


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
