from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_AUTHORITY_CONTEXT_KEY = "semantic_authority"

# Shared by every Planner invocation, including the restricted Situation entrypoint.
PLANNER_COMMUNICATION_AUTHORITY_PROMPT = (
    "Planner is Chromie's sole ordinary communication authority. You own whether to "
    "speak, the Activity's function and exact wording, including silence, useful new "
    "information, intentional repetition, correction or retraction. Use the supplied "
    "Interaction Context as immutable delivery history: scheduled or started speech "
    "is not complete delivery; interrupted speech is only partially delivered. Keep "
    "one Activity's identity and wording immutable; a new communicative decision needs "
    "a new Activity identity even when its words repeat. Repair references may cite "
    "only actually delivered Activities. Runtime validates provenance and realizes "
    "accepted wording; it never reviews or rewrites your semantics. Your input "
    "contract alone determines Goal/Work permissions; deeper reasoning grants none. "
    "A completed decision receives no second model review. One designated deeper "
    "pass is allowed only for unresolved scope before its decision is committed. "
)

SemanticAuthorityOwner = Literal["cognitive_core_runtime"]
SemanticAuthorityRole = Literal["authoritative", "observer"]


class SemanticAuthorityClaim(BaseModel):
    """One explicit semantic-owner claim for a single routed turn.

    A turn may have one authoritative owner. Observer mode is deliberately
    non-authoritative and cannot commit or execute plans.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    owner: SemanticAuthorityOwner
    role: SemanticAuthorityRole
    turn_id: str = Field(min_length=1)
    reason: str = ""

    @field_validator("turn_id")
    @classmethod
    def normalize_turn_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("turn_id is required")
        return normalized

    @model_validator(mode="after")
    def validate_role(self) -> "SemanticAuthorityClaim":
        if self.owner == "cognitive_core_runtime" and self.role not in {
            "authoritative",
            "observer",
        }:
            raise ValueError("cognitive_core_runtime must be authoritative or observer")
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
            "owner": "cognitive_core_runtime",
            "role": "authoritative",
            "communication_owner": "planner",
            "planner_path": (
                "Goal Interpretation owns WHAT; Goal Association owns persistent Goal "
                "identity and continuity; Fast/Deep Planner own HOW plus exact "
                "Communicative Act selection and wording; the Host validates immutable "
                "realization; CapabilityRuntime "
                "owns trusted execution lifecycle; Evidence owns reality"
            ),
            "fallback": "fail_closed_without_legacy_reentry",
        },
        {
            "entrypoint": "orchestrator.handle_routed_text/report_only",
            "owner": "cognitive_core_runtime",
            "role": "observer",
            "communication_owner": "planner",
            "planner_path": "same cognitive authority without effect authorization",
            "fallback": "none",
        },
        {
            "entrypoint": "orchestrator.runtime.situation.apply_goal_free_situation_opportunity",
            "owner": "cognitive_core_runtime",
            "role": "authoritative",
            "communication_owner": "planner",
            "planner_path": (
                "Trusted Goal-free Situation invokes Planner with a communication-only "
                "contract; Fast or one bounded Deep pass may choose silence or one Communicative Act while Goal, "
                "Capability Work, and effect authorization remain unavailable"
            ),
            "fallback": "fail_closed_to_silence",
        },
    ]
