from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from benchmarks.contracts import ContractError
from benchmarks.evidence.sanitize import sanitize_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a privacy-sanitized Chromie evidence archive")
    sub = parser.add_subparsers(dest="command", required=True)
    sanitize = sub.add_parser("sanitize")
    sanitize.add_argument("--input", type=Path, required=True)
    sanitize.add_argument("--output", type=Path, required=True)
    sanitize.add_argument("--exclude-audio", action="store_true")
    sanitize.add_argument("--redact-value", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        report = sanitize_evidence(
            args.input,
            output_archive=args.output,
            exclude_audio=args.exclude_audio,
            redact_values=args.redact_value,
        )
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        print(args.output)
        return 0 if report["safe_to_upload"] else 1
    except ContractError as exc:
        print(f"evidence sanitization error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
