from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.faults.runner import run_fault_manifest, run_repeated_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run controlled Chromie faults or repeated qualifications")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--repeat", type=int, default=1)
    repeat = sub.add_parser("repeat")
    repeat.add_argument("--count", type=int, default=5)
    repeat.add_argument("--timeout", type=float, default=3600.0)
    repeat.add_argument("--output-dir", type=Path, required=True)
    repeat.add_argument("command_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_fault_manifest(args.manifest, output=args.output, repeat=args.repeat)
            print(args.output)
            return 0 if report["summary"]["consistent_fail"] == 0 and report["summary"]["intermittent"] == 0 else 1
        command = list(args.command_args)
        if command and command[0] == "--":
            command = command[1:]
        report = run_repeated_command(
            command,
            count=args.count,
            output_dir=args.output_dir,
            timeout_s=args.timeout,
        )
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        return 0 if report["status"] == "consistent_pass" else 1
    except ContractError as exc:
        print(f"fault qualification error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
