from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ActionStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "skipped"]


class ActionCommand(BaseModel):
    id: str | None = None
    target: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    blocking: bool = False
    timeout_ms: int | None = None
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    id: str | None = None
    target: str | None = None
    type: str | None = None
    status: ActionStatus = "succeeded"
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
