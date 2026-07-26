from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.behavior_scenarios import (
    DEFAULT_REPORT_ROOT,
    DEFAULT_SCENARIO_ROOT,
    SUPPORTED_SUITES,
    compare_reports,
    load_scenarios,
    run_scenarios_sync,
    write_report,
)

from .catalog import MigrationError, build_migration_report

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "benchmarks/manifests/scenario_migration_v1.json"


def _summary(report: dict[str, Any], report_path: Path | None) -> None:
    print(
        f"Benchmark scenarios: {report['passed']}/{report['case_count']} passed "
        f"({report['failed']} failed)"
    )
    for case in report.get("cases", []):
        if isinstance(case, dict) and not case.get("ok"):
            print(f"  FAIL {case.get('key')}")
            for error in case.get("errors", []):
                print(f"    - {error}")
    if report_path is not None:
        print(f"Report: {report_path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, list, or run maintained scenarios through the Benchmark Suite."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate migration, count, ID, and provenance parity.")
    check.add_argument("--repo-root", type=Path, default=ROOT)
    check.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    check.add_argument("--output", type=Path)

    for name in ("list", "run"):
        command = sub.add_parser(name)
        command.add_argument("--suite", action="append", choices=sorted(SUPPORTED_SUITES))
        command.add_argument("--only", action="append", default=[])
        command.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
        if name == "run":
            command.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_ROOT)
            command.add_argument("--baseline", type=Path)
            command.add_argument("--json", action="store_true")
            command.add_argument("--no-write", action="store_true")
            command.add_argument("--allow-failures", action="store_true")
    compatibility = sub.add_parser("compatibility", help="Show retained legacy entrypoints and removal gates.")
    compatibility.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        repo_root = args.repo_root.resolve()
        manifest = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
        try:
            report = build_migration_report(repo_root, manifest)
        except MigrationError as exc:
            print(f"scenario migration error: {exc}", file=sys.stderr)
            return 2
        print(
            f"scenario migration parity: {report['inventory_total']} inventory / "
            f"{report['normalized_total']} normalized"
        )
        if args.output:
            output = args.output if args.output.is_absolute() else repo_root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0
    if args.command == "compatibility":
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"cannot load migration manifest: {exc}", file=sys.stderr)
            return 2
        for item in manifest.get("compatibility_entrypoints", []):
            print(f"{item['path']} -> {item['replacement']} [{item['state']}]")
            print(f"  earliest removal: {item['removal_schedule']['earliest_after']}")
        return 0
    try:
        scenarios = load_scenarios(
            args.scenario_root,
            suites=set(args.suite) if args.suite else None,
            only=set(args.only) if args.only else None,
        )
    except Exception as exc:
        print(f"scenario load failed: {exc}", file=sys.stderr)
        return 2
    if args.command == "list":
        for scenario in scenarios:
            print(f"{scenario.key}\t{scenario.description}")
        return 0
    report = run_scenarios_sync(scenarios)
    if args.baseline:
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            report["comparison"] = compare_reports(report, baseline)
        except Exception as exc:
            report["comparison_error"] = f"{exc.__class__.__name__}: {exc}"
    report_path = None if args.no_write else write_report(report, report_dir=args.report_dir)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _summary(report, report_path)
    return 0 if report["failed"] == 0 or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
