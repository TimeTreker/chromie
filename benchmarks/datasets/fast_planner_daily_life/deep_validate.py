#!/usr/bin/env python3
"""Validate the frozen Deep Planner daily-life corpus."""

from __future__ import annotations

import asyncio
import json

from .deep_qualification import validate_dataset


def main() -> int:
    print(json.dumps(asyncio.run(validate_dataset()), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
