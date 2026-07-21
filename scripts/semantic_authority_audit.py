#!/usr/bin/env python3
"""Audit Chromie's single-semantic-authority boundary without live services.

This check is intentionally GPU-free. It verifies the machine-readable route
matrix, maintained profile defaults, emergency fallback gates, and source-level
fail-closed invariants. Live model and MuJoCo validation remain separate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.chromie_contracts.semantic_authority import (
        semantic_authority_route_matrix,
    )
except ImportError:
    from chromie_contracts.semantic_authority import semantic_authority_route_matrix


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def audit() -> dict[str, Any]:
    errors: list[str] = []
    matrix = semantic_authority_route_matrix()

    expected_entrypoints = {
        "orchestrator.handle_routed_text/apply (mapped lane allowlisted)",
        "orchestrator.handle_routed_text/apply (mapped lane excluded)",
        "orchestrator.handle_routed_text/report_only",
        "agent./interaction with exact Router actions",
        "agent./interaction or /run emergency compatibility",
        "post_interrupt_correction/apply (mapped lane allowlisted)",
        "post_interrupt_correction/compatibility (mapped lane excluded)",
    }
    actual_entrypoints = {str(row.get("entrypoint") or "") for row in matrix}
    if actual_entrypoints != expected_entrypoints:
        errors.append(
            "semantic authority route matrix does not cover the maintained entrypoints"
        )

    for row in matrix:
        role = str(row.get("role") or "")
        if role not in {"authoritative", "observer", "adapter"}:
            errors.append(f"invalid role in route matrix: {role!r}")
        if not row.get("planner_path"):
            errors.append(f"missing planner path for {row.get('entrypoint')!r}")

    apply_rows = [
        row
        for row in matrix
        if row.get("entrypoint")
        in {
            "orchestrator.handle_routed_text/apply (mapped lane allowlisted)",
            "post_interrupt_correction/apply (mapped lane allowlisted)",
        }
    ]
    for row in apply_rows:
        if row.get("owner") != "goal_driven_runtime":
            errors.append(
                f"apply entrypoint has non-goal authority: {row.get('entrypoint')}"
            )
        if row.get("fallback") != "fail_closed_after_authority_acquisition":
            errors.append(
                f"apply entrypoint can widen authority after acquisition: {row.get('entrypoint')}"
            )

    excluded_rows = [
        row
        for row in matrix
        if row.get("entrypoint")
        in {
            "orchestrator.handle_routed_text/apply (mapped lane excluded)",
            "post_interrupt_correction/compatibility (mapped lane excluded)",
        }
    ]
    for row in excluded_rows:
        if row.get("owner") != "legacy_agent_pipeline":
            errors.append(
                "excluded mapped lane does not remain on the legacy Agent path: "
                f"{row.get('entrypoint')}"
            )
        if row.get("fallback") != "not_applicable_before_authority_acquisition":
            errors.append(
                "excluded mapped lane is not identified as pre-acquisition: "
                f"{row.get('entrypoint')}"
            )

    maintained_defaults = {
        "ORCH_COGNITIVE_RUNTIME_MODE": "apply",
        "ORCH_COGNITIVE_FALLBACK_POLICY": "fail_closed",
        "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED": "0",
        "AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED": "0",
    }
    for relative in (".env.common", ".env.example"):
        text = _read(relative)
        for key, value in maintained_defaults.items():
            if f"{key}={value}" not in text:
                errors.append(f"{relative} does not maintain {key}={value}")

    launcher = _read("scripts/start_chromie.sh")
    for key, value in maintained_defaults.items():
        if f"{key}={value}" not in launcher:
            errors.append(f"scripts/start_chromie.sh does not force {key}={value}")

    capability = _read("agent/app/agents/capability.py")
    for required in (
        "if direct_actions:",
        'planning_result": "legacy_semantic_planner_disabled"',
        "legacy_capability_fallback_enabled",
        'authority.owner == "legacy_capability_fallback"',
        "authority.emergency_fallback",
    ):
        if required not in capability:
            errors.append(f"CapabilityAgent authority guard missing: {required}")

    conversation = _read("agent/app/agents/conversation.py")
    for forbidden in (
        "_ensure_factual_subject_anchor",
        "The Sun is roughly spherical.",
        "The Sun is extremely hot.",
    ):
        if forbidden in conversation:
            errors.append(
                "ConversationAgent contains an entity-specific factual rewrite: "
                f"{forbidden}"
            )

    cognitive_runtime = _read("orchestrator/runtime/cognitive_runtime.py")
    if '"legacy_fallback"' in cognitive_runtime:
        errors.append("goal-driven runtime still declares a legacy_fallback status")
    if 'fallback_policy: str = "fail_closed"' not in cognitive_runtime:
        errors.append("goal-driven runtime code default is not fail_closed")

    orchestrator = _read("orchestrator/orchestrator.py")
    for required in (
        "_goal_driven_authority_context",
        "_legacy_agent_authority_context",
        '"status": "error"',
        "post_interrupt_compatibility_path",
    ):
        if required not in orchestrator:
            errors.append(f"Orchestrator authority boundary missing: {required}")

    if orchestrator.count("context=agent_context") < 4:
        errors.append(
            "Orchestrator does not pass an explicit authority claim through every "
            "/interaction and /run compatibility call site"
        )

    return {
        "schema_version": 1,
        "status": "pass" if not errors else "fail",
        "single_semantic_authority_enforced": not errors,
        "gpu_required": False,
        "live_model_or_robot_evidence_included": False,
        "entrypoints": matrix,
        "maintained_defaults": maintained_defaults,
        "offline_equivalence_evidence": {
            "exact_router_actions": (
                "deterministic adapter path; semantic LLM call forbidden"
            ),
            "legacy_capability_planner": (
                "retained only behind host gate, Agent gate, and per-turn "
                "emergency authority claim"
            ),
            "goal_driven_failure": (
                "fail-closed after authority acquisition; no same-turn legacy re-entry"
            ),
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit non-zero on failure")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit()
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 1 if args.check and report["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
