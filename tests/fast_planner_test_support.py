"""Shared fakes and canonical plan builders for Fast Planner tests."""

from __future__ import annotations

import json

from agent.app import planner_prompt as planner_prompt
from agent.app.capabilities.catalog import CatalogCapability
from agent.app.fast_planner import FastPlannerResolver as ProductionFastPlannerResolver
from agent.app.planner_model_contract import (
    PlannerDTOContractError,
)
from benchmarks.datasets.fast_planner_daily_life.qualification import (
    declared_ability_needs,
    declared_ability_needs_text,
)
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.plan import (
    FastPlannerAdvance,
    FastPlannerStreamFailure,
    FastPlannerStreamTerminal,
)
from shared.chromie_contracts.user_turn import user_turn_source_tokens


def _streaming_document(response):
    return json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else response


class FakeOllama:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return declared_ability_needs(self.response, kwargs.get("response_format"))

    async def generate_stream(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        yield declared_ability_needs_text(_streaming_document(self.response), kwargs.get("response_format"))

    @staticmethod
    def _parse_json(text):
        return json.loads(text)


class FastPlannerResolver(ProductionFastPlannerResolver):
    """Test adapter retaining terminal-result assertions during wire migration."""

    async def resolve_advance(self, request):
        commit = None
        async for frame in self.stream_advance(request):
            if frame.frame_type == "presentation_commit":
                commit = frame
                continue
            if isinstance(frame, FastPlannerStreamTerminal):
                return frame.advance
            if isinstance(frame, FastPlannerStreamFailure):
                return FastPlannerAdvance(
                    turn_id=str(request.sid or "turn-fast-advance"),
                    disposition="unavailable",
                    coverage="uncertain",
                    covered_responsibility_refs=[
                        item.local_ref for item in request.responsibilities
                    ],
                    activities=(
                        [commit.activity]
                        if commit is not None and commit.activity is not None
                        else []
                    ),
                    confidence=0.0,
                    unresolved=["Fast Planner stream failed closed."],
                    reason_summary="Discard the invalid terminal result.",
                    metadata={
                        "semantic_authority": "deterministic_fail_safe",
                        "phase": "streaming_responsibility_activity_plan",
                        "execution_authority": "none",
                        "error_type": frame.error_type,
                        "error": frame.reason,
                        "failure_class": frame.failure_class,
                        "failure_domain": frame.failure_domain,
                    },
                )
        raise PlannerDTOContractError("Fast Planner stream ended without a terminal frame")


class FakeCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(capability_id="soridormi.blink_eyes", agent_id="capability_agent", description="Blink eyes", input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]}, effects=["physical_motion"], available=True, interaction_executable=True, prompt_tier="common", can_run_parallel=True, parallel_metadata_declared=True, exclusive_group="body.face", resource_claims=["body.face"]),
            CatalogCapability(capability_id="soridormi.walk_forward", agent_id="capability_agent", description="Walk forward", input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]}, effects=["physical_motion"], available=True, interaction_executable=True, prompt_tier="common", can_run_parallel=True, parallel_metadata_declared=True, exclusive_group="body.primary_motion", resource_claims=["body.primary_motion"]),
            CatalogCapability(
                capability_id="soridormi.walk_velocity",
                agent_id="capability_agent",
                description="Walk at an exact velocity",
                input_schema={
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number"},
                        "vy_mps": {"type": "number"},
                        "yaw_radps": {"type": "number"},
                        "duration_s": {"type": "number", "minimum": 0.1},
                    },
                    "required": ["vx_mps", "duration_s"],
                },
                effects=["physical_motion"],
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                can_run_parallel=True,
                parallel_metadata_declared=True,
                exclusive_group="body.primary_motion",
                resource_claims=["body.primary_motion"],
            ),
            CatalogCapability(capability_id="chromie.speak", agent_id="capability_agent", description="Speak text", input_schema={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}, available=True, interaction_executable=True, prompt_tier="common"),
        ]

    async def prompt_entries(self, **kwargs):
        return self.items


class WeatherCatalog(FakeCatalog):
    def __init__(self):
        super().__init__()
        self.items.append(
            CatalogCapability(
                capability_id="chromie.weather.lookup",
                agent_id="chromie.weather",
                description="Retrieve current or short-range weather.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "date": {"type": "string", "default": "today"},
                        "period": {
                            "type": "string",
                            "default": "day",
                            "x-chromie-entity-type": "day_part",
                        },
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
                available=True,
                interaction_executable=True,
                prompt_tier="common",
                can_run_parallel=True,
                parallel_metadata_declared=True,
                resource_claims=(),
                effects=(),
                safety_class="safe_read",
                hints={
                    "side_effect_free": True,
                    "semantic_scope": {
                        "responsibility_type": "acquire_and_deliver_resource",
                        "resource_kinds": ["information"],
                    },
                },
            )
        )


