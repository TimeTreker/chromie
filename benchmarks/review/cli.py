from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import apply_semantic_reviews
from benchmarks.review.bundle import write_review_bundle
from benchmarks.review.consensus import (
    VALID_CONSENSUS_POLICIES,
    aggregate_semantic_reviews,
)
from benchmarks.review.judge import judge_review_bundle


def _json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Package, judge, aggregate, or apply semantic review for hybrid "
            "Chromie benchmarks"
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    package = sub.add_parser("package")
    package.add_argument("--normalized", type=Path, required=True)
    package.add_argument("--report", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--artifact-root", type=Path)
    package.add_argument("--include", type=Path, action="append", default=[])
    package.add_argument("--archive", type=Path)

    judge = sub.add_parser("judge")
    judge.add_argument("--bundle", type=Path, required=True)
    judge.add_argument("--reviewers", type=Path, required=True)
    judge.add_argument("--output-dir", type=Path, required=True)
    judge.add_argument("--reviewer", action="append", default=[])
    judge.add_argument("--max-input-chars", type=int, default=120_000)
    judge.add_argument("--max-artifact-chars", type=int, default=20_000)
    judge.add_argument("--dry-run", action="store_true")

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--reviews", type=Path, action="append", required=True)
    aggregate.add_argument(
        "--policy", choices=sorted(VALID_CONSENSUS_POLICIES), default="majority"
    )
    aggregate.add_argument("--minimum-reviewers", type=int, default=2)
    aggregate.add_argument("--minimum-model-families", type=int, default=1)
    aggregate.add_argument("--output", type=Path, required=True)

    apply = sub.add_parser("apply")
    apply.add_argument("--report", type=Path, required=True)
    apply.add_argument("--reviews", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            bundle = write_review_bundle(
                normalized_path=args.normalized,
                report_path=args.report,
                output_dir=args.output_dir,
                artifact_root=args.artifact_root,
                includes=args.include,
                archive_path=args.archive,
            )
            print(
                json.dumps(
                    {
                        "review_scenarios": len(bundle["scenarios"]),
                        "output_dir": str(args.output_dir),
                        "archive": str(args.archive) if args.archive else None,
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "judge":
            report = judge_review_bundle(
                bundle_path=args.bundle,
                reviewer_config_path=args.reviewers,
                output_dir=args.output_dir,
                reviewer_ids=set(args.reviewer) or None,
                max_input_chars=args.max_input_chars,
                max_artifact_chars=args.max_artifact_chars,
                dry_run=args.dry_run,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if report.get("complete") or args.dry_run else 1
        if args.command == "aggregate":
            payload = aggregate_semantic_reviews(
                [_json(path) for path in args.reviews],
                policy=args.policy,
                minimum_reviewers=args.minimum_reviewers,
                minimum_model_families=args.minimum_model_families,
            )
            _write_json(args.output, payload)
            print(args.output)
            return 0
        reviewed = apply_semantic_reviews(_json(args.report), _json(args.reviews))
        _write_json(args.output, reviewed)
        print(args.output)
        return 1 if reviewed["summary"]["fail"] or reviewed["summary"]["error"] else 0
    except ContractError as exc:
        print(f"benchmark review error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
