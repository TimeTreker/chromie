from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionContext(BaseModel):
    sid: str | None = None
    language: str | None = None
    is_speaking: bool = False
    current_generation: int | None = None
    user_state: dict[str, Any] = Field(default_factory=dict)
    robot_state: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
