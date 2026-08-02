#!/usr/bin/env python3
"""Enforce monotonic VoiceAssistant ownership and compatibility ratchets."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/runtime_structure_ratchets.json"


def _self_attributes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    attributes: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        targets: Iterable[ast.expr]
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = (node.target,)
        for target in targets:
            for item in ast.walk(target):
                if (
                    isinstance(item, ast.Attribute)
                    and isinstance(item.value, ast.Name)
                    and item.value.id == "self"
                ):
                    attributes.add(item.attr)
    return attributes


def _parent_functions(tree: ast.AST) -> dict[int, str]:
    parents: dict[int, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            parents[id(child)] = node.name
    return parents


def check() -> list[str]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rule = config["voice_assistant"]
    source_path = ROOT / rule["path"]
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    class_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == rule["class_name"]
        ),
        None,
    )
    if class_node is None:
        return [f"missing class {rule['class_name']} in {rule['path']}"]

    methods = [
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    properties = [
        node
        for node in methods
        if any(isinstance(item, ast.Name) and item.id == "property" for item in node.decorator_list)
    ]
    init = next((node for node in methods if node.name == "__init__"), None)
    if init is None:
        return ["VoiceAssistant.__init__ is missing"]

    init_attributes = _self_attributes(init)
    errors: list[str] = []
    measurements = {
        "method_count": len(methods),
        "property_count": len(properties),
        "init_lines": int(init.end_lineno or init.lineno) - init.lineno + 1,
        "init_self_attributes": len(init_attributes),
    }
    maximums = {
        "method_count": int(rule["max_method_count"]),
        "property_count": int(rule["max_property_count"]),
        "init_lines": int(rule["max_init_lines"]),
        "init_self_attributes": int(rule["max_init_self_attributes"]),
    }
    for name, value in measurements.items():
        if value > maximums[name]:
            errors.append(f"{name} grew to {value}; ratchet maximum is {maximums[name]}")

    for collaborator in rule["required_collaborators"]:
        if collaborator not in init_attributes:
            errors.append(f"VoiceAssistant.__init__ must own collaborator {collaborator!r}")
    forbidden = sorted(set(rule["forbidden_init_state_attributes"]) & init_attributes)
    if forbidden:
        errors.append(
            "lifecycle-owned state returned to VoiceAssistant.__init__: "
            + ", ".join(forbidden)
        )

    parent_functions = _parent_functions(class_node)
    direct_calls: list[tuple[int, str]] = []
    for node in ast.walk(class_node):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and function.attr == "process_llm_tts"
            and isinstance(function.value, ast.Name)
            and function.value.id == "self"
        ):
            direct_calls.append((node.lineno, parent_functions.get(id(node), "<class>")))
    owner = str(rule["direct_llm_compatibility_owner"])
    for line, parent in direct_calls:
        if parent != owner:
            errors.append(
                f"direct LLM compatibility call at {rule['path']}:{line} "
                f"is owned by {parent}, expected {owner}"
            )

    if errors:
        return errors
    print(
        "Runtime structure ratchets passed: "
        + " ".join(f"{key}={value}" for key, value in measurements.items())
        + f" direct_llm_calls={len(direct_calls)}"
    )
    return []


def main() -> int:
    errors = check()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
