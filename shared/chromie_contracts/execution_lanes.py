from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ChromieExecutionLane = Literal[
    "social_attention",
    "speaking",
    "activity",
]
LaneCoordinationRelation = Literal["parallel"]
LaneCoordinationStartPolicy = Literal["best_effort_parallel"]
LaneCoordinationFailurePolicy = Literal["independent"]


def _normalize_text(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


def _normalize_unique_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("expected a list or string")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


class LaneCoordinationGroup(BaseModel):
    """One bounded cross-lane overlap authored by the Cognitive Core.

    The group coordinates execution channels; it does not create another mind,
    select a provider, authorize an effect, or weaken provider safety.  This
    first maintained contract deliberately supports best-effort overlap only.
    Synchronized start barriers and atomic cross-provider failure semantics must
    be introduced by a later trusted-runtime contract rather than implied here.
    """

    model_config = ConfigDict(extra="forbid")

    coordination_id: str = Field(min_length=1)
    relation: LaneCoordinationRelation = "parallel"
    lanes: list[ChromieExecutionLane] = Field(min_length=2, max_length=3)
    activity_step_ids: list[str] = Field(default_factory=list)
    start_policy: LaneCoordinationStartPolicy = "best_effort_parallel"
    failure_policy: LaneCoordinationFailurePolicy = "independent"
    reason_summary: str = ""

    @field_validator("coordination_id", "reason_summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        return _normalize_text(value)

    @field_validator("activity_step_ids", mode="before")
    @classmethod
    def normalize_activity_step_ids(cls, value: Any) -> list[str]:
        return _normalize_unique_text_list(value)

    @field_validator("lanes", mode="before")
    @classmethod
    def normalize_lanes(cls, value: Any) -> list[str]:
        normalized = _normalize_unique_text_list(value)
        if len(normalized) < 2:
            raise ValueError("lane coordination requires at least two distinct lanes")
        return normalized

    @model_validator(mode="after")
    def validate_lane_membership(self) -> "LaneCoordinationGroup":
        lane_set = set(self.lanes)
        if "activity" in lane_set and not self.activity_step_ids:
            raise ValueError(
                "activity lane coordination requires activity_step_ids"
            )
        if "activity" not in lane_set and self.activity_step_ids:
            raise ValueError(
                "activity_step_ids require the activity lane"
            )
        return self
