#!/usr/bin/env python3
"""Run file-backed Chromie behavior scenarios and write a comparison report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.behavior_scenarios import (
        DEFAULT_REPORT_ROOT,
        DEFAULT_SCENARIO_ROOT,
        SUPPORTED_SUITES,
        compare_reports,
        load_scenarios,
        run_scenarios_sync,
        write_report,
    )
except ModuleNotFoundError:
    from behavior_scenarios import (
        DEFAULT_REPORT_ROOT,
        DEFAULT_SCENARIO_ROOT,
        SUPPORTED_SUITES,
        compare_reports,
        load_scenarios,
        run_scenarios_sync,
        write_report,
    )


def _print_summary(report: dict[str, object], report_path: Path | None) -> None:
    print(
        "Behavior scenarios: "
        f"{report['passed']}/{report['case_count']} passed "
        f"({report['failed']} failed)"
    )
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            continue
        status = "PASS" if case.get("ok") else "FAIL"
        print(f"  {status} {case.get('key')}: {case.get('description')}")
        if not case.get("ok"):
            for error in case.get("errors", []):
                print(f"    - {error}")
    comparison = report.get("comparison")
    if isinstance(comparison, dict):
        print(
            "Comparison: "
            f"{len(comparison.get('improvements', []))} improvements, "
            f"{len(comparison.get('regressions', []))} regressions, "
            f"{len(comparison.get('new_cases', []))} new cases"
        )
    if report_path is not None:
        print(f"Report: {report_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUPPORTED_SUITES),
        help="Scenario suite to run. Repeatable. Defaults to all suites.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Run a scenario id or suite/id key. Repeatable.",
    )
    parser.add_argument(
        "--scenario-root",
        type=Path,
        default=DEFAULT_SCENARIO_ROOT,
        help="Root directory containing suite subdirectories.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Directory where timestamped summary.json reports are written.",
    )
    parser.add_argument("--baseline", type=Path, help="Previous summary.json to compare against.")
    parser.add_argument("--list", action="store_true", help="List selected scenarios without running them.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--no-write", action="store_true", help="Do not write a report file.")
    parser.add_argument("--allow-failures", action="store_true", help="Return success even when scenarios fail.")
    args = parser.parse_args(argv)

    try:
        scenarios = load_scenarios(
            args.scenario_root,
            suites=set(args.suite) if args.suite else None,
            only=set(args.only) if args.only else None,
        )
    except Exception as exc:
        print(f"scenario load failed: {exc}", file=sys.stderr)
        return 2

    if args.list:
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
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        if report_path is not None:
            print(f"\nReport: {report_path}", file=sys.stderr)
    else:
        _print_summary(report, report_path)
    return 0 if report.get("ok") or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
