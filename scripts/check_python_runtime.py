#!/usr/bin/env python3
"""Fail closed when a host runtime cannot import Chromie's Python contracts."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


MINIMUM_PYTHON = (3, 11)


def runtime_is_supported(version: Sequence[int]) -> bool:
    """Return whether *version* satisfies Chromie's declared Python floor."""

    return tuple(version[:2]) >= MINIMUM_PYTHON


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--component",
        default="Chromie",
        help="Operator-facing name for the runtime being checked.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    current = sys.version_info
    rendered = f"{current.major}.{current.minor}.{current.micro}"
    minimum = ".".join(str(part) for part in MINIMUM_PYTHON)
    if not runtime_is_supported(current):
        print(
            f"[{args.component}][error] Python {rendered} is unsupported; "
            f"Python {minimum}+ is required.",
            file=sys.stderr,
        )
        return 1
    print(f"[{args.component}] Python runtime: {rendered} (requires {minimum}+)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
