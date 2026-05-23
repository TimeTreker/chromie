from __future__ import annotations

from typing import Any


class ToolClient:
    """Placeholder for future tool service integrations.

    In v1, tool requests are returned as action commands for the host
    orchestrator or a future tool executor to handle.
    """

    async def dry_run(self, action_type: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "type": action_type, "params": params}
