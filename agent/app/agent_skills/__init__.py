"""Passive Agent Skill selection, progressive disclosure, and read-only loading."""

from .disclosure import (
    AgentSkillDisclosureService,
    AgentSkillProgressiveDisclosureCoordinator,
    agent_skill_prompt_section,
    attach_disclosure_metadata,
    attach_planner_disclosure_metadata_fail_closed,
    bind_agent_skill_provenance_to_plan,
    plan_agent_skill_provenance_from_disclosure,
    build_agent_skill_selection_request,
    prompt_agent_skill_context,
    trace_disclosure_metadata,
)
from .selection import AgentSkillSelectionService
from .loader import (
    AgentSkillLoadError,
    AgentSkillRegistry,
    ConfiguredAgentSkillRegistry,
    build_configured_agent_skill_registry,
    compute_agent_skill_content_digest,
    load_agent_skill_registry,
    parse_agent_skill_roots,
)

__all__ = [
    "AgentSkillDisclosureService",
    "AgentSkillProgressiveDisclosureCoordinator",
    "agent_skill_prompt_section",
    "attach_disclosure_metadata",
    "attach_planner_disclosure_metadata_fail_closed",
    "bind_agent_skill_provenance_to_plan",
    "plan_agent_skill_provenance_from_disclosure",
    "build_agent_skill_selection_request",
    "prompt_agent_skill_context",
    "trace_disclosure_metadata",
    "AgentSkillSelectionService",
    "AgentSkillLoadError",
    "AgentSkillRegistry",
    "ConfiguredAgentSkillRegistry",
    "build_configured_agent_skill_registry",
    "compute_agent_skill_content_digest",
    "load_agent_skill_registry",
    "parse_agent_skill_roots",
]