def _test_what_mode(text: str, *, goal_metadata: dict | None = None) -> str:
    configured = str((goal_metadata or {}).get("output_mode") or "").strip()
    if configured:
        return configured
    lowered = str(text or "").casefold()
    if any(token in lowered for token in ("weather", "天气", "下雨", "rain", "temperature", "温度", "check", "determine whether")):
        return "information"
    if any(token in lowered for token in ("hello", "你好", "greet", "joke", "笑话", "feel", "feeling", "tired", "累")):
        return "speech"
    return "body_action"


def _work_request(**kwargs):
    context = dict(kwargs.pop("context", {}) or {})
    responsibilities = kwargs.pop("responsibilities", None)
    if responsibilities is None:
        responsibilities = context.pop("responsibility_proposals", None)
    if not responsibilities:
        text = str(kwargs.get("text") or "")
        responsibilities = [
            {
                "local_ref": "r1",
                "outcome": text or "satisfy the current user outcome",
                "bindings": {},
                "output_mode": _test_what_mode(text),
                "confidence": 0.9,
            }
        ]
    normalized_responsibilities = []
    source_tokens = user_turn_source_tokens(str(kwargs.get("text") or ""))
    for item in responsibilities:
        payload = dict(item) if isinstance(item, dict) else item.model_dump(mode="json")
        payload.setdefault("output_mode", _test_what_mode(str(payload.get("outcome") or kwargs.get("text") or "")))
        if source_tokens and not payload.get("source_evidence"):
            payload["source_evidence"] = {
                "source_start_token_ref": source_tokens[0]["ref"],
                "source_end_token_ref": source_tokens[-1]["ref"],
            }
        normalized_responsibilities.append(payload)
    return CognitiveWorkRequest(
        **kwargs,
        responsibilities=normalized_responsibilities,
        interpretation_confidence=0.9,
        context=context,
    )


def request(text: str, *, goal_ids=None, goal_metadata=None):
    goal_ids = list(goal_ids or [])
    new_goals = [
        {
            "goal_id": goal_id,
            "description": f"Goal {goal_id}",
            "source_text": text,
            "constraints": {},
            "success_criteria": [],
            "metadata": dict(goal_metadata or {}),
        }
        for goal_id in goal_ids
    ]
    return CognitiveWorkRequest(
        sid="sid-pr3",
        text=text,
        language="zh-CN",
        responsibilities=[
            {
                "local_ref": "r1",
                "outcome": text,
                "bindings": {},
                "output_mode": _test_what_mode(text, goal_metadata=goal_metadata),
                "confidence": 0.9,
            }
        ],
        interpretation_confidence=0.9,
        context={
            "active_goal_snapshots": [],
            "goal_association_resolution": {
                "associations": [],
                "new_goals": new_goals,
            },
        },
        history=[],
    )


def exact_satisfaction(goal_ids: list[str], rationale: str = "Exact plan coverage.") -> dict:
    return {
        "score": 1.0,
        "status": "exact",
        "satisfied_goal_ids": list(goal_ids),
        "unmet_goal_ids": [],
        "unmet_requirements": [],
        "rationale": rationale,
    }


def execute_step(
    step_id: str,
    capability_id: str,
    args: dict,
    goal_ids: list[str],
    reason: str,
) -> dict:
    return {
        "step_id": step_id,
        "capability_id": capability_id,
        "args": args,
        "source_goal_ids": list(goal_ids),
        "reason_summary": reason,
    }


def execute_outcome(goal_id: str, step_ids: list[str], reason: str) -> dict:
    return {
        "disposition": "execute",
        "coverage": "complete",
        "unresolved": [],
        "step_ids": list(step_ids),
        "satisfaction": exact_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def multi_goal_plan(
    *,
    disposition: str,
    coverage: str,
    goal_summary: str,
    steps: list[dict],
    goal_outcomes: dict[str, dict],
    goal_satisfaction: dict,
    response_text: str = "",
    unresolved: list[str] | None = None,
    parameter_resolutions: list[dict] | None = None,
    confidence: float = 0.97,
) -> dict:
    # Steps without explicit dependencies run in list order (each waits for the previous).
    chained, previous = [], []
    for step in steps:
        chained.append(step if "depends_on" in step else {**step, "depends_on": list(previous)})
        previous = [step["step_id"]]
    return {
        "disposition": disposition,
        "coverage": coverage,
        "confidence": confidence,
        "goal_summary": goal_summary,
        "steps": chained,
        "unresolved": list(unresolved or []),
        "parameter_resolutions": list(parameter_resolutions or []),
        "goal_outcomes": goal_outcomes,
        "goal_satisfaction": goal_satisfaction,
        "plan_relation": "exact",
        "user_confirmation_required": False,
    }
