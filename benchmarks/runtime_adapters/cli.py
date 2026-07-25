from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping, Sequence

from .adapter import RuntimeAdapter, RuntimeAdapterError, encode_observation
from .profiles import COMPONENT_PROFILES, get_component_profile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge a Benchmark Runner request to one configured Chromie component."
    )
    parser.add_argument("--component", required=True, choices=sorted(COMPONENT_PROFILES))
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def _read_request() -> Mapping[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise RuntimeAdapterError(f"stdin does not contain valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeAdapterError("adapter stdin must contain one JSON object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        profile = get_component_profile(args.component)
        adapter = RuntimeAdapter.from_environment(profile, timeout_s=args.timeout)
        observation = adapter.execute(_read_request())
    except (RuntimeAdapterError, ValueError) as exc:
        print(f"benchmark runtime adapter error: {exc}", file=sys.stderr)
        return 2
    print(encode_observation(observation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
