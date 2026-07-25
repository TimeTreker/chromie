#!/usr/bin/env bash
set -euo pipefail
python -m benchmarks.inventory.core --check
python -m pytest -q benchmarks/tests/test_inventory.py benchmarks/tests/test_contracts.py
