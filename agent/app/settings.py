from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

try:
    from chromie_contracts.social_attention import (
        SocialAttentionMode,
        normalize_social_attention_mode,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.social_attention import (
        SocialAttentionMode,
        normalize_social_attention_mode,
    )


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("AGENT_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("AGENT_PORT", "8092")))
    ollama_url: str = Field(default_factory=lambda: os.getenv("AGENT_OLLAMA_URL") or os.getenv("OLLAMA_URL") or "http://chromie-llm:11434")
    model: str = Field(default_factory=lambda: os.getenv("AGENT_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma4:e2b")
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("AGENT_TIMEOUT_MS") or os.getenv("OLLAMA_TIMEOUT_MS") or "30000"))
    use_llm: bool = Field(
        default_factory=lambda: os.getenv("AGENT_USE_LLM", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    social_attention_mode: SocialAttentionMode = Field(
        default_factory=lambda: normalize_social_attention_mode(
            os.getenv("AGENT_SOCIAL_ATTENTION_MODE", "on"),
            default="on",
        )
    )
    social_attention_model: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SOCIAL_ATTENTION_MODEL",
            os.getenv("AGENT_GOAL_INTERPRETER_MODEL", "qwen3:4b"),
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
    agent_skill_roots: str = Field(
        default_factory=lambda: os.getenv("AGENT_SKILL_ROOTS", "agent-skills")
    )
    agent_skill_selection_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SKILL_SELECTION_ENABLED",
            "1",
        ).strip().lower() not in {"0", "false", "no", "off"}
    )
    agent_skill_selection_model: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SKILL_SELECTION_MODEL",
            os.getenv("AGENT_GOAL_ASSOCIATION_MODEL", "qwen3:4b"),
        )
    )
    agent_skill_selection_timeout_ms: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_SELECTION_TIMEOUT_MS", "10000")
        ),
        ge=100,
        le=120000,
    )
    agent_skill_selection_max_candidates: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_SELECTION_MAX_CANDIDATES", "12")
        ),
        ge=1,
        le=64,
    )
    agent_skill_selection_max_selected: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_SELECTION_MAX_SELECTED", "4")
        ),
        ge=1,
        le=8,
    )
    agent_skill_selection_min_confidence: float = Field(
        default_factory=lambda: float(
            os.getenv("AGENT_SKILL_SELECTION_MIN_CONFIDENCE", "0.55")
        ),
        ge=0.0,
        le=1.0,
    )
    agent_skill_selection_num_ctx: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_SELECTION_NUM_CTX", "8192")
        ),
        ge=512,
    )
    agent_skill_selection_num_predict: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_SELECTION_NUM_PREDICT", "512")
        ),
        ge=32,
        le=4096,
    )
    agent_skill_progressive_disclosure_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_SKILL_PROGRESSIVE_DISCLOSURE_ENABLED",
            "1",
        ).strip().lower() not in {"0", "false", "no", "off"}
    )
    agent_skill_projection_max_chars: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_PROJECTION_MAX_CHARS", "3000")
        ),
        ge=128,
        le=50000,
    )
    agent_skill_projection_total_max_chars: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_PROJECTION_TOTAL_MAX_CHARS", "6000")
        ),
        ge=128,
        le=100000,
    )
    agent_skill_projection_count_limit: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_SKILL_PROJECTION_COUNT_LIMIT", "4")
        ),
        ge=1,
        le=8,
    )
    capability_catalog_refresh_sec: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_CAPABILITY_CATALOG_REFRESH_SEC", "30")),
        ge=1.0,
        le=3600.0,
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
    external_information_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_EXTERNAL_INFORMATION_ENABLED", "0"
        ).strip().lower() not in {"0", "false", "no", "off"}
    )
    external_information_url: str = Field(
        default_factory=lambda: os.getenv("AGENT_EXTERNAL_INFORMATION_URL", "").strip()
    )
    external_information_token: str = Field(
        default_factory=lambda: os.getenv("AGENT_EXTERNAL_INFORMATION_TOKEN", "").strip()
    )
    external_information_timeout_ms: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_EXTERNAL_INFORMATION_TIMEOUT_MS", "15000")
        ),
        ge=100,
        le=120000,
    )
    capability_prompt_tier_preset: str = Field(
        default_factory=lambda: os.getenv("AGENT_CAPABILITY_PROMPT_TIER_PRESET", "")
    )
    capability_prompt_tier_overrides: str = Field(
        default_factory=lambda: os.getenv("AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES", "")
    )
    cognitive_gateway_attention_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "AGENT_COGNITIVE_GATEWAY_ATTENTION_ENABLED",
            "1",
        ).strip().lower() not in {"0", "false", "no", "off"}
    )
    cognitive_gateway_attention_model: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
            os.getenv("AGENT_GOAL_INTERPRETER_MODEL", "qwen3:4b"),
        )
    )
    cognitive_gateway_attention_timeout_ms: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_COGNITIVE_GATEWAY_ATTENTION_TIMEOUT_MS", "2500")
        ),
        ge=100,
        le=120000,
    )
    cognitive_gateway_attention_min_suppression_confidence: float = Field(
        default_factory=lambda: float(
            os.getenv(
                "AGENT_COGNITIVE_GATEWAY_ATTENTION_MIN_SUPPRESSION_CONFIDENCE",
                "0.72",
            )
        ),
        ge=0.0,
        le=1.0,
    )
    cognitive_gateway_attention_num_ctx: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_CTX", "2048")
        ),
        ge=512,
        le=131072,
    )
    cognitive_gateway_attention_num_predict: int = Field(
        default_factory=lambda: int(
            os.getenv("AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_PREDICT", "96")
        ),
        ge=32,
        le=1024,
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
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_NUM_CTX", "8192")), ge=2048, le=131072
    )
    fast_planner_num_predict: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_FAST_PLANNER_NUM_PREDICT", "2048")), ge=128, le=4096
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
    log_level: str = Field(default_factory=lambda: os.getenv("AGENT_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))
    ollama_fallback_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://chromie-llm:11434"))
    ollama_fallback_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:4b"))
    ollama_fallback_timeout_ms: int = Field(default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT_MS", "3000")))
    ollama_num_ctx: int = Field(default_factory=lambda: int(float(os.getenv("OLLAMA_NUM_CTX", os.getenv("OLLAMA_CONTEXT_LENGTH", "0")) or "0")), ge=0)
    ollama_num_predict: int = Field(default_factory=lambda: int(float(os.getenv("OLLAMA_NUM_PREDICT", "0") or "0")), ge=0)
    llm_prompt_chars_per_token_estimate: float = Field(default_factory=lambda: float(os.getenv("AGENT_LLM_PROMPT_CHARS_PER_TOKEN_ESTIMATE", "2.0")), gt=0.0)
    llm_context_safety_margin_tokens: int = Field(default_factory=lambda: int(os.getenv("AGENT_LLM_CONTEXT_SAFETY_MARGIN_TOKENS", "0")), ge=0)
    goal_interpreter_debug_raw: bool = Field(default_factory=lambda: os.getenv("CHROMIE_AGENT_GOAL_INTERPRETER_DEBUG_RAW", os.getenv("AGENT_GOAL_INTERPRETER_DEBUG_RAW", "0")).strip().lower() not in {"", "0", "false", "no", "off"})
    goal_interpreter_debug_prompt: bool = Field(default_factory=lambda: os.getenv("CHROMIE_AGENT_GOAL_INTERPRETER_DEBUG_PROMPT", os.getenv("AGENT_GOAL_INTERPRETER_DEBUG_PROMPT", "0")).strip().lower() not in {"", "0", "false", "no", "off"})
    weather_geocoding_url: str = Field(default_factory=lambda: os.getenv("AGENT_WEATHER_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search"))
    weather_forecast_url: str = Field(default_factory=lambda: os.getenv("AGENT_WEATHER_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"))
    weather_timeout_s: float = Field(default_factory=lambda: float(os.getenv("AGENT_WEATHER_TIMEOUT_S", "8")), gt=0.0)
    environment: dict[str, str] = Field(default_factory=lambda: dict(os.environ), exclude=True, repr=False)
    mode: Literal["runtime"] = "runtime"

class GoalInterpreterSettings(BaseModel):
    ollama_url: str = Field(default_factory=lambda: os.getenv("AGENT_GOAL_INTERPRETER_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("AGENT_GOAL_INTERPRETER_MODEL", "qwen3:4b"))
    deep_model: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_DEEP_PLANNER_MODEL",
            os.getenv("AGENT_GOAL_INTERPRETER_MODEL", "qwen3:4b"),
        )
    )
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("AGENT_GOAL_INTERPRETER_TIMEOUT_MS", "5400")))
    llm_num_ctx: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_INTERPRETER_LLM_NUM_CTX", "4096")),
        ge=2048,
        le=131072,
    )
    llm_num_predict: int = Field(default_factory=lambda: int(os.getenv("AGENT_GOAL_INTERPRETER_LLM_NUM_PREDICT", "512")))
    llm_keep_alive: str = Field(
        default_factory=lambda: os.getenv(
            "AGENT_GOAL_INTERPRETER_LLM_KEEP_ALIVE",
            os.getenv("OLLAMA_KEEP_ALIVE", "24h"),
        )
    )
    warm_llm_on_startup: bool = Field(
        default_factory=lambda: os.getenv("AGENT_GOAL_INTERPRETER_WARM_LLM_ON_STARTUP", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    warm_llm_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_GOAL_INTERPRETER_WARM_LLM_TIMEOUT_MS", "60000"))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("AGENT_GOAL_INTERPRETER_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))

AgentServiceSettings = Settings
agent_service_settings = Settings()
goal_interpreter_settings = GoalInterpreterSettings()
