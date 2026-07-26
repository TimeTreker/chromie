#!/usr/bin/env bash
set -euo pipefail
python -m benchmarks.inventory.core --check
python -m benchmarks.adapters.normalize --check
python -m benchmarks.datasets.social_attention.validate --check
python -m benchmarks.e2e.validate --check
python -m benchmarks.social_attention --check
python -m benchmarks.stress.validate --check
python -m benchmarks.scenarios check
python -m benchmarks.mining.validate --check
python -m pytest -q benchmarks/tests
python scripts/check_router_removed.py
