from __future__ import annotations

import logging
import os
import time
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .agents import AgentServices
from .capabilities.local import build_chromie_registry
from .clients.ollama_client import OllamaClient
from .runtime import AgentRuntime
from .schema import AgentResult, AgentRunRequest, HealthResponse


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8092")))
    ollama_url: str = Field(default_factory=lambda: os.getenv("AGENT_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("AGENT_MODEL", "qwen3:4b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("AGENT_TIMEOUT_MS", "2500")))
    use_llm: bool = Field(
        default_factory=lambda: os.getenv("AGENT_USE_LLM", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    max_speak_chars: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_SPEAK_CHARS", "120")))
    log_level: str = Field(default_factory=lambda: os.getenv("AGENT_LOG_LEVEL", "INFO"))
    mode: Literal["runtime"] = "runtime"


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.agent")

ollama_client = OllamaClient(settings.ollama_url, settings.model, timeout_ms=settings.timeout_ms)
services = AgentServices(
    ollama=ollama_client,
    use_llm=settings.use_llm,
    max_speak_chars=settings.max_speak_chars,
)
runtime = AgentRuntime(services)
capability_registry = build_chromie_registry()

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
    """Return Chromie's local capability registry.

    The full global registry may also include remote MCP manifests loaded by an
    agent host. This endpoint exposes the Chromie-side speech/task capabilities.
    """

    return capability_registry.model_dump()


@app.get("/capabilities/llm-context")
async def capability_llm_context(language: str = "en") -> dict[str, str]:
    return {"context": capability_registry.llm_context(language=language)}


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
