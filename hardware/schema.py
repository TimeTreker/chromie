from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from shared.chromie_contracts.action import (
    ActionCommand,
    ActionPriority,
    ActionResult,
    ActionStatus,
)

__all__ = [
    "ActionCommand",
    "ActionPriority",
    "ActionResult",
    "ActionStatus",
    "HealthResponse",
    "RobotState",
]


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
