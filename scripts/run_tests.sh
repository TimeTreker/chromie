#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${INSTALL_TEST_DEPS:-0}" == "1" ]]; then
  python -m pip install -r requirements-test.txt
fi

python -m unittest discover -s tests -v

# The original Agent tests use plain pytest-style functions but do not depend on
# pytest fixtures. Run them directly so the default suite stays dependency-light.
PYTHONPATH=agent python - <<'PY'
import inspect
import runpy

modules = [
    runpy.run_path("agent/tests/test_capability_registry.py"),
    runpy.run_path("agent/tests/test_task_graph_validator_executor.py"),
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
