#!/usr/bin/env python3
"""Verify maintained Host startup owns every direct Orchestrator environment read."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_SETTINGS = ROOT / "orchestrator" / "runtime" / "host_settings.py"
ORCHESTRATOR = ROOT / "orchestrator" / "orchestrator.py"
BOOTSTRAP_KEYS = {"LOG_LEVEL"}
FORBIDDEN_FACTORIES = {
    "AcceleratorTelemetrySampler.from_env",
    "ConversationStateManager.from_env",
    "EpisodeRecorder.from_env",
    "ExperienceManager.from_env",
    "MindManager.from_env",
    "SystemResourceSampler.from_env",
}
PARSER_NAMES = {
    "_raw",
    "_text",
    "_bool",
    "_int",
    "_float",
    "_choice",
    "_path",
    "_optional_int",
    "_optional_path",
    "_device",
    "_phrases",
}


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _direct_env_keys(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getenv"
            and node.args
        ):
            key = _literal(node.args[0])
            if key:
                keys.add(key)
        elif isinstance(func, ast.Name) and func.id in PARSER_NAMES and len(node.args) >= 2:
            key = _literal(node.args[1])
            if key:
                keys.add(key)
    return keys


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    value: ast.AST = node.func
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def check(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    owned = _direct_env_keys(root / HOST_SETTINGS.relative_to(ROOT))
    discovered: dict[str, list[str]] = {}
    for path in sorted((root / "orchestrator").rglob("*.py")):
        if any(
            part in {"__pycache__", ".git", ".venv", "venv"}
            for part in path.parts
        ):
            continue
        if path == root / HOST_SETTINGS.relative_to(ROOT):
            continue
        for key in sorted(_direct_env_keys(path)):
            discovered.setdefault(key, []).append(path.relative_to(root).as_posix())
    missing = sorted(set(discovered) - owned - BOOTSTRAP_KEYS)
    for key in missing:
        errors.append(
            f"HostSettingsSnapshot does not own {key}; direct readers: "
            + ", ".join(discovered[key])
        )

    tree = ast.parse(
        (root / ORCHESTRATOR.relative_to(ROOT)).read_text(encoding="utf-8"),
        filename=str(ORCHESTRATOR),
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in FORBIDDEN_FACTORIES:
            errors.append(
                f"maintained VoiceAssistant composition still invokes {name}"
            )
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        for error in errors:
            print(f"[host-config][error] {error}", file=sys.stderr)
        return 1
    owned = _direct_env_keys(HOST_SETTINGS)
    print(
        "Host configuration ownership passed: "
        f"typed_keys={len(owned)} bootstrap_keys={len(BOOTSTRAP_KEYS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
