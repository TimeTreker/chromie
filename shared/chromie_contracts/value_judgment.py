"""Value Judgment: Chromie's "should I act on this?" authority (owner amendment 2026-10-10).

Value Judgment answers only whether Chromie should act on a request: proceed, ask, or
decline with a reason. It never decides how, never selects or edits Capabilities and never
writes what Chromie says. It runs only for Plans that would use a value-reviewed
Capability (the owner-editable list below).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ValueAffected = Literal["nobody_else", "family_member", "another_adult", "child", "stranger", "owner_unknown"]
ValueConcern = Literal[
    "none", "others_property", "privacy", "consent", "deception", "harm_risk",
    "irreversible", "rules_or_law", "family_conflict",
]
ValueDecision = Literal["proceed", "ask", "decline"]

VALUE_REVIEW_RELATIVE_PATH = Path("capabilities/value_review.json")


class ValueJudgmentModelOutput(BaseModel):
    """The model writes who is affected and the concern before its decision."""

    model_config = ConfigDict(extra="forbid")

    affected: ValueAffected
    concern: ValueConcern
    decision: ValueDecision
    reason: str = Field(min_length=3, max_length=160)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class ValueJudgmentResult(BaseModel):
    """One judgment for one turn; a failed judgment withholds reviewed effects (fail closed)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["judged", "failed"]
    judgment: ValueJudgmentModelOutput | None = None
    failure_class: str = ""
    reason: str = Field(default="", max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def permits_effects(self) -> bool:
        return self.status == "judged" and self.judgment is not None and self.judgment.decision == "proceed"


def load_value_review_capability_ids(path: Path) -> frozenset[str]:
    """Owner-editable list of Capabilities whose use needs a proceed verdict."""
    raw = json.loads(path.read_text())
    ids = raw.get("capability_ids") if isinstance(raw, dict) else None
    if not isinstance(ids, list) or not all(isinstance(item, str) and item.strip() for item in ids):
        raise ValueError(f"{path}: capability_ids must be a list of Capability IDs")
    return frozenset(item.strip() for item in ids)
