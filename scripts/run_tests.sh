#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${INSTALL_TEST_DEPS:-0}" == "1" ]]; then
  python -m pip install -r requirements-test.txt
fi

python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_host_configuration_ownership.py
python scripts/check_service_configuration_ownership.py
python scripts/check_runtime_structure.py
python scripts/check_docs.py
./scripts/benchmark_check.sh

LOG_LEVEL=WARNING AGENT_LOG_LEVEL=WARNING AGENT_GOAL_INTERPRETER_LOG_LEVEL=WARNING \
  python -m unittest discover -s tests

# The original Agent tests use plain pytest-style functions but do not depend on
# pytest fixtures. Run them directly so the default suite stays dependency-light.
PYTHONPATH=agent python - <<'PY'
import inspect
import runpy

modules = [
    runpy.run_path("agent/tests/test_capability_registry.py"),
    runpy.run_path("agent/tests/test_work_dag_validator_engine.py"),
]

tests = [
    function
    for module in modules
    for name, function in module.items()
    if name.startswith("test_")
    and inspect.isfunction(function)
]

for test in tests:
    test()

print(f"{len(tests)} legacy Agent tests passed")
PY
