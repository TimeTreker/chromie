from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import MiningError, load_json, validate_mining_manifest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "benchmarks/manifests/scenario_mining_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate scenario mining and promotion policy.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = load_json(args.manifest)
        validate_mining_manifest(manifest)
    except MiningError as exc:
        print(f"scenario mining validation error: {exc}", file=sys.stderr)
        return 2
    print("scenario mining policy: valid; automatic promotion disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
