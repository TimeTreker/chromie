#!/usr/bin/env python3
"""Enforce explicit ownership for tests that read Python implementation source."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "test_source_ownership.json"
ALLOWED_CATEGORIES = frozenset({"architecture_policy", "generated_artifact_contract"})


@dataclass(frozen=True, order=True)
class SourceReadFinding:
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _literal_python_path(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Constant)
        and isinstance(item.value, str)
        and item.value.endswith(".py")
        for item in ast.walk(node)
    )


def _reads_python_source(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "read_text":
        return _literal_python_path(node.func.value)
    if isinstance(node.func, ast.Name) and node.func.id == "open" and node.args:
        return _literal_python_path(node.args[0])
    return False


def discover_python_source_readers(root: Path) -> dict[str, tuple[int, ...]]:
    readers: dict[str, tuple[int, ...]] = {}
    for path in sorted((root / "tests").glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue
        lines = tuple(
            sorted(
                node.lineno
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and _reads_python_source(node)
            )
        )
        if lines:
            readers[path.relative_to(root).as_posix()] = lines
    return readers


def load_ownership(path: Path, *, root: Path) -> tuple[dict[str, str], list[SourceReadFinding]]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [SourceReadFinding(path.relative_to(root).as_posix(), 0, f"cannot load ownership registry: {exc}")]
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        return {}, [SourceReadFinding(path.relative_to(root).as_posix(), 0, "ownership registry must use schema_version 1.0")]
    items = payload.get("python_source_readers")
    if not isinstance(items, list):
        return {}, [SourceReadFinding(path.relative_to(root).as_posix(), 0, "python_source_readers must be a list")]

    approved: dict[str, str] = {}
    findings: list[SourceReadFinding] = []
    for index, item in enumerate(items):
        location = f"python_source_readers[{index}]"
        if not isinstance(item, dict):
            findings.append(SourceReadFinding(path.relative_to(root).as_posix(), 0, f"{location} must be an object"))
            continue
        test_path = str(item.get("test_path") or "").strip()
        category = str(item.get("category") or "").strip()
        reason = str(item.get("reason") or "").strip()
        candidate = Path(test_path)
        if candidate.is_absolute() or ".." in candidate.parts or not test_path.startswith("tests/test_"):
            findings.append(SourceReadFinding(path.relative_to(root).as_posix(), 0, f"{location} has unsafe test_path"))
            continue
        if category not in ALLOWED_CATEGORIES:
            findings.append(SourceReadFinding(path.relative_to(root).as_posix(), 0, f"{location} has unsupported category {category!r}"))
            continue
        if len(reason) < 40:
            findings.append(SourceReadFinding(path.relative_to(root).as_posix(), 0, f"{location} needs a concrete ownership reason"))
            continue
        if test_path in approved:
            findings.append(SourceReadFinding(path.relative_to(root).as_posix(), 0, f"duplicate ownership entry for {test_path}"))
            continue
        approved[test_path] = category
    return approved, findings


def audit_test_ownership(
    root: Path = ROOT,
    *,
    config_path: Path | None = None,
) -> list[SourceReadFinding]:
    config = config_path or (root / "config" / "test_source_ownership.json")
    approved, findings = load_ownership(config, root=root)
    readers = discover_python_source_readers(root)

    for path, lines in readers.items():
        if path not in approved:
            findings.append(
                SourceReadFinding(
                    path,
                    lines[0],
                    "behavior tests may not inspect Python implementation text; move behavior to executable assertions or register a reviewed architecture/artifact contract",
                )
            )
    for path in approved:
        if path not in readers:
            findings.append(
                SourceReadFinding(
                    config.relative_to(root).as_posix(),
                    0,
                    f"stale source-reading ownership entry: {path}",
                )
            )
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    findings = audit_test_ownership(args.root, config_path=args.config)
    if findings:
        for finding in findings:
            print(f"[test-ownership][error] {finding.render()}", file=sys.stderr)
        return 1
    readers = discover_python_source_readers(args.root)
    print(
        "Test ownership checks passed "
        f"({len(readers)} reviewed Python-source artifact/architecture test files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
