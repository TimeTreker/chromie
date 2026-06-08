from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ActionCommand(BaseModel):
    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    target: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
    priority: str = "normal"
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
