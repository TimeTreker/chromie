from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_AUTHORITY_CONTEXT_KEY = "semantic_authority"

SemanticAuthorityOwner = Literal[
    "goal_driven_runtime",
    "legacy_capability_fallback",
    "goal_interpretation_action_adapter",
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
        if self.owner == "goal_interpretation_action_adapter" and self.role != "adapter":
            raise ValueError("goal_interpretation_action_adapter must use adapter role")
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
                "Core readiness may start complete native Vocal, exact trusted "
                "safe reads, while background Social Attention may prepare optional body decoration as Goal Association continues; "
                "Goal Association explicitly binds progress to canonical Goals; completely "
                "bound native conversation may adopt canonical speech without Planner or "
                "Response Composer, completely bound safe reads may adopt a canonical Plan "
                "without Fast Planner, otherwise Fast/Deep Planning applies; Response "
                "Composer runs only when a new presentation decision still requires it"
            ),
            "fallback": "fail_closed_after_authority_acquisition",
        },
        {
            "entrypoint": (
                "orchestrator.handle_routed_text/apply "
                "(mapped lane excluded)"
            ),
            "owner": "goal_driven_runtime",
            "role": "authoritative",
            "selection": (
                "mapped route lane is not in ORCH_COGNITIVE_APPLY_LANES"
            ),
            "planner_path": (
                "no planner is entered; the Host emits a typed fail-closed response"
            ),
            "fallback": "fail_closed_without_legacy_reentry",
        },
        {
            "entrypoint": "orchestrator.handle_routed_text/report_only",
            "owner": "goal_driven_runtime",
            "role": "observer",
            "planner_path": (
                "same Goal semantics and planner fallback, but no readiness execution "
                "or other effect authorization; evidence only"
            ),
            "fallback": "legacy_agent_pipeline_remains_the_only_authority",
        },
        {
            "entrypoint": "agent./interaction with exact Goal Interpretation actions",
            "owner": "goal_interpretation_action_adapter",
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
            "owner": "goal_driven_runtime",
            "role": "authoritative",
            "selection": (
                "corrected mapped route lane is not in "
                "ORCH_COGNITIVE_APPLY_LANES"
            ),
            "planner_path": (
                "no planner is entered; the Host fails closed and physical resume stays locked"
            ),
            "fallback": "fail_closed_without_legacy_reentry",
        },
    ]
