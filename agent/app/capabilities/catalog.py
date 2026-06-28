from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .models import CapabilityRegistry, ToolCapability

logger = logging.getLogger("chromie.agent.capability_catalog")

CapabilityInvocationKind = Literal["mcp_tool", "named_skill"]
CapabilityRoute = Literal["chat", "robot_action", "tool", "memory"]

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "can",
    "could",
    "do",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "one",
    "please",
    "slowly",
    "the",
    "this",
    "to",
    "you",
    "your",
    "一",
    "下",
    "个",
    "你",
    "吗",
    "呢",
    "吧",
    "可",
    "以",
    "会",
    "能",
    "我",
    "想",
    "请",
    "帮",
    "麻",
    "烦",
}

def _normalize_token(token: str) -> str:
    token = token.strip().lower()
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    if len(token) > 3 and token[-1] == token[-2]:
        token = token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())
    expanded: list[str] = []
    for token in raw:
        expanded.extend(part for part in token.split("_") if part)
    normalized = {
        _normalize_token(token)
        for token in expanded
        if token and token not in _STOP_WORDS and not (len(token) == 1 and token.isascii())
    }
    normalized.discard("")
    return normalized


def _schema_terms(schema: dict[str, Any]) -> str:
    terms: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"properties", "required", "enum", "description", "title"}:
                    terms.append(str(item))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(schema)
    return " ".join(terms)


def json_compact(value: Any, *, max_chars: int = 420) -> str:
    text = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


class CatalogCapability(BaseModel):
    capability_id: str
    agent_id: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    effects: list[str] = Field(default_factory=list)
    safety_class: str = "safe_read"
    requires_confirmation: bool = False
    available: bool = True
    route: CapabilityRoute = "tool"
    source: str = "registry"
    invocation_kind: CapabilityInvocationKind = "mcp_tool"
    interaction_executable: bool = False
    tags: list[str] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.capability_id.replace(".", " "),
                self.agent_id.replace(".", " "),
                self.description,
                " ".join(self.effects),
                " ".join(self.tags),
                " ".join(str(value) for value in self.hints.values()),
                _schema_terms(self.input_schema),
            ]
        )


class CapabilityMatch(CatalogCapability):
    score: float = Field(ge=0.0, le=1.0)


class CapabilitySearchResult(BaseModel):
    query: str
    matched: bool = False
    suggested_route: CapabilityRoute = "chat"
    suggested_agents: list[str] = Field(default_factory=list)
    matches: list[CapabilityMatch] = Field(default_factory=list)
    catalog_version: int = 0
    live_refresh_error: str | None = None


class CapabilitySearchRequest(BaseModel):
    text: str
    language: str = "auto"
    limit: int = Field(default=8, ge=1, le=32)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    refresh: bool = False
    prefer_interaction_executable: bool = True


class CapabilityInvoker(Protocol):
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context: Any = None) -> Any: ...


