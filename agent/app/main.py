from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .agents import AgentServices
from .capabilities.catalog import CapabilityCatalog, CapabilitySearchRequest, CapabilitySearchResult
from .capabilities.loader import build_configured_registry, parse_manifest_paths
from .clients.ollama_client import OllamaClient
from .interaction import (
    AgentResultInteractionAdapter,
    InteractionOutputCoordinator,
    NativeInteractionOutputError,
)
from .runtime import AgentRuntime, InteractionRuntime
from .schema import AgentResult, AgentRunRequest, HealthResponse
from .task_graph import (
    ExecutionTrace,
    TaskGraph,
    TaskGraphCancelResponse,
    TaskGraphConfirmationGrantRequest,
    TaskGraphConfirmationGrantResponse,
    TaskGraphDryRunRequest,
    TaskGraphExecuteRequest,
    TaskGraphGuardedExecuteRequest,
    TaskGraphSchedulerStatus,
    TaskGraphPlanner,
    TaskGraphService,
    TaskGraphValidationResponse,
)
from .tool_invocation import McpStreamableHttpInvoker

try:
    from chromie_contracts.interaction import InteractionResponse
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8092")))
    ollama_url: str = Field(default_factory=lambda: os.getenv("AGENT_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("AGENT_MODEL", "gemma4:e2b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("AGENT_TIMEOUT_MS", "30000")))
    use_llm: bool = Field(
        default_factory=lambda: os.getenv("AGENT_USE_LLM", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    max_speak_chars: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_SPEAK_CHARS", "220")))
    expressive_body_cues: Literal["off", "sim_only", "on"] = Field(
        default_factory=lambda: os.getenv("AGENT_EXPRESSIVE_BODY_CUES", "sim_only")
    )
    interaction_output_mode: Literal["native", "legacy-adapter"] = Field(
        default_factory=lambda: os.getenv("AGENT_INTERACTION_OUTPUT_MODE", "native")
    )
    native_interaction_fallback: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_NATIVE_INTERACTION_FALLBACK",
            "0",
        ).strip().lower()
        not in {"0", "false", "no", "off"}
    )
    enable_task_graph_planning: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_TASK_GRAPH_PLANNING", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    enable_read_only_task_graph_execution: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    enable_planning_task_graph_execution: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    enable_parallel_task_graph_execution: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION",
            "0",
        ).strip().lower()
        not in {"0", "false", "no", "off"}
    )
    task_graph_max_concurrency: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_TASK_GRAPH_MAX_CONCURRENCY", "4")
        ),
        ge=1,
        le=64,
    )
    enable_guarded_task_graph_execution: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    enable_physical_task_graph_execution: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    task_graph_execution_token: str = Field(
        default_factory=lambda: os.getenv("AGENT_TASK_GRAPH_EXECUTION_TOKEN", "")
    )
    task_graph_diagnostics_token: str = Field(
        default_factory=lambda: (
            os.getenv("AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN", "").strip()
            or os.getenv("AGENT_TASK_GRAPH_EXECUTION_TOKEN", "").strip()
        )
    )
    task_graph_trace_max_entries: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_TASK_GRAPH_TRACE_MAX_ENTRIES", "128")
        ),
        ge=1,
        le=10000,
    )
    task_graph_trace_ttl_sec: float = Field(
        default_factory=lambda: float(
            os.getenv("AGENT_TASK_GRAPH_TRACE_TTL_SEC", "900")
        ),
        gt=0,
        le=86400,
    )
    task_graph_grant_max_entries: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_TASK_GRAPH_GRANT_MAX_ENTRIES", "128")
        ),
        ge=1,
        le=10000,
    )
    capability_manifests: str = Field(default_factory=lambda: os.getenv("AGENT_CAPABILITY_MANIFESTS", ""))
    capability_catalog_refresh_sec: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_CAPABILITY_CATALOG_REFRESH_SEC", "30")),
        ge=1.0,
        le=3600.0,
    )
    capability_match_min_score: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_CAPABILITY_MATCH_MIN_SCORE", "0.16")),
        ge=0.0,
        le=1.0,
    )
    capability_match_limit: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_CAPABILITY_MATCH_LIMIT", "8")),
        ge=1,
        le=32,
    )
    log_level: str = Field(default_factory=lambda: os.getenv("AGENT_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))
    mode: Literal["runtime"] = "runtime"


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.agent")

ollama_client = OllamaClient(settings.ollama_url, settings.model, timeout_ms=settings.timeout_ms)
configured_registry = build_configured_registry(parse_manifest_paths(settings.capability_manifests))
capability_registry = configured_registry.registry
try:
    capability_registry.get_tool("soridormi.skill.list")
except KeyError:
    capability_catalog_invoker = None
else:
    capability_catalog_invoker = McpStreamableHttpInvoker(capability_registry)
capability_catalog = CapabilityCatalog(
    capability_registry,
    live_invoker=capability_catalog_invoker,
    refresh_ttl_s=settings.capability_catalog_refresh_sec,
    min_score=settings.capability_match_min_score,
)
task_graph_planner = (
    TaskGraphPlanner(capability_registry, ollama_client)
    if settings.enable_task_graph_planning and settings.use_llm
    else None
)
services = AgentServices(
    ollama=ollama_client,
    use_llm=settings.use_llm,
    max_speak_chars=settings.max_speak_chars,
    expressive_body_cues=settings.expressive_body_cues,
    task_graph_planner=task_graph_planner,
    capability_catalog=capability_catalog,
    capability_match_limit=settings.capability_match_limit,
)
runtime = AgentRuntime(services)
interaction_runtime = InteractionRuntime(services)
interaction_adapter = AgentResultInteractionAdapter()
interaction_output = InteractionOutputCoordinator(
    interaction_runtime,
    runtime,
    mode=settings.interaction_output_mode,
    fallback_to_legacy=settings.native_interaction_fallback,
    adapter=interaction_adapter,
)
read_only_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_read_only_task_graph_execution
    else None
)
planning_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_planning_task_graph_execution
    else None
)
if settings.enable_physical_task_graph_execution and not settings.enable_guarded_task_graph_execution:
    raise ValueError(
        "AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION is required when physical TaskGraph execution is enabled"
    )
