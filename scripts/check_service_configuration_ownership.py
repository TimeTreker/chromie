#!/usr/bin/env python3
"""Enforce service-owned environment parsing boundaries."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNERS = {
    "asr": ("asr", "asr/settings.py"),
    "tts": ("tts", "tts/settings.py"),
    "agent": ("agent/app", "agent/app/settings.py"),
    "shared-runtime": ("shared/chromie_runtime", "shared/chromie_runtime/settings.py"),
}


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    message: str


def _is_environment_read(node: ast.Call) -> bool:
    function = node.func
    if (
        isinstance(function, ast.Attribute)
        and function.attr == "getenv"
        and isinstance(function.value, ast.Name)
        and function.value.id == "os"
    ):
        return True
    return (
        isinstance(function, ast.Attribute)
        and function.attr in {"get", "__getitem__"}
        and isinstance(function.value, ast.Attribute)
        and isinstance(function.value.value, ast.Name)
        and function.value.value.id == "os"
        and function.value.attr == "environ"
    )


def check(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for service, (service_directory, owner) in OWNERS.items():
        service_root = root / service_directory
        owner_path = root / owner
        if not owner_path.is_file():
            findings.append(Finding(owner, 0, "typed settings owner is missing"))
            continue
        for path in sorted(service_root.rglob("*.py")):
            if path == owner_path or "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _is_environment_read(node):
                    findings.append(
                        Finding(
                            path.relative_to(root).as_posix(),
                            node.lineno,
                            f"{service} environment parsing must be owned by {owner}",
                        )
                    )
    return findings


def main() -> int:
    findings = check()
    if findings:
        for finding in findings:
            print(f"[service-config][error] {finding.path}:{finding.line}: {finding.message}")
        return 1
    print("Service configuration ownership passed: Agent, ASR, TTS, and shared runtime own environment parsing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
