#!/usr/bin/env bash
set -euo pipefail
python -m benchmarks.inventory.core --check
pytest -q benchmarks/tests/test_inventory.py
