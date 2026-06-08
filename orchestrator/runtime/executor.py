from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from schemas.agent import AgentResult
    from schemas.action import ActionResult
except ImportError:  # pragma: no cover
    from orchestrator.schemas.agent import AgentResult
    from orchestrator.schemas.action import ActionResult

if TYPE_CHECKING:
    from orchestrator.clients.action_client import ActionClient

logger = logging.getLogger(__name__)


class AgentResultExecutor:
    """Executes only non-audio actions.

    Speech scheduling remains owned by the host orchestrator because it needs
    playback ordering and interruption awareness.
    """

    def __init__(self, action_client: "ActionClient | None" = None):
        self.action_client = action_client

    async def execute_actions(
        self,
        session: Any,
        result: AgentResult,
        *,
        dry_run: bool = False,
    ) -> list[ActionResult]:
        out: list[ActionResult] = []
        for action in result.actions:
            if action.requires_confirmation:
                logger.info("Action waiting for confirmation: %s", action.model_dump(mode="json"))
                out.append(
                    ActionResult(
                        id=action.id,
                        target=action.target,
                        type=action.type,
                        status="skipped",
                        message="confirmation_required",
                    )
                )
                continue
            if dry_run or self.action_client is None:
                logger.info("Action dry-run: %s", action.model_dump(mode="json"))
                out.append(
                    ActionResult(
                        id=action.id,
                        target=action.target,
                        type=action.type,
                        status="skipped" if dry_run else "completed",
                        message="dry_run" if dry_run else "no action client configured",
                    )
                )
                continue
            out.append(await self.action_client.execute(session, action))
        return out
