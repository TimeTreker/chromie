from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.regression.compare import compare_qualification_runs


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Chromie qualification archives")
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--max-relative-regression", type=float, default=0.20)
    compare.add_argument("--absolute-latency-ms", type=float, default=100.0)
    args = parser.parse_args(argv)
    try:
        payload = compare_qualification_runs(
            args.baseline,
            args.candidate,
            max_relative_regression=args.max_relative_regression,
            absolute_latency_ms=args.absolute_latency_ms,
        )
        _write(args.output, payload)
        print(args.output)
        return 1 if payload["verdict"] == "regression" else 0
    except ContractError as exc:
        print(f"benchmark regression error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
