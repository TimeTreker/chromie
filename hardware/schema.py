from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ActionStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ActionPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ActionCommand(BaseModel):
    """Low-level command accepted by the hardware daemon.

    The agent plans actions, but the host orchestrator is responsible for
    scheduling/cancelling them and sending only approved commands here.
    """

    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    target: str = Field(default="robot_pose_controller")
    type: str = Field(..., description="Action type, e.g. head.turn, led.set")
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
    priority: ActionPriority = ActionPriority.NORMAL
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "chromie-orchestrator"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("action type must not be empty")
        if "." not in value:
            raise ValueError("action type should be namespaced, e.g. head.turn")
        return value


class ActionResult(BaseModel):
    id: str
    status: ActionStatus
    target: str
    type: str
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RobotState(BaseModel):
    driver: str
    ready: bool = True
    emergency_stopped: bool = False
    is_moving: bool = False
    pose: dict[str, Any] = Field(default_factory=dict)
    battery: float | None = Field(default=None, ge=0.0, le=1.0)
    last_action_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    ok: bool
    service: Literal["chromie-hardware"] = "chromie-hardware"
    driver: str
    state: RobotState


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    detail: dict[str, Any] = Field(default_factory=dict)
