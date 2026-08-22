from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


GoalCancellationEvidenceStatus = Literal[
    "cancelled",
    "not_cancelled",
    "uncertain",
]


class GoalCancellationEvidence(BaseModel):
    """Bounded factual result of one deterministic named-Goal cancellation attempt.

    This contract records control facts only. It does not decide what the result
    means conversationally and it never owns user-visible wording.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    evidence_id: str = Field(min_length=1, max_length=200)
    source_turn_id: str = Field(min_length=1, max_length=160)
    target_goal_ids: list[str] = Field(min_length=1, max_length=16)
    coaffected_goal_ids: list[str] = Field(default_factory=list, max_length=16)
    released_confirmation_goal_ids: list[str] = Field(
        default_factory=list, max_length=16
    )
    status: GoalCancellationEvidenceStatus
    runtime_dispatch_attempted: bool = False
    goal_state_reconciled: bool = False
    confirmation_state_reconciled: bool = False
    reason_code: str = Field(default="", max_length=160)

    @field_validator(
        "evidence_id",
        "source_turn_id",
        "reason_code",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator(
        "target_goal_ids",
        "coaffected_goal_ids",
        "released_confirmation_goal_ids",
        mode="before",
    )
    @classmethod
    def normalize_goal_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("Goal cancellation evidence goal IDs must be an array")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return out

    @model_validator(mode="after")
    def validate_truth_shape(self) -> "GoalCancellationEvidence":
        if self.status == "cancelled" and not self.goal_state_reconciled:
            raise ValueError("cancelled evidence requires reconciled Goal state")
        if self.status == "not_cancelled" and self.goal_state_reconciled:
            raise ValueError("not_cancelled evidence cannot claim reconciled cancellation")
        return self

    @classmethod
    def create(cls, **kwargs: Any) -> "GoalCancellationEvidence":
        payload = {
            key: value
            for key, value in kwargs.items()
            if key != "evidence_id"
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        evidence_id = f"goal_cancel_{hashlib.sha256(encoded).hexdigest()[:24]}"
        return cls(evidence_id=evidence_id, **payload)


__all__ = [
    "GoalCancellationEvidence",
    "GoalCancellationEvidenceStatus",
]
