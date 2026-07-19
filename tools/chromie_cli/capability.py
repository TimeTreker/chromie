"""Read-only capability contract auditing for the Chromie developer CLI."""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import contextmanager
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

VALID_SAFETY_CLASSES = {
    "safe_read",
    "planning_only",
    "low_risk_action",
    "physical_motion",
    "safety_critical",
    "restricted",
}

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def capability_check(
    root: Path,
    manifest: Path | None = None,
    *,
    live: bool = False,
    timeout_s: float = 10.0,
    excluded_effects: frozenset[str] = frozenset(),
) -> CommandResult:
    """Audit one authoritative capability manifest and optionally its live MCP surface.

    The command is deliberately read-only. It does not register capabilities, import
    provider implementations, execute package content, or grant any execution authority.
    """

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
                diagnostics.append(
                    Diagnostic(
                        "ok",
                        "manifest_json_valid",
                        f"Manifest JSON parsed successfully: {manifest_path}",
                    )
                )
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

    static_failed = any(item.level == "failure" for item in diagnostics)
    static_validation = {
        "status": "failure" if static_failed else "ok",
        "reason_code": "static_contract_failed" if static_failed else "static_contract_passed",
    }

    live_details: dict[str, Any]
    if not live:
        live_details = {
            "requested": False,
            "status": "not_requested",
            "reason_code": "live_probe_not_requested",
            "endpoints": [],
        }
    elif static_failed or payload is None:
        live_details = {
            "requested": True,
            "status": "skipped",
            "reason_code": "live_probe_skipped_static_failure",
            "endpoints": [],
        }
        diagnostics.append(
            Diagnostic(
                "warning",
                "live_probe_skipped_static_failure",
                "Live provider probe was skipped because the static contract is invalid.",
            )
        )
    else:
        live_details, live_diagnostics = _run_live_probe(
            root,
            manifest_path,
            timeout_s=timeout_s,
            excluded_effects=excluded_effects,
        )
        diagnostics.extend(live_diagnostics)

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

    return CommandResult(
        status=status,
        message="Capability contract audit complete.",
        details={
            "manifest": str(manifest_path),
            "summary": _manifest_summary(payload),
            "static_validation": static_validation,
            "live_probe": live_details,
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
    if not str(payload.get("source") or "").strip():
        diagnostics.append(Diagnostic("failure", "missing_source", "source is missing"))

    metadata = payload.get("metadata")
    if payload.get("source") == "soridormi":
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

        diagnostics.extend(
            _check_semantic_version(
                agent.get("version"),
                code="invalid_agent_version",
                label=f"{agent_id or '<unknown>'}.version",
            )
        )
        diagnostics.extend(_check_transport(agent, agent_id or "<unknown>"))

        tools = agent.get("tools")
        if not isinstance(tools, list):
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "invalid_tools",
                    f"{agent_id or '<unknown>'}.tools must be a list",
                )
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


def _check_semantic_version(value: Any, *, code: str, label: str) -> list[Diagnostic]:
    version = str(value or "")
    if not _SEMVER.fullmatch(version):
        return [
            Diagnostic(
                "failure",
                code,
                f"{label} must be a semantic version such as 0.1.0",
            )
        ]
    return []


def _check_transport(agent: dict[str, Any], agent_id: str) -> list[Diagnostic]:
    transport = agent.get("transport")
    if not isinstance(transport, dict):
        return [
            Diagnostic(
                "failure",
                "missing_transport",
                f"{agent_id}.transport must be an object",
            )
        ]
    kind = str(transport.get("kind") or "")
    if not kind:
        return [
            Diagnostic("failure", "missing_transport_kind", f"{agent_id}.transport.kind is missing")
        ]
    if kind in {"mcp_streamable_http", "streamable_http"} and not str(
        transport.get("url") or ""
    ).strip():
        return [
            Diagnostic(
                "failure",
                "missing_transport_url",
                f"{agent_id} uses {kind} but transport.url is missing",
            )
        ]
    return []


def _check_tool_contract(tool: dict[str, Any], tool_name: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(
        _check_semantic_version(
            tool.get("version"),
            code="invalid_tool_version",
            label=f"{tool_name}.version",
        )
    )

    for key in ("input_schema", "output_schema"):
        schema = tool.get(key)
        if not isinstance(schema, dict):
            diagnostics.append(
                Diagnostic("failure", "invalid_schema", f"{tool_name}.{key} must be an object")
            )
            continue
        if schema.get("type") != "object":
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "schema_root_not_object",
                    f"{tool_name}.{key}.type must be 'object'",
                )
            )
        for path, field_name in _schema_property_names(schema, prefix=key):
            if field_name.lower() in FORBIDDEN_FIELD_NAMES:
                diagnostics.append(
                    Diagnostic(
                        "failure",
                        "forbidden_low_level_field",
                        f"{tool_name}.{path} exposes forbidden low-level field {field_name!r}",
                    )
                )

    effects_raw = tool.get("effects")
    effects = {
        str(effect).strip()
        for effect in effects_raw
        if str(effect).strip()
    } if isinstance(effects_raw, list) else set()
    if not effects:
        diagnostics.append(
            Diagnostic("failure", "missing_effects", f"{tool_name}.effects must be non-empty")
        )

    safety_class = str(tool.get("safety_class") or "")
    if safety_class not in VALID_SAFETY_CLASSES:
        diagnostics.append(
            Diagnostic(
                "failure",
                "invalid_safety_class",
                f"{tool_name}.safety_class is invalid: {safety_class or '<missing>'}",
            )
        )

    for field_name in (
        "availability",
        "execution",
        "confirmation",
        "monitoring",
        "default_failure_policy",
    ):
        if not isinstance(tool.get(field_name), dict):
            diagnostics.append(
                Diagnostic(
                    "failure",
                    f"missing_{field_name}",
                    f"{tool_name}.{field_name} must be an object",
                )
            )

    if "physical_motion" in effects and safety_class not in {
        "physical_motion",
        "safety_critical",
    }:
        diagnostics.append(
            Diagnostic(
                "failure",
                "physical_effect_safety_mismatch",
                f"{tool_name} declares physical_motion without a physical safety class",
            )
        )
    if safety_class == "physical_motion" and "physical_motion" not in effects:
        diagnostics.append(
            Diagnostic(
                "failure",
                "physical_class_effect_mismatch",
                f"{tool_name} uses physical_motion safety class without physical_motion effect",
            )
        )
    if "safety_control" in effects and safety_class != "safety_critical":
        diagnostics.append(
            Diagnostic(
                "failure",
                "safety_control_class_mismatch",
                f"{tool_name} declares safety_control but is not safety_critical",
            )
        )
    if "planning_only" in effects and safety_class != "planning_only":
        diagnostics.append(
            Diagnostic(
                "failure",
                "planning_effect_class_mismatch",
                f"{tool_name} declares planning_only but does not use planning_only safety class",
            )
        )

    if tool.get("interaction_executable") is True:
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


