from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .analyzer import compare_reports
from .profiles import StressProfileError


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StressProfileError(f"cannot load stress report {path}: {exc}") from exc
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        raise StressProfileError(f"stress report {path} must use schema_version 1")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare compatible Chromie stress-distribution reports."
    )
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        comparison = compare_reports([_load(path) for path in args.input])
    except StressProfileError as exc:
        print(f"stress comparison error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(comparison, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
