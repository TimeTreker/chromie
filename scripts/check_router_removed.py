#!/usr/bin/env python3
"""Fail closed if the removed Router architecture is reintroduced.

Historical changelog text and retained regression provenance may mention the
former component. Current production topology, environment, APIs, imports, and
architecture documents may not depend on it.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = (
    Path("router"),
    Path("goal_interpretation"),
    Path("orchestrator/clients/router_client.py"),
)
RETIRED_DOCUMENTS = (
    Path("docs/ORCHESTRATOR_TASK_PROPOSAL_MERGE.md"),
    Path("docs/SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md"),
    Path("docs/FAST_COGNITIVE_PLANNING.md"),
    Path("docs/CATALOG_AWARE_GOAL_INTERPRETATION.md"),
    Path("docs/MODEL_ASSISTED_COGNITIVE_GUARDRAILS.md"),
)
RETIRED_CURRENT_TOKENS = (
    "quick_router_review_request",
    "router_action_confidence",
    '"router_mode"',
    "router-agent-contract",
    "router-contract",
    "Router/intent",
    "Compatibility Router/attention",
    "llm_hints.router_contract",
    "tests.test_router_llm_prompt",
    "physical_pending_work_gets_safety_prelude",
    "Tasks emitted by routers are proposals",
    "Router-proposed advisory operations",
    "A Router may propose",
    "The Router must not invent",
    "Router splits the responsibilities",
    "`RouteDecision`, `chromie-agent`, `/route`, `AGENT_GOAL_INTERPRETER_*`",
)
STRUCTURAL_TOKENS = (
    "chromie-router",
    "RouterClient",
    "CHROMIE_BENCHMARK_ROUTER_",
    "ROUTER_URL",
    "ROUTER_PORT",
    "ROUTER_MODEL",
    "ROUTER_REVIEW_MODEL",
    "self.router_url",
    "self.enable_router",
    '"goal_interpretation/requirements.txt"',
    "http://127.0.0.1:8091/route",
    "## Router HTTP API",
    "AGENT_GOAL_INTERPRETER_PORT",
    "AGENT_GOAL_INTERPRETER_HOST",
    "--router-url",
    "assistant.router_client",
    "ORCH_ENABLE_ROUTER",
    "AGENT_GOAL_INTERPRETER_URL",
    "router_prompt_tier",
    "router_semantic_task_operations",
    "router_action_count",
    "router_compound_action_plan",
    "slow_router",
    "The deployed Router remains",
    "service currently named Router",
    "legacy routing path remains deployed",
    "ASR/TTS/Router/Agent",
    "ASR、TTS、Ollama、Router 和 Agent",
    "builds Chromie-owned ASR, TTS, Router, and Agent images",
)
CURRENT_FILES = (
    Path("compose.yml"),
    Path("docker-compose.yml"),
    Path("compose.override.yml"),
    Path(".env.common"),
    Path(".env.local.example"),
    Path("README.md"),
    Path("ROADMAP.md"),
    Path("CHROMIE_RUNBOOK.md"),
    Path("SUPPORT.md"),
    Path("docs/ACCEPTANCE.md"),
    Path("docs/CONFIGURATION.md"),
    Path("docs/USER_OUTCOME_ACCEPTANCE.md"),
    Path("tools/chromie_cli/env.py"),
    Path("tools/chromie_cli/doctor.py"),
    Path("scripts/test_matrix.py"),
    Path("docs/SCENARIO_DRIVEN_DEVELOPMENT.md"),
    Path("scenarios/README.md"),
    Path("orchestrator/orchestrator.py"),
    Path("orchestrator/README.md"),
    Path("agent/README.md"),
    Path("docs/API_REFERENCE.md"),
    Path("docs/COGNITIVE_GATEWAY.md"),
    Path("docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md"),
    Path("scripts/start_chromie.sh"),
    Path("scripts/start_voice_mujoco.sh"),
    Path("scripts/status_voice_mujoco.sh"),
    Path("scripts/interaction_text_mujoco_check.py"),
    Path("scripts/general_ability_acceptance.py"),
    Path("scripts/gpu_smoke_test.sh"),
    Path("scripts/release_provenance.py"),
    Path("benchmarks/manifests/runtime_adapters.json"),
)


def removed_path_has_maintained_content(path: Path) -> bool:
    """Return whether a removed path contains more than ignored cache residue."""

    if path.is_symlink():
        return True
    if not path.exists():
        return False
    if not path.is_dir():
        return True
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if "__pycache__" in relative.parts:
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            return True
    return False


def audit_removed_router(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in FORBIDDEN_PATHS:
        path = root / relative
        if removed_path_has_maintained_content(path):
            errors.append(f"removed Router path contains maintained content: {relative}")
    for relative in RETIRED_DOCUMENTS:
        if (root / relative).exists():
            errors.append(f"retired pre-Core document is still maintained: {relative}")
    for relative in CURRENT_FILES:
        path = root / relative
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in STRUCTURAL_TOKENS:
            if token in text:
                errors.append(
                    f"{relative} contains removed Router structure {token!r}"
                )

    # The active Python import graph may not import a router package or client.
    for base in (
        root / "agent",
        root / "orchestrator",
        root / "shared",
        root / "tools",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if (
                "import router" in text
                or "from router" in text
                or "router_client" in text
            ):
                errors.append(f"{path.relative_to(root)} imports removed Router code")

    # Active code and maintained tests may not use Router-owned metadata or services.
    for base in (
        root / "agent",
        root / "orchestrator",
        root / "shared",
        root / "tools",
        root / "scripts",
        root / "tests",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if (
                path.resolve() == Path(__file__).resolve()
                or path.name.startswith("test_router_removal_")
            ):
                continue
            text = path.read_text(encoding="utf-8")
            for token in (
                "router_client",
                "ORCH_ENABLE_ROUTER",
                "AGENT_GOAL_INTERPRETER_URL",
                "router_prompt_tier",
                "router_semantic_task_operations",
                "router_action_count",
                "router_compound_action_plan",
                "slow_router",
                "primary_router",
                "quick_router",
                "second_router",
                "fast_router",
                "RouterCapability",
                "CapabilityRouter",
                "RouterCore",
                "RouterRegression",
                "RouterRouteDecision",
                "router_ms",
                "_router_",
            ):
                if token in text:
                    errors.append(
                        f"{path.relative_to(root)} contains removed Router contract "
                        f"{token!r}"
                    )

    # Current docs may discuss removal but not claim a deployed Router authority.
    docs_root = root / "docs"
    if docs_root.exists():
        for path in docs_root.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for token in (
                "The deployed Router remains",
                "service currently named Router",
                "legacy routing path remains deployed",
                "ASR/TTS/Router/Agent",
                "ASR、TTS、Ollama、Router 和 Agent",
                "builds Chromie-owned ASR, TTS, Router, and Agent images",
            ):
                if token in text:
                    errors.append(
                        f"{path.relative_to(root)} contains stale "
                        f"current-architecture claim {token!r}"
                    )

    # Retired Router-era contract names may not survive in maintained docs,
    # Roadmap text, or active scenario metadata. Historical changelog/evidence
    # files use explicit provenance wording and are intentionally outside this
    # current-facing scan.
    current_text_paths = [root / "README.md", root / "ROADMAP.md"]
    for base, pattern in ((root / "docs", "*.md"), (root / "scenarios", "*.json")):
        if base.exists():
            current_text_paths.extend(base.rglob(pattern))
    for path in current_text_paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in RETIRED_CURRENT_TOKENS:
            if token in text:
                errors.append(
                    f"{path.relative_to(root)} contains retired Router-era "
                    f"contract or architecture text {token!r}"
                )

    compose_path = root / "docker-compose.yml"
    if compose_path.exists():
        compose_text = compose_path.read_text(encoding="utf-8")
        if compose_text.count("\n  chromie-agent:\n") != 1:
            errors.append(
                "docker-compose.yml must define exactly one chromie-agent service"
            )
        if "8091" in compose_text:
            errors.append(
                "docker-compose.yml still references removed Goal Interpreter "
                "service port 8091"
            )
    return errors


def main() -> int:
    errors = audit_removed_router()
    if errors:
        print("Router removal guard failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 2
    print("Router architecture removal guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
