from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .profiles import EvidenceProfileError, EvidenceProfileManifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate E2E evidence profiles")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/manifests/e2e_evidence_profiles.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    try:
        manifest = EvidenceProfileManifest.from_file(path)
    except EvidenceProfileError as exc:
        print(f"E2E evidence profile validation error: {exc}", file=sys.stderr)
        return 2
    summary = {
        "schema_version": 1,
        "profile_count": len(manifest.profiles),
        "profiles": [item.to_dict() for item in manifest.profiles],
    }
    if args.check:
        print(f"E2E evidence profiles valid: {len(manifest.profiles)}")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
