#!/usr/bin/env python3
"""Compatibility redirect to the Benchmark candidate-promotion workflow."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.mining.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["promote", *sys.argv[1:]]))
