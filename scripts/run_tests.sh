#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${INSTALL_TEST_DEPS:-0}" == "1" ]]; then
  python -m pip install -r requirements-test.txt
fi

python -m benchmarks.regression restore-fixtures

python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_host_configuration_ownership.py
python scripts/check_service_configuration_ownership.py
python scripts/check_runtime_structure.py
python scripts/check_docs.py
./scripts/benchmark_check.sh --skip-policy-check

LOG_LEVEL=WARNING AGENT_LOG_LEVEL=WARNING AGENT_USER_MEANING_INTERPRETER_LOG_LEVEL=WARNING \
  python -m pytest -q tests

python scripts/run_legacy_agent_tests.py
