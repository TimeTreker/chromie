from __future__ import annotations

import argparse
import json
from pathlib import Path

from .capabilities.loader import build_configured_registry
from .task_graph.executor import DagDryRunExecutor
from .task_graph.models import TaskGraph
from .task_graph.validator import GraphValidator


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or dry-run a Chromie TaskGraph JSON file.")
    parser.add_argument("graph", help="TaskGraph JSON file.")
    parser.add_argument("--manifest", action="append", default=[], help="External capability bundle JSON. May be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Run a deterministic dry-run trace instead of only validating.")
    parser.add_argument("--no-auto-confirm", action="store_true", help="Dry-run confirmation nodes as declined.")
    args = parser.parse_args()

    registry = build_configured_registry(args.manifest).registry
    graph = TaskGraph.model_validate(json.loads(Path(args.graph).read_text(encoding="utf-8")))
    report = GraphValidator(registry).validate(graph)
    if not report.valid:
        print(json.dumps({"valid": False, "errors": report.errors, "warnings": report.warnings}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    if not args.dry_run:
        print(json.dumps({"valid": True, "warnings": report.warnings}, ensure_ascii=False, indent=2))
        return
    trace = DagDryRunExecutor(registry, auto_confirm=not args.no_auto_confirm).run(graph, validate=False)
    print(json.dumps(trace.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
