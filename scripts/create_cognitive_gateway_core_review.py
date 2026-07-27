#!/usr/bin/env python3
"""Create a fingerprint-bound human-review record template.

This helper does not approve evidence. It binds the exact retained artifacts and
writes every qualitative check as pending so a reviewer must inspect the bundle
and make the decision explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "cognitive_gateway_core_qualification_v1.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create(args: argparse.Namespace) -> dict[str, Any]:
    identity_path = args.runtime_identity.expanduser().resolve()
    live_path = args.live_summary.expanduser().resolve()
    mujoco_path = args.mujoco_summary.expanduser().resolve()
    cancellation_path = args.cancellation_summary.expanduser().resolve()
    identity = _read_json(identity_path)
    manifest = _read_json(args.manifest.expanduser().resolve())
    expected = manifest.get("human_review_expectations")
    checks = (
        expected.get("required_checks")
        if isinstance(expected, dict)
        and isinstance(expected.get("required_checks"), list)
        else []
    )
    payload = {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "runtime_identity_sha256": identity.get("identity_sha256"),
        "artifact_sha256": {
            "live_summary": _sha256(live_path),
            "mujoco_summary": _sha256(mujoco_path),
            "cancellation_summary": _sha256(cancellation_path),
        },
        "reviewer": args.reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "pending",
        "checks": {str(item): "pending" for item in checks},
        "findings": [],
        "notes": "Review the retained responses, traces, cancellation timing, and safe-idle evidence before changing decision.",
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--runtime-identity", type=Path, required=True)
    parser.add_argument("--live-summary", type=Path, required=True)
    parser.add_argument("--mujoco-summary", type=Path, required=True)
    parser.add_argument("--cancellation-summary", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = create(args)
    except Exception as exc:
        print(f"[gateway-core-review][error] {exc}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
