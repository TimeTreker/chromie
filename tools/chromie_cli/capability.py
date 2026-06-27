"""Capability manifest checks for the Chromie developer CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .env import Diagnostic, diagnostics_payload, load_env, parse_bool
from .output import CommandResult, ExitCode


FORBIDDEN_FIELD_NAMES = {
    "action_14d",
    "joint_target",
    "joint_targets",
    "motor_command",
    "motor_commands",
    "torque_command",
    "torque_commands",
    "actuator_ctrl",
    "actuator_control",
    "actuator_controls",
    "controller_array",
    "controller_arrays",
    "bus_command",
    "bus_commands",
}


def capability_check(root: Path, manifest: Path | None = None) -> CommandResult:
    root = root.resolve()
    manifest_path = _resolve_manifest_path(root, manifest)
    diagnostics: list[Diagnostic] = []
    payload: dict[str, Any] | None = None

    if not manifest_path.exists():
        diagnostics.append(
            Diagnostic("failure", "manifest_missing", f"Manifest not found: {manifest_path}")
        )
    else:
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
            else:
                diagnostics.append(
                    Diagnostic("failure", "manifest_not_object", "Manifest root must be an object")
                )
        except json.JSONDecodeError as exc:
            diagnostics.append(
                Diagnostic("failure", "manifest_invalid_json", f"Manifest JSON is invalid: {exc}")
            )

    if payload is not None:
        diagnostics.extend(_check_manifest(payload))
        diagnostics.extend(_check_feature_gate_alignment(root, manifest_path))

    failures = [item for item in diagnostics if item.level == "failure"]
    warnings = [item for item in diagnostics if item.level == "warning"]
    if failures:
        status = "failure"
        exit_code = ExitCode.FAILURE
    elif warnings:
        status = "warning"
        exit_code = ExitCode.WARNING
    else:
        status = "ok"
        exit_code = ExitCode.OK

    summary = _manifest_summary(payload)
    return CommandResult(
        status=status,
        message="Capability manifest check complete.",
        details={
            "manifest": str(manifest_path),
            "summary": summary,
            "diagnostics": diagnostics_payload(diagnostics),
        },
        exit_code=exit_code,
    )


def _resolve_manifest_path(root: Path, manifest: Path | None) -> Path:
    if manifest is None:
        return root / "capabilities" / "soridormi.json"
    if manifest.is_absolute():
        return manifest
    return root / manifest


def _check_manifest(payload: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if payload.get("schema_version") in {None, ""}:
        diagnostics.append(
            Diagnostic("failure", "missing_schema_version", "schema_version is missing")
        )
    if payload.get("source") != "soridormi":
        diagnostics.append(
            Diagnostic("warning", "unexpected_source", "Manifest source is not soridormi")
        )

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        diagnostics.append(
            Diagnostic("failure", "missing_metadata", "metadata object is missing")
        )
    else:
        upstream_commit = str(metadata.get("upstream_commit") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", upstream_commit):
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "missing_upstream_commit",
                    "metadata.upstream_commit must be a 40-character hex revision",
                )
            )
        if not metadata.get("upstream_repository"):
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "missing_upstream_repository",
                    "metadata.upstream_repository is missing",
                )
            )

    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        diagnostics.append(
            Diagnostic("failure", "missing_agents", "agents must be a non-empty list")
        )
        return diagnostics

    agent_ids: set[str] = set()
    tool_names: set[str] = set()
    capability_ids: set[str] = set()
    for agent in agents:
        if not isinstance(agent, dict):
            diagnostics.append(
                Diagnostic("failure", "invalid_agent", "agent entries must be objects")
            )
            continue
        agent_id = str(agent.get("agent_id") or "")
        if not agent_id:
            diagnostics.append(Diagnostic("failure", "missing_agent_id", "agent_id is missing"))
        elif agent_id in agent_ids:
            diagnostics.append(
                Diagnostic("failure", "duplicate_agent_id", f"Duplicate agent_id: {agent_id}")
            )
        else:
            agent_ids.add(agent_id)

        tools = agent.get("tools")
        if not isinstance(tools, list):
            diagnostics.append(
                Diagnostic("failure", "invalid_tools", f"{agent_id or '<unknown>'}.tools must be a list")
            )
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                diagnostics.append(
                    Diagnostic("failure", "invalid_tool", "tool entries must be objects")
                )
                continue
            name = str(tool.get("name") or "")
            if not name:
                diagnostics.append(Diagnostic("failure", "missing_tool_name", "tool name is missing"))
            elif name in tool_names:
                diagnostics.append(
                    Diagnostic("failure", "duplicate_tool_name", f"Duplicate tool name: {name}")
                )
            else:
                tool_names.add(name)

            capability_id = str(tool.get("capability_id") or "")
            if capability_id:
                if capability_id in capability_ids:
                    diagnostics.append(
                        Diagnostic(
                            "failure",
                            "duplicate_capability_id",
                            f"Duplicate capability_id: {capability_id}",
                        )
                    )
                capability_ids.add(capability_id)

            if str(tool.get("agent_id") or "") != agent_id:
                diagnostics.append(
                    Diagnostic(
                        "failure",
                        "tool_agent_mismatch",
                        f"{name or '<unnamed>'} agent_id does not match parent agent",
                    )
                )
            diagnostics.extend(_check_tool_contract(tool, name or "<unnamed>"))

    if tool_names:
        diagnostics.append(
            Diagnostic("ok", "tool_count", f"Manifest declares {len(tool_names)} unique tools")
        )
    return diagnostics


def _check_tool_contract(tool: dict[str, Any], tool_name: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for key in ("input_schema", "output_schema"):
        schema = tool.get(key)
        if schema is None:
            continue
        if not isinstance(schema, dict):
            diagnostics.append(
                Diagnostic("failure", "invalid_schema", f"{tool_name}.{key} must be an object")
            )
            continue
        for path, field_name in _schema_property_names(schema, prefix=key):
            if field_name.lower() in FORBIDDEN_FIELD_NAMES:
                diagnostics.append(
                    Diagnostic(
                        "failure",
                        "forbidden_low_level_field",
                        f"{tool_name}.{path} exposes forbidden low-level field {field_name!r}",
                    )
                )
    if tool.get("interaction_executable") is True:
        effects = set(tool.get("effects") or [])
        if "physical_motion" in effects and not _confirmation_required(tool):
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "executable_motion_without_confirmation",
                    f"{tool_name} is interaction-executable physical motion without confirmation",
                )
            )
    return diagnostics


def _schema_property_names(schema: Any, *, prefix: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for name, child in properties.items():
                child_path = f"{prefix}.properties.{name}"
                found.append((child_path, str(name)))
                found.extend(_schema_property_names(child, prefix=child_path))
        for key in ("items", "additionalProperties"):
            if key in schema:
                found.extend(_schema_property_names(schema[key], prefix=f"{prefix}.{key}"))
        for key in ("oneOf", "anyOf", "allOf"):
            variants = schema.get(key)
            if isinstance(variants, list):
                for index, child in enumerate(variants):
                    found.extend(
                        _schema_property_names(child, prefix=f"{prefix}.{key}[{index}]")
                    )
    return found


def _confirmation_required(tool: dict[str, Any]) -> bool:
    confirmation = tool.get("confirmation")
    if isinstance(confirmation, dict):
        return confirmation.get("required") is True or bool(confirmation.get("required_in_modes"))
    return False


def _check_feature_gate_alignment(root: Path, manifest_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    snapshot = load_env(root)
    configured = snapshot.get("ORCH_SORIDORMI_MANIFEST")
    soridormi_enabled = parse_bool(snapshot.get("ORCH_ENABLE_SORIDORMI_SKILLS")) is True
    if soridormi_enabled and configured:
        configured_path = root / configured
        try:
            same_file = configured_path.resolve() == manifest_path.resolve()
        except OSError:
            same_file = False
        if not same_file:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "manifest_not_configured",
                    f"Checking {manifest_path} but ORCH_SORIDORMI_MANIFEST points to {configured}",
                )
            )
    return diagnostics


def _manifest_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    agents = payload.get("agents")
    tool_count = 0
    if isinstance(agents, list):
        for agent in agents:
            if isinstance(agent, dict) and isinstance(agent.get("tools"), list):
                tool_count += len(agent["tools"])
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "schema_version": payload.get("schema_version"),
        "source": payload.get("source"),
        "agent_count": len(agents) if isinstance(agents, list) else 0,
        "tool_count": tool_count,
        "upstream_commit": metadata.get("upstream_commit") if isinstance(metadata, dict) else None,
    }
