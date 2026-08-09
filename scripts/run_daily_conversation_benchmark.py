#!/usr/bin/env python3
"""Execute the maintained daily-conversation cohort and retain semantic review input."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import shlex
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.adapters.legacy_json import normalize_json_file  # noqa: E402
from benchmarks.contracts import ContractError  # noqa: E402
from benchmarks.review.bundle import write_review_bundle  # noqa: E402
from benchmarks.runners.core import BenchmarkRunner, select_cases  # noqa: E402
from benchmarks.runners.executors import CommandExecutor  # noqa: E402
from benchmarks.runners.models import RunProfile  # noqa: E402


DATASET_DIR = Path("benchmarks/datasets/daily_conversation")
SCENARIO_GLOB = "scenarios/**/*.json"


def _default_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(".chromie/benchmarks/daily-conversation") / timestamp


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scenario_paths(dataset_dir: Path) -> list[Path]:
    paths = sorted(path for path in dataset_dir.glob(SCENARIO_GLOB) if path.is_file())
    if not paths:
        raise ContractError(
            f"daily-conversation dataset contains no files matching {SCENARIO_GLOB!r}"
        )
    return paths


def _load_cases(repo_root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: dict[str, Path] = {}
    for path in _scenario_paths(repo_root / DATASET_DIR):
        for case in normalize_json_file(
            path,
            repo_root=repo_root,
            layer="integration",
            datasets=("daily_conversation",),
            evidence_requirements=("static", "live_model"),
        ):
            scenario_id = case["id"]
            prior = seen.get(scenario_id)
            if prior is not None:
                raise ContractError(
                    f"duplicate daily-conversation scenario {scenario_id!r}: "
                    f"{prior} and {path}"
                )
            seen[scenario_id] = path
            cases.append(case)
    return cases


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Chromie's Git-controlled daily-conversation scenarios through an "
            "explicit project adapter and package the retained outputs for semantic review."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--command",
        required=True,
        help=(
            "project adapter command; receives one normalized scenario as JSON on stdin "
            "and returns one benchmark observation as JSON on stdout"
        ),
    )
    parser.add_argument("--model", required=True, help="candidate model identity")
    parser.add_argument(
        "--prompt-revision", required=True, help="candidate prompt/configuration revision"
    )
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--id", action="append", default=[], help="run one scenario ID")
    parser.add_argument("--cohort", action="append", default=[])
    parser.add_argument("--language", action="append", default=[])
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir or _default_output_dir()
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    try:
        cases = _load_cases(repo_root)
        selected = select_cases(
            cases,
            ids=set(args.id) or None,
            cohorts=set(args.cohort) or None,
            languages=set(args.language) or None,
        )
        if not selected:
            raise ContractError("no daily-conversation scenarios matched the filters")

        normalized = {
            "schema_version": 1,
            "generated_from": f"{DATASET_DIR.as_posix()}/{SCENARIO_GLOB}",
            "cases": selected,
        }
        normalized_path = output_dir / "normalized.json"
        report_path = output_dir / "run.json"
        review_dir = output_dir / "review"
        _write_json(normalized_path, normalized)

        profile = RunProfile(
            mode="live_model",
            evidence_level="live_model",
            model=args.model,
            prompt_revision=args.prompt_revision,
            metadata={"dataset": "chromie.daily_conversation.v1"},
        )
        report = BenchmarkRunner(
            CommandExecutor(shlex.split(args.command), timeout_s=args.timeout_s),
            profile,
        ).run(selected)
        _write_json(report_path, report)
        bundle = write_review_bundle(
            normalized_path=normalized_path,
            report_path=report_path,
            output_dir=review_dir,
        )
    except (ContractError, OSError, ValueError) as exc:
        print(f"daily conversation benchmark error: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(
        json.dumps(
            {
                "executed": summary["total"],
                "hard_pass_pending_semantic_review": summary["review"],
                "hard_fail": summary["fail"],
                "execution_error": summary["error"],
                "review_scenarios": len(bundle["scenarios"]),
                "run_report": str(report_path),
                "review_bundle": str(review_dir / "review-bundle.json"),
                "review_template": str(review_dir / "review-template.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if summary["fail"] or summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(run())
