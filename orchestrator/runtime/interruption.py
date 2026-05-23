from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class InterruptionState:
    playback_generation: int = 0
    active_tasks: set[asyncio.Task] = field(default_factory=set)

    def next_generation(self) -> int:
        self.playback_generation += 1
        return self.playback_generation

    def is_stale(self, generation: int) -> bool:
        return generation != self.playback_generation

    def track(self, task: asyncio.Task) -> None:
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    def cancel_all(self) -> None:
        for task in list(self.active_tasks):
            if not task.done():
                task.cancel()
