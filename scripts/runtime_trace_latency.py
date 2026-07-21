#!/usr/bin/env python3
"""Build retained Runtime Trace latency reports and evaluate release gates."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.chromie_runtime.latency_evidence import (  # noqa: E402
    build_latency_report,
    evaluate_latency_gate,
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _git_dirty() -> bool | None:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except Exception:
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize = subparsers.add_parser("summarize", help="build a latency report")
    summarize.add_argument("--source", action="append", required=True)
    summarize.add_argument("--output", required=True)
    summarize.add_argument("--evidence-class", required=True)
    summarize.add_argument("--environment", required=True)
    summarize.add_argument("--label", default="")
    summarize.add_argument("--chromie-revision")
    summarize.add_argument("--include-abandoned", action="store_true")

    gate = subparsers.add_parser("gate", help="compare candidate evidence")
    gate.add_argument("--baseline", required=True)
    gate.add_argument("--candidate", required=True)
    gate.add_argument("--policy", required=True)
    gate.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "summarize":
            report = build_latency_report(
                sources=args.source,
                evidence_class=args.evidence_class,
                environment=args.environment,
                label=args.label,
                chromie_revision=args.chromie_revision or _git_revision(),
                chromie_dirty=_git_dirty(),
                include_abandoned=args.include_abandoned,
            )
            _write_json(Path(args.output).expanduser(), report)
            count = report["source"]["included_trace_count"]
            print(
                f"Runtime Trace latency report: samples={count} "
                f"output={Path(args.output).expanduser()}"
            )
            return 0 if count else 2

        result = evaluate_latency_gate(
            baseline=_read_json(Path(args.baseline).expanduser()),
            candidate=_read_json(Path(args.candidate).expanduser()),
            policy=_read_json(Path(args.policy).expanduser()),
        )
        _write_json(Path(args.output).expanduser(), result)
        print(
            f"Runtime Trace latency gate: status={result['status']} "
            f"output={Path(args.output).expanduser()}"
        )
        if result["status"] == "pass":
            return 0
        if result["status"] == "fail":
            return 1
        return 2
    except Exception as exc:
        print(f"runtime-trace-latency error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