class CapabilityCatalog:
    """Shared, queryable catalog for Router and normal interaction handling.

    Static entries come from Chromie's capability registry. Soridormi named
    skills are refreshed from the live provider because those exact IDs are the
    IDs the host InteractionRuntime can execute.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        live_invoker: CapabilityInvoker | None = None,
        refresh_ttl_s: float = 30.0,
        min_score: float = 0.16,
    ) -> None:
        self.registry = registry
        self.live_invoker = live_invoker
        self.refresh_ttl_s = max(1.0, float(refresh_ttl_s))
        self.min_score = max(0.0, min(1.0, float(min_score)))
        self._static = self._static_entries(registry)
        self._live: dict[str, CatalogCapability] = {}
        self._refresh_lock = asyncio.Lock()
        self._last_refresh_monotonic = 0.0
        self._last_refresh_error: str | None = None
        self._version = 1

    @property
    def version(self) -> int:
        return self._version

    def entries(self) -> list[CatalogCapability]:
        merged = {item.capability_id: item for item in self._static}
        merged.update(self._live)
        return [merged[key] for key in sorted(merged)]

    async def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        await self.refresh_live_named_skills(force=refresh)
        return {
            "schema_version": "0.1",
            "catalog_version": self._version,
            "capabilities": [item.model_dump(mode="json") for item in self.entries()],
            "live_refresh_error": self._last_refresh_error,
        }

    async def search(
        self,
        text: str,
        *,
        language: str = "auto",
        limit: int = 8,
        min_score: float | None = None,
        refresh: bool = False,
        prefer_interaction_executable: bool = True,
    ) -> CapabilitySearchResult:
        del language  # Reserved for future multilingual embeddings.
        await self.refresh_live_named_skills(force=refresh)
        query = " ".join((text or "").strip().split())
        query_tokens = _tokens(query)
        threshold = self.min_score if min_score is None else float(min_score)
        scored: list[CapabilityMatch] = []
        for entry in self.entries():
            if not entry.available:
                continue
            score = self._score(query, query_tokens, entry)
            if score <= 0:
                continue
            scored.append(
                CapabilityMatch(
                    **entry.model_dump(mode="python"),
                    score=round(score, 4),
                )
            )
        scored.sort(
            key=lambda item: (
                item.score,
                item.interaction_executable,
                item.invocation_kind == "named_skill",
                item.capability_id,
            ),
            reverse=True,
        )
        if prefer_interaction_executable:
            # The normal InteractionRuntime can directly execute live named
            # skills, while static MCP tools are routing/planning context only.
            # Once an executable candidate clears the same relevance threshold,
            # keep it ahead of non-executable entries even when a planning tool
            # has slightly stronger lexical overlap. Static entries remain in
            # the result so downstream planners still retain full context.
            executable_matches = {
                item.capability_id
                for item in scored
                if item.interaction_executable and item.score >= threshold
            }
            if executable_matches:
                scored.sort(
                    key=lambda item: (
                        item.capability_id in executable_matches,
                        item.score,
                        item.invocation_kind == "named_skill",
                        item.capability_id,
                    ),
                    reverse=True,
                )
        limit = max(1, int(limit))
        if len(scored) < limit:
            seen = {item.capability_id for item in scored}
            context_fill = [
                CapabilityMatch(
                    **entry.model_dump(mode="python"),
                    score=0.0,
                )
                for entry in sorted(
                    (item for item in self.entries() if item.available and item.capability_id not in seen),
                    key=lambda item: (
                        item.interaction_executable,
                        item.invocation_kind == "named_skill",
                        item.capability_id,
                    ),
                    reverse=True,
                )
            ]
            scored.extend(context_fill[: max(0, limit - len(scored))])
        if not scored:
            scored = [
                CapabilityMatch(
                    **entry.model_dump(mode="python"),
                    score=0.0,
                )
                for entry in sorted(
                    (item for item in self.entries() if item.available),
                    key=lambda item: (
                        item.interaction_executable,
                        item.invocation_kind == "named_skill",
                        item.capability_id,
                    ),
                    reverse=True,
                )
            ]
        matches = scored[:limit]
        matched = bool(matches and matches[0].score >= threshold)
        route = self._route_for(matches) if matched else "chat"
        agents = self._agents_for(route, matches) if matched else []
        return CapabilitySearchResult(
            query=query,
            matched=matched,
            suggested_route=route,
            suggested_agents=agents,
            matches=matches,
            catalog_version=self._version,
            live_refresh_error=self._last_refresh_error,
        )

    async def llm_context(
        self,
        *,
        text: str | None = None,
        language: str = "en",
        limit: int = 12,
    ) -> str:
        if text:
            result = await self.search(text, language=language, limit=limit, min_score=0.0)
            entries: list[CatalogCapability] = list(result.matches)
        else:
            await self.refresh_live_named_skills()
            entries = [item for item in self.entries() if item.available]
        zh = language.lower().startswith("zh")
        header = "Chromie 当前可用能力：" if zh else "Available Chromie capabilities:"
        lines = [header]
        for item in entries[:limit]:
            executable = "可直接执行" if zh else "interaction-executable"
            if not item.interaction_executable:
                executable = "仅供路由/规划" if zh else "routing/planning only"
            api = json_compact(item.input_schema)
            lines.append(
                f"- {item.capability_id}: {item.description} "
                f"[{executable}; effects={','.join(item.effects) or 'none'}; api={api}]"
            )
        if zh:
            lines.extend(
                [
                    "规则：只能选择目录中的能力；不得编造能力；不得生成原始关节、电机或力矩控制。",
                    "如果请求不受支持，应明确说明并给出目录中最接近的安全替代方案。",
                ]
            )
        else:
            lines.extend(
                [
                    "Rules: select only catalog capabilities; never invent capabilities; never emit raw joint, motor, or torque controls.",
                    "If the request is unsupported, say so and offer the closest safe catalog alternative.",
                ]
            )
        return "\n".join(lines)

    async def refresh_live_named_skills(self, *, force: bool = False) -> None:
        if self.live_invoker is None:
            return
        now = time.monotonic()
        if not force and now - self._last_refresh_monotonic < self.refresh_ttl_s:
            return
        async with self._refresh_lock:
            now = time.monotonic()
            if not force and now - self._last_refresh_monotonic < self.refresh_ttl_s:
                return
            self._last_refresh_monotonic = now
            try:
                outcome = await self.live_invoker.invoke("soridormi.skill.list", {})
                if getattr(outcome, "status", None) != "success":
                    raise RuntimeError(getattr(outcome, "error", None) or "skill catalog lookup failed")
                output = getattr(outcome, "output", {})
                skills = output.get("skills") if isinstance(output, dict) else None
                if not isinstance(skills, list):
                    raise RuntimeError("skill catalog response has no skills list")
                live: dict[str, CatalogCapability] = {}
                for item in skills:
                    if not isinstance(item, dict):
                        continue
                    upstream_id = str(item.get("skill_id") or "").strip()
                    if not upstream_id:
                        continue
                    # Match the host SkillRegistry namespace exactly. The
                    # provider contract returns an unprefixed opaque skill_id.
                    capability_id = f"soridormi.{upstream_id}"
                    effects = list(item.get("effects") or ["physical_motion"])
                    safety_class = str(item.get("safety_class") or "physical_motion")
                    provider_requires_confirmation = bool(
                        item.get("requires_confirmation", False)
                    )
                    requires_confirmation = (
                        provider_requires_confirmation
                        or safety_class in {"physical_motion", "safety_critical"}
                        or "physical_motion" in effects
                    )
                    live[capability_id] = CatalogCapability(
                        capability_id=capability_id,
                        agent_id="soridormi.skill",
                        description=str(item.get("description") or item.get("summary") or ""),
                        input_schema=dict(item.get("parameters_schema") or item.get("input_schema") or {}),
                        effects=effects,
                        safety_class=safety_class,
                        requires_confirmation=requires_confirmation,
                        available=bool(item.get("available", True)),
                        route="robot_action",
                        source="soridormi.live_named_skills",
                        invocation_kind="named_skill",
                        interaction_executable=True,
                        tags=["soridormi", "robot", "named_skill"],
                        hints={
                            "when_to_use": item.get("when_to_use"),
                            "examples": item.get("examples"),
                        },
                        metadata={
                            "upstream_skill_id": upstream_id,
                            "mode": output.get("mode"),
                            "version": item.get("version"),
                        },
                    )
                if live != self._live:
                    self._live = live
                    self._version += 1
                self._last_refresh_error = None
            except Exception as exc:  # keep the last known-good catalog
                self._last_refresh_error = f"{type(exc).__name__}: {exc}"
                logger.warning("live capability refresh failed: %s", self._last_refresh_error)

    def _static_entries(self, registry: CapabilityRegistry) -> list[CatalogCapability]:
        entries: list[CatalogCapability] = []
        for tool in registry.tools_for_llm():
            agent = registry.get_agent(tool.agent_id)
            entries.append(
                CatalogCapability(
                    capability_id=tool.name,
                    agent_id=tool.agent_id,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    effects=list(tool.effects),
                    safety_class=tool.safety_class,
                    requires_confirmation=tool.confirmation.required,
                    available=tool.availability.available and agent.status.available,
                    route=self._route_for_tool(tool),
                    source="registry",
                    invocation_kind="mcp_tool",
                    interaction_executable=False,
                    tags=[*agent.tags],
                    hints=dict(tool.llm_hints),
                    metadata={"version": tool.version},
                )
            )
        return entries

    def _route_for_tool(self, tool: ToolCapability) -> CapabilityRoute:
        effects = set(tool.effects)
        if tool.agent_id.startswith("soridormi.") or effects & {
            "physical_motion",
            "safety_control",
            "planning_only",
            "creates_plan",
            "commissioning_no_motion",
        }:
            return "robot_action"
        if "memory_write" in effects or tool.agent_id.startswith("chromie.memory"):
            return "memory"
        if effects <= {"user_interaction", "audio_input", "audio_output", "read_only"} and tool.agent_id == "chromie.speech":
            return "chat"
        return "tool"

    def _score(
        self,
        query: str,
        query_tokens: set[str],
        entry: CatalogCapability,
    ) -> float:
        if not query_tokens:
            return 0.0
        searchable = entry.searchable_text().lower()
        doc_tokens = _tokens(searchable)
        overlap = query_tokens & doc_tokens
        coverage = len(overlap) / max(1, len(query_tokens))
        precision = len(overlap) / max(1, min(len(doc_tokens), 12))
        score = 0.72 * coverage + 0.18 * precision
        normalized_query = " ".join(sorted(query_tokens))
        if normalized_query and normalized_query in searchable:
            score += 0.1
        name_tokens = _tokens(entry.capability_id.replace(".", " "))
        if query_tokens & name_tokens:
            score += 0.08
        if entry.interaction_executable:
            score += 0.03
        return max(0.0, min(1.0, score))

    def _route_for(self, matches: list[CapabilityMatch]) -> CapabilityRoute:
        if not matches:
            return "chat"
        weighted: dict[CapabilityRoute, float] = {}
        for match in matches[:4]:
            weighted[match.route] = weighted.get(match.route, 0.0) + match.score
        return max(weighted, key=weighted.get)

    def _agents_for(
        self,
        route: CapabilityRoute,
        matches: list[CapabilityMatch],
    ) -> list[str]:
        agents = ["capability_agent", "conversation_agent"]
        if route == "robot_action" and any(
            match.safety_class in {"physical_motion", "safety_critical"}
            or "physical_motion" in match.effects
            for match in matches[:4]
        ):
            agents.append("safety_agent")
        agents.append("speaker_agent")
        return agents
