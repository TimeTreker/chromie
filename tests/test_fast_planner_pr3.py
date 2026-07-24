from __future__ import annotations

import asyncio
import unittest

from agent.app.fast_planner import FastPlannerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from agent.app.capabilities.catalog import CatalogCapability
from shared.chromie_contracts.plan import CanonicalPlan


class FakeOllama:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ScriptedOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(capability_id="soridormi.blink_eyes", agent_id="capability_agent", description="Blink eyes", input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]}, route="robot_action", available=True, interaction_executable=True, prompt_tier="common"),
            CatalogCapability(capability_id="soridormi.walk_forward", agent_id="capability_agent", description="Walk forward", input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]}, route="robot_action", available=True, interaction_executable=True, prompt_tier="common"),
            CatalogCapability(capability_id="chromie.speak", agent_id="capability_agent", description="Speak text", input_schema={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}, route="chat", available=True, interaction_executable=True, prompt_tier="common"),
        ]

    async def prompt_entries(self, **kwargs):
        return self.items


def request(text: str, route="robot_action", *, goal_ids=None):
    goal_ids = list(goal_ids or [])
    new_goals = [
        {
            "goal_id": goal_id,
            "description": f"Goal {goal_id}",
            "source_text": text,
            "constraints": {},
            "success_criteria": [],
        }
        for goal_id in goal_ids
    ]
    return AgentRunRequest(
        sid="sid-pr3",
        text=text,
        language="zh-CN",
        route_decision=RouteDecision(route=route, intent="test", confidence=0.9, source="llm"),
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


def unsatisfied_satisfaction(goal_ids: list[str], rationale: str) -> dict:
    return {
        "score": 0.0,
        "status": "unsatisfied",
        "satisfied_goal_ids": [],
        "unmet_goal_ids": list(goal_ids),
        "unmet_requirements": [rationale],
        "rationale": rationale,
    }


def execute_step(
    step_id: str,
    skill_id: str,
    args: dict,
    goal_ids: list[str],
    reason: str,
) -> dict:
    return {
        "step_id": step_id,
        "skill_id": skill_id,
        "args": args,
        "timing": "sequential",
        "source_goal_ids": list(goal_ids),
        "reason_summary": reason,
    }


def execute_outcome(goal_id: str, step_ids: list[str], reason: str) -> dict:
    return {
        "disposition": "execute",
        "coverage": "complete",
        "response_text": "",
        "unresolved": [],
        "step_ids": list(step_ids),
        "satisfaction": exact_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def respond_outcome(goal_id: str, text: str, reason: str) -> dict:
    return {
        "disposition": "respond",
        "coverage": "complete",
        "response_text": text,
        "unresolved": [],
        "step_ids": [],
        "satisfaction": exact_satisfaction([goal_id], reason),
        "rationale": reason,
    }


def escalate_outcome(goal_id: str, reason: str) -> dict:
    return {
        "disposition": "escalate",
        "coverage": "uncertain",
        "response_text": "",
        "unresolved": [reason],
        "step_ids": [],
        "satisfaction": unsatisfied_satisfaction([goal_id], reason),
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
    escalation_reason: str = "",
    unresolved: list[str] | None = None,
    parameter_resolutions: list[dict] | None = None,
    confidence: float = 0.97,
) -> dict:
    return {
        "disposition": disposition,
        "coverage": coverage,
        "confidence": confidence,
        "goal_summary": goal_summary,
        "response_text": response_text,
        "steps": steps,
        "escalation_reason": escalation_reason,
        "unresolved": list(unresolved or []),
        "parameter_resolutions": list(parameter_resolutions or []),
        "goal_outcomes": goal_outcomes,
        "goal_satisfaction": goal_satisfaction,
        "plan_relation": "exact",
        "user_confirmation_required": False,
    }


class CanonicalPlanContractTests(unittest.TestCase):
    def test_partial_plan_cannot_carry_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="fast", disposition="escalate", coverage="partial", confidence=0.5, escalation_reason="compound", steps=[{"step_id":"s","skill_id":"soridormi.walk_forward","args":{"duration_s":15}}])

    def test_complete_execute_requires_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="fast", disposition="execute", coverage="complete", confidence=0.9)

    def test_response_plan_cannot_hide_executable_steps(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(
                plan_id="p",
                planner_tier="fast",
                disposition="respond",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-joke"],
                response_text="A joke.",
                steps=[{
                    "step_id": "wrong",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "source_goal_ids": ["goal-joke"],
                }],
            )

    def test_simple_chat_can_be_complete_response(self):
        plan = CanonicalPlan(plan_id="p", planner_tier="fast", disposition="respond", coverage="complete", confidence=0.9, response_text="你好。")
        self.assertEqual(plan.response_text, "你好。")

    def test_fast_mixed_plan_is_valid_for_execute_and_respond_outcomes(self):
        plan = CanonicalPlan(
            plan_id="p-fast-mixed",
            planner_tier="fast",
            disposition="mixed",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-blink", "goal-joke"],
            steps=[{
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            goal_outcomes=[
                {
                    "goal_id": "goal-blink",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["blink"],
                },
                {
                    "goal_id": "goal-joke",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "A short joke.",
                },
            ],
            goal_satisfaction={"score": 1.0, "status": "exact"},
        )
        self.assertEqual(plan.disposition, "mixed")


class FastPlannerResolverTests(unittest.TestCase):
    def test_simple_blink_produces_complete_direct_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.94,"goal_ids":["goal-blink"],"goal_summary":"blink four times","steps":[{"step_id":"blink","skill_id":"soridormi.blink_eyes","args":{"count":4},"timing":"sequential","source_goal_ids":["goal-blink"]}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("眨四下眼睛。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual(plan.coverage, "complete")
        self.assertEqual(plan.steps[0].skill_id, "soridormi.blink_eyes")
        self.assertEqual(plan.metadata["authority"], "advisory")

    def test_simple_chat_produces_complete_response(self):
        raw = {"disposition":"respond","coverage":"complete","confidence":0.93,"goal_summary":"greet","response_text":"你好。","steps":[],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("你好。", route="chat", goal_ids=["goal-greet"])))
        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.steps, [])


    def test_chat_route_schema_is_response_only(self):
        raw = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 0.93,
            "goal_summary": "greet",
            "response_text": "Hello!",
            "steps": [],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        ollama = FakeOllama(raw)
        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("Hello.", route="chat", goal_ids=["goal-greet"])
            )
        )
        self.assertEqual(plan.disposition, "respond")
        schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 0)
        self.assertEqual(
            schema["properties"]["disposition"]["enum"],
            ["respond", "escalate"],
        )

    def test_contract_repair_receives_all_compound_shape_defects(self):
        invalid = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 0.95,
            "response_text": "Done.",
            "steps": [
                {
                    "step_id": "walk",
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                    "source_goal_ids": ["goal-walk"],
                },
                {
                    "step_id": "blink",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "source_goal_ids": ["goal-blink"],
                },
            ],
            "goal_satisfaction": {"score": 1.0, "status": "substantial"},
        }
        repaired = {
            **multi_goal_plan(
                disposition="escalate",
                coverage="uncertain",
                confidence=0.95,
                goal_summary="Walk for one second, then blink twice.",
                steps=[],
                goal_outcomes={
                    "goal-walk": escalate_outcome(
                        "goal-walk",
                        "Compound request requires deeper planning.",
                    ),
                    "goal-blink": escalate_outcome(
                        "goal-blink",
                        "Compound request requires deeper planning.",
                    ),
                },
                goal_satisfaction=unsatisfied_satisfaction(
                    ["goal-walk", "goal-blink"],
                    "Compound request requires deep multi-goal accounting.",
                ),
                escalation_reason=(
                    "Compound request requires deep multi-goal accounting."
                ),
                unresolved=["goal-walk", "goal-blink"],
            )
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk for one second, then blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        repair_prompt = ollama.prompts[1][0]
        self.assertIn("goal satisfaction score is inconsistent with status", repair_prompt)
        self.assertIn("respond planner output must not carry executable steps", repair_prompt)
        self.assertIn("complete multi-goal planner output requires goal_outcomes", repair_prompt)
        self.assertIn("regenerate one fresh complete model-authored plan object", repair_prompt)
        self.assertIn(
            "Previous Fast Planner output when doing a semantic replan:\nnull",
            repair_prompt,
        )

    def test_compound_walk_and_blink_escalates_without_partial_steps(self):
        raw = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.88,
            goal_summary="walk while blinking",
            steps=[],
            goal_outcomes={
                "goal-walk": escalate_outcome(
                    "goal-walk", "concurrency feasibility"
                ),
                "goal-blink": escalate_outcome(
                    "goal-blink", "blink timing requires deeper planning"
                ),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-walk", "goal-blink"],
                "compound_goal_requires_full_planning",
            ),
            escalation_reason="compound_goal_requires_full_planning",
            unresolved=["concurrency feasibility", "blink count"],
        )
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("往前走15秒，同时眨眼。", goal_ids=["goal-walk", "goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertIn("concurrency feasibility", plan.unresolved)
        self.assertEqual(
            {item.disposition for item in plan.goal_outcomes},
            {"escalate"},
        )
        self.assertEqual(plan.metadata["path_classification"], "semantic_escalation")

    def test_multi_goal_fast_schema_requires_complete_model_authored_plan(self):
        raw = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.9,
            goal_summary="Two independent goals.",
            steps=[],
            goal_outcomes={
                "goal-a": escalate_outcome("goal-a", "Goal A needs Deep Planner."),
                "goal-b": escalate_outcome("goal-b", "Goal B needs Deep Planner."),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-a", "goal-b"], "Deep planning is required."
            ),
            escalation_reason="heterogeneous multi-goal request requires deep planning",
            unresolved=["goal-a", "goal-b"],
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Handle both requested goals.",
                    goal_ids=["goal-a", "goal-b"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        schema = ollama.prompts[0][1]["response_format"]
        self.assertEqual(schema["title"], "FastPlannerMultiGoalPlanOutput")
        self.assertIn("goal_outcomes", schema["required"])
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["required"],
            ["goal-a", "goal-b"],
        )
        self.assertEqual(
            schema["properties"]["goal_outcomes"]["minProperties"], 2
        )
        self.assertIn("mixed", schema["properties"]["disposition"]["enum"])
        self.assertIn(
            "escalate",
            schema["$defs"]["PlannerModelGoalOutcome"]["properties"]
            ["disposition"]["enum"],
        )
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 2)
        goal_a_outcome = schema["properties"]["goal_outcomes"]["properties"][
            "goal-a"
        ]
        goal_a_satisfaction = goal_a_outcome["properties"]["satisfaction"][
            "anyOf"
        ][0]
        self.assertEqual(
            goal_a_satisfaction["properties"]["satisfied_goal_ids"]["items"][
                "enum"
            ],
            ["goal-a"],
        )
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_goal_ids"]["items"][
                "enum"
            ],
            ["goal-a"],
        )
        self.assertEqual(goal_a_outcome["properties"]["step_ids"]["maxItems"], 1)
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_goal_ids"]["maxItems"], 0
        )
        self.assertEqual(
            goal_a_satisfaction["properties"]["unmet_requirements"]["maxItems"],
            0,
        )
        self.assertEqual(
            schema["properties"]["goal_satisfaction"]["anyOf"][0][
                "properties"
            ]["satisfied_goal_ids"]["minItems"],
            2,
        )
        self.assertLess(
            list(schema["properties"]).index("goal_outcomes"),
            list(schema["properties"]).index("steps"),
        )
        self.assertLess(
            list(schema["properties"]).index("goal_outcomes"),
            list(schema["properties"]).index("disposition"),
        )
        aggregate_branches = schema["allOf"][0]["anyOf"]
        mixed_branches = [
            branch
            for branch in aggregate_branches
            if branch["properties"]["disposition"]["enum"] == ["mixed"]
        ]
        self.assertEqual(len(mixed_branches), 2)
        self.assertTrue(
            all(
                branch["properties"]["steps"]["maxItems"] == 1
                for branch in mixed_branches
            )
        )
        self.assertEqual(
            set(schema["$defs"]["PlannerModelStep"]["required"]),
            {
                "step_id",
                "skill_id",
                "args",
                "timing",
                "source_goal_ids",
                "reason_summary",
            },
        )
        self.assertEqual(schema["properties"]["goal_summary"]["maxLength"], 240)
        self.assertEqual(
            schema["$defs"]["PlannerModelStep"]["properties"]
            ["reason_summary"]["maxLength"],
            160,
        )
        self.assertEqual(
            schema["$defs"]["PlannerModelGoalOutcome"]["properties"]
            ["rationale"]["maxLength"],
            200,
        )
        self.assertEqual(
            schema["$defs"]["PlannerGoalSatisfaction"]["properties"]
            ["rationale"]["maxLength"],
            200,
        )
        self.assertEqual(
            schema["$defs"]["PlanParameterResolution"]["properties"]
            ["source_ref"]["maxLength"],
            160,
        )
        self.assertEqual(
            set(schema["$defs"]["PlanParameterResolution"]["required"]),
            {
                "step_id",
                "parameter",
                "strategy",
                "value",
                "confidence",
                "blocking",
                "rationale",
                "source_ref",
                "source_goal_ids",
            },
        )
        self.assertIn("one short sentence each", ollama.prompts[0][0])

    def test_explicit_numeric_grounding_mismatch_gets_bounded_model_repair(self):
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Walk for two seconds and blink.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-walk"],
                    "Walk forward.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 1},
                    ["goal-blink"],
                    "Blink once.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk is covered."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "The blink is covered."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"]
            ),
            parameter_resolutions=[
                {
                    "step_id": "walk",
                    "parameter": "duration_s",
                    "strategy": "user_supplied",
                    "value": 1.0,
                    "confidence": 0.99,
                    "blocking": False,
                    "rationale": "Copied from the goal.",
                    "source_ref": "2 seconds",
                    "source_goal_ids": ["goal-walk"],
                }
            ],
        )
        repaired = {
            **invalid,
            "steps": [
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk forward.",
                ),
                invalid["steps"][1],
            ],
            "parameter_resolutions": [
                {
                    **invalid["parameter_resolutions"][0],
                    "value": "2.0",
                }
            ],
        }
        ollama = ScriptedOllama([invalid, repaired])
        run_request = request(
            "Walk forward for 2 seconds, then blink.",
            goal_ids=["goal-walk", "goal-blink"],
        )
        run_request.context["goal_association_resolution"]["new_goals"][0][
            "description"
        ] = "Walk forward for 2 seconds."

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(run_request)
        )

        self.assertEqual(plan.steps[0].args["duration_s"], 2.0)
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn(
            "source_ref does not cite its resolved value",
            ollama.prompts[1][0],
        )

    def test_multi_goal_fast_execute_terminates_without_repair(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            confidence=0.97,
            goal_summary="Execute two ordered physical goals.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-walk"],
                    "Execute the first physical goal.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-blink"],
                    "Execute the second physical goal.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "The walk step covers this goal."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "The blink step covers this goal."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"],
                "Both physical goals are fully planned.",
            ),
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk forward for one second, then blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.planner_tier, "fast")
        self.assertEqual(plan.disposition, "execute")
        self.assertEqual([step.step_id for step in plan.steps], ["walk", "blink"])
        self.assertTrue(plan.metadata["model_authored_steps"])
        self.assertFalse(plan.metadata["host_semantic_compilation"])
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        self.assertEqual(len(ollama.prompts), 1)

    def test_multi_goal_fast_mixed_terminates_without_deep_planning(self):
        raw = multi_goal_plan(
            disposition="mixed",
            coverage="complete",
            confidence=0.98,
            goal_summary="Execute one goal and answer another.",
            response_text="A concise model-authored answer.",
            steps=[
                execute_step(
                    "physical-step",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-action"],
                    "Execute the physical goal exactly.",
                )
            ],
            goal_outcomes={
                "goal-action": execute_outcome(
                    "goal-action",
                    ["physical-step"],
                    "The physical step covers the action goal.",
                ),
                "goal-answer": respond_outcome(
                    "goal-answer",
                    "A concise model-authored answer.",
                    "Answer the conversational goal directly.",
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-action", "goal-answer"],
                "Both goals are fully planned.",
            ),
        )
        ollama = FakeOllama(raw)

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Complete the physical goal and answer the other goal.",
                    goal_ids=["goal-action", "goal-answer"],
                )
            )
        )

        self.assertEqual(plan.planner_tier, "fast")
        self.assertEqual(plan.disposition, "mixed")
        self.assertEqual(
            plan.goal_outcomes[1].response_text,
            "A concise model-authored answer.",
        )
        self.assertEqual(plan.steps[0].step_id, "physical-step")
        self.assertEqual(plan.metadata["path_classification"], "terminal")
        self.assertEqual(len(ollama.prompts), 1)

    def test_mixed_aggregate_repair_is_constrained_by_model_authored_outcomes(self):
        initial = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Execute one goal and answer another.",
            response_text="A concise model-authored answer.",
            steps=[
                execute_step(
                    "physical-step",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-action"],
                    "Execute the physical goal exactly.",
                )
            ],
            goal_outcomes={
                "goal-action": execute_outcome(
                    "goal-action", ["physical-step"], "Physical goal plan."
                ),
                "goal-answer": respond_outcome(
                    "goal-answer", "A concise answer.", "Answer goal plan."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-action", "goal-answer"]
            ),
        )
        repaired = {**initial, "disposition": "mixed"}
        ollama = ScriptedOllama([initial, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Complete both abstract goals.",
                    goal_ids=["goal-action", "goal-answer"],
                )
            )
        )

        self.assertEqual(plan.disposition, "mixed")
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        first_schema = ollama.prompts[0][1]["response_format"]
        repair_schema = ollama.prompts[1][1]["response_format"]
        self.assertIn("execute", first_schema["properties"]["disposition"]["enum"])
        self.assertEqual(
            repair_schema["properties"]["disposition"]["enum"], ["mixed"]
        )

    def test_low_confidence_complete_claim_is_forced_to_escalate(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.51,"goal_ids":["goal-blink"],"steps":[{"skill_id":"soridormi.blink_eyes","args":{"count":3}}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog(), min_confidence=0.8).resolve(request("眨眼。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])

    def test_non_common_or_non_executable_skill_escalates(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.95,"goal_ids":["goal-action"],"steps":[{"step_id":"invented","skill_id":"invented.skill","args":{},"source_goal_ids":["goal-action"]}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("做点什么。", goal_ids=["goal-action"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.escalation_reason, "step_not_in_executable_common_catalog")

    def test_prompt_defines_complete_coverage_not_skill_matching(self):
        ollama = FakeOllama({"disposition":"respond","coverage":"complete","confidence":0.9,"response_text":"你好。","steps":[],"goal_satisfaction":{"score":1.0,"status":"exact"}})
        asyncio.run(FastPlannerResolver(ollama, FakeCatalog()).resolve(request("你好。", route="chat", goal_ids=["goal-greet"])))
        prompt = ollama.prompts[0][0]
        self.assertIn("Finding one matching skill is not complete coverage", prompt)
        self.assertIn("zero steps", prompt)

    def test_multi_goal_prompt_preserves_explicit_in_range_arguments(self):
        raw = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Two exact actions.",
            steps=[
                execute_step(
                    "walk",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-walk"],
                    "Walk for the supplied duration.",
                ),
                execute_step(
                    "blink",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-blink"],
                    "Blink the supplied count.",
                ),
            ],
            goal_outcomes={
                "goal-walk": execute_outcome(
                    "goal-walk", ["walk"], "Walk goal covered."
                ),
                "goal-blink": execute_outcome(
                    "goal-blink", ["blink"], "Blink goal covered."
                ),
            },
            goal_satisfaction=exact_satisfaction(
                ["goal-walk", "goal-blink"]
            ),
        )
        ollama = FakeOllama(raw)

        asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk for 2 seconds and blink twice.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        prompt = ollama.prompts[0][0]
        self.assertIn("copy it exactly", prompt)
        self.assertIn("never silently replace it with a schema default", prompt)
        self.assertIn("Catalog defaults are only for parameters", prompt)
        self.assertIn("A material adjustment must use a non-exact plan_relation", prompt)

    def test_uses_dynamic_schema_for_goal_and_skill_ids(self):
        ollama = FakeOllama({
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink"],
            },
        })

        asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("blink twice", goal_ids=["goal-blink"])
            )
        )

        schema = ollama.prompts[0][1]["response_format"]
        self.assertIsInstance(schema, dict)
        self.assertEqual(schema["title"], "FastPlannerModelOutput")
        self.assertNotIn("oneOf", schema)
        self.assertNotIn("planner_tier", schema["properties"])
        self.assertNotIn("goal_ids", schema["properties"])
        self.assertIn("confidence", schema["required"])
        self.assertIn("goal_satisfaction", schema["required"])
        step_schema = schema["$defs"]["PlannerModelStep"]
        self.assertIn("source_goal_ids", step_schema["required"])
        self.assertEqual(
            step_schema["properties"]["skill_id"]["enum"],
            ["soridormi.blink_eyes", "soridormi.walk_forward"],
        )
        prompt = ollama.prompts[0][0]
        self.assertIn("FINAL AUTHORITATIVE USER TURN", prompt)
        self.assertIn("FINAL CANONICAL GOALS JSON", prompt)
        self.assertNotIn(
            "chromie.speak",
            step_schema["properties"]["skill_id"]["enum"],
        )

    def test_response_transport_step_is_repaired_to_conversational_response(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "steps": [{
                "step_id": "say",
                "skill_id": "chromie.speak",
                "args": {"text": "A short joke."},
                "source_goal_ids": ["goal-joke"],
            }],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = {
            "disposition": "respond",
            "coverage": "complete",
            "confidence": 0.95,
            "response_text": "A short joke.",
            "steps": [],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-joke"],
            },
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("Tell me a short joke.", route="chat", goal_ids=["goal-joke"])
            )
        )

        self.assertEqual(plan.disposition, "respond")
        self.assertEqual(plan.steps, [])
        self.assertEqual(len(ollama.prompts), 2)
        self.assertIn("owned by Response Composer", ollama.prompts[1][0])

    def test_live_branch_minimal_escalation_repairs_under_flat_contract(self):
        branch_minimal = {
            "planner_tier": "fast",
            "disposition": "escalate",
            "coverage": "partial",
            "steps": [],
            "escalation_reason": "compound request requires deep planning",
        }
        repaired = multi_goal_plan(
            disposition="escalate",
            coverage="uncertain",
            confidence=0.9,
            goal_summary="Two goals require Deep Planner.",
            steps=[],
            goal_outcomes={
                "goal-walk": escalate_outcome(
                    "goal-walk", "The first goal requires deeper planning."
                ),
                "goal-blink": escalate_outcome(
                    "goal-blink", "The second goal requires deeper planning."
                ),
            },
            goal_satisfaction=unsatisfied_satisfaction(
                ["goal-walk", "goal-blink"],
                "The Fast Planner cannot safely complete the plan.",
            ),
            escalation_reason="compound request requires deep planning",
            unresolved=["goal-walk", "goal-blink"],
        )
        ollama = ScriptedOllama([branch_minimal, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request(
                    "Walk forward, then blink.",
                    goal_ids=["goal-walk", "goal-blink"],
                )
            )
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.goal_ids, ["goal-walk", "goal-blink"])
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertEqual(len(ollama.prompts), 2)
        schema = ollama.prompts[0][1]["response_format"]
        self.assertNotIn("oneOf", schema)
        self.assertEqual(schema["title"], "FastPlannerMultiGoalPlanOutput")
        self.assertEqual(ollama.prompts[1][1]["response_format"], schema)
        repair_prompt = ollama.prompts[1][0]
        self.assertGreater(
            repair_prompt.index("FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON"),
            repair_prompt.index("FINAL CANONICAL GOALS JSON"),
        )

    def test_same_user_text_follows_different_model_authored_plans(self):
        """The host must not map words in the utterance to fixed actions."""

        text = "Carry out both abstract goals."
        first = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="First model-authored plan.",
            steps=[
                execute_step(
                    "s1",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-a"],
                    "Model selected walking for goal A.",
                ),
                execute_step(
                    "s2",
                    "soridormi.blink_eyes",
                    {"count": 2},
                    ["goal-b"],
                    "Model selected blinking for goal B.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["s1"], "Goal A plan."),
                "goal-b": execute_outcome("goal-b", ["s2"], "Goal B plan."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )
        second = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Second model-authored plan.",
            steps=[
                execute_step(
                    "s1-alt",
                    "soridormi.blink_eyes",
                    {"count": 1},
                    ["goal-a"],
                    "Model selected blinking for goal A.",
                ),
                execute_step(
                    "s2-alt",
                    "soridormi.walk_forward",
                    {"duration_s": 2.0},
                    ["goal-b"],
                    "Model selected walking for goal B.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["s1-alt"], "Goal A plan."),
                "goal-b": execute_outcome("goal-b", ["s2-alt"], "Goal B plan."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )

        request_value = request(text, goal_ids=["goal-a", "goal-b"])
        plan_one = asyncio.run(
            FastPlannerResolver(FakeOllama(first), FakeCatalog()).resolve(
                request_value
            )
        )
        plan_two = asyncio.run(
            FastPlannerResolver(FakeOllama(second), FakeCatalog()).resolve(
                request_value
            )
        )

        self.assertEqual(
            [step.skill_id for step in plan_one.steps],
            ["soridormi.walk_forward", "soridormi.blink_eyes"],
        )
        self.assertEqual(
            [step.skill_id for step in plan_two.steps],
            ["soridormi.blink_eyes", "soridormi.walk_forward"],
        )
        self.assertNotEqual(
            [step.step_id for step in plan_one.steps],
            [step.step_id for step in plan_two.steps],
        )

    def test_multi_goal_host_does_not_generate_missing_step_ids(self):
        invalid = multi_goal_plan(
            disposition="execute",
            coverage="complete",
            goal_summary="Invalid plan missing a model-authored step ID.",
            steps=[
                {
                    "step_id": "",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 1},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-a"],
                    "reason_summary": "Missing identifier must not be repaired locally.",
                },
                execute_step(
                    "valid-b",
                    "soridormi.walk_forward",
                    {"duration_s": 1.0},
                    ["goal-b"],
                    "Valid second step.",
                ),
            ],
            goal_outcomes={
                "goal-a": execute_outcome("goal-a", ["missing"], "Invalid link."),
                "goal-b": execute_outcome("goal-b", ["valid-b"], "Valid link."),
            },
            goal_satisfaction=exact_satisfaction(["goal-a", "goal-b"]),
        )
        ollama = FakeOllama(invalid)
        plan = asyncio.run(
            FastPlannerResolver(
                ollama,
                FakeCatalog(),
                max_contract_repairs=0,
            ).resolve(request("Abstract request.", goal_ids=["goal-a", "goal-b"]))
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.metadata["path_classification"], "contract_failure")
        self.assertEqual(plan.steps, [])

    def test_legacy_step_shape_requires_one_model_revision_without_local_mapping(self):
        invalid = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "capability_id": "soridormi.blink_eyes",
                "parameters": {"count": 2},
            }],
            "goal_satisfaction": {"score": 1.0, "status": "exact"},
        }
        repaired = {
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-blink"],
            "steps": [{
                "step_id": "blink",
                "skill_id": "soridormi.blink_eyes",
                "args": {"count": 2},
                "source_goal_ids": ["goal-blink"],
            }],
            "goal_satisfaction": {
                "score": 1.0,
                "status": "exact",
                "satisfied_goal_ids": ["goal-blink"],
            },
        }
        ollama = ScriptedOllama([invalid, repaired])

        plan = asyncio.run(
            FastPlannerResolver(ollama, FakeCatalog()).resolve(
                request("blink twice", goal_ids=["goal-blink"])
            )
        )

        self.assertEqual(len(ollama.prompts), 2)
        self.assertEqual(plan.steps[0].skill_id, "soridormi.blink_eyes")
        self.assertTrue(plan.metadata["contract_repair_succeeded"])
        self.assertIn("capability_id", ollama.prompts[1][0])
        self.assertIn("extra_forbidden", ollama.prompts[1][0])

    def test_model_failure_escalates_safely(self):
        plan = asyncio.run(FastPlannerResolver(FakeOllama(RuntimeError("offline")), FakeCatalog()).resolve(request("眨眼。")))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.metadata["status"], "escalate")
        self.assertEqual(plan.metadata["path_classification"], "contract_failure")


class OrchestratorFastPlannerTests(unittest.TestCase):
    def test_report_only_schedules_without_changing_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        class Client:
            async def resolve_fast_plan(self, *args, **kwargs):
                return CanonicalPlan(plan_id="p", planner_tier="fast", disposition="respond", coverage="complete", confidence=0.9, response_text="hi")

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_mode = "report_only"
            assistant.fast_planner_timeout_ms = 1000
            assistant.enable_agent = True
            assistant.agent_client = Client()
            assistant.fast_planner_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None
            decision = ODecision(route="chat", intent="conversation", confidence=0.8, source="llm")
            reviewed = assistant._schedule_fast_planner_report(object(), user_text="hello", session_id="sid", context={"history":[]}, decision=decision)
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(reviewed.metadata["fast_planner_resolution"]["status"], "scheduled")
            await asyncio.gather(*list(assistant.fast_planner_report_tasks))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
