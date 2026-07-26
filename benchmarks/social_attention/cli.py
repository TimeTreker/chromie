from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmarks.contracts import ContractError
from benchmarks.runners.core import load_normalized_cases

from .qualification import (
    QualificationError,
    build_qualification_report,
    load_manifest,
    load_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or build the Social Attention baseline qualification report."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/manifests/social_attention_qualification_v1.json"),
    )
    parser.add_argument("--normalized", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        action="append",
        default=[],
        help=(
            "E2E report for one homogeneous launcher-effective mode/style slice. "
            "Repeat to assemble the complete baseline bundle."
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()

    def resolved(path: Path | None) -> Path | None:
        if path is None:
            return None
        return path if path.is_absolute() else repo_root / path

    try:
        manifest = load_manifest(resolved(args.manifest))
        if args.check:
            if args.report or args.normalized or args.inventory or args.output:
                raise QualificationError("--check validates only the qualification manifest")
            print(
                f"validated {len(manifest['hard_gates'])} Social Attention hard gates"
            )
            return 0
        if not args.report or bool(args.normalized) == bool(args.inventory):
            raise QualificationError(
                "qualification report requires --report and exactly one of "
                "--normalized or --inventory"
            )
        cases = load_normalized_cases(
            repo_root,
            normalized_path=resolved(args.normalized),
            inventory_path=resolved(args.inventory),
        )
        report = build_qualification_report(
            manifest=manifest,
            cases=cases,
            e2e_reports=[load_report(resolved(path)) for path in args.report],
        )
    except (QualificationError, ContractError) as exc:
        print(f"Social Attention qualification error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = resolved(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        try:
            print(output.relative_to(repo_root))
        except ValueError:
            print(output)
    else:
        sys.stdout.write(rendered)
    return 0 if report["qualification"]["state"] == "human_review_required" else 1


if __name__ == "__main__":
    raise SystemExit(main())
