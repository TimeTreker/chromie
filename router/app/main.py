from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .capability_catalog import CapabilityCatalogClient, CapabilityCatalogResult
from .config import router_mode_from_env
from .fallback import fallback_decision
from .llm_router import OllamaLLMRouter
from .rules import route_by_priority_rules, route_by_rules
from .schema import HealthResponse, RouteDecision, RouteRequest, finalize_decision


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("ROUTER_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("ROUTER_PORT", "8091")))
    mode: Literal["rules_only", "llm_only", "hybrid"] = Field(
        default_factory=router_mode_from_env
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
    capability_catalog_url: str = Field(
        default_factory=lambda: os.getenv(
            "ROUTER_CAPABILITY_CATALOG_URL",
            "http://chromie-agent:8092",
        )
    )
    capability_catalog_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS", "600"))
    )
    capability_match_limit: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_MATCH_LIMIT", "8"))
    )
    allow_legacy_robot_rules: bool = Field(
        default_factory=lambda: os.getenv(
            "ROUTER_ALLOW_LEGACY_ROBOT_RULES",
            "0",
        ).strip().lower() not in {"0", "false", "no", "off"}
    )
    log_level: str = Field(default_factory=lambda: os.getenv("ROUTER_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))


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

capability_catalog = CapabilityCatalogClient(
    settings.capability_catalog_url,
    timeout_ms=settings.capability_catalog_timeout_ms,
    limit=settings.capability_match_limit,
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
            "capability_agent",
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


def _catalog_decision(
    request: RouteRequest,
    result: CapabilityCatalogResult,
) -> RouteDecision | None:
    if not result.matched or not result.matches:
        return None
    route = result.suggested_route
    if route not in {"chat", "robot_action", "tool", "memory"}:
        route = "tool"
    top = result.matches[0]
    score = float(top.get("score") or 0.0)
    agents = list(result.suggested_agents or ["capability_agent", "speaker_agent"])
    return finalize_decision(
        RouteDecision(
            route=route,
            agents=agents,
            intent=f"capability:{top.get('capability_id', 'match')}",
            confidence=max(0.56, min(0.99, score)),
            language=request.language or "auto",
            priority="normal",
            needs_agent=True,
            should_speak=True,
            candidate_capabilities=result.matches,
            reason=f"Matched shared capability catalog v{result.catalog_version}",
            source="catalog",
        ),
        request,
        source="catalog",
    )


@app.post("/route", response_model=RouteDecision)
async def route(request: RouteRequest) -> RouteDecision:
    start = time.perf_counter()
    request.text = request.text.strip()

    priority = route_by_priority_rules(request)
    if priority is not None:
        decision = priority
    else:
        catalog_result = await capability_catalog.search(
            text=request.text,
            language=request.language,
        )
        decision = _catalog_decision(request, catalog_result)

        legacy_decision: RouteDecision | None = None
        if decision is None and settings.mode in ("rules_only", "hybrid") and settings.rules_first:
            legacy_decision = route_by_rules(request)
            if (
                legacy_decision is not None
                and legacy_decision.route == "robot_action"
                and not settings.allow_legacy_robot_rules
            ):
                legacy_decision = None
            decision = legacy_decision

        if decision is None:
            if settings.mode == "rules_only":
                decision = fallback_decision(request, reason="catalog_and_rules_no_match")
            elif settings.mode in ("llm_only", "hybrid"):
                request.context = {
                    **request.context,
                    "candidate_capabilities": catalog_result.matches,
                    "capability_catalog_version": catalog_result.catalog_version,
                }
                decision = await llm_router.route(request)
            else:
                decision = fallback_decision(request, reason=f"unknown_router_mode:{settings.mode}")

    decision = finalize_decision(decision, request, source=decision.source)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "route sid=%s source=%s route=%s intent=%s confidence=%.2f capabilities=%d ms=%.1f",
        request.sid,
        decision.source,
        decision.route,
        decision.intent,
        decision.confidence,
        len(decision.candidate_capabilities),
        elapsed_ms,
    )
    return decision


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
