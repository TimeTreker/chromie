from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class ScheduledSpeech:
    order: int
    text: str = field(compare=False)
    sid: str | None = field(default=None, compare=False)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


class OrderedSpeechScheduler:
    def __init__(self):
        self._order = 0
        self._lock = asyncio.Lock()

    async def next(self, text: str, sid: str | None = None, **metadata: Any) -> ScheduledSpeech:
        async with self._lock:
            item = ScheduledSpeech(order=self._order, text=text, sid=sid, metadata=metadata)
            self._order += 1
            return item

    async def reset(self) -> None:
        async with self._lock:
            self._order = 0
