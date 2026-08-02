#!/usr/bin/env python3
"""Run and retain Chromie's source-only qualification gates.

This command binds deterministic source checks to one Git revision. It never
claims target, audio, simulator, robot, LAN, or release evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "source_qualification.json"
DEFAULT_OUTPUT_ROOT = ROOT / ".chromie" / "qualification" / "source"


class SourceQualificationError(RuntimeError):
    """Raised when the qualification contract itself is invalid."""


@dataclass(frozen=True)
class Gate:
    gate_id: str
    argv: tuple[str, ...]
    dependency: str = ""
    full_suite: bool = False


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise SourceQualificationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def load_contract(path: Path) -> tuple[tuple[Gate, ...], tuple[str, ...]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceQualificationError(f"cannot read qualification contract: {exc}") from exc
    if payload.get("schema_version") != "1.0":
        raise SourceQualificationError("source qualification schema_version must be 1.0")
    raw_gates = payload.get("gates")
    if not isinstance(raw_gates, list) or not raw_gates:
        raise SourceQualificationError("source qualification gates must be a non-empty list")
    gates: list[Gate] = []
    seen: set[str] = set()
    for raw in raw_gates:
        if not isinstance(raw, dict):
            raise SourceQualificationError("qualification gate must be an object")
        gate_id = str(raw.get("id") or "").strip()
        argv = raw.get("argv")
        if not gate_id or gate_id in seen:
            raise SourceQualificationError(f"qualification gate id is missing or duplicated: {gate_id!r}")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(item, str) and item for item in argv
        ):
            raise SourceQualificationError(f"qualification gate {gate_id} has invalid argv")
        seen.add(gate_id)
        gates.append(
            Gate(
                gate_id=gate_id,
                argv=tuple(argv),
                dependency=str(raw.get("dependency") or "").strip(),
                full_suite=bool(raw.get("full_suite", False)),
            )
        )
    exclusions = payload.get("excluded_target_claims")
    if not isinstance(exclusions, list) or not all(
        isinstance(item, str) and item.strip() for item in exclusions
    ):
        raise SourceQualificationError("excluded_target_claims must be non-empty strings")
    return tuple(gates), tuple(str(item).strip() for item in exclusions)


def _render_argv(argv: Sequence[str]) -> list[str]:
    replacements = {"{python}": sys.executable, "{root}": str(ROOT)}
    return [replacements.get(item, item) for item in argv]


def _bounded(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[-limit:]


def _dependency_unavailable(returncode: int, output: str, dependency: str) -> bool:
    if not dependency or returncode != 2:
        return False
    lowered = output.casefold()
    return "unavailable" in lowered or "install the pinned test dependencies" in lowered


def run_gate(gate: Gate) -> dict[str, Any]:
    argv = _render_argv(gate.argv)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        unavailable = _dependency_unavailable(
            completed.returncode, output, gate.dependency
        )
        status = "passed" if completed.returncode == 0 else "unavailable" if unavailable else "failed"
        returncode = completed.returncode
    except OSError as exc:
        output = str(exc)
        status = "unavailable" if gate.dependency else "failed"
        returncode = None
    return {
        "id": gate.gate_id,
        "argv": argv,
        "status": status,
        "returncode": returncode,
        "dependency": gate.dependency or None,
        "full_suite": gate.full_suite,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        "output_tail": _bounded(output),
    }


def qualify(
    *,
    config_path: Path,
    output_path: Path,
    skip_full_suite: bool,
    allow_dirty: bool,
) -> tuple[int, dict[str, Any]]:
    gates, exclusions = load_contract(config_path)
    revision = _git("rev-parse", "HEAD")
    dirty_paths = tuple(line for line in _git("status", "--porcelain").splitlines() if line)
    selected = tuple(gate for gate in gates if not (skip_full_suite and gate.full_suite))
    results = [run_gate(gate) for gate in selected]
    failed = [item["id"] for item in results if item["status"] == "failed"]
    unavailable = [item["id"] for item in results if item["status"] == "unavailable"]
    clean = not dirty_paths
    source_qualified = not failed and not unavailable and (clean or allow_dirty)
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "source_clean": clean,
        "dirty_paths": list(dirty_paths),
        "source_qualified": source_qualified,
        "status": "passed" if source_qualified else "failed" if failed else "blocked",
        "failed_gates": failed,
        "unavailable_gates": unavailable,
        "skipped_full_suite": skip_full_suite,
        "target_validated": False,
        "release_qualified": False,
        "excluded_target_claims": list(exclusions),
        "gates": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    if source_qualified:
        return 0, report
    return (1 if failed or (dirty_paths and not allow_dirty) else 3), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-full-suite", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or DEFAULT_OUTPUT_ROOT / run_id / "report.json"
    try:
        code, report = qualify(
            config_path=args.config,
            output_path=output,
            skip_full_suite=args.skip_full_suite,
            allow_dirty=args.allow_dirty,
        )
    except SourceQualificationError as exc:
        print(f"[source-qualification][error] {exc}", file=sys.stderr)
        return 2
    print(
        "Source qualification "
        f"{report['status']}: revision={report['revision'][:12]} "
        f"failed={len(report['failed_gates'])} unavailable={len(report['unavailable_gates'])} "
        f"report={output}"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
