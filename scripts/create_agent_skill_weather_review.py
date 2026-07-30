#!/usr/bin/env python3
"""Create a fingerprint-bound pending review for live Agent Skill/weather evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "benchmarks" / "manifests" / "agent_skill_weather_qualification_v1.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create(args: argparse.Namespace) -> dict[str, Any]:
    manifest = _read_json(args.manifest.expanduser().resolve())
    runtime_identity = args.runtime_identity.expanduser().resolve()
    live_summary = args.live_summary.expanduser().resolve()
    cognitive_events = args.cognitive_events.expanduser().resolve()
    checks = manifest.get("human_review_checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("qualification manifest has no human_review_checks")
    payload = {
        "schema_version": 1,
        "qualification_id": manifest.get("qualification_id"),
        "reviewer": args.reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": "pending",
        "artifact_sha256": {
            "runtime_identity": _sha256(runtime_identity),
            "live_summary": _sha256(live_summary),
            "cognitive_events": _sha256(cognitive_events),
        },
        "checks": {str(item): "pending" for item in checks},
        "findings": [],
        "notes": (
            "Inspect the retained user responses, terminal Plan provenance, tool "
            "evidence, and Chongqing-to-Neixiang correction before approving."
        ),
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
    parser.add_argument("--cognitive-events", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = create(args)
    except Exception as exc:
        print(f"[agent-skill-weather-review][error] {exc}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
