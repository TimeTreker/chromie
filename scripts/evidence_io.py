"""Small file, JSON, clock, and git helpers shared by evidence scripts.

Scripts run as ``python scripts/<name>.py`` import this module as
``evidence_io``; tests and tools that import ``scripts.<name>`` reach it as
``scripts.evidence_io``. It needs only the standard library and the
repository's own ``shared`` package, so every script can use it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.chromie_runtime.atomic_files import atomic_write_json  # noqa: E402


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of one file, read in 1 MiB chunks."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON file whose top-level value must be an object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def write_json(path: Path, payload: Any) -> None:
    """Atomically write sorted, indented UTF-8 JSON, creating parent directories."""

    atomic_write_json(path, payload)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id() -> str:
    """Return a compact UTC timestamp used to name one evidence run directory."""

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def scenario_turns(inputs: Mapping[str, Any]) -> list[str]:
    """Return the user turns of a scenario that declares exactly one of text or turns."""

    text = inputs.get("text")
    turns = inputs.get("turns")
    if isinstance(text, str) and text.strip() and turns is None:
        return [text.strip()]
    if (
        isinstance(turns, list)
        and turns
        and all(isinstance(item, str) and item.strip() for item in turns)
        and text is None
    ):
        return [item.strip() for item in turns]
    raise ValueError("scenario inputs must contain either non-empty text or non-empty turns")


def git_revision(root: Path = ROOT) -> str | None:
    """Return the HEAD revision of ``root``, or None outside a git checkout."""

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_state(root: Path = ROOT) -> dict[str, Any]:
    """Return the HEAD revision and whether the work tree is dirty."""

    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    return {"revision": revision, "dirty": dirty}
