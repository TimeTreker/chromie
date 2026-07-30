#!/usr/bin/env python3
"""Run the pinned high-signal Ruff ratchet over its explicit source scope."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
RUFF_VERSION = "0.16.0"
DEFAULT_SCOPE = ROOT / "config" / "ruff_scope.txt"
DEFAULT_CONFIG = ROOT / "ruff.toml"
_VERSION_PATTERN = re.compile(r"^ruff\s+(?P<version>\S+)$")


class RuffGateError(RuntimeError):
    """Raised when the Ruff gate configuration or executable is invalid."""


def load_scope(path: Path, *, root: Path = ROOT) -> tuple[str, ...]:
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuffGateError(f"cannot read Ruff scope {path}: {exc}") from exc

    entries = tuple(
        line.strip()
        for line in raw_lines
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not entries:
        raise RuffGateError("Ruff scope must contain at least one Python path")
    if entries != tuple(sorted(entries)):
        raise RuffGateError("Ruff scope entries must be sorted")
    if len(entries) != len(set(entries)):
        raise RuffGateError("Ruff scope contains duplicate paths")

    for entry in entries:
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuffGateError(f"Ruff scope path must be repository-relative: {entry}")
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise RuffGateError(f"Ruff scope escapes repository root: {entry}") from exc
        if not resolved.exists():
            raise RuffGateError(f"Ruff scope path does not exist: {entry}")
        if resolved.is_file() and resolved.suffix != ".py":
            raise RuffGateError(f"Ruff scope file must be Python: {entry}")
    return entries


def _run(command: Sequence[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuffGateError(
            "Ruff is unavailable; install the pinned test dependencies with "
            "`python -m pip install -r requirements-test.txt`"
        ) from exc


def verify_ruff_version(ruff_command: str = "ruff") -> None:
    completed = _run([ruff_command, "--version"])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuffGateError(f"cannot execute Ruff: {detail or completed.returncode}")
    match = _VERSION_PATTERN.fullmatch(completed.stdout.strip())
    version = match.group("version") if match else ""
    if version != RUFF_VERSION:
        raise RuffGateError(
            f"Ruff version mismatch: expected {RUFF_VERSION}, got {version or 'unknown'}"
        )


def run_ruff(
    *,
    ruff_command: str = "ruff",
    scope_path: Path = DEFAULT_SCOPE,
    config_path: Path = DEFAULT_CONFIG,
) -> int:
    load_scope(scope_path)
    if not config_path.is_file():
        raise RuffGateError(f"Ruff configuration does not exist: {config_path}")
    verify_ruff_version(ruff_command)
    command = [
        ruff_command,
        "check",
        "--config",
        str(config_path),
        f"@{scope_path}",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ruff-command", default="ruff")
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        return run_ruff(
            ruff_command=args.ruff_command,
            scope_path=args.scope,
            config_path=args.config,
        )
    except RuffGateError as exc:
        print(f"[ruff][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
