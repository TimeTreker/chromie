from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmarks.adapters.normalize import normalize_config

from .catalog import build_candidate_catalog, discover_candidates
from .models import (
    MiningError,
    create_review_record,
    load_json,
    validate_candidate,
    validate_mining_manifest,
)
from .promote import promote_candidate
from .variations import build_variation_briefs

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "benchmarks/manifests/scenario_mining_v1.json"
DEFAULT_CONFIG = ROOT / "benchmarks/manifests/suites.json"


def _manifest(path: Path) -> dict:
    value = load_json(path)
    validate_mining_manifest(value)
    return value


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index, review, vary, and promote mined Benchmark candidates.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index")
    index.add_argument("--candidate-dir", type=Path, action="append", default=[])
    index.add_argument("--output", type=Path)

    review = sub.add_parser("review")
    review.add_argument("candidate", type=Path)
    review.add_argument("--decision", choices=("approved", "rejected"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--output", type=Path, required=True)

    variations = sub.add_parser("variations")
    variations.add_argument("candidate", type=Path)
    variations.add_argument("--axis", action="append", required=True, help="axis=value; repeatable")
    variations.add_argument("--output", type=Path, required=True)

    promote = sub.add_parser("promote")
    promote.add_argument("candidate", type=Path)
    promote.add_argument("--review", type=Path, required=True)
    promote.add_argument("--scenario-root", type=Path, default=ROOT / "scenarios")
    promote.add_argument("--suite")
    promote.add_argument("--id")
    promote.add_argument("--allow-related", action="store_true")
    promote.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = _manifest(args.manifest)
        if args.command == "index":
            roots = args.candidate_dir or [ROOT / item for item in manifest["candidate_roots"]]
            normalized = normalize_config(ROOT, DEFAULT_CONFIG)["cases"]
            candidates = discover_candidates(roots, manifest)
            report = build_candidate_catalog(candidates, normalized, manifest)
            print(
                f"candidate catalog: {report['candidate_count']} candidates / "
                f"{report['committed_scenario_count']} committed scenarios"
            )
            if args.output:
                _write(args.output, report)
            return 0
        candidate = load_json(args.candidate)
        validate_candidate(candidate, manifest)
        if args.command == "review":
            review = create_review_record(
                candidate,
                decision=args.decision,
                reviewer=args.reviewer,
                rationale=args.rationale,
            )
            _write(args.output, review)
            print(args.output)
            return 0
        if args.command == "variations":
            requested: list[tuple[str, str]] = []
            for raw in args.axis:
                if "=" not in raw:
                    raise MiningError("variation axes must use axis=value")
                axis, value = raw.split("=", 1)
                requested.append((axis.strip(), value.strip()))
            briefs = build_variation_briefs(candidate, requested, manifest)
            _write(args.output, {"schema_version": 1, "variations": briefs})
            print(args.output)
            return 0
        target, _ = promote_candidate(
            args.candidate,
            args.review,
            manifest,
            scenario_root=args.scenario_root,
            target_id=args.id,
            suite=args.suite,
            allow_related=args.allow_related,
            dry_run=args.dry_run,
        )
        print(target)
        print(f"validate: python scripts/scenario_author.py validate {target}")
        print(f"run: python -m benchmarks.scenarios run --only {target.parent.name}/{target.stem} --no-write")
        return 0
    except MiningError as exc:
        print(f"scenario mining error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
