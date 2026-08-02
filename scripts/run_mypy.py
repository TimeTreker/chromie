#!/usr/bin/env python3
"""Run the pinned incremental Mypy ratchet over owned files and packages."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
MYPY_VERSION = "2.3.0"
DEFAULT_SCOPE = ROOT / "config" / "mypy_scope.txt"
DEFAULT_CONFIG = ROOT / "mypy.ini"
_VERSION_PATTERN = re.compile(r"^mypy\s+(?P<version>\S+)(?:\s+.*)?$")


class MypyGateError(RuntimeError):
    """Raised when the incremental Mypy gate cannot run safely."""


def load_scope(path: Path, *, root: Path = ROOT) -> tuple[str, ...]:
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MypyGateError(f"cannot read Mypy scope {path}: {exc}") from exc

    entries = tuple(
        line.strip()
        for line in raw_lines
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not entries:
        raise MypyGateError("Mypy scope must contain at least one Python module")
    if entries != tuple(sorted(entries)):
        raise MypyGateError("Mypy scope entries must be sorted")
    if len(entries) != len(set(entries)):
        raise MypyGateError("Mypy scope contains duplicate paths")

    expanded: list[str] = []
    for entry in entries:
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise MypyGateError(f"Mypy scope path must be repository-relative: {entry}")
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise MypyGateError(f"Mypy scope escapes repository root: {entry}") from exc
        if resolved.is_file():
            if resolved.suffix != ".py":
                raise MypyGateError(
                    f"Mypy scope file entry must be Python source: {entry}"
                )
            expanded.append(candidate.as_posix())
            continue
        if not resolved.is_dir() or not (resolved / "__init__.py").is_file():
            raise MypyGateError(
                f"Mypy scope entry must be a Python file or package: {entry}"
            )
        package_files = sorted(
            path.relative_to(root).as_posix()
            for path in resolved.rglob("*.py")
            if "__pycache__" not in path.parts
        )
        if not package_files:
            raise MypyGateError(f"Mypy package scope is empty: {entry}")
        expanded.extend(package_files)

    if len(expanded) != len(set(expanded)):
        raise MypyGateError(
            "Mypy scope entries overlap; package and file entries must not select "
            "the same module twice"
        )
    return tuple(sorted(expanded))


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
        raise MypyGateError(
            "Mypy is unavailable; install the pinned test dependencies with "
            "`python -m pip install -r requirements-test.txt`"
        ) from exc


def verify_mypy_version(mypy_command: str = "mypy") -> None:
    completed = _run([mypy_command, "--version"])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise MypyGateError(f"cannot execute Mypy: {detail or completed.returncode}")
    match = _VERSION_PATTERN.fullmatch(completed.stdout.strip())
    version = match.group("version") if match else ""
    if version != MYPY_VERSION:
        raise MypyGateError(
            f"Mypy version mismatch: expected {MYPY_VERSION}, got {version or 'unknown'}"
        )


def run_mypy(
    *,
    mypy_command: str = "mypy",
    scope_path: Path = DEFAULT_SCOPE,
    config_path: Path = DEFAULT_CONFIG,
) -> int:
    entries = load_scope(scope_path)
    if not config_path.is_file():
        raise MypyGateError(f"Mypy configuration does not exist: {config_path}")
    verify_mypy_version(mypy_command)
    command = [
        mypy_command,
        "--config-file",
        str(config_path),
        *entries,
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mypy-command", default="mypy")
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        return run_mypy(
            mypy_command=args.mypy_command,
            scope_path=args.scope,
            config_path=args.config,
        )
    except MypyGateError as exc:
        print(f"[mypy][error] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
