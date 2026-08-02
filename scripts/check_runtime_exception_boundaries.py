#!/usr/bin/env python3
"""Verify the symbol-level inventory of broad runtime exception handlers."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("config/runtime_exception_boundaries.json")
RUNTIME_ROOTS = (
    "agent/app",
    "orchestrator",
    "shared/chromie_runtime",
    "shared/chromie_contracts",
)
ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "narrow_reraise",
        "typed_failure_mapping",
        "fail_closed_boundary",
        "diagnostic_cleanup",
    }
)


@dataclass(frozen=True, order=True)
class BroadHandler:
    path: str
    symbol: str
    ordinal: int
    line: int

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.path, self.symbol, self.ordinal)


@dataclass(frozen=True, order=True)
class InventoryFinding:
    path: str
    symbol: str
    line: int
    message: str


def _is_broad(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(_is_broad(item) for item in node.elts)
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[str] = []
        self.counts: dict[str, int] = {}
        self.handlers: list[BroadHandler] = []

    @property
    def symbol(self) -> str:
        return ".".join(self.symbols) if self.symbols else "<module>"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbols.append(node.name)
        self.generic_visit(node)
        self.symbols.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbols.append(node.name)
        self.generic_visit(node)
        self.symbols.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.symbols.append(node.name)
        self.generic_visit(node)
        self.symbols.pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad(node.type):
            ordinal = self.counts.get(self.symbol, 0) + 1
            self.counts[self.symbol] = ordinal
            self.handlers.append(
                BroadHandler(
                    path=self.path,
                    symbol=self.symbol,
                    ordinal=ordinal,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)


def iter_runtime_python(root: Path) -> Iterator[Path]:
    for relative in RUNTIME_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if not any(part in {"__pycache__", ".git"} for part in path.parts):
                yield path


def scan_broad_handlers(root: Path) -> list[BroadHandler]:
    handlers: list[BroadHandler] = []
    for path in iter_runtime_python(root):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _Visitor(relative)
        visitor.visit(tree)
        handlers.extend(visitor.handlers)
    return sorted(handlers)


def load_inventory(path: Path) -> tuple[dict[tuple[str, str, int], dict[str, Any]], list[InventoryFinding]]:
    findings: list[InventoryFinding] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [
            InventoryFinding(
                path=path.as_posix(),
                symbol="<inventory>",
                line=0,
                message=f"cannot load exception inventory: {type(exc).__name__}: {exc}",
            )
        ]
    if payload.get("schema_version") != "1.0":
        findings.append(
            InventoryFinding(
                path=path.as_posix(),
                symbol="<inventory>",
                line=0,
                message="schema_version must be 1.0",
            )
        )
    entries = payload.get("handlers")
    if not isinstance(entries, list):
        return {}, findings + [
            InventoryFinding(
                path=path.as_posix(),
                symbol="<inventory>",
                line=0,
                message="handlers must be an array",
            )
        ]
    inventory: dict[tuple[str, str, int], dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append(
                InventoryFinding(path=path.as_posix(), symbol=f"handlers[{index}]", line=0, message="entry must be an object")
            )
            continue
        entry_path = str(entry.get("path") or "").strip()
        symbol = str(entry.get("symbol") or "").strip()
        ordinal = entry.get("ordinal")
        classification = str(entry.get("classification") or "").strip()
        owner = str(entry.get("owner") or "").strip()
        contract = str(entry.get("contract") or "").strip()
        if not entry_path or not symbol or not isinstance(ordinal, int) or ordinal < 1:
            findings.append(
                InventoryFinding(path=path.as_posix(), symbol=f"handlers[{index}]", line=0, message="path, symbol, and positive ordinal are required")
            )
            continue
        key = (entry_path, symbol, ordinal)
        if key in inventory:
            findings.append(
                InventoryFinding(path=entry_path, symbol=symbol, line=0, message=f"duplicate inventory key ordinal={ordinal}")
            )
            continue
        if classification not in ALLOWED_CLASSIFICATIONS:
            findings.append(
                InventoryFinding(path=entry_path, symbol=symbol, line=0, message=f"invalid classification={classification!r}")
            )
        if not owner or not contract:
            findings.append(
                InventoryFinding(path=entry_path, symbol=symbol, line=0, message="owner and failure contract are required")
            )
        inventory[key] = entry
    return inventory, findings


def audit_runtime_exception_boundaries(
    root: Path = ROOT,
    *,
    inventory_path: Path | None = None,
) -> list[InventoryFinding]:
    root = root.resolve()
    path = inventory_path or (root / DEFAULT_INVENTORY)
    inventory, findings = load_inventory(path)
    live = {handler.key: handler for handler in scan_broad_handlers(root)}
    for key, handler in live.items():
        if key not in inventory:
            findings.append(
                InventoryFinding(
                    path=handler.path,
                    symbol=handler.symbol,
                    line=handler.line,
                    message=(
                        "broad exception handler is not classified in "
                        f"{DEFAULT_INVENTORY.as_posix()} (ordinal={handler.ordinal})"
                    ),
                )
            )
    for key in sorted(set(inventory) - set(live)):
        entry = inventory[key]
        findings.append(
            InventoryFinding(
                path=str(entry["path"]),
                symbol=str(entry["symbol"]),
                line=0,
                message=(
                    "stale broad-exception classification; remove or update "
                    f"ordinal={entry['ordinal']}"
                ),
            )
        )
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    inventory = args.inventory
    if inventory is not None and not inventory.is_absolute():
        inventory = root / inventory
    findings = audit_runtime_exception_boundaries(root, inventory_path=inventory)
    if args.json:
        print(json.dumps({"status": "failed" if findings else "passed", "findings": [item.__dict__ for item in findings]}, ensure_ascii=False, indent=2))
    elif findings:
        for item in findings:
            location = f"{item.path}:{item.line}" if item.line else item.path
            print(f"{location} [{item.symbol}] {item.message}")
    else:
        print("Runtime exception-boundary inventory passed.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
