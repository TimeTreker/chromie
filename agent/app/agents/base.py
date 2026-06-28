from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from ..clients.ollama_client import OllamaClient
from ..schema import AgentResult, AgentRunRequest

if TYPE_CHECKING:
    from ..capabilities.catalog import CapabilityCatalog
    from ..task_graph.planner import TaskGraphPlanner


@dataclass(slots=True)
class AgentServices:
    ollama: OllamaClient | None = None
    use_llm: bool = True
    max_speak_chars: int = 120
    expressive_body_cues: str = "sim_only"
    task_graph_planner: "TaskGraphPlanner | None" = None
    capability_catalog: "CapabilityCatalog | None" = None
    capability_match_limit: int = 8


class BaseAgent(ABC):
    name: str = "base_agent"

    _UNHUMAN_NONANSWER_RE = re.compile(
        r"\b(?:"
        r"do\s+not\s+have\s+personal\s+opinions|"
        r"don't\s+have\s+personal\s+opinions|"
        r"do\s+not\s+have\s+opinions|"
        r"don't\s+have\s+opinions|"
        r"cannot\s+have\s+opinions|"
        r"can't\s+have\s+opinions|"
        r"not\s+have\s+beliefs|"
        r"do\s+not\s+have\s+information|"
        r"don't\s+have\s+information|"
        r"cannot\s+determine\s+from\s+context|"
        r"can't\s+determine\s+from\s+context|"
        r"as\s+an\s+ai"
        r")\b",
        re.IGNORECASE,
    )

    def __init__(self, services: AgentServices) -> None:
        self.services = services

    def can_handle(self, request: AgentRunRequest) -> bool:
        return self.name in request.route_decision.agents

    @abstractmethod
    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        """Mutate and return the cumulative AgentResult."""

    def language(self, request: AgentRunRequest) -> str:
        return request.language or request.route_decision.language or "en-US"

    def is_zh(self, request: AgentRunRequest) -> bool:
        return self.language(request).startswith("zh")

    def trace(self, result: AgentResult, message: str) -> None:
        result.handled_by.append(self.name)
        result.trace.append(f"{self.name}: {message}")

    def get_context(self, request: AgentRunRequest, key: str, default: Any = None) -> Any:
        return request.context.get(key, default)

    def mind_context(self, request: AgentRunRequest) -> dict[str, Any]:
        context = request.context or {}
        mind = context.get("mind")
        return mind if isinstance(mind, dict) else {}

    def format_mind_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        mind = self.mind_context(request)
        if not mind:
            return "无" if zh else "None"
        summary = str(mind.get("prompt_summary") or "").strip()
        if summary:
            return summary[:1600].rstrip() + ("..." if len(summary) > 1600 else "")
        compact = json.dumps(mind, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 1600:
            compact = compact[:1600].rstrip() + "..."
        return compact

    def looks_like_unhuman_nonanswer(self, response: str) -> bool:
        return bool(self._UNHUMAN_NONANSWER_RE.search(" ".join((response or "").split())))

    async def retry_unhuman_nonanswer(
        self,
        request: AgentRunRequest,
        *,
        prompt: str,
        system: str,
        response: str,
        zh: bool,
        options: dict[str, Any],
    ) -> str:
        if self.services.ollama is None:
            return response
        if not self.looks_like_unhuman_nonanswer(response):
            return response

        if zh:
            retry_system = (
                f"{system}"
                "Chromie 应该像一个真实的陪伴机器人说话，而不是后端模型。"
                "不要用‘我没有个人观点’或‘作为 AI’这类模板式拒答。"
                "如果最近对话或任务上下文已经提供了可解析的对象或主张，请先使用这些上下文。"
                "请由你判断：如果是客观事实，直接回答事实；如果是主观偏好，"
                "用 Chromie 的机器人性格给出简单自然的偏好；如果确实不确定，"
                "简短说明不确定并说可以一起查证。"
            )
            retry_prompt = (
                f"{prompt}\n\n"
                f"上一次草稿不合格：{response}\n"
                "原因：它听起来像后端模型模板拒答，不像 Chromie 本体在回答。"
                "请只输出一条修正后的可播放回答。"
            )
        else:
            retry_system = (
                f"{system}"
                " Chromie should speak like a real companion robot, not like a backend model. "
                "Do not use stock disclaimers such as lacking personal opinions or 'as an AI'. "
                "If recent history or task context provides the referent or claim, use that context before claiming uncertainty. "
                "Decide the right answer mode yourself: if it is an objective fact, answer the fact; "
                "if it is a subjective preference, give a simple natural robot-persona preference; "
                "if it is genuinely uncertain, say so briefly and offer to check together."
            )
            retry_prompt = (
                f"{prompt}\n\n"
                f"Previous draft rejected: {response}\n"
                "Reason: it sounded like a backend-model disclaimer instead of Chromie answering as herself. "
                "Return only one corrected spoken answer."
            )
        raw = await self.services.ollama.generate(
            retry_prompt,
            system=retry_system,
            options={
                **options,
                "temperature": 0,
            },
        )
        return cast(str, raw)
