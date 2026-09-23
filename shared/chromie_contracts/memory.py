from __future__ import annotations

import json

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryKind = Literal[
    "preference", "fact", "note", "instruction", "constraint", "relationship", "other"
]


class MemoryUpdateProposal(BaseModel):
    """Model-authored, Host-validated memory mutation proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["remember", "forget", "clear_profile"] = "remember"
    scope: Literal["session", "profile"] = "session"
    kind: MemoryKind
    text: str = Field(min_length=1, max_length=1000)
    key: str | None = Field(default=None, max_length=160)
    persistence_policy: Literal["ephemeral", "durable_with_explicit_consent"] = "ephemeral"
    consent_basis: Literal["explicit_current_turn"] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_memory_authority(self) -> "MemoryUpdateProposal":
        durable = self.persistence_policy == "durable_with_explicit_consent"
        if self.scope == "session":
            if self.operation != "remember" or durable:
                raise ValueError("session memory supports only ephemeral remember")
            if self.consent_basis is not None or self.retention_days is not None:
                raise ValueError("session memory must not carry durable consent fields")
            return self
        if not durable or self.consent_basis != "explicit_current_turn":
            raise ValueError(
                "profile memory requires durable_with_explicit_consent and explicit_current_turn"
            )
        if self.operation == "forget" and not self.key:
            raise ValueError("profile forget requires a stable memory key")
        if self.operation == "remember" and not self.key:
            raise ValueError("durable profile memory requires a stable memory key")
        if self.operation == "remember" and self.retention_days is None:
            raise ValueError("durable profile memory requires bounded retention_days")
        if self.operation != "remember" and self.retention_days is not None:
            raise ValueError("forget and clear_profile must not set retention_days")
        return self

    @field_validator("text", "key", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.strip().split())
        return normalized or None


def role_memory_context(context: dict[str, Any], *, role: Literal["umi", "ga", "planner"]) -> str:
    """Project whole entries already activated and privacy-filtered by Memory.

    Cognitive scope and persistence remain independent. Never read raw stores or
    reconstruct missing facts from a summary at this model-facing boundary.
    """
    memory = context.get("session_memory")
    entries = memory.get("extracted_memory", []) if isinstance(memory, dict) else []
    selected: list[dict[str, Any]] = []
    budget = 2400 if role == "umi" else 4800
    fields = (
        "id", "scope", "kind", "key", "text", "confidence", "relation",
        "subject_refs", "source_person_refs", "source_ref_ids", "source_turn_ids",
        "source_sids", "audience_refs", "disclosure_scope", "persistence_policy",
        "consent_basis", "expires_ms", "memory_tier", "memory_backing",
    )
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not entry.get("text"):
            continue
        item = {key: entry[key] for key in fields if key in entry}
        encoded = json.dumps([*selected, item], ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= budget:
            selected.append(item)
        if len(selected) >= (4 if role == "umi" else 8):
            break
    if not selected:
        return ""
    purpose = {
        "umi": "Interpret the current user meaning using only activated relevant memory as context.",
        "ga": "Relate authoritative UMI Responsibilities to current and lasting Goal continuity.",
        "planner": (
            "Plan from canonical meaning, current Runtime Work and Evidence, with relevant remembered context. "
            "Consider relevant activated Memory before creating new Work, but require current trusted Evidence or exact verified-memory retrieval for factual completion."
        ),
    }[role]
    return (
        "Activated Memory JSON (context only):\n"
        + json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
        + "\n" + purpose
        + " memory_tier describes whether this activated context came from working RAM or "
        "long-term durable storage; scope describes relevance and persistence_policy describes "
        "retention policy. A long-term item is intentionally more stable, not more authoritative. "
        "Neither memory nor its confidence replaces current meaning, Goal state, Runtime state, "
        "execution Evidence, or authorization. Never turn remembered context into a new Responsibility or infer completion from it.\n\n"
    )
