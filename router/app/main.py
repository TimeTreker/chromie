from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .fallback import fallback_decision
from .llm_router import OllamaLLMRouter
from .rules import route_by_rules
from .schema import HealthResponse, RouteDecision, RouteRequest, finalize_decision


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("ROUTER_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("ROUTER_PORT", "8091")))
    mode: Literal["rules_only", "llm_only", "hybrid"] = Field(
        default_factory=lambda: os.getenv("ROUTER_MODE", "hybrid").strip().lower()
    )
    rules_first: bool = Field(
        default_factory=lambda: os.getenv("ROUTER_RULES_FIRST", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    ollama_url: str = Field(default_factory=lambda: os.getenv("ROUTER_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("ROUTER_MODEL", "qwen3:0.6b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_TIMEOUT_MS", "800")))
    llm_timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_LLM_TIMEOUT_MS", os.getenv("ROUTER_TIMEOUT_MS", "800"))))
    confidence_threshold: float = Field(
        default_factory=lambda: float(os.getenv("ROUTER_CONFIDENCE_THRESHOLD", "0.55"))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("ROUTER_LOG_LEVEL", "INFO"))


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.router")

app = FastAPI(
    title="Chromie Router",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

llm_router = OllamaLLMRouter(
    ollama_url=settings.ollama_url,
    model=settings.model,
    timeout_ms=settings.llm_timeout_ms,
    confidence_threshold=settings.confidence_threshold,
    prompt_path=Path(__file__).parent / "prompts" / "router_system.txt",
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        mode=settings.mode,
        model=settings.model,
        ollama_url=settings.ollama_url,
        rules_first=settings.rules_first,
    )


@app.get("/routes")
async def routes() -> dict:
    return {
        "routes": ["chat", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"],
        "agents": [
            "conversation_agent",
            "speaker_agent",
            "robot_pose_controller_agent",
            "motion_planner_agent",
            "safety_agent",
            "tool_agent",
            "memory_agent",
            "vision_agent",
        ],
    }


@app.post("/route", response_model=RouteDecision)
async def route(request: RouteRequest) -> RouteDecision:
    start = time.perf_counter()
    request.text = request.text.strip()

    decision: RouteDecision | None = None

    if settings.mode in ("rules_only", "hybrid") and settings.rules_first:
        decision = route_by_rules(request)
        if decision is not None:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.info(
                "route sid=%s source=%s route=%s intent=%s confidence=%.2f ms=%.1f",
                request.sid,
                decision.source,
                decision.route,
                decision.intent,
                decision.confidence,
                elapsed_ms,
            )
            return decision

    if settings.mode == "rules_only":
        decision = fallback_decision(request, reason="rules_only_no_match")
    elif settings.mode in ("llm_only", "hybrid"):
        decision = await llm_router.route(request)
    else:
        decision = fallback_decision(request, reason=f"unknown_router_mode:{settings.mode}")

    decision = finalize_decision(decision, request, source=decision.source)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "route sid=%s source=%s route=%s intent=%s confidence=%.2f ms=%.1f",
        request.sid,
        decision.source,
        decision.route,
        decision.intent,
        decision.confidence,
        elapsed_ms,
    )
    return decision


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
