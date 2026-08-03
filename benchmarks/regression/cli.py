from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.regression.compare import compare_qualification_runs
from benchmarks.regression.replay import (
    load_replay_scenario,
    minimize_replay,
    run_replay,
)


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

    replay = sub.add_parser("replay")
    replay.add_argument("--archive", type=Path, required=True)
    replay.add_argument("--scenario", required=True)
    replay.add_argument("--repo", type=Path, default=Path.cwd())
    replay.add_argument("--output-dir", type=Path, required=True)
    replay.add_argument("--capture", choices=("auto", "monitor", "acoustic"), default="auto")
    replay.add_argument("--start-services", action="store_true")
    replay.add_argument("--timeout", type=float, default=2400.0)

    minimize = sub.add_parser("minimize")
    minimize.add_argument("--archive", type=Path, required=True)
    minimize.add_argument("--scenario", required=True)
    minimize.add_argument("--repo", type=Path, default=Path.cwd())
    minimize.add_argument("--output-dir", type=Path, required=True)
    minimize.add_argument("--capture", choices=("auto", "monitor", "acoustic"), default="auto")
    minimize.add_argument("--start-services", action="store_true")
    minimize.add_argument("--timeout", type=float, default=2400.0)
    minimize.add_argument(
        "--oracle-command",
        nargs=argparse.REMAINDER,
        help=(
            "Optional semantic failure predicate. It receives replay JSON on stdin "
            "and must return {\"failure_reproduced\": boolean}. Without it, "
            "the mechanical failure boundary is used."
        ),
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            payload = compare_qualification_runs(
                args.baseline,
                args.candidate,
                max_relative_regression=args.max_relative_regression,
                absolute_latency_ms=args.absolute_latency_ms,
            )
            _write(args.output, payload)
            print(args.output)
            return 1 if payload["verdict"] == "regression" else 0
        scenario = load_replay_scenario(args.archive, args.scenario)
        repo = args.repo.resolve()
        if args.command == "replay":
            payload = run_replay(
                scenario,
                repo_root=repo,
                output_dir=args.output_dir.resolve(),
                capture=args.capture,
                start_services=args.start_services,
                timeout_s=args.timeout,
            )
            _write(args.output_dir / "replay-report.json", payload)
            print(args.output_dir / "replay-report.json")
            return 0 if payload["returncode"] == 0 else 1
        payload = minimize_replay(
            scenario,
            repo_root=repo,
            output_dir=args.output_dir.resolve(),
            capture=args.capture,
            start_services=args.start_services,
            timeout_s=args.timeout,
            oracle_command=args.oracle_command,
        )
        print(args.output_dir / "minimization-report.json")
        return 0 if payload["minimized_turns"] else 1
    except ContractError as exc:
        print(f"benchmark regression error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