if settings.enable_guarded_task_graph_execution and not settings.task_graph_execution_token:
    raise ValueError(
        "AGENT_TASK_GRAPH_EXECUTION_TOKEN is required when guarded TaskGraph execution is enabled"
    )
guarded_invoker = (
    McpStreamableHttpInvoker(capability_registry)
    if settings.enable_guarded_task_graph_execution
    else None
)
task_graph_service = TaskGraphService(
    capability_registry,
    read_only_invoker=read_only_invoker,
    planning_invoker=planning_invoker,
    guarded_invoker=guarded_invoker,
    allow_physical_motion=settings.enable_physical_task_graph_execution,
    enable_parallel_execution=settings.enable_parallel_task_graph_execution,
    max_concurrency=settings.task_graph_max_concurrency,
    trace_max_entries=settings.task_graph_trace_max_entries,
    trace_ttl_s=settings.task_graph_trace_ttl_sec,
    grant_max_entries=settings.task_graph_grant_max_entries,
)
logger.info(
    "loaded capability registry sources=%s manifests=%s tools=%d",
    ",".join(configured_registry.sources),
    ",".join(configured_registry.manifest_files) or "<none>",
    len(capability_registry.list_tools()),
)

app = FastAPI(
    title="Chromie Agent",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)


def require_task_graph_execution_auth(authorization: str | None) -> None:
    expected = f"Bearer {settings.task_graph_execution_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid TaskGraph execution authorization")


def require_task_graph_diagnostics_auth(authorization: str | None) -> None:
    if not settings.task_graph_diagnostics_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "TaskGraph diagnostics are disabled; configure "
                "AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN"
            ),
        )
    expected = f"Bearer {settings.task_graph_diagnostics_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=401,
            detail="invalid TaskGraph diagnostics authorization",
        )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    scheduler = task_graph_service.scheduler_status()
    return HealthResponse(
        ok=True,
        model=settings.model,
        ollama_url=settings.ollama_url,
        use_llm=settings.use_llm,
        available_agents=runtime.available_agents(),
        capability_sources=configured_registry.sources,
        capability_manifest_files=configured_registry.manifest_files,
        task_graph_planning_enabled=task_graph_planner is not None,
        read_only_task_graph_execution_enabled=read_only_invoker is not None,
        planning_task_graph_execution_enabled=planning_invoker is not None,
        parallel_task_graph_execution_enabled=(
            settings.enable_parallel_task_graph_execution
        ),
        task_graph_max_concurrency=settings.task_graph_max_concurrency,
        task_graph_active_count=scheduler.active_count,
        task_graph_waiting_count=scheduler.waiting_count,
        guarded_task_graph_execution_enabled=guarded_invoker is not None,
        physical_task_graph_execution_enabled=(
            guarded_invoker is not None and settings.enable_physical_task_graph_execution
        ),
        interaction_output_mode=settings.interaction_output_mode,
        native_interaction_fallback_enabled=settings.native_interaction_fallback,
        capability_catalog_enabled=True,
        capability_catalog_version=capability_catalog.version,
    )


@app.get("/agents")
async def agents() -> dict:
    return {
        "agents": runtime.available_agents(),
        "notes": {
            "speaker_agent": "decides wording/style only; it does not access audio devices",
            "robot_pose_controller_agent": "plans pose/head/gesture commands",
            "motion_planner_agent": "plans simple safe movement commands",
            "safety_agent": "validates and clamps risky actions",
        },
    }


@app.get("/capabilities")
async def capabilities() -> dict:
    payload = capability_registry.model_dump()
    payload["sources"] = configured_registry.sources
    payload["manifest_files"] = configured_registry.manifest_files
    return payload


@app.get("/capabilities/catalog")
async def capability_catalog_snapshot(refresh: bool = False) -> dict[str, object]:
    return await capability_catalog.snapshot(refresh=refresh)


