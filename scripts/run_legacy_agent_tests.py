#!/usr/bin/env python3
"""Run the plain-function legacy Agent tests without pytest.

The tests under ``agent/tests`` use pytest-style functions but no fixtures, so
the default suite runs them directly and stays dependency-light. Both
``scripts/run_tests.sh`` and the ``legacy-agent`` test-matrix group call this.
"""

from __future__ import annotations

import inspect
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "agent/tests/test_capability_registry.py",
    "agent/tests/test_work_dag_validator_engine.py",
)


def main() -> int:
    for path in (ROOT / "agent", ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    tests = [
        function
        for module in (runpy.run_path(str(ROOT / relative)) for relative in MODULES)
        for name, function in module.items()
        if name.startswith("test_") and inspect.isfunction(function)
    ]
    for test in tests:
        test()
    print(f"{len(tests)} legacy Agent tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
