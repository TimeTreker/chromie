from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .models import CapabilityRegistry, ToolCapability

logger = logging.getLogger("chromie.agent.capability_catalog")

CapabilityInvocationKind = Literal["mcp_tool", "named_skill"]
CapabilityRoute = Literal["chat", "robot_action", "tool", "memory"]
CapabilityPromptTier = Literal["common", "rare"]
DEFAULT_PROMPT_TIER_PRESET_PATH = (
    Path(__file__).resolve().parents[3] / "capabilities" / "prompt_tiers.json"
)
DEFAULT_BEHAVIOR_DOMAIN_PRESET_PATH = (
    Path(__file__).resolve().parents[3] / "capabilities" / "behavior_domains.json"
)

SAFETY_LOCKED_PROMPT_TIER_SAFETY_CLASSES = {
    "guarded_operation",
    "high_risk_action",
    "restricted",
    "safety_critical",
}
SAFETY_LOCKED_PROMPT_TIER_EFFECTS = {
    "commissioning_no_motion",
    "emergency_stop",
    "safety_control",
}
SAFETY_LOCKED_PROMPT_TIER_TAGS = {
    "calibration",
    "commissioning",
    "safety-critical",
    "safety_critical",
    "safety_sensitive",
}

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
    prompt_tier: CapabilityPromptTier = "rare"
    prompt_tier_locked: bool = False
    prompt_tier_source: str = "preset"
    prompt_tier_reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    behavior_domains: list[str] = Field(default_factory=list)
    hints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    can_run_parallel: bool | None = None
    parallel_metadata_declared: bool = False
    exclusive_group: str | None = None
    resource_claims: list[str] = Field(default_factory=list)
    execution_constraints: dict[str, Any] = Field(default_factory=dict)

    def searchable_text(self) -> str:
        return " ".join(
            [
                self.capability_id.replace(".", " "),
                self.agent_id.replace(".", " "),
                self.description,
                " ".join(self.effects),
                " ".join(self.tags),
                " ".join(self.behavior_domains),
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
        prompt_tier_preset: Mapping[str, Any] | None = None,
        prompt_tier_overrides: Mapping[str, Any] | None = None,
        behavior_domain_preset: Mapping[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.live_invoker = live_invoker
        self.refresh_ttl_s = max(1.0, float(refresh_ttl_s))
        self.min_score = max(0.0, min(1.0, float(min_score)))
        if prompt_tier_preset is None:
            prompt_tier_preset = self.load_prompt_tier_preset(None)
        self.prompt_tier_presets = self._normalize_prompt_tier_entries(prompt_tier_preset)
        self.prompt_tier_overrides = self._normalize_prompt_tier_overrides(prompt_tier_overrides)
        if behavior_domain_preset is None:
            behavior_domain_preset = self.load_behavior_domain_preset(None)
        self.behavior_domain_presets = self._normalize_behavior_domain_entries(
            behavior_domain_preset
        )
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

    async def prompt_entries(
        self,
        *,
        scope: Literal["common", "all"] = "common",
        refresh: bool = False,
    ) -> list[CatalogCapability]:
        await self.refresh_live_named_skills(force=refresh)
        entries = [item for item in self.entries() if item.available]
        if scope == "common":
            entries = [
                item
                for item in entries
                if item.prompt_tier == "common" and not item.prompt_tier_locked
            ]
        return sorted(
            entries,
            key=lambda item: (
                item.prompt_tier != "common",
                item.prompt_tier_locked,
                not item.interaction_executable,
                item.route,
                item.capability_id,
            ),
        )

    async def get_capability(
        self,
        capability_id: str,
        *,
        refresh: bool = False,
    ) -> CatalogCapability | None:
        await self.refresh_live_named_skills(force=refresh)
        target = (capability_id or "").strip()
        if not target:
            return None
        for item in self.entries():
            if item.capability_id == target:
                return item
        return None

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
                for raw_item in skills:
                    if not isinstance(raw_item, dict):
                        raise ValueError(
                            "Soridormi skill catalog entries must be objects"
                        )
                    item = dict(raw_item)
                    upstream_id = str(item.get("skill_id") or "").strip()
                    if not upstream_id:
                        raise ValueError(
                            "Soridormi skill catalog entry has no skill_id"
                        )
                    # Match the host SkillRegistry namespace exactly. The
                    # provider contract returns an unprefixed opaque skill_id.
                    capability_id = f"soridormi.{upstream_id}"
                    if capability_id in live:
                        raise ValueError(
                            "duplicate Soridormi skill_id in one catalog: "
                            f"{upstream_id}"
                        )

                    execution = item.get("execution")
                    execution_contract = (
                        execution if isinstance(execution, dict) else {}
                    )
                    availability = item.get("availability")
                    availability_contract = (
                        availability if isinstance(availability, dict) else {}
                    )
                    confirmation = item.get("confirmation")
                    confirmation_contract = (
                        confirmation if isinstance(confirmation, dict) else {}
                    )
                    effects_raw = item.get("effects")
                    if effects_raw is None:
                        effects = ["physical_motion"]
                    elif isinstance(effects_raw, list):
                        effects = [
                            str(value)
                            for value in effects_raw
                            if str(value).strip()
                        ]
                    else:
                        raise ValueError(
                            f"Soridormi skill {upstream_id!r} effects must be a list"
                        )
                    safety_class = str(
                        item.get("safety_class") or "physical_motion"
                    )
                    provider_requires_confirmation = bool(
                        item.get(
                            "requires_confirmation",
                            confirmation_contract.get("required", False),
                        )
                    )
                    requires_confirmation = (
                        provider_requires_confirmation
                        or safety_class in {"physical_motion", "safety_critical"}
                        or "physical_motion" in effects
                    )
                    input_schema = (
                        item.get("parameters_schema")
                        or item.get("input_schema")
                        or {}
                    )
                    if not isinstance(input_schema, dict):
                        raise ValueError(
                            f"Soridormi skill {upstream_id!r} input schema must be an object"
                        )
                    can_run_parallel = item.get(
                        "can_run_parallel",
                        execution_contract.get("can_run_parallel"),
                    )
                    exclusive_group = (
                        str(
                            item.get("exclusive_group")
                            or execution_contract.get("exclusive_group")
                            or ""
                        ).strip()
                        or None
                    )
                    resource_claims = item.get(
                        "resource_claims",
                        execution_contract.get("resource_claims", []),
                    )
                    if not isinstance(resource_claims, list):
                        raise ValueError(
                            f"Soridormi skill {upstream_id!r} resource_claims must be a list"
                        )
                    execution_constraints = item.get(
                        "execution_constraints",
                        execution_contract.get("execution_constraints", {}),
                    )
                    if not isinstance(execution_constraints, dict):
                        raise ValueError(
                            f"Soridormi skill {upstream_id!r} execution_constraints must be an object"
                        )

                    capability = CatalogCapability(
                        capability_id=capability_id,
                        agent_id="soridormi.skill",
                        description=str(
                            item.get("description") or item.get("summary") or ""
                        ),
                        input_schema=dict(input_schema),
                        effects=effects,
                        safety_class=safety_class,
                        requires_confirmation=requires_confirmation,
                        available=bool(
                            item.get(
                                "available",
                                availability_contract.get("available", True),
                            )
                        ),
                        route="robot_action",
                        source="soridormi.live_named_skills",
                        invocation_kind="named_skill",
                        interaction_executable=True,
                        prompt_tier=self._prompt_tier_for_live_skill(
                            capability_id, item
                        ),
                        prompt_tier_locked=self._prompt_tier_lock_flag(item),
                        prompt_tier_source=self._prompt_tier_source_for_live_skill(
                            capability_id, item
                        ),
                        prompt_tier_reason=self._prompt_tier_reason_from(item)
                        or self._preset_prompt_tier_reason(capability_id),
                        tags=["soridormi", "robot", "named_skill"],
                        behavior_domains=self._behavior_domains_for(
                            capability_id,
                            item.get("behavior_domains"),
                            (item.get("metadata") or {}).get("behavior_domains")
                            if isinstance(item.get("metadata"), dict)
                            else None,
                        ),
                        hints={
                            "when_to_use": item.get("when_to_use"),
                            "examples": item.get("examples"),
                            "safety_sensitive": item.get("safety_sensitive"),
                        },
                        metadata={
                            "upstream_skill_id": upstream_id,
                            "mode": output.get("mode"),
                            "version": item.get("version"),
                        },
                        can_run_parallel=(
                            bool(can_run_parallel)
                            if can_run_parallel is not None
                            else None
                        ),
                        parallel_metadata_declared=(
                            can_run_parallel is not None
                            or exclusive_group is not None
                            or bool(resource_claims)
                            or bool(execution_constraints)
                        ),
                        exclusive_group=exclusive_group,
                        resource_claims=[
                            str(value)
                            for value in resource_claims
                            if str(value).strip()
                        ],
                        execution_constraints=dict(execution_constraints),
                    )
                    live[capability_id] = self._apply_prompt_tier_policy(
                        capability
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
            capability = CatalogCapability(
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
                interaction_executable=self._interaction_executable_for_tool(tool),
                prompt_tier=self._prompt_tier_for_tool(tool),
                prompt_tier_locked=self._prompt_tier_lock_flag(tool.llm_hints),
                prompt_tier_source=self._prompt_tier_source_for_tool(tool),
                prompt_tier_reason=self._prompt_tier_reason_from(tool.llm_hints),
                tags=[*agent.tags],
                behavior_domains=self._behavior_domains_for(
                    tool.name,
                    tool.llm_hints.get("behavior_domains"),
                ),
                hints=dict(tool.llm_hints),
                metadata={"version": tool.version},
                can_run_parallel=(
                    bool(tool.llm_hints.get("can_run_parallel"))
                    if "can_run_parallel" in tool.llm_hints
                    else None
                ),
                parallel_metadata_declared=any(
                    key in tool.llm_hints
                    for key in (
                        "can_run_parallel",
                        "exclusive_group",
                        "resource_claims",
                        "execution_constraints",
                    )
                ),
                exclusive_group=(
                    str(tool.llm_hints.get("exclusive_group") or "").strip() or None
                ),
                resource_claims=[
                    str(value)
                    for value in (tool.llm_hints.get("resource_claims") or [])
                    if str(value).strip()
                ],
                execution_constraints=dict(
                    tool.llm_hints.get("execution_constraints") or {}
                ),
            )
            entries.append(self._apply_prompt_tier_policy(capability))
        return entries

    def _prompt_tier_for_live_skill(
        self,
        capability_id: str,
        item: dict[str, Any],
    ) -> CapabilityPromptTier:
        explicit = str(item.get("prompt_tier") or item.get("router_prompt_tier") or "").strip().lower()
        if explicit in {"common", "rare"}:
            return explicit  # type: ignore[return-value]
        preset = self.prompt_tier_presets.get(capability_id)
        if preset:
            return preset["prompt_tier"]  # type: ignore[return-value]
        return "rare"

    def _prompt_tier_source_for_live_skill(self, capability_id: str, item: dict[str, Any]) -> str:
        explicit = str(item.get("prompt_tier") or item.get("router_prompt_tier") or "").strip()
        if explicit:
            return "provider"
        preset = self.prompt_tier_presets.get(capability_id)
        return str(preset.get("prompt_tier_source") or "preset") if preset else "preset"

    def _prompt_tier_for_tool(self, tool: ToolCapability) -> CapabilityPromptTier:
        explicit = str(tool.llm_hints.get("prompt_tier") or "").strip().lower()
        if explicit in {"common", "rare"}:
            return explicit  # type: ignore[return-value]
        preset = self.prompt_tier_presets.get(tool.name)
        if preset:
            return preset["prompt_tier"]  # type: ignore[return-value]
        return "rare"

    def _prompt_tier_source_for_tool(self, tool: ToolCapability) -> str:
        explicit = str(tool.llm_hints.get("prompt_tier") or "").strip()
        if explicit:
            return "provider"
        preset = self.prompt_tier_presets.get(tool.name)
        return str(preset.get("prompt_tier_source") or "preset") if preset else "preset"

    @classmethod
    def load_behavior_domain_preset(cls, path: str | Path | None) -> dict[str, Any]:
        raw = str(path or "").strip()
        source = Path(raw).expanduser() if raw else DEFAULT_BEHAVIOR_DOMAIN_PRESET_PATH
        if not source.exists():
            if raw:
                raise FileNotFoundError(
                    f"behavior domain preset file does not exist: {source}"
                )
            logger.warning("default behavior domain preset not found: %s", source)
            return {}
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("behavior domain preset file must contain a JSON object")
        return payload

    @staticmethod
    def _normalize_behavior_domain_entries(
        payload: Mapping[str, Any] | None,
    ) -> dict[str, list[str]]:
        if not payload:
            return {}
        raw: Any = payload.get("behavior_domains") if isinstance(
            payload.get("behavior_domains"), Mapping
        ) else payload
        if not isinstance(raw, Mapping):
            return {}
        normalized: dict[str, list[str]] = {}
        for capability_id, value in raw.items():
            if not isinstance(capability_id, str) or not capability_id.strip():
                continue
            values = value if isinstance(value, (list, tuple, set)) else [value]
            domains: list[str] = []
            seen: set[str] = set()
            for item in values:
                domain = str(item or "").strip().lower()
                if domain and domain not in seen:
                    seen.add(domain)
                    domains.append(domain)
            if domains:
                normalized[capability_id.strip()] = domains
        return normalized

    def _behavior_domains_for(self, capability_id: str, *values: Any) -> list[str]:
        domains: list[str] = []
        seen: set[str] = set()
        for value in (*values, self.behavior_domain_presets.get(capability_id, [])):
            items = value if isinstance(value, (list, tuple, set)) else [value]
            for item in items:
                domain = str(item or "").strip().lower()
                if domain and domain not in seen:
                    seen.add(domain)
                    domains.append(domain)
        return domains

    @classmethod
    def load_prompt_tier_preset(cls, path: str | Path | None) -> dict[str, Any]:
        raw = str(path or "").strip()
        source = Path(raw).expanduser() if raw else DEFAULT_PROMPT_TIER_PRESET_PATH
        if not source.exists():
            if raw:
                raise FileNotFoundError(f"prompt tier preset file does not exist: {source}")
            logger.warning("default prompt tier preset not found: %s", source)
            return {}
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("prompt tier preset file must contain a JSON object")
        return payload

    @classmethod
    def load_prompt_tier_overrides(cls, path: str | Path | None) -> dict[str, dict[str, Any]]:
        if not path:
            return {}
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("prompt tier override file must contain a JSON object")
        return cls._normalize_prompt_tier_overrides(payload)

    @classmethod
    def _normalize_prompt_tier_entries(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        if not payload:
            return {}
        return cls._normalize_prompt_tier_overrides(
            {
                "prompt_tiers": payload.get("prompt_tiers")
                if isinstance(payload.get("prompt_tiers"), Mapping)
                else payload
            },
            default_source="preset",
        )

    @staticmethod
    def _normalize_prompt_tier_overrides(
        overrides: Mapping[str, Any] | None,
        *,
        default_source: str = "experience",
    ) -> dict[str, dict[str, Any]]:
        if not overrides:
            return {}
        raw: Any = overrides
        if isinstance(overrides.get("prompt_tiers"), Mapping):
            raw = overrides["prompt_tiers"]
        normalized: dict[str, dict[str, Any]] = {}
        if not isinstance(raw, Mapping):
            return normalized
        for capability_id, value in raw.items():
            if not isinstance(capability_id, str) or not capability_id.strip():
                continue
            if isinstance(value, str):
                payload: dict[str, Any] = {"prompt_tier": value}
            elif isinstance(value, Mapping):
                payload = dict(value)
            else:
                continue
            tier = str(payload.get("prompt_tier") or payload.get("tier") or "").strip().lower()
            if tier not in {"common", "rare"}:
                continue
            normalized[capability_id.strip()] = {
                "prompt_tier": tier,
                "prompt_tier_source": str(
                    payload.get("prompt_tier_source")
                    or payload.get("source")
                    or default_source
                ).strip()
                or default_source,
                "prompt_tier_reason": str(
                    payload.get("prompt_tier_reason")
                    or payload.get("reason")
                    or ""
                ).strip()
                or None,
            }
        return normalized

    def _preset_prompt_tier_reason(self, capability_id: str) -> str | None:
        preset = self.prompt_tier_presets.get(capability_id)
        if not preset:
            return None
        return str(preset.get("prompt_tier_reason") or "").strip() or None

    def _apply_prompt_tier_policy(self, capability: CatalogCapability) -> CatalogCapability:
        locked, reason = self._safety_prompt_tier_lock(capability)
        if locked:
            return capability.model_copy(
                update={
                    "prompt_tier": "rare",
                    "prompt_tier_locked": True,
                    "prompt_tier_source": "safety_lock",
                    "prompt_tier_reason": reason,
                }
            )
        override = self.prompt_tier_overrides.get(capability.capability_id)
        if not override:
            return capability
        return capability.model_copy(
            update={
                "prompt_tier": override["prompt_tier"],
                "prompt_tier_source": override.get("prompt_tier_source") or "experience",
                "prompt_tier_reason": override.get("prompt_tier_reason"),
            }
        )

    @classmethod
    def _safety_prompt_tier_lock(cls, capability: CatalogCapability) -> tuple[bool, str | None]:
        if capability.prompt_tier_locked:
            return True, capability.prompt_tier_reason or "provider marked capability prompt tier as locked"
        safety_class = str(capability.safety_class or "").strip().lower()
        if safety_class in SAFETY_LOCKED_PROMPT_TIER_SAFETY_CLASSES:
            return True, f"safety_class={safety_class} is safety-sensitive"
        effects = {str(effect).strip().lower() for effect in capability.effects}
        locked_effects = sorted(effects & SAFETY_LOCKED_PROMPT_TIER_EFFECTS)
        if locked_effects:
            return True, f"effect={locked_effects[0]} is safety-sensitive"
        tags = {str(tag).strip().lower() for tag in capability.tags}
        locked_tags = sorted(tags & SAFETY_LOCKED_PROMPT_TIER_TAGS)
        if locked_tags:
            return True, f"tag={locked_tags[0]} is safety-sensitive"
        if cls._truthy(capability.hints.get("safety_sensitive")):
            return True, "hint safety_sensitive=true"
        if cls._truthy(capability.metadata.get("safety_sensitive")):
            return True, "metadata safety_sensitive=true"
        return False, None

    @classmethod
    def _prompt_tier_lock_flag(cls, payload: Mapping[str, Any]) -> bool:
        return any(
            cls._truthy(payload.get(key))
            for key in (
                "prompt_tier_locked",
                "router_prompt_tier_locked",
                "safety_sensitive",
            )
        )

    @staticmethod
    def _prompt_tier_reason_from(payload: Mapping[str, Any]) -> str | None:
        reason = str(
            payload.get("prompt_tier_reason")
            or payload.get("router_prompt_tier_reason")
            or ""
        ).strip()
        return reason or None

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on", "locked"}

    @staticmethod
    def _interaction_executable_for_tool(tool: ToolCapability) -> bool:
        return tool.name == "chromie.speak"

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
        semantic_score = self._semantic_action_score(query, entry)
        if semantic_score > 0:
            score = max(score, semantic_score)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _semantic_action_score(query: str, entry: CatalogCapability) -> float:
        normalized_query = " ".join((query or "").strip().lower().split())
        if not normalized_query:
            return 0.0
        entry_text = " ".join(
            [
                entry.capability_id.lower(),
                entry.description.lower(),
                " ".join(entry.tags).lower(),
                " ".join(str(value) for value in entry.hints.values()).lower(),
            ]
        )
        if "眨" in normalized_query and "blink" in entry_text and "eye" in entry_text:
            return 0.86 if entry.interaction_executable else 0.62
        if CapabilityCatalog._is_forward_motion_query(normalized_query):
            walk_surface = (
                "walk_forward" in entry_text
                or "walk velocity" in entry_text
                or "walk_velocity" in entry_text
                or "walk forward" in entry_text
                or "move forward" in entry_text
                or ("walking" in entry_text and "forward" in entry_text)
            )
            if walk_surface:
                return 0.88 if entry.interaction_executable else 0.58
            if "motion" in entry_text and ("create_plan" in entry_text or "task preview" in entry_text):
                return 0.36
        return 0.0

    @staticmethod
    def _is_forward_motion_query(normalized_query: str) -> bool:
        query = normalized_query or ""
        zh_forward = any(phrase in query for phrase in ("往前", "向前", "朝前", "前进"))
        zh_motion = any(phrase in query for phrase in ("走", "移动", "挪", "行走"))
        if zh_forward and zh_motion:
            return True
        if re.search(r"\b(?:walk|move|go|step)\s+(?:forward|ahead)\b", query):
            return True
        if re.search(r"\b(?:forward|ahead)\s+(?:walk|motion|move|movement|step)\b", query):
            return True
        return False

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
        if route == "tool":
            return ["tool_agent", "speaker_agent"]
        if route == "memory":
            return ["memory_agent", "speaker_agent"]
        if route == "chat":
            return ["conversation_agent", "speaker_agent"]

        agents = ["capability_agent"]
        if route == "robot_action" and any(
            match.safety_class in {"physical_motion", "safety_critical"}
            or "physical_motion" in match.effects
            for match in matches[:4]
        ):
            agents.append("safety_agent")
        agents.append("speaker_agent")
        return agents
