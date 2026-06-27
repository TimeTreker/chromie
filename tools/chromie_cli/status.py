"""Runtime status summary command for the Chromie developer CLI."""

from __future__ import annotations

from pathlib import Path

from .env import deployment_mode, load_env, selected_status_values, validate_config
from .output import CommandResult, ExitCode


def status(root: Path) -> CommandResult:
    snapshot = load_env(root)
    diagnostics = validate_config(snapshot)
    failures = [item for item in diagnostics if item.level == "failure"]
    warnings = [item for item in diagnostics if item.level == "warning"]
    if failures:
        result_status = "failure"
        exit_code = ExitCode.FAILURE
    elif warnings:
        result_status = "warning"
        exit_code = ExitCode.WARNING
    else:
        result_status = "ok"
        exit_code = ExitCode.OK

    mode = deployment_mode(snapshot)
    details = {
        "mode": mode,
        "active_profile": snapshot.active_profile,
        "runtime_file_used": snapshot.runtime_file_used,
        "physical_execution": "disabled"
        if not snapshot.bool_value("AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION")
        else "unsupported_enabled",
        "structured_interaction": "enabled"
        if snapshot.bool_value("ORCH_ENABLE_INTERACTION_RESPONSE")
        else "compatibility_rollback",
        "soridormi_skills": "enabled"
        if snapshot.bool_value("ORCH_ENABLE_SORIDORMI_SKILLS")
        else "disabled",
        "risk_summary": {
            "physical_task_graph": snapshot.get(
                "AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION", "0"
            ),
            "guarded_task_graph": snapshot.get(
                "AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION", "0"
            ),
            "legacy_action_dry_run": snapshot.get("ORCH_ACTION_DRY_RUN", "true"),
        },
        "values": selected_status_values(snapshot),
        "failures": [item.message for item in failures],
        "warnings": [item.message for item in warnings],
    }
    return CommandResult(
        status=result_status,
        message=f"Chromie runtime status: {mode}.",
        details=details,
        exit_code=exit_code,
    )
