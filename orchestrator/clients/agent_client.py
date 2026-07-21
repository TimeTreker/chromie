from __future__ import annotations

import logging
from typing import Any

import aiohttp
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import ResponseCompositionResolution
from shared.chromie_contracts.semantic_task import SemanticTaskOperationSet
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

try:
    from schemas.agent import AgentRequest, AgentResult
    from schemas.route import RouteDecision
except ImportError:  # pragma: no cover
    from orchestrator.schemas.agent import AgentRequest, AgentResult
    from orchestrator.schemas.route import RouteDecision

logger = logging.getLogger(__name__)


class AgentClient:
    TRACE_MODULE = TraceModule(
        name="orchestrator.agent_client",
        component_type="service_client",
        implementation="AgentClient",
        schema_version=1,
    )

    def __init__(self, base_url: str, timeout_ms: int = 3000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(100, int(timeout_ms))

    async def run(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> AgentResult:
        req = AgentRequest(
            sid=sid,
            text=text,
            route_decision=route_decision,
            context=context or {},
            history=history or [],
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.post(
            f"{self.base_url}/run",
            json=req.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Agent returned HTTP {resp.status}: {body[:500]}")
            return AgentResult.model_validate_json(body)

    async def health(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()

    async def run_interaction(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> InteractionResponse:
        req = AgentRequest(
            sid=sid,
            text=text,
            route_decision=route_decision,
            context=context or {},
            history=history or [],
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.post(
            f"{self.base_url}/interaction",
            json=req.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Agent interaction endpoint returned HTTP {resp.status}: {body[:500]}"
                )
            return InteractionResponse.model_validate_json(body)

    async def resolve_fast_plan(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout_ms: int | None = None,
    ) -> CanonicalPlan:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_fast_plan",
            kind="tool_call",
            attributes={"endpoint": "/fast-plan", "timeout_ms": effective_timeout_ms},
        ) as span:
            req = AgentRequest(
                sid=sid,
                text=text,
                route_decision=route_decision,
                context=runtime_tracer.inject_carrier(context or {}),
                history=history or [],
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/fast-plan",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent fast-plan endpoint returned HTTP {resp.status}: {body[:500]}"
                    )
                result = CanonicalPlan.model_validate_json(body)
            runtime_tracer.merge_fragment_from_metadata(result.metadata)
            span.set_attribute("disposition", result.disposition)
            span.set_attribute("step_count", len(result.steps))
            return result

    async def resolve_deep_plan(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout_ms: int | None = None,
    ) -> CanonicalPlan:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_deep_plan",
            kind="tool_call",
            attributes={"endpoint": "/deep-plan", "timeout_ms": effective_timeout_ms},
        ) as span:
            req = AgentRequest(
                sid=sid,
                text=text,
                route_decision=route_decision,
                context=runtime_tracer.inject_carrier(context or {}),
                history=history or [],
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/deep-plan",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent deep-plan endpoint returned HTTP {resp.status}: {body[:500]}"
                    )
                result = CanonicalPlan.model_validate_json(body)
            runtime_tracer.merge_fragment_from_metadata(result.metadata)
            span.set_attribute("disposition", result.disposition)
            span.set_attribute("step_count", len(result.steps))
            return result

    async def compose_response_plan(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout_ms: int | None = None,
    ) -> ResponseCompositionResolution:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="compose_response_plan",
            kind="tool_call",
            attributes={
                "endpoint": "/compose-response-plan",
                "timeout_ms": effective_timeout_ms,
            },
        ) as span:
            req = AgentRequest(
                sid=sid,
                text=text,
                route_decision=route_decision,
                context=runtime_tracer.inject_carrier(context or {}),
                history=history or [],
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/compose-response-plan",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent response-composer endpoint returned HTTP {resp.status}: {body[:500]}"
                    )
                result = ResponseCompositionResolution.model_validate_json(body)
            runtime_tracer.merge_fragment_from_metadata(result.metadata)
            span.set_attribute("result_status", result.status)
            return result

    async def resolve_goal_association(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout_ms: int | None = None,
    ) -> GoalAssociationResolution:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_goal_association",
            kind="tool_call",
            attributes={
                "endpoint": "/goal-association",
                "timeout_ms": effective_timeout_ms,
            },
        ) as span:
            req = AgentRequest(
                sid=sid,
                text=text,
                route_decision=route_decision,
                context=runtime_tracer.inject_carrier(context or {}),
                history=history or [],
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/goal-association",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent goal-association endpoint returned HTTP {resp.status}: {body[:500]}"
                    )
                result = GoalAssociationResolution.model_validate_json(body)
            runtime_tracer.merge_fragment_from_metadata(result.metadata)
            span.set_attribute(
                "result_status", str(result.metadata.get("status") or "resolved")
            )
            return result

    async def resolve_task_continuity(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        timeout_ms: int | None = None,
    ) -> SemanticTaskOperationSet:
        req = AgentRequest(
            sid=sid,
            text=text,
            route_decision=route_decision,
            context=context or {},
            history=history or [],
        )
        timeout = aiohttp.ClientTimeout(
            total=max(100, int(timeout_ms or self.timeout_ms)) / 1000.0
        )
        async with session.post(
            f"{self.base_url}/task-continuity",
            json=req.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Agent task-continuity endpoint returned HTTP {resp.status}: {body[:500]}"
                )
            return SemanticTaskOperationSet.model_validate_json(body)

    async def execute_planning_task_graph(
        self,
        session: aiohttp.ClientSession,
        graph: dict[str, Any],
        *,
        timeout_ms: int = 120000,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(100, int(timeout_ms)) / 1000.0)
        async with session.post(
            f"{self.base_url}/task-graphs/execute-planning",
            json={"graph": graph},
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Agent TaskGraph execution returned HTTP {resp.status}: {body[:500]}"
                )
            return dict(await resp.json())
