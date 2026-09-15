from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SEMANTIC_AUTHORITY_CONTEXT_KEY = "semantic_authority"

PLANNER_WORK_AUTHORITY_PROMPT = (
    "You are Chromie's task Planner. You own HOW to fulfill the authoritative Goals: "
    "exact Work, input requirements, prospective adequacy and bounded deeper delegation. "
    "GI owns WHAT; GA owns Goal identity and continuity. Preserve those meanings. "
    "Social Cognition owns interaction decisions and exact words, including answers, "
    "questions, progress and optional social expression. You establish a respond, "
    "clarify, limitation or confirmation decision; Host binds that decision as a "
    "communication need for SC. Never author utterances or decorative gestures. "
    "A respond disposition delegates established communication obligations; it is "
    "not delivered speech or Goal-completion Evidence. Runtime alone admits Work, "
    "holds confirmation, coordinates resources and records execution; you cannot "
    "grant consent or declare unobserved effects. Produce one complete semantic "
    "decision. No downstream model reviews or repairs it. "
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
            "communication_owner": "social_cognition",
            "planner_path": (
                "Goal Interpretation owns WHAT; Goal Association owns persistent Goal "
                "identity and continuity; Fast/Deep Planner own task HOW; Social Cognition "
                "owns interaction selection and wording; the Host validates immutable "
                "realization; CapabilityRuntime "
                "owns trusted execution lifecycle; Evidence owns reality"
            ),
            "fallback": "fail_closed_without_legacy_reentry",
        },
        {
            "entrypoint": "orchestrator.handle_routed_text/report_only",
            "owner": "cognitive_core_runtime",
            "role": "observer",
            "communication_owner": "social_cognition",
            "planner_path": "same cognitive authority without effect authorization",
            "fallback": "none",
        },
        {
            "entrypoint": "orchestrator.runtime.situation.apply_goal_free_situation_opportunity",
            "owner": "cognitive_core_runtime",
            "role": "authoritative",
            "communication_owner": "social_cognition",
            "planner_path": (
                "Trusted Goal-free Situation invokes Social Cognition for silence, "
                "exact interaction and optional eligible expression. Existing Runtime "
                "owns safety and delivery; task Work and Goal mutation remain unavailable"
            ),
            "fallback": "fail_closed_to_silence",
        },
    ]
