from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from benchmarks.contracts import ContractError
from benchmarks.runners.core import BenchmarkRunner, load_normalized_cases, select_cases
from benchmarks.runners.executors import CommandExecutor, ReplayExecutor
from benchmarks.runners.models import RunProfile


def run_cli(default_layers: set[str] | None = None, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run normalized Chromie benchmark scenarios")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--normalized", type=Path)
    source.add_argument("--inventory", type=Path)
    parser.add_argument("--layer", action="append", default=[])
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--mode", choices=("replay", "live_model"), required=True)
    parser.add_argument("--replay-file", type=Path)
    parser.add_argument("--command", help="explicit adapter command for live_model mode")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--model")
    parser.add_argument("--prompt-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    normalized = args.normalized
    inventory = args.inventory
    if normalized is not None and not normalized.is_absolute():
        normalized = repo_root / normalized
    if inventory is not None and not inventory.is_absolute():
        inventory = repo_root / inventory
    try:
        cases = load_normalized_cases(
            repo_root, normalized_path=normalized, inventory_path=inventory
        )
        layers = set(args.layer) or default_layers
        selected = select_cases(
            cases,
            layers=layers,
            datasets=set(args.dataset) or None,
            ids=set(args.id) or None,
        )
        if not selected:
            raise ContractError("no scenarios matched the requested benchmark cohort")
        if args.mode == "replay":
            if args.replay_file is None or args.command:
                raise ContractError("replay mode requires --replay-file and forbids --command")
            replay_path = args.replay_file
            if not replay_path.is_absolute():
                replay_path = repo_root / replay_path
            executor = ReplayExecutor.from_file(replay_path)
            evidence_level = "replay"
        else:
            if not args.command or args.replay_file is not None:
                raise ContractError("live_model mode requires --command and forbids --replay-file")
            executor = CommandExecutor(shlex.split(args.command), timeout_s=args.timeout_s)
            evidence_level = "live_model"
        report = BenchmarkRunner(
            executor,
            RunProfile(
                mode=args.mode,
                evidence_level=evidence_level,
                model=args.model,
                prompt_revision=args.prompt_revision,
            ),
        ).run(selected)
    except ContractError as exc:
        print(f"benchmark runner error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output.relative_to(repo_root))
    else:
        sys.stdout.write(rendered)
    return 1 if report["summary"]["fail"] or report["summary"]["error"] else 0
