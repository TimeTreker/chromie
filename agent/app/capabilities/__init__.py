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

__all__ = [
    "AgentManifest",
    "AgentStatus",
    "CapabilityBundle",
    "CapabilityRegistry",
    "ConfirmationPolicy",
    "ExecutionPolicy",
    "FailurePolicy",
    "MonitoringPolicy",
    "ToolAvailability",
    "ToolCapability",
    "TransportSpec",
    "chromie_capability_bundle",
    "chromie_manifests",
]
