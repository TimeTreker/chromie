from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import apply_semantic_reviews
from benchmarks.review.bundle import write_review_bundle


def _json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package or apply semantic review for hybrid Chromie benchmarks"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    package = sub.add_parser("package")
    package.add_argument("--normalized", type=Path, required=True)
    package.add_argument("--report", type=Path, required=True)
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--artifact-root", type=Path)
    package.add_argument("--include", type=Path, action="append", default=[])
    package.add_argument("--archive", type=Path)

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
        reviewed = apply_semantic_reviews(_json(args.report), _json(args.reviews))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(reviewed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(args.output)
        return 1 if reviewed["summary"]["fail"] or reviewed["summary"]["error"] else 0
    except ContractError as exc:
        print(f"benchmark review error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
