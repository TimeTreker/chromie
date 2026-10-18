#!/usr/bin/env bash
set -euo pipefail
# scripts/run_tests.sh runs the repository policy gate first and passes
# --skip-policy-check; standalone benchmark work always runs it.
run_policy_check=1
if [[ "${1:-}" == "--skip-policy-check" ]]; then
  run_policy_check=0
fi
python -m benchmarks.inventory.core --check
python -m benchmarks.adapters.normalize --check
python -m benchmarks.datasets.social_attention.validate --check
python -m benchmarks.e2e.validate --check
python -m benchmarks.social_attention --check
python -m benchmarks.stress.validate --check
python -m benchmarks.scenarios check
python scripts/general_ability_acceptance.py --mode check --no-write --scenario-root scenarios/everyday
python -m benchmarks.mining.validate --check
python -m pytest -q benchmarks/tests
if [[ "$run_policy_check" == "1" ]]; then
  python scripts/check_repository_policies.py
fi
