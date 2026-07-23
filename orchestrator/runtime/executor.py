from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

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

    TRACE_MODULE = TraceModule(
        name="orchestrator.action_executor",
        component_type="execution",
        implementation="AgentResultExecutor",
    )

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
            async with runtime_tracer.span(
                module=self.TRACE_MODULE,
                operation="execute_action",
                kind="execution",
                attributes={
                    "action_id": action.id,
                    "target": action.target,
                    "action_type": action.type,
                    "requires_confirmation": action.requires_confirmation,
                    "dry_run": dry_run,
                },
            ) as span:
                item = await self._execute_one(session, action, dry_run=dry_run)
                span.set_attribute("result_status", item.status)
                span.set_attribute("result_message", item.message or "")
                out.append(item)
        return out

    async def _execute_one(
        self,
        session: Any,
        action: Any,
        *,
        dry_run: bool,
    ) -> ActionResult:
        if action.requires_confirmation:
            logger.info(
                "Action waiting for confirmation: %s",
                action.model_dump(mode="json"),
            )
            return ActionResult(
                id=action.id,
                target=action.target,
                type=action.type,
                status="skipped",
                message="confirmation_required",
            )
        if dry_run:
            logger.info("Action dry-run: %s", action.model_dump(mode="json"))
            return ActionResult(
                id=action.id,
                target=action.target,
                type=action.type,
                status="skipped",
                message="dry_run",
            )
        if self.action_client is None:
            logger.error(
                "Action execution unavailable because no action client is configured: %s",
                action.model_dump(mode="json"),
            )
            return ActionResult(
                id=action.id,
                target=action.target,
                type=action.type,
                status="failed",
                message="action_client_unavailable",
            )
        return await self.action_client.execute(session, action)
