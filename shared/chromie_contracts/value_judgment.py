"""Value Judgment: Chromie's "should I act on this?" authority (owner amendment 2026-10-10).

Value Judgment answers only whether Chromie should act on a request: proceed, ask, or
decline with a reason. It never decides how, never selects or edits Capabilities and never
writes what Chromie says. It runs only for Plans that would use a value-reviewed
Capability (the owner-editable list below), on the turn's first Plan and on any later Plan
of the turn that adds one not yet judged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ValueAffected = Literal["nobody_else", "family_member", "another_adult", "child", "stranger", "owner_unknown"]
ValueConcern = Literal[
    "none", "others_property", "privacy", "consent", "deception", "harm_risk",
    "irreversible", "rules_or_law", "family_conflict",
]
ValueDecision = Literal["proceed", "ask", "decline"]

# Concerns that by definition touch someone besides the person asking.
VALUE_CONCERNS_ABOUT_OTHERS = frozenset({"others_property", "privacy", "consent", "deception", "family_conflict"})

VALUE_REVIEW_RELATIVE_PATH = Path("capabilities/value_review.json")


class ValueJudgmentModelOutput(BaseModel):
    """The model writes who is affected and the concern before its decision.

    Each fact narrows what follows it: a concern about someone else's things, privacy,
    consent, deception or family needs someone besides the person asking, and with no
    concern the decision is proceed (live 2026-10-21: "nobody_else" with "others_property"
    asked whose a household TV remote was).
    """

    model_config = ConfigDict(extra="forbid")

    affected: ValueAffected
    concern: ValueConcern
    decision: ValueDecision
    reason: str = Field(min_length=3, max_length=160)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def facts_settle_the_decision(self) -> "ValueJudgmentModelOutput":
        if self.affected == "nobody_else" and self.concern in VALUE_CONCERNS_ABOUT_OTHERS:
            raise ValueError(f"concern {self.concern} needs someone besides the person asking")
        if self.concern == "none" and self.decision != "proceed":
            raise ValueError("with no value concern the decision is proceed")
        return self


def value_judgment_response_schema() -> dict[str, Any]:
    """Native decoder states for the facts the DTO validates, in their written order."""

    base = ValueJudgmentModelOutput.model_json_schema()
    concerns = [value for value in get_args(ValueConcern) if value != "none"]
    others = [value for value in get_args(ValueAffected) if value != "nobody_else"]
    self_only = [value for value in concerns if value not in VALUE_CONCERNS_ABOUT_OTHERS]

    def state(affected: list[str], concern: list[str], decision: list[str]) -> dict[str, Any]:
        properties = dict(base["properties"])
        for name, values in (("affected", affected), ("concern", concern), ("decision", decision)):
            properties[name] = {"type": "string", "enum": values}
        return {"type": "object", "additionalProperties": False, "properties": properties,
                "required": base["required"]}

    decisions = list(get_args(ValueDecision))
    return {"title": base["title"], "oneOf": [
        state(["nobody_else"], ["none"], ["proceed"]),
        state(["nobody_else"], self_only, decisions),
        state(others, ["none"], ["proceed"]),
        state(others, concerns, decisions),
    ]}


class ValueJudgmentResult(BaseModel):
    """One judgment for what a Plan adds unjudged in its turn; a failed judgment withholds reviewed effects (fail closed)."""

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
