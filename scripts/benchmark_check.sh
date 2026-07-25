#!/usr/bin/env bash
set -euo pipefail
python -m benchmarks.inventory.core --check
python -m benchmarks.adapters.normalize --check
python -m benchmarks.datasets.social_attention.validate --check
python -m benchmarks.e2e.validate --check
python -m pytest -q benchmarks/tests/test_inventory.py benchmarks/tests/test_contracts.py benchmarks/tests/test_runners.py benchmarks/tests/test_runtime_adapters.py benchmarks/tests/test_cognitive_gateway_terminology.py benchmarks/tests/test_social_attention_dataset.py benchmarks/tests/test_e2e_evidence_profiles.py
python scripts/check_router_removed.py