@app.post("/capabilities/search", response_model=CapabilitySearchResult)
async def capability_search(request: CapabilitySearchRequest) -> CapabilitySearchResult:
    return await capability_catalog.search(
        request.text,
        language=request.language,
        limit=request.limit,
        min_score=request.min_score,
        refresh=request.refresh,
        prefer_interaction_executable=request.prefer_interaction_executable,
    )


@app.get("/capabilities/llm-context")
async def capability_llm_context(
    language: str = "en",
    text: str | None = None,
    limit: int = 20,
) -> dict[str, str]:
    return {
        "context": await capability_catalog.llm_context(
            text=text,
            language=language,
            limit=max(1, min(limit, 64)),
        )
    }


@app.post("/task-graphs/validate", response_model=TaskGraphValidationResponse)
async def validate_task_graph(graph: TaskGraph) -> TaskGraphValidationResponse:
    return task_graph_service.validate(graph)


@app.post("/task-graphs/dry-run", response_model=ExecutionTrace)
async def dry_run_task_graph(
    request: TaskGraphDryRunRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_diagnostics_auth(authorization)
    try:
        return task_graph_service.dry_run(request.graph, auto_confirm=request.auto_confirm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-read-only", response_model=ExecutionTrace)
async def execute_read_only_task_graph(request: TaskGraphExecuteRequest) -> ExecutionTrace:
    try:
        return await task_graph_service.execute_read_only(request.graph)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-planning", response_model=ExecutionTrace)
async def execute_planning_task_graph(request: TaskGraphExecuteRequest) -> ExecutionTrace:
    try:
        return await task_graph_service.execute_planning(request.graph)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/task-graphs/execute-guarded", response_model=ExecutionTrace)
async def execute_guarded_task_graph(
    request: TaskGraphGuardedExecuteRequest,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_execution_auth(authorization)
    try:
        return await task_graph_service.execute_guarded(
            request.graph,
            request.confirmation_grant,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/task-graphs/confirmation-grants",
    response_model=TaskGraphConfirmationGrantResponse,
)
async def create_task_graph_confirmation_grant(
    request: TaskGraphConfirmationGrantRequest,
    authorization: str | None = Header(default=None),
) -> TaskGraphConfirmationGrantResponse:
    require_task_graph_execution_auth(authorization)
    try:
        return task_graph_service.issue_confirmation_grant(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/task-graphs/{graph_id}/cancel",
    response_model=TaskGraphCancelResponse,
)
async def cancel_task_graph(
    graph_id: str,
    authorization: str | None = Header(default=None),
) -> TaskGraphCancelResponse:
    require_task_graph_execution_auth(authorization)
    return task_graph_service.cancel_execution(graph_id)


@app.get("/task-graphs/{graph_id}/trace", response_model=ExecutionTrace)
async def get_task_graph_trace(
    graph_id: str,
    authorization: str | None = Header(default=None),
) -> ExecutionTrace:
    require_task_graph_diagnostics_auth(authorization)
    trace = task_graph_service.get_trace(graph_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No TaskGraph trace found for {graph_id!r}")
    return trace


@app.get("/task-graphs/scheduler/status", response_model=TaskGraphSchedulerStatus)
async def get_task_graph_scheduler_status(
    authorization: str | None = Header(default=None),
) -> TaskGraphSchedulerStatus:
    require_task_graph_diagnostics_auth(authorization)
    return task_graph_service.scheduler_status()


@app.post("/run", response_model=AgentResult)
async def run_agent(request: AgentRunRequest) -> AgentResult:
    start = time.perf_counter()
    result = await runtime.run(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "agent sid=%s route=%s intent=%s status=%s agents=%s actions=%d speak_immediate=%d speak_after=%d ms=%.1f",
        request.sid,
        request.route_decision.route,
        request.route_decision.intent,
        result.status,
        ",".join(result.handled_by),
        len(result.actions),
        len(result.speak_immediate),
        len(result.speak_after),
        elapsed_ms,
    )
    result.trace.append(f"runtime: total_ms={elapsed_ms:.1f}")
    return result


@app.post("/interaction", response_model=InteractionResponse)
async def run_interaction(request: AgentRunRequest) -> InteractionResponse:
    start = time.perf_counter()
    try:
        response = await interaction_output.run(request)
    except NativeInteractionOutputError as exc:
        logger.exception(
            "native_interaction_validation_failed sid=%s route=%s intent=%s fallback=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            settings.native_interaction_fallback,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    response.metadata["runtime_ms"] = round(elapsed_ms, 1)
    logger.info(
        "interaction sid=%s route=%s intent=%s status=%s output_mode=%s speech=%d skills=%d confirmation=%s ms=%.1f",
        request.sid,
        request.route_decision.route,
        request.route_decision.intent,
        response.status,
        response.metadata.get("interaction_output_mode"),
        len(response.speech),
        len(response.skills),
        response.requires_confirmation,
        elapsed_ms,
    )
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
