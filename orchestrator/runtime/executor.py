from __future__ import annotations

import logging
from typing import Any

import aiohttp

try:
    from clients.action_client import ActionClient
    from schemas.agent import AgentResult
    from schemas.action import ActionResult
except ImportError:  # pragma: no cover
    from orchestrator.clients.action_client import ActionClient
    from orchestrator.schemas.agent import AgentResult
    from orchestrator.schemas.action import ActionResult

logger = logging.getLogger(__name__)


class AgentResultExecutor:
    """Executes only non-audio actions.

    Speech scheduling remains owned by the host orchestrator because it needs
    playback ordering and interruption awareness.
    """

    def __init__(self, action_client: ActionClient | None = None):
        self.action_client = action_client

    async def execute_actions(
        self,
        session: aiohttp.ClientSession,
        result: AgentResult,
        *,
        dry_run: bool = False,
    ) -> list[ActionResult]:
        out: list[ActionResult] = []
        for action in result.actions:
            if dry_run or self.action_client is None:
                logger.info("Action dry-run: %s", action.model_dump(mode="json"))
                out.append(
                    ActionResult(
                        id=action.id,
                        target=action.target,
                        type=action.type,
                        status="skipped" if dry_run else "succeeded",
                        message="dry_run" if dry_run else "no action client configured",
                    )
                )
                continue
            out.append(await self.action_client.execute(session, action))
        return out
