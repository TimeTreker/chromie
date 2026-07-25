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
    ROOT / "goal_interpretation",
    ROOT / "orchestrator/clients/router_client.py",
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
)
CURRENT_FILES = (
    ROOT / "compose.yml",
    ROOT / "docker-compose.yml",
    ROOT / "compose.override.yml",
    ROOT / ".env.common",
    ROOT / ".env.local.example",
    ROOT / "README.md",
    ROOT / "ROADMAP.md",
    ROOT / "CHROMIE_RUNBOOK.md",
    ROOT / "SUPPORT.md",
    ROOT / "docs/ACCEPTANCE.md",
    ROOT / "docs/SCENARIO_DRIVEN_DEVELOPMENT.md",
    ROOT / "scenarios/README.md",
    ROOT / "orchestrator/orchestrator.py",
    ROOT / "orchestrator/README.md",
    ROOT / "agent/README.md",
    ROOT / "docs/API_REFERENCE.md",
    ROOT / "docs/COGNITIVE_GATEWAY.md",
    ROOT / "docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md",
    ROOT / "scripts/start_chromie.sh",
    ROOT / "scripts/start_voice_mujoco.sh",
    ROOT / "scripts/status_voice_mujoco.sh",
    ROOT / "scripts/interaction_text_mujoco_check.py",
    ROOT / "scripts/general_ability_acceptance.py",
    ROOT / "scripts/deep_thought_response_check.py",
    ROOT / "scripts/gpu_smoke_test.sh",
    ROOT / "scripts/release_provenance.py",
    ROOT / "benchmarks/manifests/runtime_adapters.json",
)

errors: list[str] = []
for path in FORBIDDEN_PATHS:
    if path.exists():
        errors.append(f"removed Router path exists: {path.relative_to(ROOT)}")
for path in CURRENT_FILES:
    if not path.exists():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    for token in STRUCTURAL_TOKENS:
        if token in text:
            errors.append(f"{path.relative_to(ROOT)} contains removed Router structure {token!r}")

# The active Python import graph may not import a router package or client.
for base in (ROOT / "agent", ROOT / "orchestrator", ROOT / "shared", ROOT / "tools"):
    if not base.exists():
        continue
    for path in base.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import router" in text or "from router" in text or "router_client" in text:
            errors.append(f"{path.relative_to(ROOT)} imports removed Router code")


compose_path = ROOT / "docker-compose.yml"
if compose_path.exists():
    compose_text = compose_path.read_text(encoding="utf-8")
    if compose_text.count("\n  chromie-agent:\n") != 1:
        errors.append("docker-compose.yml must define exactly one chromie-agent service")
    if "8091" in compose_text:
        errors.append("docker-compose.yml still references removed Goal Interpreter service port 8091")

if errors:
    print("Router removal guard failed:", file=sys.stderr)
    for error in sorted(set(errors)):
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(2)
print("Router architecture removal guard passed")
