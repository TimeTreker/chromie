#!/usr/bin/env bash
set -euo pipefail
python -m benchmarks.inventory.core --check
python -m pytest -q benchmarks/tests/test_inventory.py benchmarks/tests/test_contracts.py benchmarks/tests/test_runners.py benchmarks/tests/test_runtime_adapters.py benchmarks/tests/test_cognitive_gateway_terminology.py
