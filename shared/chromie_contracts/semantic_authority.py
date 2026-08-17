from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_AUTHORITY_CONTEXT_KEY = "semantic_authority"

SemanticAuthorityOwner = Literal["goal_driven_runtime"]
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
    """Machine-readable ownership map for the maintained cognitive entrypoint."""

    return [
        {
            "entrypoint": "orchestrator.handle_routed_text/apply",
            "owner": "goal_driven_runtime",
            "role": "authoritative",
            "planner_path": (
                "Goal Interpretation owns WHAT; Goal Association owns persistent Goal "
                "identity and continuity; Fast/Deep Planner own HOW and Communicative "
                "Act selection; Response Composer owns wording realization; CapabilityRuntime "
                "owns trusted execution lifecycle; Evidence owns reality"
            ),
            "fallback": "fail_closed_without_legacy_reentry",
        },
        {
            "entrypoint": "orchestrator.handle_routed_text/report_only",
            "owner": "goal_driven_runtime",
            "role": "observer",
            "planner_path": "same cognitive authority without effect authorization",
            "fallback": "none",
        },
    ]
