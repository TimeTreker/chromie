from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ServiceError(BaseModel):
    ok: bool = False
    service: str
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
