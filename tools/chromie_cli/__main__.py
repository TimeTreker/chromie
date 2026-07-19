"""Command entry point for Chromie's developer usability CLI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TextIO

from .capability import capability_check
from .config import config_show, config_validate
from .doctor import doctor
from .evidence import evidence_bundle
from .output import CommandResult, ExitCode, write_result
from .status import status
from .trace import trace_view


class ChromieArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(int(ExitCode.USAGE), f"{self.prog}: error: {message}\n")


def _run_status(command: str, args: argparse.Namespace) -> CommandResult:
    return status(args.root)


def _run_doctor(command: str, args: argparse.Namespace) -> CommandResult:
    return doctor(args.root)


def _run_config_show(command: str, args: argparse.Namespace) -> CommandResult:
    return config_show(args.root)


def _run_config_validate(command: str, args: argparse.Namespace) -> CommandResult:
    return config_validate(args.root)


def _run_capability_check(command: str, args: argparse.Namespace) -> CommandResult:
    return capability_check(
        args.root,
        args.manifest,
        live=args.live,
        timeout_s=args.timeout_s,
        excluded_effects=frozenset(args.exclude_effect),
    )


def _run_evidence_bundle(command: str, args: argparse.Namespace) -> CommandResult:
    return evidence_bundle(
        args.root,
        evidence_root=args.evidence_root,
        output=args.output,
    )


def _run_trace_view(command: str, args: argparse.Namespace) -> CommandResult:
    return trace_view(
        args.root,
        trace_root=args.trace_root,
        source_file=args.file,
        session=args.session,
        interaction=args.interaction,
        graph=args.graph,
        trace=args.trace,
        limit=args.limit,
    )


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = ChromieArgumentParser(
        prog="chromie",
        description="Chromie developer usability tools.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write machine-readable JSON output",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to inspect",
    )

    subparsers = parser.add_subparsers(dest="command_name", metavar="COMMAND")
    status_parser = subparsers.add_parser(
        "status",
        help="summarize configured deployment mode and safety gates",
    )
    status_parser.set_defaults(handler=_run_status, command="status")
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="run environment, file, service, Soridormi, and audio checks",
    )
    doctor_parser.set_defaults(handler=_run_doctor, command="doctor")

    config = subparsers.add_parser("config", help="inspect or validate configuration")
    config_subparsers = config.add_subparsers(dest="config_command", metavar="COMMAND")
    config_show_parser = config_subparsers.add_parser(
        "show",
        help="print the effective Chromie runtime configuration",
    )
    config_show_parser.set_defaults(handler=_run_config_show, command="config show")
    config_validate_parser = config_subparsers.add_parser(
        "validate",
        help="validate configuration without starting the stack",
    )
    config_validate_parser.set_defaults(
        handler=_run_config_validate,
        command="config validate",
    )

    capability = subparsers.add_parser("capability", help="inspect capability manifests")
    capability_subparsers = capability.add_subparsers(
        dest="capability_command",
        metavar="COMMAND",
    )
    capability_check_parser = capability_subparsers.add_parser(
        "check",
        help="audit a capability manifest and optionally compare its live MCP schema",
    )
    capability_check_parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest path relative to --root; default capabilities/soridormi.json",
    )
    capability_check_parser.add_argument(
        "--live",
        action="store_true",
        help="probe the configured MCP endpoint and compare its advertised schemas",
    )
    capability_check_parser.add_argument(
        "--timeout-s",
        type=_positive_float,
        default=10.0,
        help="live MCP probe timeout in seconds; default 10",
    )
    capability_check_parser.add_argument(
        "--exclude-effect",
        action="append",
        default=[],
        help="exclude manifest tools with this effect from the live comparison",
    )
    capability_check_parser.set_defaults(
        handler=_run_capability_check,
        command="capability check",
    )

    evidence = subparsers.add_parser("evidence", help="inspect evidence readiness")
    evidence_subparsers = evidence.add_subparsers(
        dest="evidence_command",
        metavar="COMMAND",
    )
    evidence_bundle_parser = evidence_subparsers.add_parser(
        "bundle",
        help="prepare evidence bundle metadata and preflight output",
    )
    evidence_bundle_parser.add_argument(
        "--evidence-root",
        type=Path,
        default=None,
        help="evidence root to scan; default .chromie/acceptance under --root",
    )
    evidence_bundle_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional JSON output path",
    )
    evidence_bundle_parser.set_defaults(
        handler=_run_evidence_bundle,
        command="evidence bundle",
    )

    trace = subparsers.add_parser("trace", help="inspect retained trace artifacts")
    trace_subparsers = trace.add_subparsers(dest="trace_command", metavar="COMMAND")
    trace_view_parser = trace_subparsers.add_parser(
        "view",
        help="view retained session, interaction, Skill Runtime, and TaskGraph traces",
    )
    trace_view_parser.add_argument(
        "--trace-root",
        type=Path,
        default=None,
        help="trace root to scan; default .chromie/acceptance under --root",
    )
    trace_view_parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="single JSON or JSONL trace artifact to inspect",
    )
    trace_view_parser.add_argument(
        "--session",
        default=None,
        help="filter by Orchestrator session id",
    )
    trace_view_parser.add_argument(
        "--interaction",
        default=None,
        help="filter by InteractionResponse or Skill Runtime interaction id",
    )
    trace_view_parser.add_argument(
        "--graph",
        default=None,
        help="filter by TaskGraph graph id",
    )
    trace_view_parser.add_argument(
        "--trace",
        default=None,
        help="filter by Skill Runtime trace id",
    )
    trace_view_parser.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="maximum summarized records per artifact",
    )
    trace_view_parser.set_defaults(handler=_run_trace_view, command="trace view")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    parser = build_parser()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(stderr)
        return int(ExitCode.USAGE)

    result = handler(getattr(args, "command"), args)
    write_result(result, stream=stdout, json_output=args.json)
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