def _run_live_probe(
    root: Path,
    manifest_path: Path,
    *,
    timeout_s: float,
    excluded_effects: frozenset[str],
) -> tuple[dict[str, Any], list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    snapshot = load_env(root)
    try:
        with _temporary_environment(snapshot.values):
            results = asyncio.run(
                _probe_live_registry(
                    manifest_path,
                    timeout_s=timeout_s,
                    excluded_effects=excluded_effects,
                )
            )
    except ImportError as exc:
        diagnostics.append(
            Diagnostic(
                "failure",
                "live_probe_dependency_missing",
                f"Live MCP probe dependencies are unavailable: {exc}",
            )
        )
        return {
            "requested": True,
            "status": "failure",
            "reason_code": "live_probe_dependency_missing",
            "endpoints": [],
        }, diagnostics
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                "failure",
                "live_probe_failed",
                f"Live MCP probe failed: {type(exc).__name__}: {exc}",
            )
        )
        return {
            "requested": True,
            "status": "failure",
            "reason_code": "live_probe_failed",
            "endpoints": [],
            "error_type": type(exc).__name__,
        }, diagnostics

    endpoints: list[dict[str, Any]] = []
    endpoint_failed = False
    endpoint_warning = False
    for result in results:
        mismatch_details = {
            name: list(items)
            for name, items in result.schema_mismatch_details.items()
        }
        schema_warnings = {
            name: list(items)
            for name, items in result.schema_warnings.items()
        }
        endpoint_has_failure = bool(result.missing_tools or result.schema_mismatches)
        endpoint_has_warning = bool(result.extra_tools or schema_warnings)
        endpoint_status = (
            "failure"
            if endpoint_has_failure
            else "warning"
            if endpoint_has_warning
            else "ready"
        )
        endpoint = {
            "url": result.url,
            "status": endpoint_status,
            "expected_tool_count": len(result.expected_schemas),
            "advertised_tool_count": len(result.advertised_schemas),
            "missing_tools": sorted(result.missing_tools),
            "extra_tools": sorted(result.extra_tools),
            "schema_mismatches": sorted(result.schema_mismatches),
            "schema_mismatch_details": mismatch_details,
            "schema_warnings": schema_warnings,
        }
        endpoints.append(endpoint)

        for tool_name in sorted(result.missing_tools):
            endpoint_failed = True
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "live_tool_missing",
                    f"{result.url} does not advertise manifest tool {tool_name}",
                )
            )
        for tool_name in sorted(result.schema_mismatches):
            endpoint_failed = True
            details = mismatch_details.get(tool_name, [])
            suffix = f": {details[0]}" if details else ""
            diagnostics.append(
                Diagnostic(
                    "failure",
                    "live_schema_mismatch",
                    f"{result.url} advertises a weaker or incompatible schema for {tool_name}{suffix}",
                )
            )
        for tool_name in sorted(result.extra_tools):
            endpoint_warning = True
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "live_tool_unregistered",
                    f"{result.url} advertises tool {tool_name} that is absent from the manifest",
                )
            )
        for tool_name, warnings in sorted(schema_warnings.items()):
            endpoint_warning = True
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "live_schema_warning",
                    f"{result.url} schema warning for {tool_name}: {warnings[0]}",
                )
            )

    if endpoint_failed:
        live_status = "failure"
        reason_code = "live_contract_failed"
    elif endpoint_warning:
        live_status = "warning"
        reason_code = "live_contract_warning"
    else:
        live_status = "ready"
        reason_code = "live_contract_ready"
        diagnostics.append(
            Diagnostic(
                "ok",
                "live_contract_ready",
                f"Live provider contract matches the manifest across {len(endpoints)} endpoint(s).",
            )
        )

    return {
        "requested": True,
        "status": live_status,
        "reason_code": reason_code,
        "timeout_s": timeout_s,
        "excluded_effects": sorted(excluded_effects),
        "endpoints": endpoints,
    }, diagnostics


