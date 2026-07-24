from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields


ToolResultStatus = Literal[
    "completed",
    "partial",
    "failed",
    "cancelled",
    "timed_out",
    "refused",
    "not_run",
]
ToolAnswerMode = Literal["direct", "summary", "detailed"]
ToolInterpretationStatus = Literal["resolved", "fallback", "unavailable", "invalid"]


def canonical_value_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ToolResultEvidence(BaseModel):
    """One bounded, schema-validated tool observation exposed for interpretation."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=160)
    tool_id: str = Field(min_length=1, max_length=160)
    status: ToolResultStatus
    data: dict[str, Any] = Field(default_factory=dict)
    output_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("evidence_id", "tool_id", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("data")
    @classmethod
    def reject_low_level_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_digest(self) -> "ToolResultEvidence":
        if canonical_value_sha256(self.data) != self.output_sha256:
            raise ValueError("tool result evidence digest mismatch")
        return self


class ToolResultFactReference(BaseModel):
    """A model-selected exact JSON Pointer into trusted evidence."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=160)
    json_pointer: str = Field(min_length=1, max_length=320)

    @field_validator("evidence_id", mode="before")
    @classmethod
    def normalize_evidence_id(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("json_pointer", mode="before")
    @classmethod
    def normalize_pointer(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text.startswith("/"):
            raise ValueError("json_pointer must be an RFC 6901-style absolute pointer")
        return text


class ToolResultInterpretationRequest(BaseModel):
    """Trusted request for user-focused synthesis over complete tool evidence."""

    model_config = ConfigDict(extra="forbid")

    sid: str = ""
    user_request: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="en-US", min_length=1, max_length=32)
    evidence: list[ToolResultEvidence] = Field(min_length=1, max_length=16)
    fallback_response: str = Field(default="", max_length=500)
    max_spoken_chars: int = Field(default=160, ge=24, le=600)
    detailed_max_spoken_chars: int = Field(default=360, ge=80, le=1200)
    max_sentences: int = Field(default=2, ge=1, le=4)
    detailed_max_sentences: int = Field(default=4, ge=2, le=8)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sid", "user_request", "language", "fallback_response", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("context")
    @classmethod
    def reject_low_level_context(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> "ToolResultInterpretationRequest":
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("tool result evidence IDs must be unique")
        if self.detailed_max_spoken_chars < self.max_spoken_chars:
            raise ValueError("detailed spoken budget must not be smaller than normal budget")
        if self.detailed_max_sentences < self.max_sentences:
            raise ValueError("detailed sentence budget must not be smaller than normal budget")
        return self


class ToolResultInterpretation(BaseModel):
    """Evidence-bound spoken answer returned by the interpretation stage."""

    model_config = ConfigDict(extra="forbid")

    status: ToolInterpretationStatus
    spoken_response: str = Field(default="", max_length=1200)
    answer_mode: ToolAnswerMode = "summary"
    selected_facts: list[ToolResultFactReference] = Field(default_factory=list, max_length=12)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=600)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("spoken_response", "rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @model_validator(mode="after")
    def validate_response_presence(self) -> "ToolResultInterpretation":
        if self.status in {"resolved", "fallback"} and not self.spoken_response:
            raise ValueError("resolved tool result interpretation requires spoken_response")
        if self.status in {"unavailable", "invalid"} and self.spoken_response:
            raise ValueError("unavailable tool result interpretation must not contain speech")
        return self


__all__ = [
    "ToolAnswerMode",
    "ToolResultEvidence",
    "ToolResultFactReference",
    "ToolResultInterpretation",
    "ToolResultInterpretationRequest",
    "ToolResultStatus",
    "canonical_value_sha256",
]
