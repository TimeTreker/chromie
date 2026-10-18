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


_SOURCE_TEXT_READERS = frozenset({"read_text", "read_bytes", "open"})
_SOURCE_INTROSPECTION = frozenset({"getsource", "getsourcelines"})
_PATH_CALLS = frozenset(
    {
        "Path", "PurePath", "PosixPath", "joinpath", "resolve", "absolute",
        "with_name", "with_suffix", "relative_to", "glob", "rglob", "iglob",
        "sorted", "list", "tuple", "set", "items", "keys", "values",
    }
)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_python_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py")


def _is_path_shaped(node: ast.AST) -> bool:
    """Whether an expression only builds, selects or lists paths."""
    if isinstance(node, (ast.Constant, ast.Name, ast.Attribute, ast.JoinedStr)):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
        return _is_path_shaped(node.left) and _is_path_shaped(node.right)
    if isinstance(node, ast.Starred):
        return _is_path_shaped(node.value)
    if isinstance(node, ast.Subscript):
        return _is_path_shaped(node.value)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_path_shaped(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _is_path_shaped(key) for key in node.keys)
    if isinstance(node, ast.Call):
        if _call_name(node) not in _PATH_CALLS:
            return False
        receiver = [node.func.value] if isinstance(node.func, ast.Attribute) else []
        return all(_is_path_shaped(item) for item in [*receiver, *node.args])
    return False


class _SourceReadDetector:
    """Find calls that read Python implementation text in one test module.

    Detected forms: ``inspect.getsource``/``getsourcelines``; ``read_text``,
    ``read_bytes`` or ``open`` on a path built from a ``.py`` literal, from a
    name assigned such a path, from a loop over a ``*.py`` glob, or from a
    module ``__file__``; and calls to a local helper that reads text when passed
    a ``.py`` literal.
    """

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        self.python_path_names = self._python_path_names()
        self.reader_helpers = self._reader_helpers()

    def _mentions_python_path(self, node: ast.AST) -> bool:
        for item in ast.walk(node):
            if _is_python_literal(item):
                return True
            if isinstance(item, ast.Name) and item.id in self.python_path_names:
                return True
            if (
                isinstance(item, ast.Attribute)
                and item.attr == "__file__"
                and not (isinstance(item.value, ast.Name) and item.value.id == "__file__")
            ):
                return True
        return False

    def _python_path_names(self) -> set[str]:
        names: set[str] = set()
        changed = True
        while changed:
            changed = False
            for node in ast.walk(self.tree):
                targets: list[ast.expr] = []
                value: ast.AST | None = None
                if isinstance(node, ast.Assign):
                    targets, value = list(node.targets), node.value
                elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                    targets, value = [node.target], node.value
                elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                    targets, value = [node.target], node.iter
                if value is None:
                    continue
                if not self._mentions_python_path_value(value, names):
                    continue
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name) and item.id not in names:
                            names.add(item.id)
                            changed = True
        return names

    @staticmethod
    def _mentions_python_path_value(value: ast.AST, names: set[str]) -> bool:
        if not _is_path_shaped(value):
            return False
        return any(
            _is_python_literal(item) or (isinstance(item, ast.Name) and item.id in names)
            for item in ast.walk(value)
        )

    def _reader_helpers(self) -> set[str]:
        helpers: set[str] = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(item, ast.Call) and _call_name(item) in _SOURCE_TEXT_READERS
                for item in ast.walk(node)
            ):
                helpers.add(node.name)
        return helpers

    def reads_python_source(self, node: ast.Call) -> bool:
        name = _call_name(node)
        if name in _SOURCE_INTROSPECTION:
            return True
        if name in {"read_text", "read_bytes"} and isinstance(node.func, ast.Attribute):
            return self._mentions_python_path(node.func.value)
        if name == "open" and isinstance(node.func, ast.Name) and node.args:
            return self._mentions_python_path(node.args[0])
        if name in self.reader_helpers and isinstance(node.func, ast.Name):
            return any(_is_python_literal(item) for arg in node.args for item in ast.walk(arg))
        return False


def discover_python_source_readers(root: Path) -> dict[str, tuple[int, ...]]:
    readers: dict[str, tuple[int, ...]] = {}
    for path in sorted((root / "tests").glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue
        detector = _SourceReadDetector(tree)
        lines = tuple(
            sorted(
                node.lineno
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and detector.reads_python_source(node)
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