async def _probe_live_registry(
    manifest_path: Path,
    *,
    timeout_s: float,
    excluded_effects: frozenset[str],
):
    """Load the existing authoritative registry and reuse its MCP schema probe."""

    from agent.app.capabilities.loader import build_configured_registry
    from agent.app.capabilities.probe import probe_mcp_capabilities

    configured = build_configured_registry([str(manifest_path)])
    return await probe_mcp_capabilities(
        configured.registry,
        timeout_s=timeout_s,
        excluded_effects=excluded_effects,
    )


@contextmanager
def _temporary_environment(values: dict[str, str]):
    previous = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _manifest_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    agents = payload.get("agents")
    tools: list[dict[str, Any]] = []
    if isinstance(agents, list):
        for agent in agents:
            if isinstance(agent, dict) and isinstance(agent.get("tools"), list):
                tools.extend(tool for tool in agent["tools"] if isinstance(tool, dict))
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "schema_version": payload.get("schema_version"),
        "source": payload.get("source"),
        "agent_count": len(agents) if isinstance(agents, list) else 0,
        "tool_count": len(tools),
        "physical_tool_count": sum(
            1 for tool in tools if "physical_motion" in set(tool.get("effects") or [])
        ),
        "safety_critical_tool_count": sum(
            1 for tool in tools if tool.get("safety_class") == "safety_critical"
        ),
        "open_input_schema_count": sum(
            1
            for tool in tools
            if isinstance(tool.get("input_schema"), dict)
            and tool["input_schema"].get("type") == "object"
            and tool["input_schema"].get("additionalProperties") is not False
        ),
        "upstream_commit": metadata.get("upstream_commit") if isinstance(metadata, dict) else None,
    }
