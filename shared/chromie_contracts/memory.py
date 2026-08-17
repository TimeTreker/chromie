from __future__ import annotations

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
