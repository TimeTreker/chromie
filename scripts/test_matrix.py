#!/usr/bin/env python3
"""Run roadmap-aligned Chromie test groups.

This is a Level A convenience runner. It groups existing unit and
dependency-light integration tests by module boundary so a developer can run
one module, several modules, or the complete local suite before moving to the
Level B/C/D evidence commands in docs/ACCEPTANCE.md.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class TestGroup:
    description: str
    commands: tuple[tuple[str, ...], ...]


def _unittest(*modules: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "unittest", "-v", *modules)


GROUPS: dict[str, TestGroup] = {
    "docs": TestGroup(
        "Documentation consistency, ownership, current focus, and API routes.",
        ((sys.executable, "scripts/check_docs.py"),),
    ),
    "asr": TestGroup(
        "ASR transcription executor and import-safe client behavior.",
        (_unittest("tests.test_asr_transcription", "tests.test_client_imports"),),
    ),
    "tts": TestGroup(
        "TTS model-source and cancellable worker behavior.",
        (_unittest("tests.test_tts_model_sources", "tests.test_tts_cancellable_worker"),),
    ),
    "router": TestGroup(
        "Deterministic hard filter, capability routing, model routing, and regressions.",
        (
            _unittest(
                "tests.test_router_core",
                "tests.test_router_capability_routing",
                "tests.test_router_regression_evaluator",
                "tests.test_llm_capability_routing",
                "tests.test_capability_router_actions",
            ),
        ),
    ),
    "behavior": TestGroup(
        "File-backed behavior scenarios for Router and InteractionRuntime.",
        (
            _unittest(
                "tests.test_behavior_scenario_runner",
                "tests.test_behavior_truth_suite",
                "tests.test_scenario_author",
            ),
            (sys.executable, "scripts/scenario_runner.py", "--suite", "router", "--suite", "interaction", "--no-write"),
        ),
    ),
    "agent": TestGroup(
        "Agent contracts, native interaction, capability catalog, and conversation state.",
        (
            _unittest(
                "tests.test_action_execution",
                "tests.test_agent_interaction",
                "tests.test_capability_aware_interaction",
                "tests.test_capability_catalog_service",
                "tests.test_contract_compatibility",
                "tests.test_conversation_state",
                "tests.test_interaction_contracts",
                "tests.test_native_interaction_runtime",
                "tests.test_ollama_client",
            ),
        ),
    ),
    "skill-runtime": TestGroup(
        "Trusted Skill Runtime, confirmation dialogue, evidence, and control-plane flow.",
        (
            _unittest(
                "tests.test_confirmation_dialogue",
                "tests.test_control_plane_integration",
                "tests.test_interaction_control_plane",
                "tests.test_interaction_coordinator",
                "tests.test_session_evidence",
                "tests.test_skill_runtime",
            ),
        ),
    ),
    "taskgraph": TestGroup(
        "TaskGraph validation, scheduling, grants, retention, and execution policy.",
        (
            _unittest(
                "tests.test_guarded_task_graph_execution",
                "tests.test_planning_task_graph_execution",
                "tests.test_read_only_task_graph_execution",
                "tests.test_resource_arbiter",
                "tests.test_task_graph_planning",
                "tests.test_task_graph_retention",
            ),
        ),
    ),
    "soridormi": TestGroup(
        "Soridormi manifest, MCP invocation, provider conformance, and fault behavior.",
        (
            _unittest(
                "tests.test_capability_probe",
                "tests.test_mcp_tool_invoker",
                "tests.test_provider_conformance",
                "tests.test_provider_fault_matrix",
                "tests.test_provider_readiness_verifier",
                "tests.test_soridormi_acceptance",
                "tests.test_soridormi_manifest_materialization",
                "tests.test_soridormi_skill_provider",
            ),
        ),
    ),
    "voice-alpha": TestGroup(
        "Voice-to-MuJoCo alpha acceptance tooling and text-path regression coverage.",
        (
            _unittest(
                "tests.test_interaction_text_acceptance",
                "tests.test_interaction_text_mujoco_check",
                "tests.test_interaction_text_skill_sweep",
                "tests.test_m13_acceptance",
                "tests.test_m5_target_acceptance",
            ),
        ),
    ),
    "release": TestGroup(
        "Release provenance, runtime configuration, Compose, profiles, and gates.",
        (
            _unittest(
                "tests.test_compose_configuration",
                "tests.test_hardware_profile_detection",
                "tests.test_release_provenance",
                "tests.test_robot_candidate_verifier",
                "tests.test_runtime_configuration",
            ),
        ),
    ),
    "legacy-agent": TestGroup(
        "Dependency-light legacy Agent tests.",
        (
            (
                sys.executable,
                "-c",
                (
                    "import inspect, runpy, sys; "
                    "sys.path.insert(0, 'agent'); "
                    "mods=[runpy.run_path('agent/tests/test_capability_registry.py'),"
                    "runpy.run_path('agent/tests/test_task_graph_validator_executor.py')]; "
                    "tests=[f for m in mods for n,f in m.items() "
                    "if n.startswith('test_') and inspect.isfunction(f)]; "
                    "[f() for f in tests]; "
                    "print(f'{len(tests)} legacy Agent tests passed')"
                ),
            ),
        ),
    ),
    "all": TestGroup(
        "Canonical dependency-light local suite.",
        (("./scripts/run_tests.sh",),),
    ),
}

COMBOS: dict[str, tuple[str, ...]] = {
    "local-modules": (
        "docs",
        "asr",
        "tts",
        "router",
        "behavior",
        "agent",
        "skill-runtime",
        "taskgraph",
        "soridormi",
        "voice-alpha",
        "release",
        "legacy-agent",
    ),
    "voice-mujoco-alpha": (
        "docs",
        "asr",
        "tts",
        "router",
        "behavior",
        "agent",
        "skill-runtime",
        "taskgraph",
        "soridormi",
        "voice-alpha",
        "release",
    ),
    "embodiment": ("agent", "skill-runtime", "taskgraph", "soridormi"),
    "frontend-voice": ("asr", "tts", "router", "behavior", "agent", "skill-runtime"),
}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def expand(selection: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in selection:
        if item in COMBOS:
            expanded.extend(COMBOS[item])
        elif item in GROUPS:
            expanded.append(item)
        else:
            valid = sorted([*GROUPS.keys(), *COMBOS.keys()])
            raise SystemExit(f"unknown test group {item!r}; valid: {', '.join(valid)}")
    return _dedupe(expanded)


def print_list() -> None:
    print("Groups:")
    for name in sorted(GROUPS):
        print(f"  {name:18} {GROUPS[name].description}")
    print("\nCombinations:")
    for name in sorted(COMBOS):
        print(f"  {name:18} {', '.join(COMBOS[name])}")


def run_command(command: tuple[str, ...], *, dry_run: bool) -> int:
    print("+ " + " ".join(command), flush=True)
    if dry_run:
        return 0
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("groups", nargs="*", help="Test groups or combinations to run.")
    parser.add_argument("--list", action="store_true", help="List available groups and combinations.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    args = parser.parse_args(argv)

    if args.list:
        print_list()
        return 0

    selected = expand(args.groups or ["all"])
    for name in selected:
        print(f"\n== {name}: {GROUPS[name].description} ==", flush=True)
        for command in GROUPS[name].commands:
            code = run_command(command, dry_run=args.dry_run)
            if code != 0:
                return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
