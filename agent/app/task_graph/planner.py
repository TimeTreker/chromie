from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

from ..capabilities.models import CapabilityRegistry
from ..clients.ollama_client import OllamaClient

from .models import TaskGraph
from .validator import GraphValidator


class TaskGraphPlanner:
    """Generate and validate an LLM-authored TaskGraph without executing it."""

    def __init__(self, registry: CapabilityRegistry, ollama: OllamaClient) -> None:
        self.registry = registry
        self.ollama = ollama

    async def plan(self, *, user_request: str, language: str, context: dict[str, Any]) -> TaskGraph:
        raw = await self.ollama.generate(
            self._prompt(user_request=user_request, language=language, context=context),
            system=self._system_prompt(),
            options={"temperature": 0.1, "top_p": 0.8, "num_predict": 1200},
            response_format="json",
        )
        payload = cast(dict[str, Any], raw)
        graph_payload = payload.get("task_graph", payload)
        if not isinstance(graph_payload, dict):
            raise ValueError("TaskGraph planner response must contain a JSON object")

        graph = TaskGraph.model_validate(graph_payload).model_copy(
            update={
                "graph_id": f"graph_{uuid4().hex[:12]}",
                "created_by": "llm",
                "user_request": user_request,
            },
            deep=True,
        )
        if not graph.nodes:
            raise ValueError("TaskGraph planner returned an empty graph")

        report = GraphValidator(self.registry).validate(graph)
        report.raise_for_errors()
        return graph

    def _system_prompt(self) -> str:
        return (
            "You are Chromie's TaskGraph planner. Return one JSON object matching the requested schema. "
            "Use only tools listed in the capability registry. Never invent tool names. "
            "Do not call restricted or unavailable tools. Physical motion must depend on a confirmation node "
            "and be covered by a safety monitor. Return a plan only; never claim that tools already ran."
        )

    def _prompt(self, *, user_request: str, language: str, context: dict[str, Any]) -> str:
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "effects": tool.effects,
                "safety_class": tool.safety_class,
                "confirmation_required": tool.confirmation.required,
                "requires_safety_monitor": tool.monitoring.requires_safety_monitor,
            }
            for tool in self.registry.tools_for_llm()
        ]
        safe_context = {
            key: value
            for key, value in context.items()
            if key in {"conversation_id", "robot_state", "user_state", "location", "timezone"}
        }
        schema_hint = {
            "graph_id": "ignored-client-id",
            "version": "0.1",
            "summary": "short plan summary",
            "requires_confirmation": False,
            "nodes": [
                {
                    "id": "unique_node_id",
                    "tool": "registered.tool.name",
                    "type": "query|plan|action|monitor|confirmation|report|safety",
                    "args": {},
                    "depends_on": [],
                    "during": [],
                }
            ],
        }
        return (
            f"User request: {user_request}\n"
            f"Language: {language}\n"
            f"Safe context: {json.dumps(safe_context, ensure_ascii=False)}\n"
            f"Capability registry: {json.dumps(tools, ensure_ascii=False)}\n"
            f"Return this TaskGraph shape: {json.dumps(schema_hint, ensure_ascii=False)}"
        )
