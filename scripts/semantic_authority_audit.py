#!/usr/bin/env python3
"""Audit that Chromie exposes one maintained semantic authority architecture."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.chromie_contracts.semantic_authority import semantic_authority_route_matrix


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def audit() -> dict[str, Any]:
    errors: list[str] = []
    matrix = semantic_authority_route_matrix()
    expected = {
        "orchestrator.handle_routed_text/apply",
        "orchestrator.handle_routed_text/report_only",
    }
    if {str(row.get("entrypoint") or "") for row in matrix} != expected:
        errors.append("semantic authority matrix must contain only maintained Goal-driven entrypoints")
    for row in matrix:
        if row.get("owner") != "goal_driven_runtime":
            errors.append(f"non-canonical semantic owner: {row.get('owner')!r}")
        if row.get("role") not in {"authoritative", "observer"}:
            errors.append(f"invalid maintained semantic role: {row.get('role')!r}")
    apply = next((row for row in matrix if row.get("entrypoint", "").endswith("/apply")), {})
    if apply.get("fallback") != "fail_closed_without_legacy_reentry":
        errors.append("apply path must fail closed without legacy semantic re-entry")

    runtime_mode_surfaces = (".env.common", ".env.example", "scripts/start_chromie.sh")
    for relative in runtime_mode_surfaces:
        text = _read(relative)
        if "ORCH_COGNITIVE_RUNTIME_MODE=apply" not in text:
            errors.append(f"{relative} does not maintain ORCH_COGNITIVE_RUNTIME_MODE=apply")

    fallback_key_surfaces = (
        *runtime_mode_surfaces,
        ".env.local.example",
        "orchestrator/.env.local.example",
    )
    for relative in fallback_key_surfaces:
        text = _read(relative)
        for forbidden in (
            "ORCH_COGNITIVE_FALLBACK_POLICY",
            "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED",
            "AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED",
        ):
            if forbidden in text:
                errors.append(f"{relative} still exposes removed semantic fallback key {forbidden}")

    removed_paths = (
        "agent/app/runtime.py",
        "agent/app/interaction.py",
        "agent/app/dispatcher.py",
        "agent/app/agents",
    )
    for relative in removed_paths:
        path = ROOT / relative
        exists = path.is_file() or (path.is_dir() and any(path.rglob("*.py")))
        if exists:
            errors.append(f"removed legacy Agent runtime still exists: {relative}")

    main = _read("agent/app/main.py")
    for forbidden in ('@app.post("/run"', '@app.post("/interaction"', '@app.get("/agents"'):
        if forbidden in main:
            errors.append(f"legacy Agent production endpoint still exists: {forbidden}")

    orchestrator = _read("orchestrator/orchestrator.py")
    if "_goal_driven_authority_context" not in orchestrator:
        errors.append("Orchestrator is missing Goal-driven authority context")
    for forbidden in (
        "_legacy_agent_authority_context",
        "process_llm_tts",
        "legacy_semantic_fallback",
    ):
        if forbidden in orchestrator:
            errors.append(f"Orchestrator still contains removed semantic rollback surface: {forbidden}")

    cognitive_runtime = _read("orchestrator/runtime/cognitive_runtime.py")
    if 'fallback_policy: Literal["fail_closed"] = "fail_closed"' not in cognitive_runtime and 'fallback_policy: str = "fail_closed"' not in cognitive_runtime:
        errors.append("Goal-driven runtime code default is not fail-closed")
    if '"legacy_fallback"' in cognitive_runtime:
        errors.append("Goal-driven runtime still declares a legacy_fallback status")

    bounded_guards = {
        "single_semantic_authority": not errors,
        "goal_interpretation_owns_what": "Goal Interpretation" in _read("docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md"),
        "planner_owns_how": "Planner" in _read("docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md"),
        "runtime_owns_lifecycle": "Runtime owns lifecycle" in _read("docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md"),
    }
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "semantic_authority_matrix": matrix,
        "bounded_cognition_guards": bounded_guards,
        "single_semantic_authority_enforced": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"semantic-authority-audit: {report['status']}")
        for error in report["errors"]:
            print(f"  - {error}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
