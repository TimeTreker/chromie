"""Config commands for the Chromie developer CLI."""

from __future__ import annotations

from pathlib import Path

from .env import (
    diagnostics_payload,
    load_env,
    selected_status_values,
    summarize_diagnostics,
    validate_config,
)
from .output import CommandResult, ExitCode


def config_show(root: Path) -> CommandResult:
    snapshot = load_env(root)
    details = {
        "root": str(snapshot.root),
        "active_profile": snapshot.active_profile,
        "runtime_file_used": snapshot.runtime_file_used,
        "sources": snapshot.sources,
        "values": selected_status_values(snapshot),
    }
    return CommandResult(
        status="ok",
        message="Effective Chromie configuration summary.",
        details=details,
        exit_code=ExitCode.OK,
    )


def config_validate(root: Path) -> CommandResult:
    snapshot = load_env(root)
    diagnostics = validate_config(snapshot)
    status, exit_code = summarize_diagnostics(diagnostics)
    return CommandResult(
        status=status,
        message="Configuration validation complete.",
        details={
            "active_profile": snapshot.active_profile,
            "runtime_file_used": snapshot.runtime_file_used,
            "sources": snapshot.sources,
            "diagnostics": diagnostics_payload(diagnostics),
        },
        exit_code=ExitCode(exit_code),
    )
