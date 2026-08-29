from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "chromie-agent"
    model: str | None = None
    ollama_url: str | None = None
    use_llm: bool = True
    capability_sources: list[str] = Field(default_factory=list)
    capability_manifest_files: list[str] = Field(default_factory=list)
    agent_skill_roots: list[str] = Field(default_factory=list)
    agent_skill_package_files: list[str] = Field(default_factory=list)
    agent_skill_count: int = 0
    agent_skill_model_selection_enabled: bool = False
    agent_skill_selection_model: str | None = None
    agent_skill_selection_max_candidates: int = 0
    agent_skill_selection_max_selected: int = 0
    agent_skill_progressive_disclosure_enabled: bool = False
    agent_skill_projection_max_chars: int = 0
    agent_skill_projection_total_max_chars: int = 0
    agent_skill_projection_count_limit: int = 0
    read_only_work_dag_execution_enabled: bool = False
    planning_work_dag_execution_enabled: bool = False
    parallel_work_dag_execution_enabled: bool = False
    dag_engine_max_concurrency: int = 1
    work_dag_active_count: int = 0
    work_dag_waiting_count: int = 0
    active_work_dag_ids: list[str] = Field(default_factory=list)
    guarded_work_dag_execution_enabled: bool = False
    physical_work_dag_execution_enabled: bool = False
    capability_catalog_enabled: bool = False
    capability_catalog_version: int = 0
    goal_association_enabled: bool = False
    goal_association_model: str | None = None
    fast_planner_enabled: bool = False
    fast_planner_model: str | None = None
    deep_planner_enabled: bool = False
    deep_planner_model: str | None = None


def detect_language(text: str) -> str:
    text = text or ""
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return "zh-CN"
    if any("\u0400" <= ch <= "\u04ff" for ch in text):
        return "ru-RU"
    return "en-US"
