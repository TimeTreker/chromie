from __future__ import annotations

import logging

import aiohttp

from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

try:
    from schemas.action import ActionCommand, ActionResult
except ImportError:  # pragma: no cover
    from orchestrator.schemas.action import ActionCommand, ActionResult

logger = logging.getLogger(__name__)


class ActionClient:
    TRACE_MODULE = TraceModule(
        name="orchestrator.action_client",
        component_type="provider_client",
        implementation="ActionClient",
    )

    def __init__(self, base_url: str, timeout_ms: int = 5000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(100, int(timeout_ms))

    async def execute(self, session: aiohttp.ClientSession, action: ActionCommand) -> ActionResult:
        timeout_ms = action.timeout_ms or self.timeout_ms
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="execute",
            kind="tool_call",
            attributes={
                "action_id": action.id,
                "target": action.target,
                "action_type": action.type,
                "timeout_ms": timeout_ms,
            },
        ) as span:
            timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/actions",
                json=action.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    span.set_status("error")
                    return ActionResult(
                        id=action.id,
                        target=action.target,
                        type=action.type,
                        status="failed",
                        message=f"HTTP {resp.status}: {body[:500]}",
                    )
                result = ActionResult.model_validate_json(body)
                span.set_attribute("result_status", result.status)
                return result

    async def health(self, session: aiohttp.ClientSession) -> dict:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()
