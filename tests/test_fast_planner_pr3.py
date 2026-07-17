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


class FastPlannerResolverTests(unittest.TestCase):
    def test_simple_blink_produces_complete_direct_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.94,"goal_ids":["goal-blink"],"goal_summary":"blink four times","steps":[{"skill_id":"soridormi.blink_eyes","args":{"count":4},"timing":"sequential"}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
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

    def test_compound_walk_and_blink_escalates_without_partial_steps(self):
        raw = {"disposition":"escalate","coverage":"partial","confidence":0.88,"goal_summary":"walk while blinking","steps":[],"escalation_reason":"compound_goal_requires_full_planning","unresolved":["concurrency feasibility","blink count"]}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("往前走15秒，同时眨眼。", goal_ids=["goal-walk", "goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])
        self.assertIn("concurrency feasibility", plan.unresolved)

    def test_low_confidence_complete_claim_is_forced_to_escalate(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.51,"goal_ids":["goal-blink"],"steps":[{"skill_id":"soridormi.blink_eyes","args":{"count":3}}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog(), min_confidence=0.8).resolve(request("眨眼。", goal_ids=["goal-blink"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.steps, [])

    def test_non_common_or_non_executable_skill_escalates(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.95,"goal_ids":["goal-action"],"steps":[{"skill_id":"invented.skill","args":{}}],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(FastPlannerResolver(FakeOllama(raw), FakeCatalog()).resolve(request("做点什么。", goal_ids=["goal-action"])))
        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.escalation_reason, "step_not_in_executable_common_catalog")

    def test_prompt_defines_complete_coverage_not_skill_matching(self):
        ollama = FakeOllama({"disposition":"respond","coverage":"complete","confidence":0.9,"response_text":"你好。","steps":[],"goal_satisfaction":{"score":1.0,"status":"exact"}})
        asyncio.run(FastPlannerResolver(ollama, FakeCatalog()).resolve(request("你好。", route="chat", goal_ids=["goal-greet"])))
        prompt = ollama.prompts[0][0]
        self.assertIn("Finding one matching skill is not complete coverage", prompt)
        self.assertIn("zero steps", prompt)

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
        repaired = {
            "disposition": "escalate",
            "coverage": "partial",
            "confidence": 0.9,
            "steps": [],
            "escalation_reason": "compound request requires deep planning",
            "goal_satisfaction": None,
        }
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
        self.assertEqual(ollama.prompts[1][1]["response_format"], schema)

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
