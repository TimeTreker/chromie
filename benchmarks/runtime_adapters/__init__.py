"""Deployment-neutral adapters for exercising real Chromie components."""

from .adapter import RuntimeAdapter, RuntimeAdapterError
from .profiles import COMPONENT_PROFILES, ComponentProfile, get_component_profile

__all__ = [
    "COMPONENT_PROFILES",
    "ComponentProfile",
    "RuntimeAdapter",
    "RuntimeAdapterError",
    "get_component_profile",
]
