"""MCP-ready capability registry for Chromie's global agent host."""

from .models import (
    AgentManifest,
    AgentStatus,
    CapabilityBundle,
    CapabilityRegistry,
    ConfirmationPolicy,
    ExecutionPolicy,
    FailurePolicy,
    MonitoringPolicy,
    ToolAvailability,
    ToolCapability,
    TransportSpec,
)
from .local import chromie_capability_bundle, chromie_manifests
from .loader import (
    ConfiguredRegistry,
    build_configured_registry,
    load_capability_bundle,
    load_capability_bundles,
    parse_manifest_paths,
)
from .probe import CapabilityProbeResult, probe_mcp_capabilities

__all__ = [
    "AgentManifest",
    "AgentStatus",
    "CapabilityBundle",
    "CapabilityProbeResult",
    "CapabilityRegistry",
    "ConfiguredRegistry",
    "ConfirmationPolicy",
    "ExecutionPolicy",
    "FailurePolicy",
    "MonitoringPolicy",
    "ToolAvailability",
    "ToolCapability",
    "TransportSpec",
    "chromie_capability_bundle",
    "chromie_manifests",
    "build_configured_registry",
    "load_capability_bundle",
    "load_capability_bundles",
    "parse_manifest_paths",
    "probe_mcp_capabilities",
]
