from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator
from urllib.parse import quote

import aiohttp
from pydantic import TypeAdapter
from shared.chromie_contracts.core_interpretation import (
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    FastPlannerAdvance,
    FastPlannerStreamFrame,
    FastPlannerStreamTerminal,
)
from shared.chromie_contracts.reflection import ReflectionRequest, ReflectionResolution
from shared.chromie_contracts.tool_result import (
    ToolExecutionRequest,
    ToolExecutionResponse,
)
from shared.chromie_contracts.user_turn import (
    AttentionReviewRequest,
    AttentionReviewResult,
    CoreTurnRequest,
    GatewayContextSnapshot,
    UserTurnEnvelope,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

logger = logging.getLogger(__name__)

_FAST_PLANNER_STREAM_FRAME_ADAPTER = TypeAdapter(FastPlannerStreamFrame)


class AgentClient:
    TRACE_MODULE = TraceModule(
        name="orchestrator.agent_client",
        component_type="service_client",
        implementation="AgentClient",
        schema_version=1,
    )

    def __init__(
        self,
        base_url: str,
        timeout_ms: int = 3000,
        *,
        goal_interpreter_timeout_ms: int | None = None,
        dag_engine_execution_token: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(100, int(timeout_ms))
        effective_goal_interpreter_timeout_ms = (
            self.timeout_ms
            if goal_interpreter_timeout_ms is None
            else goal_interpreter_timeout_ms
        )
        self.goal_interpreter_timeout_ms = max(
            100,
            int(effective_goal_interpreter_timeout_ms),
        )
        self.dag_engine_execution_token = (
            str(dag_engine_execution_token).strip()
            if dag_engine_execution_token is not None
            else os.getenv("AGENT_DAG_ENGINE_EXECUTION_TOKEN", "").strip()
        )


    async def review_attention(
        self,
        session: aiohttp.ClientSession,
        *,
        request: AttentionReviewRequest,
    ) -> AttentionReviewResult:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.post(
            f"{self.base_url}/cognitive-gateway/attention-review",
            json=request.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Cognitive Gateway attention review returned HTTP "
                    f"{resp.status}: {body[:500]}"
                )
            return AttentionReviewResult.model_validate_json(body)

    async def interpret_turn(
        self,
        session: aiohttp.ClientSession,
        *,
        turn_envelope: UserTurnEnvelope,
        context_snapshot: GatewayContextSnapshot,
    ) -> CoreInterpretationResult:
        request = CoreTurnRequest(
            turn_envelope=turn_envelope,
            context_snapshot=context_snapshot,
        )
        timeout = aiohttp.ClientTimeout(
            total=self.goal_interpreter_timeout_ms / 1000.0
        )
        async with session.post(
            f"{self.base_url}/cognitive-core/interpret",
            json=request.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Cognitive Core returned HTTP {resp.status}: {body[:500]}"
                )
            return CoreInterpretationResult.model_validate_json(body)

    async def health(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()


    async def stream_fast_advance(
        self,
        session: aiohttp.ClientSession,
        *,
        request: CognitiveWorkRequest,
        timeout_ms: int | None = None,
    ) -> AsyncIterator[FastPlannerStreamFrame]:
        """Yield validated NDJSON frames from one Fast Planner invocation."""

        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="stream_fast_advance",
            kind="tool_call",
            attributes={
                "endpoint": "/fast-advance",
                "timeout_ms": effective_timeout_ms,
            },
        ) as span:
            req = request.model_copy(
                update={
                    "context": runtime_tracer.inject_carrier(request.context),
                }
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/fast-advance",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        "Agent fast-advance stream returned HTTP "
                        f"{resp.status}: {body[:500]}"
                    )
                pending = b""
                frame_count = 0
                terminal_seen = False
                async for chunk in resp.content:
                    pending += bytes(chunk)
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not line.strip():
                            continue
                        frame = _FAST_PLANNER_STREAM_FRAME_ADAPTER.validate_json(
                            line
                        )
                        frame_count += 1
                        if isinstance(frame, FastPlannerStreamTerminal):
                            terminal_seen = True
                            runtime_tracer.merge_fragment_from_metadata(
                                frame.advance.metadata
                            )
                        yield frame
                if pending.strip():
                    frame = _FAST_PLANNER_STREAM_FRAME_ADAPTER.validate_json(pending)
                    frame_count += 1
                    if isinstance(frame, FastPlannerStreamTerminal):
                        terminal_seen = True
                        runtime_tracer.merge_fragment_from_metadata(
                            frame.advance.metadata
                        )
                    yield frame
                span.set_attribute("frame_count", frame_count)
                span.set_attribute("terminal_seen", terminal_seen)

    async def resolve_fast_plan(
        self,
        session: aiohttp.ClientSession,
        *,
        request: CognitiveWorkRequest,
        timeout_ms: int | None = None,
    ) -> CanonicalPlan:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_fast_plan",
            kind="tool_call",
            attributes={"endpoint": "/fast-plan", "timeout_ms": effective_timeout_ms},
        ) as span:
            req = request.model_copy(
                update={
                    "context": runtime_tracer.inject_carrier(request.context),
                }
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
        request: CognitiveWorkRequest,
        timeout_ms: int | None = None,
    ) -> CanonicalPlan:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_deep_plan",
            kind="tool_call",
            attributes={"endpoint": "/deep-plan", "timeout_ms": effective_timeout_ms},
        ) as span:
            req = request.model_copy(
                update={
                    "context": runtime_tracer.inject_carrier(request.context),
                }
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

    async def resolve_reflection(
        self,
        session: aiohttp.ClientSession,
        *,
        request: ReflectionRequest,
        timeout_ms: int | None = None,
    ) -> ReflectionResolution:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="resolve_reflection",
            kind="tool_call",
            attributes={"endpoint": "/reflection", "timeout_ms": effective_timeout_ms},
        ) as span:
            req = request.model_copy(
                update={
                    "context": runtime_tracer.inject_carrier(request.context),
                }
            )
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/reflection",
                json=req.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent reflection endpoint returned HTTP {resp.status}: {body[:500]}"
                    )
                result = ReflectionResolution.model_validate_json(body)
            span.set_attribute("action_count", len(result.actions))
            return result

    async def execute_tool(
        self,
        session: aiohttp.ClientSession,
        *,
        request: ToolExecutionRequest,
        timeout_ms: int | None = None,
    ) -> ToolExecutionResponse:
        effective_timeout_ms = max(100, int(timeout_ms or self.timeout_ms))
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="execute_tool",
            kind="tool_call",
            attributes={
                "endpoint": "/tools/execute",
                "timeout_ms": effective_timeout_ms,
                "tool_id": request.tool_id,
            },
        ) as span:
            timeout = aiohttp.ClientTimeout(total=effective_timeout_ms / 1000.0)
            async with session.post(
                f"{self.base_url}/tools/execute",
                json=request.model_dump(mode="json"),
                timeout=timeout,
            ) as resp:
                body = await resp.text()
                span.set_attribute("http_status", resp.status)
                if resp.status != 200:
                    raise RuntimeError(
                        f"Agent tool execution returned HTTP {resp.status}: {body[:500]}"
                    )
                result = ToolExecutionResponse.model_validate_json(body)
            span.set_attribute("result_status", result.status)
            return result

    async def resolve_goal_association(
        self,
        session: aiohttp.ClientSession,
        *,
        request: CognitiveWorkRequest,
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
            req = request.model_copy(
                update={
                    "context": runtime_tracer.inject_carrier(request.context),
                }
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

    async def execute_planning_work_dag(
        self,
        session: aiohttp.ClientSession,
        dag: dict[str, Any],
        *,
        timeout_ms: int = 120000,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=max(100, int(timeout_ms)) / 1000.0)
        async with session.post(
            f"{self.base_url}/work-dags/execute-planning",
            json={"dag": dag},
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    f"Agent WorkDAG execution returned HTTP {resp.status}: {body[:500]}"
                )
            return dict(await resp.json())

    async def cancel_planning_work_dag(
        self,
        session: aiohttp.ClientSession,
        dag_id: str,
        *,
        timeout_ms: int = 3000,
    ) -> dict[str, Any]:
        normalized_dag_id = str(dag_id or "").strip()
        if not normalized_dag_id:
            raise ValueError("WorkDAG cancellation requires dag_id")
        if not self.dag_engine_execution_token:
            raise RuntimeError(
                "AGENT_DAG_ENGINE_EXECUTION_TOKEN is required for "
                "WorkDAG cancellation"
            )
        timeout = aiohttp.ClientTimeout(
            total=max(100, int(timeout_ms)) / 1000.0
        )
        async with session.post(
            (
                f"{self.base_url}/work-dags/"
                f"{quote(normalized_dag_id, safe='')}/cancel"
            ),
            headers={
                "Authorization": (
                    f"Bearer {self.dag_engine_execution_token}"
                )
            },
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(
                    "Agent WorkDAG cancellation returned "
                    f"HTTP {resp.status}: {body[:500]}"
                )
            return dict(await resp.json())
