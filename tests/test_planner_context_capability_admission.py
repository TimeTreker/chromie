from __future__ import annotations

import asyncio

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.capabilities.local import chromie_manifests
from agent.app.planner_context import fast_capability_context
from agent.app.planner_schema import fast_streaming_advance_response_schema
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest


class _Catalog:
    def __init__(self, entries: list[CatalogCapability]) -> None:
        self.entries = entries

    async def prompt_entries(self, *, scope: str, refresh: bool = False):
        del refresh
        return [
            item
            for item in self.entries
            if scope != "common" or item.prompt_tier == "common"
        ]


def _capability(
    capability_id: str,
    *,
    hints: dict | None = None,
) -> CatalogCapability:
    return CatalogCapability(
        capability_id=capability_id,
        agent_id="test",
        description=capability_id,
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        available=True,
        interaction_executable=True,
        prompt_tier="common",
        can_run_parallel=True,
        parallel_metadata_declared=True,
        effects=("read_only",),
        safety_class="safe_read",
        hints=hints or {},
    )


def _request(*, context: dict | None = None) -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid="planner-context-admission",
        text="what is the weather today in Chongqing?",
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": "what is the weather today in Chongqing?",
                "output_mode": "information",
                "confidence": 1.0,
            }
        ],
        interpretation_confidence=1.0,
        context=context or {},
    )


def _memory_capability() -> CatalogCapability:
    return _capability(
        "chromie.memory.retrieve_verified_tool_result",
        hints={
            "planner_context_requirements": {
                "nonempty": ["verified_tool_memory_index"],
            }
        },
    )


def test_fast_catalog_hides_context_gated_capability_without_evidence() -> None:
    weather = _capability("chromie.weather.lookup")
    memory = _memory_capability()

    _, common, entries = asyncio.run(
        fast_capability_context(_Catalog([weather, memory]), _request())
    )

    assert [item.capability_id for item in common] == ["chromie.weather.lookup"]
    assert [item.capability_id for item in entries] == ["chromie.weather.lookup"]


def test_fast_catalog_exposes_context_gated_capability_when_evidence_exists() -> None:
    weather = _capability("chromie.weather.lookup")
    memory = _memory_capability()
    request = _request(
        context={
            "verified_tool_memory_index": [
                {
                    "evidence_id": "evidence-weather",
                    "tool_id": "chromie.weather.lookup",
                    "request_args": {"location": "Chongqing"},
                }
            ]
        }
    )

    _, common, entries = asyncio.run(
        fast_capability_context(_Catalog([weather, memory]), request)
    )

    assert [item.capability_id for item in common] == [
        "chromie.weather.lookup",
        "chromie.memory.retrieve_verified_tool_result",
    ]
    assert [item.capability_id for item in entries] == [
        "chromie.weather.lookup",
        "chromie.memory.retrieve_verified_tool_result",
    ]


def test_verified_memory_declares_nonempty_index_requirement() -> None:
    memory_tools = [
        tool
        for manifest in chromie_manifests()
        if manifest.agent_id == "chromie.memory"
        for tool in manifest.tools
        if tool.name == "chromie.memory.retrieve_verified_tool_result"
    ]

    assert len(memory_tools) == 1
    assert memory_tools[0].llm_hints["planner_context_requirements"] == {
        "nonempty": ["verified_tool_memory_index"]
    }


def test_fast_streaming_activity_budget_is_bounded_per_responsibility() -> None:
    responsibilities = _request().responsibilities
    one = fast_streaming_advance_response_schema(
        ["r1"],
        responsibilities=responsibilities,
        capabilities=[],
        interpretation_unresolved=[],
    )
    assert one["properties"]["activities"]["maxItems"] == 5

    two_responsibilities = [
        *responsibilities,
        responsibilities[0].model_copy(
            update={"local_ref": "r2", "outcome": "also tell me the local time"}
        ),
    ]
    two = fast_streaming_advance_response_schema(
        ["r1", "r2"],
        responsibilities=two_responsibilities,
        capabilities=[],
        interpretation_unresolved=[],
    )
    assert two["properties"]["activities"]["maxItems"] == 10
