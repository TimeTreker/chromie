from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ActionStatus = Literal["accepted", "running", "completed", "failed", "cancelled", "rejected", "skipped"]


class ActionCommand(BaseModel):
    id: str = Field(default_factory=lambda: f"act_{uuid4().hex[:12]}")
    target: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
    timeout_ms: int | None = None
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    id: str
    target: str
    type: str
    status: ActionStatus = "completed"
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
