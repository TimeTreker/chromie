#!/usr/bin/env python3
"""Run a frozen repeated inference-contention series and summarize the samples.

This wrapper deliberately does not own provider semantics or scheduler policy. It forwards
one already-chosen `qualify_inference_provider.py --contention-only` transaction unchanged,
adds only per-trial output paths, verifies that source identity does not change between
trials, and then invokes the maintained contention summarizer.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
QUALIFIER = ROOT / "scripts" / "qualify_inference_provider.py"
SUMMARIZER = ROOT / "scripts" / "summarize_inference_provider_evidence.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qualify_inference_provider import (  # noqa: E402
    _git_dirty,
    _git_revision,
    _git_worktree_state_sha256,
)


def _source_identity() -> tuple[str | None, bool | None, str | None]:
    return (_git_revision(), _git_dirty(), _git_worktree_state_sha256())


def _normalize_forwarded_args(values: Sequence[str]) -> list[str]:
    args = list(values)
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        raise ValueError("missing qualifier arguments after '--'")
    if any(arg == "--output" or arg.startswith("--output=") for arg in args):
        raise ValueError("do not forward --output; the series runner owns trial output paths")
    if "--contention-only" not in args:
        raise ValueError(
            "series runs require --contention-only so every provider measures the same slice"
        )
    if "--goal-interpreter-probe" in args:
        raise ValueError(
            "do not mix --goal-interpreter-probe into a repeated contention series"
        )
    return args


def _assert_source_unchanged(expected: tuple[str | None, bool | None, str | None]) -> None:
    current = _source_identity()
    if current != expected:
        raise RuntimeError(
            "Chromie source identity changed during contention series: "
            f"expected={expected!r} current={current!r}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "qualifier_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded verbatim after '--' to qualify_inference_provider.py.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.trials <= 0:
        raise SystemExit("--trials must be positive")
    try:
        qualifier_args = _normalize_forwarded_args(args.qualifier_args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    output_dir = args.output_dir.expanduser().resolve()
    summary_output = args.summary_output.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob("trial-*.json"))
    if existing:
        raise SystemExit(
            f"refusing to mix with {len(existing)} existing trial file(s) in {output_dir}"
        )

    frozen_source = _source_identity()
    if frozen_source[0] is None or frozen_source[2] is None:
        raise SystemExit("unable to capture stable Chromie git/worktree identity")

    width = max(3, len(str(args.trials)))
    for index in range(1, args.trials + 1):
        _assert_source_unchanged(frozen_source)
        trial_path = output_dir / f"trial-{index:0{width}d}.json"
        command = [
            sys.executable,
            str(QUALIFIER),
            *qualifier_args,
            "--output",
            str(trial_path),
        ]
        print(f"[contention-series] trial {index}/{args.trials}: {trial_path}")
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode != 0:
            print(
                "[contention-series] qualification trial failed; retained evidence is "
                f"at {trial_path}",
                file=sys.stderr,
            )
            return result.returncode
        _assert_source_unchanged(frozen_source)

    summary_output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SUMMARIZER),
        "--source",
        str(output_dir),
        "--label",
        args.label,
        "--output",
        str(summary_output),
    ]
    print(f"[contention-series] summarize: {summary_output}")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        return result.returncode
    _assert_source_unchanged(frozen_source)
    print(
        "[contention-series] complete "
        f"trials={args.trials} source_revision={frozen_source[0]} "
        f"worktree_sha256={frozen_source[2]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
