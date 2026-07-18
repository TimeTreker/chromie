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
from .clients.weather_client import OpenMeteoWeatherClient
from .interaction import (
    AgentResultInteractionAdapter,
    InteractionOutputCoordinator,
    NativeInteractionOutputError,
)
from .runtime import AgentRuntime, InteractionRuntime
from .task_continuity import TaskContinuityResolver
from .goal_association import GoalAssociationResolver
from .fast_planner import FastPlannerResolver
from .deep_planner import DeepPlannerResolver
from .response_composer import ResponseComposerResolver
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
    from chromie_contracts.semantic_authority import semantic_authority_route_matrix
    from chromie_contracts.semantic_task import SemanticTaskOperationSet
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import InteractionResponse
    from shared.chromie_contracts.semantic_authority import semantic_authority_route_matrix
    from shared.chromie_contracts.semantic_task import SemanticTaskOperationSet


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8092")))
    ollama_url: str = Field(default_factory=lambda: os.getenv("AGENT_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("AGENT_MODEL", "gemma4:e2b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("AGENT_TIMEOUT_MS", "30000")))
    response_review_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_RESPONSE_REVIEW_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    response_review_model: str = Field(
        default_factory=lambda: os.getenv("AGENT_RESPONSE_REVIEW_MODEL", "gemma4:e2b")
    )
    response_review_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_RESPONSE_REVIEW_TIMEOUT_MS", "4000"))
    )
    response_review_mode: str = Field(
        default_factory=lambda: os.getenv("AGENT_RESPONSE_REVIEW_MODE", "auto")
    )
    use_llm: bool = Field(
        default_factory=lambda: os.getenv("AGENT_USE_LLM", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    max_speak_chars: int = Field(default_factory=lambda: int(os.getenv("AGENT_MAX_SPEAK_CHARS", "220")))
    expressive_body_cues: Literal["off", "sim_only", "on"] = Field(
        default_factory=lambda: os.getenv("AGENT_EXPRESSIVE_BODY_CUES", "off")
    )
    social_attention_mode: Literal["off", "report_only", "sim_only", "on"] = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SOCIAL_ATTENTION_MODE",
            os.getenv("AGENT_EXPRESSIVE_BODY_CUES", "off"),
        )
    )
    social_attention_model: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SOCIAL_ATTENTION_MODEL",
            os.getenv("ROUTER_MODEL", "qwen3:4b"),
        )
    )
    social_attention_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_SOCIAL_ATTENTION_TIMEOUT_MS", "2500")),
        ge=100,
        le=120000,
    )
    social_attention_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_SOCIAL_ATTENTION_NUM_CTX", "4096")),
        ge=512,
    )
    social_attention_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_SOCIAL_ATTENTION_NUM_PREDICT", "160")),
        ge=32,
        le=4096,
    )
    social_attention_wait_after_response_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_SOCIAL_ATTENTION_WAIT_AFTER_RESPONSE_MS", "0")),
        ge=0,
        le=120000,
    )
    social_attention_max_behaviors: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_SOCIAL_ATTENTION_MAX_BEHAVIORS", "2")),
        ge=1,
        le=3,
    )
    social_attention_capability_ids: tuple[str, ...] = Field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.getenv(
                "AGENT_SOCIAL_ATTENTION_CAPABILITIES",
                "",
            ).split(",")
            if item.strip()
        )
    )
    social_attention_fallback_target: str = Field(
        default_factory=lambda: os.getenv("AGENT_SOCIAL_ATTENTION_FALLBACK_TARGET", "none")
    )
    social_attention_fallback_direction: str | None = Field(
        default_factory=lambda: os.getenv("AGENT_SOCIAL_ATTENTION_FALLBACK_DIRECTION") or None
    )
    social_attention_fallback_yaw_rad: float | None = Field(
        default_factory=lambda: (
            float(os.getenv("AGENT_SOCIAL_ATTENTION_FALLBACK_YAW_RAD"))
            if os.getenv("AGENT_SOCIAL_ATTENTION_FALLBACK_YAW_RAD") not in {None, ""}
            else None
        )
    )
    social_attention_fallback_confidence: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_SOCIAL_ATTENTION_FALLBACK_CONFIDENCE", "0.0")),
        ge=0.0,
        le=1.0,
    )
    require_capability_plan_review: bool = Field(
        default_factory=lambda: os.getenv("AGENT_REQUIRE_CAPABILITY_PLAN_REVIEW", "0").strip().lower()
        not in {"0", "false", "no", "off"}
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
    legacy_capability_fallback_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED",
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
    weather_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_WEATHER_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    capability_prompt_tier_preset: str = Field(
        default_factory=lambda: os.getenv("AGENT_CAPABILITY_PROMPT_TIER_PRESET", "")
    )
    capability_prompt_tier_overrides: str = Field(
        default_factory=lambda: os.getenv("AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES", "")
    )
    task_continuity_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_TASK_CONTINUITY_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    task_continuity_model: str = Field(
        default_factory=lambda: os.getenv("AGENT_TASK_CONTINUITY_MODEL", "qwen3:4b")
    )
    task_continuity_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_TASK_CONTINUITY_TIMEOUT_MS", "3000")),
        ge=100,
        le=120000,
    )
    task_continuity_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_TASK_CONTINUITY_MIN_CONFIDENCE", "0.65")),
        ge=0.0,
        le=1.0,
    )
    task_continuity_max_active_tasks: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_TASK_CONTINUITY_MAX_ACTIVE_TASKS", "8")),
        ge=1,
        le=32,
    )
    task_continuity_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_TASK_CONTINUITY_NUM_CTX", "4096")),
        ge=2048,
        le=131072,
    )
    goal_association_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_GOAL_ASSOCIATION_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    goal_association_model: str = Field(
        default_factory=lambda: os.getenv("AGENT_GOAL_ASSOCIATION_MODEL", "qwen3:4b")
    )
    goal_association_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_ASSOCIATION_TIMEOUT_MS", "3000")), ge=100, le=120000
    )
    goal_association_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_GOAL_ASSOCIATION_MIN_CONFIDENCE", "0.65")), ge=0.0, le=1.0
    )
    goal_association_max_active_goals: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_ASSOCIATION_MAX_ACTIVE_GOALS", "8")), ge=1, le=32
    )
    goal_association_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_ASSOCIATION_NUM_CTX", "4096")), ge=2048, le=131072
    )
    goal_association_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_ASSOCIATION_NUM_PREDICT", "512")), ge=128, le=4096
    )
    fast_planner_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_FAST_PLANNER_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    fast_planner_model: str = Field(default_factory=lambda: os.getenv("AGENT_FAST_PLANNER_MODEL", "qwen3:4b"))
    fast_planner_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_TIMEOUT_MS", "2500")), ge=100, le=120000
    )
    fast_planner_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_FAST_PLANNER_MIN_CONFIDENCE", "0.80")), ge=0.0, le=1.0
    )
    fast_planner_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_NUM_CTX", "4096")), ge=2048, le=131072
    )
    fast_planner_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_NUM_PREDICT", "512")), ge=128, le=4096
    )
    fast_planner_max_capabilities: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_MAX_CAPABILITIES", "24")), ge=1, le=64
    )
    deep_planner_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_DEEP_PLANNER_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    deep_planner_model: str = Field(default_factory=lambda: os.getenv("AGENT_DEEP_PLANNER_MODEL", "gemma4:e2b"))
    deep_planner_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_DEEP_PLANNER_TIMEOUT_MS", "9000")), ge=100, le=120000
    )
    deep_planner_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_DEEP_PLANNER_MIN_CONFIDENCE", "0.65")), ge=0.0, le=1.0
    )
    deep_planner_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_DEEP_PLANNER_NUM_CTX", "8192")), ge=4096, le=131072
    )
    deep_planner_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_DEEP_PLANNER_NUM_PREDICT", "1024")), ge=256, le=8192
    )
    deep_planner_max_capabilities: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_DEEP_PLANNER_MAX_CAPABILITIES", "96")), ge=1, le=256
    )
    deep_planner_min_goal_satisfaction: float = Field(default_factory=lambda: float(os.getenv("AGENT_DEEP_PLANNER_MIN_GOAL_SATISFACTION", "0.75")), ge=0.0, le=1.0)
    deep_planner_max_replans: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_DEEP_PLANNER_MAX_REPLANS", "1")), ge=0, le=2
    )
    response_composer_enabled: bool = Field(
        default_factory=lambda: os.getenv("AGENT_RESPONSE_COMPOSER_ENABLED", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    response_composer_model: str = Field(
        default_factory=lambda: os.getenv("AGENT_RESPONSE_COMPOSER_MODEL", "gemma4:e2b")
    )
    response_composer_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_RESPONSE_COMPOSER_TIMEOUT_MS", "4500")), ge=100, le=120000
    )
    response_composer_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_RESPONSE_COMPOSER_NUM_CTX", "4096")), ge=2048, le=131072
    )
    response_composer_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_RESPONSE_COMPOSER_NUM_PREDICT", "640")), ge=128, le=4096
    )
    task_continuity_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_TASK_CONTINUITY_NUM_PREDICT", "256")),
        ge=128,
        le=4096,
    )
    log_level: str = Field(default_factory=lambda: os.getenv("AGENT_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))
    mode: Literal["runtime"] = "runtime"


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.agent")

ollama_client = OllamaClient(
    settings.ollama_url,
    settings.model,
    timeout_ms=settings.timeout_ms,
    purpose="agent_default",
)
weather_client = OpenMeteoWeatherClient() if settings.weather_enabled else None

response_reviewer_client = (
    OllamaClient(
        settings.ollama_url,
        settings.response_review_model,
        timeout_ms=settings.response_review_timeout_ms,
        purpose="response_review",
    )
    if settings.use_llm and settings.response_review_enabled
    else None
)
social_attention_client = (
    OllamaClient(
        settings.ollama_url,
        settings.social_attention_model,
        timeout_ms=settings.social_attention_timeout_ms,
        purpose="social_attention",
    )
    if settings.use_llm and settings.social_attention_mode != "off"
    else None
)
task_continuity_client = (
    OllamaClient(
        settings.ollama_url,
        settings.task_continuity_model,
        timeout_ms=settings.task_continuity_timeout_ms,
        purpose="task_continuity",
    )
    if settings.use_llm and settings.task_continuity_enabled
    else None
)
task_continuity_resolver = (
    TaskContinuityResolver(
        task_continuity_client,
        min_confidence=settings.task_continuity_min_confidence,
        max_active_tasks=settings.task_continuity_max_active_tasks,
        num_ctx=settings.task_continuity_num_ctx,
        num_predict=settings.task_continuity_num_predict,
    )
    if task_continuity_client is not None
    else None
)
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
    prompt_tier_preset=CapabilityCatalog.load_prompt_tier_preset(
        settings.capability_prompt_tier_preset
    ),
    prompt_tier_overrides=CapabilityCatalog.load_prompt_tier_overrides(
        settings.capability_prompt_tier_overrides
    ),
)
task_graph_planner = (
    TaskGraphPlanner(capability_registry, ollama_client)
    if settings.enable_task_graph_planning and settings.use_llm
    else None
)
services = AgentServices(
    ollama=ollama_client,
    response_reviewer=response_reviewer_client,
    response_review_mode=settings.response_review_mode,
    use_llm=settings.use_llm,
    max_speak_chars=settings.max_speak_chars,
    expressive_body_cues=settings.expressive_body_cues,
    social_attention_mode=settings.social_attention_mode,
    social_attention_ollama=social_attention_client,
    social_attention_num_ctx=settings.social_attention_num_ctx,
    social_attention_num_predict=settings.social_attention_num_predict,
    social_attention_max_behaviors=settings.social_attention_max_behaviors,
    social_attention_wait_after_response_ms=settings.social_attention_wait_after_response_ms,
    social_attention_capability_ids=settings.social_attention_capability_ids,
    social_attention_fallback_target=settings.social_attention_fallback_target,
    social_attention_fallback_direction=settings.social_attention_fallback_direction,
    social_attention_fallback_yaw_rad=settings.social_attention_fallback_yaw_rad,
    social_attention_fallback_confidence=settings.social_attention_fallback_confidence,
    require_capability_plan_review=settings.require_capability_plan_review,
    legacy_capability_fallback_enabled=settings.legacy_capability_fallback_enabled,
    task_graph_planner=task_graph_planner,
    capability_catalog=capability_catalog,
    capability_match_limit=settings.capability_match_limit,
    weather_client=weather_client,
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
goal_association_client = (
    OllamaClient(
        settings.ollama_url,
        settings.goal_association_model,
        timeout_ms=settings.goal_association_timeout_ms,
        purpose="goal_association",
    )
    if settings.use_llm and settings.goal_association_enabled
    else None
)
goal_association_resolver = (
    GoalAssociationResolver(
        goal_association_client,
        min_confidence=settings.goal_association_min_confidence,
        max_active_goals=settings.goal_association_max_active_goals,
        num_ctx=settings.goal_association_num_ctx,
        num_predict=settings.goal_association_num_predict,
    )
    if goal_association_client is not None
    else None
)

fast_planner_client = (
    OllamaClient(
        settings.ollama_url,
        settings.fast_planner_model,
        timeout_ms=settings.fast_planner_timeout_ms,
        purpose="fast_planner",
    )
    if settings.use_llm and settings.fast_planner_enabled
    else None
)
fast_planner_resolver = (
    FastPlannerResolver(
        fast_planner_client,
        capability_catalog,
        min_confidence=settings.fast_planner_min_confidence,
        num_ctx=settings.fast_planner_num_ctx,
        num_predict=settings.fast_planner_num_predict,
        max_capabilities=settings.fast_planner_max_capabilities,
    )
    if fast_planner_client is not None
    else None
)
deep_planner_client = (
    OllamaClient(
        settings.ollama_url,
        settings.deep_planner_model,
        timeout_ms=settings.deep_planner_timeout_ms,
        purpose="deep_planner",
    )
    if settings.use_llm and settings.deep_planner_enabled
    else None
)
deep_planner_resolver = (
    DeepPlannerResolver(
        deep_planner_client, capability_catalog,
        min_confidence=settings.deep_planner_min_confidence,
        num_ctx=settings.deep_planner_num_ctx,
        num_predict=settings.deep_planner_num_predict,
        max_capabilities=settings.deep_planner_max_capabilities,
        max_replans=settings.deep_planner_max_replans,
        min_goal_satisfaction=settings.deep_planner_min_goal_satisfaction,
    )
    if deep_planner_client is not None
    else None
)
response_composer_client = (
    OllamaClient(
        settings.ollama_url,
        settings.response_composer_model,
        timeout_ms=settings.response_composer_timeout_ms,
        purpose="response_composer",
    )
    if settings.use_llm and settings.response_composer_enabled
    else None
)
response_composer_resolver = (
    ResponseComposerResolver(
        response_composer_client,
        num_ctx=settings.response_composer_num_ctx,
        num_predict=settings.response_composer_num_predict,
    )
    if response_composer_client is not None
    else None
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
        legacy_capability_fallback_enabled=settings.legacy_capability_fallback_enabled,
        capability_catalog_enabled=True,
        capability_catalog_version=capability_catalog.version,
        task_continuity_enabled=task_continuity_resolver is not None,
        goal_association_enabled=goal_association_resolver is not None,
        goal_association_model=(
            settings.goal_association_model if goal_association_resolver is not None else None
        ),
        fast_planner_enabled=fast_planner_resolver is not None,
        fast_planner_model=(settings.fast_planner_model if fast_planner_resolver is not None else None),
        deep_planner_enabled=deep_planner_resolver is not None,
        deep_planner_model=(settings.deep_planner_model if deep_planner_resolver is not None else None),
        response_composer_enabled=response_composer_resolver is not None,
        response_composer_model=(settings.response_composer_model if response_composer_resolver is not None else None),
        task_continuity_model=(
            settings.task_continuity_model if task_continuity_resolver is not None else None
        ),
        social_attention_mode=settings.social_attention_mode,
        social_attention_model=(
            settings.social_attention_model if social_attention_client is not None else None
        ),
    )


@app.get("/semantic-authority")
async def semantic_authority() -> dict[str, object]:
    return {
        "matching_turn_authority_required": True,
        "claim_is_caller_authentication": False,
        "claim_is_single_use_replay_protection": False,
        "legacy_capability_fallback_enabled": (
            settings.legacy_capability_fallback_enabled
        ),
        "route_matrix": semantic_authority_route_matrix(),
    }


@app.get("/agents")
async def agents() -> dict:
    return {
        "agents": runtime.available_agents(),
        "notes": {
            "speaker_agent": "decides wording/style only; it does not access audio devices",
            "robot_pose_controller_agent": "legacy compatibility parser; disabled unless context.allow_legacy_rule_agents=true",
            "motion_planner_agent": "legacy compatibility parser; disabled unless context.allow_legacy_rule_agents=true",
            "safety_agent": "validates and clamps risky actions",
        },
    }


@app.post("/fast-plan")
async def resolve_fast_plan(request: AgentRunRequest):
    if fast_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Fast planner is disabled")
    return await fast_planner_resolver.resolve(request)


@app.post("/deep-plan")
async def resolve_deep_plan(request: AgentRunRequest):
    if deep_planner_resolver is None:
        raise HTTPException(status_code=503, detail="Deep planner is disabled")
    return await deep_planner_resolver.resolve(request)


@app.post("/compose-response-plan")
async def compose_response_plan(request: AgentRunRequest):
    if response_composer_resolver is None:
        raise HTTPException(status_code=503, detail="Response composer is disabled")
    await interaction_runtime.prepare_response_composition_context(request)
    return await response_composer_resolver.resolve(request)


@app.post("/goal-association")
async def resolve_goal_association(request: AgentRunRequest):
    if goal_association_resolver is None:
        raise HTTPException(status_code=503, detail="Goal association resolver is disabled")
    return await goal_association_resolver.resolve(request)


@app.post("/task-continuity", response_model=SemanticTaskOperationSet)
async def resolve_task_continuity(request: AgentRunRequest) -> SemanticTaskOperationSet:
    if task_continuity_resolver is None:
        raise HTTPException(status_code=503, detail="Task continuity resolver is disabled")
    try:
        return await task_continuity_resolver.resolve(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - final service-boundary guard
        logger.exception(
            "task_continuity_endpoint_degraded sid=%s error_type=%s error=%s",
            request.sid,
            type(exc).__name__,
            exc,
        )
        return SemanticTaskOperationSet(
            confidence=0.0,
            reason_summary="Task continuity service failed safely; no operation was accepted.",
            metadata={
                "resolver": "task_continuity_agent",
                "status": "service_unavailable",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
                "sid": request.sid,
            },
        )


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
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
