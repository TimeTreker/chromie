from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_AUTHORITY_CONTEXT_KEY = "semantic_authority"

SemanticAuthorityOwner = Literal[
    "goal_driven_runtime",
    "legacy_capability_fallback",
    "router_action_adapter",
    "legacy_agent_pipeline",
]
SemanticAuthorityRole = Literal["authoritative", "observer", "adapter"]


class SemanticAuthorityClaim(BaseModel):
    """One explicit semantic-owner claim for a single routed turn.

    A turn may have one authoritative owner. Observer and adapter roles are
    deliberately non-authoritative: observers cannot commit or execute plans,
    and adapters may only materialize an already-selected exact action.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    owner: SemanticAuthorityOwner
    role: SemanticAuthorityRole
    turn_id: str = Field(min_length=1)
    reason: str = ""
    emergency_fallback: bool = False

    @field_validator("turn_id")
    @classmethod
    def normalize_turn_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("turn_id is required")
        return normalized

    @model_validator(mode="after")
    def validate_role(self) -> "SemanticAuthorityClaim":
        if self.owner == "goal_driven_runtime" and self.role not in {
            "authoritative",
            "observer",
        }:
            raise ValueError("goal_driven_runtime must be authoritative or observer")
        if self.owner == "legacy_capability_fallback":
            if self.role != "authoritative" or not self.emergency_fallback:
                raise ValueError(
                    "legacy_capability_fallback requires authoritative role and "
                    "emergency_fallback=true"
                )
        if self.owner == "router_action_adapter" and self.role != "adapter":
            raise ValueError("router_action_adapter must use adapter role")
        if self.owner == "legacy_agent_pipeline" and self.role != "authoritative":
            raise ValueError("legacy_agent_pipeline must use authoritative role")
        return self


def semantic_authority_from_context(
    context: dict[str, Any] | None,
) -> SemanticAuthorityClaim | None:
    raw = (context or {}).get(SEMANTIC_AUTHORITY_CONTEXT_KEY)
    if raw is None:
        return None
    return SemanticAuthorityClaim.model_validate(raw)


def context_with_semantic_authority(
    context: dict[str, Any] | None,
    claim: SemanticAuthorityClaim,
) -> dict[str, Any]:
    result = dict(context or {})
    result[SEMANTIC_AUTHORITY_CONTEXT_KEY] = claim.model_dump(
        mode="json", exclude_none=True
    )
    return result


def semantic_authority_route_matrix() -> list[dict[str, Any]]:
    """Machine-readable ownership map for service diagnostics and tests."""

    return [
        {
            "entrypoint": (
                "orchestrator.handle_routed_text/apply "
                "(mapped lane allowlisted)"
            ),
            "owner": "goal_driven_runtime",
            "role": "authoritative",
            "selection": (
                "mapped route lane is in ORCH_COGNITIVE_APPLY_LANES and the "
                "apply preconditions pass"
            ),
            "planner_path": (
                "Goal Association -> Fast Planner -> terminal Deep Planner when "
                "required -> Response Composer -> trusted runtime adapter"
            ),
            "fallback": "fail_closed_after_authority_acquisition",
        },
        {
            "entrypoint": (
                "orchestrator.handle_routed_text/apply "
                "(mapped lane excluded)"
            ),
            "owner": "legacy_agent_pipeline",
            "role": "authoritative",
            "selection": (
                "mapped route lane is not in ORCH_COGNITIVE_APPLY_LANES, before "
                "Goal-driven authority acquisition"
            ),
            "planner_path": (
                "existing routed Agent path; exact Router actions remain "
                "adapter-only"
            ),
            "fallback": "not_applicable_before_authority_acquisition",
        },
        {
            "entrypoint": "orchestrator.handle_routed_text/report_only",
            "owner": "goal_driven_runtime",
            "role": "observer",
            "planner_path": "same goal-driven stages, evidence only",
            "fallback": "legacy_agent_pipeline_remains_the_only_authority",
        },
        {
            "entrypoint": "agent./interaction with exact Router actions",
            "owner": "router_action_adapter",
            "role": "adapter",
            "planner_path": "schema validation and SkillRequest materialization only",
            "fallback": "none",
        },
        {
            "entrypoint": "agent./interaction or /run emergency compatibility",
            "owner": "legacy_capability_fallback",
            "role": "authoritative",
            "planner_path": "legacy CapabilityAgent semantic planner",
            "fallback": "requires explicit service enablement and per-turn claim",
        },
        {
            "entrypoint": (
                "post_interrupt_correction/apply "
                "(mapped lane allowlisted)"
            ),
            "owner": "goal_driven_runtime",
            "role": "authoritative",
            "selection": (
                "corrected mapped route lane is in ORCH_COGNITIVE_APPLY_LANES "
                "and the apply preconditions pass"
            ),
            "planner_path": "same apply coordinator as normal routed text",
            "fallback": "fail_closed_after_authority_acquisition",
        },
        {
            "entrypoint": (
                "post_interrupt_correction/compatibility "
                "(mapped lane excluded)"
            ),
            "owner": "legacy_agent_pipeline",
            "role": "authoritative",
            "selection": (
                "corrected mapped route lane is not in "
                "ORCH_COGNITIVE_APPLY_LANES, before Goal-driven authority acquisition"
            ),
            "planner_path": (
                "existing post-interrupt Agent path; exact Router actions remain "
                "adapter-only and physical resume stays locked"
            ),
            "fallback": "not_applicable_before_authority_acquisition",
        },
    ]
