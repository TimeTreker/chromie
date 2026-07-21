from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

InteractionStatus = Literal["ok", "clarify", "refused", "ignored", "error"]
SkillTiming = Literal["parallel", "sequential"]
SpeechTiming = Literal["immediate", "parallel", "sequential", "after_skills"]
SkillResultStatus = Literal[
    "accepted",
    "running",
    "completed",
    "refused",
    "failed",
    "cancelled",
    "timed_out",
]

FORBIDDEN_LOW_LEVEL_FIELDS = frozenset(
    {
        "action_14d",
        "actuator_ctrl",
        "joint_command",
        "joint_commands",
        "joint_target",
        "joint_targets",
        "motor_command",
        "motor_commands",
        "positions_by_name",
        "raw_joint_targets",
        "raw_motor_commands",
        "torque_command",
        "torque_commands",
    }
)

RAW_PLANAR_CONTROLLER_FIELDS = frozenset({"vx", "vy", "yaw"})


def find_raw_controller_array_schema(value: Any, *, path: str = "$") -> str | None:
    """Return the first schema path exposing a raw planar command array.

    Bounded named skills may expose semantic speed or duration parameters.  A
    repeated ``commands[]`` surface containing the complete ``vx``/``vy``/``yaw``
    controller vector is different: it lets a model author a low-level motion
    recipe.  Keep that provider compatibility contract callable by trusted
    runtime code, but never publish it as an LLM-visible capability.
    """

    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if str(key).strip().lower() == "commands" and isinstance(item, dict):
                items = item.get("items")
                properties = items.get("properties") if isinstance(items, dict) else None
                if isinstance(properties, dict) and RAW_PLANAR_CONTROLLER_FIELDS.issubset(
                    {str(name).strip().lower() for name in properties}
                ):
                    return child_path
            found = find_raw_controller_array_schema(item, path=child_path)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = find_raw_controller_array_schema(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def reject_forbidden_low_level_fields(value: Any, *, path: str = "$") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_LOW_LEVEL_FIELDS:
                raise ValueError(f"forbidden low-level field at {path}.{key}")
            reject_forbidden_low_level_fields(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_forbidden_low_level_fields(item, path=f"{path}[{index}]")
    return value


class InteractionSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"speech_{uuid4().hex[:12]}")
    text: str = Field(min_length=1)
    timing: SpeechTiming = "immediate"
    style: str = "brief"
    priority: str = "normal"
    interruptible: bool = True
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join((value or "").strip().split())
        if not normalized:
            raise ValueError("speech text must not be empty")
        return normalized

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SkillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"skillreq_{uuid4().hex[:12]}")
    skill_id: str = Field(min_length=1)
    skill_version: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    timing: SkillTiming = "parallel"
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    cancellable: bool = True
    requires_confirmation: bool = False
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("request_id", "skill_id")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("identifier must not be empty")
        return normalized

    @field_validator("args", "metadata")
    @classmethod
    def reject_low_level_payloads(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SkillResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    skill_id: str
    skill_version: str | None = None
    status: SkillResultStatus
    provider_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    reason_code: str | None = None
    message: str = ""
    trace_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("output")
    @classmethod
    def reject_low_level_output(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SkillTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: str = Field(min_length=1)
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def reject_low_level_trace_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)


class SkillTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: f"skilltrace_{uuid4().hex[:12]}")
    interaction_id: str
    request_id: str
    skill_id: str
    provider_id: str
    status: SkillResultStatus = "accepted"
    events: list[SkillTraceEvent] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(default_factory=lambda: f"interaction_{uuid4().hex[:12]}")
    status: InteractionStatus = "ok"
    speech: list[InteractionSpeech] = Field(default_factory=list)
    skills: list[SkillRequest] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_low_level_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return reject_forbidden_low_level_fields(value)

    @model_validator(mode="after")
    def propagate_confirmation_requirement(self) -> "InteractionResponse":
        if any(request.requires_confirmation for request in self.skills):
            self.requires_confirmation = True
        return self
