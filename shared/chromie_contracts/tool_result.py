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
ToolExecutionStatus = Literal["completed", "failed", "timed_out", "refused", "unavailable"]


class ToolExecutionRequest(BaseModel):
    """Trusted execution request for one already-planned semantic tool call."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    tool_id: str = Field(min_length=1, max_length=160)
    args: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default="", max_length=160)
    language: str = Field(default="en-US", min_length=1, max_length=32)

    @field_validator("request_id", "tool_id", "correlation_id", "language", mode="before")
    @classmethod
    def normalize_execution_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("args")
    @classmethod
    def reject_low_level_args(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class ToolExecutionResponse(BaseModel):
    """Normalized provider result returned to the trusted Host Capability Runtime."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)
    tool_id: str = Field(min_length=1, max_length=160)
    status: ToolExecutionStatus
    output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason_code: str = Field(default="", max_length=160)
    message: str = Field(default="", max_length=600)

    @field_validator("request_id", "tool_id", "reason_code", "message", mode="before")
    @classmethod
    def normalize_execution_result_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @field_validator("output", "metadata")
    @classmethod
    def reject_low_level_payloads(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def validate_execution_output(self) -> "ToolExecutionResponse":
        if self.status == "completed" and not self.output:
            raise ValueError("completed tool execution requires structured output")
        if self.status != "completed" and self.output:
            raise ValueError("non-completed tool execution must not expose output")
        return self


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


__all__ = [
    "ToolExecutionRequest",
    "ToolExecutionResponse",
    "ToolExecutionStatus",
    "ToolResultEvidence",
    "ToolResultStatus",
    "canonical_value_sha256",
]
