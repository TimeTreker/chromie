from __future__ import annotations

import logging
import os
import time
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .agents import AgentServices
from .capabilities.loader import build_configured_registry, parse_manifest_paths
from .clients.ollama_client import OllamaClient
from .runtime import AgentRuntime
from .schema import AgentResult, AgentRunRequest, HealthResponse
from .task_graph import (
    ExecutionTrace,
    TaskGraph,
    TaskGraphDryRunRequest,
    TaskGraphPlanner,
    TaskGraphService,
    TaskGraphValidationResponse,
)


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
    max_speak_chars: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_SPEAK_CHARS", "160")))
    enable_task_graph_planning: bool = Field(
        default_factory=lambda: os.getenv("AGENT_ENABLE_TASK_GRAPH_PLANNING", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    capability_manifests: str = Field(default_factory=lambda: os.getenv("AGENT_CAPABILITY_MANIFESTS", ""))
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
task_graph_planner = (
    TaskGraphPlanner(capability_registry, ollama_client)
    if settings.enable_task_graph_planning and settings.use_llm
    else None
)
services = AgentServices(
    ollama=ollama_client,
    use_llm=settings.use_llm,
    max_speak_chars=settings.max_speak_chars,
    task_graph_planner=task_graph_planner,
)
runtime = AgentRuntime(services)
task_graph_service = TaskGraphService(capability_registry)
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


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        model=settings.model,
        ollama_url=settings.ollama_url,
        use_llm=settings.use_llm,
        available_agents=runtime.available_agents(),
        capability_sources=configured_registry.sources,
        capability_manifest_files=configured_registry.manifest_files,
        task_graph_planning_enabled=task_graph_planner is not None,
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


@app.get("/capabilities/llm-context")
async def capability_llm_context(language: str = "en") -> dict[str, str]:
    return {"context": capability_registry.llm_context(language=language)}


@app.post("/task-graphs/validate", response_model=TaskGraphValidationResponse)
async def validate_task_graph(graph: TaskGraph) -> TaskGraphValidationResponse:
    return task_graph_service.validate(graph)


@app.post("/task-graphs/dry-run", response_model=ExecutionTrace)
async def dry_run_task_graph(request: TaskGraphDryRunRequest) -> ExecutionTrace:
    try:
        return task_graph_service.dry_run(request.graph, auto_confirm=request.auto_confirm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/task-graphs/{graph_id}/trace", response_model=ExecutionTrace)
async def get_task_graph_trace(graph_id: str) -> ExecutionTrace:
    trace = task_graph_service.get_trace(graph_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No TaskGraph trace found for {graph_id!r}")
    return trace


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
