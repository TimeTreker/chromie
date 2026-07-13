from __future__ import annotations

import asyncio
import unittest

from agent.app.capabilities.catalog import CatalogCapability
from agent.app.deep_planner import DeepPlannerResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.plan import CanonicalPlan


class SequencedOllama:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FullCatalog:
    def __init__(self):
        self.items = [
            CatalogCapability(
                capability_id="soridormi.walk_forward", agent_id="capability_agent",
                description="Walk forward", route="robot_action", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"duration_s":{"type":"number","minimum":0.1}},"required":["duration_s"]},
                can_run_parallel=False, parallel_metadata_declared=True,
                exclusive_group="base_motion", resource_claims=["base_motion"],
            ),
            CatalogCapability(
                capability_id="soridormi.blink_eyes", agent_id="capability_agent",
                description="Blink eyes", route="robot_action", available=True,
                interaction_executable=True, prompt_tier="common",
                input_schema={"type":"object","properties":{"count":{"type":"integer","minimum":1,"maximum":10}},"required":["count"]},
                can_run_parallel=True, parallel_metadata_declared=True,
                exclusive_group="eye_expression", resource_claims=["eye_expression"],
            ),
            CatalogCapability(
                capability_id="rare.observe_doorway", agent_id="capability_agent",
                description="Observe doorway", route="tool", available=True,
                interaction_executable=True, prompt_tier="rare",
                input_schema={"type":"object","properties":{}},
            ),
        ]
        self.scopes = []

    async def prompt_entries(self, **kwargs):
        self.scopes.append(kwargs.get("scope"))
        return self.items


def request(text="往前走15秒，然后眨眼。"):
    return AgentRunRequest(
        sid="sid-pr4", text=text, language="zh-CN",
        route_decision=RouteDecision(route="robot_action", intent="semantic_capability_planning", confidence=0.0, source="llm"),
        context={"fast_plan_resolution":{"disposition":"escalate","coverage":"partial","steps":[]}}, history=[])


class CanonicalDeepPlanContractTests(unittest.TestCase):
    def test_deep_partial_plan_can_clarify_without_steps(self):
        plan = CanonicalPlan(plan_id="p", planner_tier="deep", disposition="clarify", coverage="partial", confidence=0.7, unresolved=["duration"])
        self.assertEqual(plan.disposition, "clarify")

    def test_deep_plan_cannot_escalate_back_to_fast(self):
        with self.assertRaises(ValueError):
            CanonicalPlan(plan_id="p", planner_tier="deep", disposition="escalate", coverage="uncertain", confidence=0.0, escalation_reason="retry fast")


class DeepPlannerResolverTests(unittest.TestCase):
    def test_full_catalog_exact_plan(self):
        raw = {"disposition":"execute","coverage":"complete","confidence":0.91,"goal_summary":"walk then blink","steps":[
            {"skill_id":"soridormi.walk_forward","args":{"duration_s":15}},
            {"skill_id":"soridormi.blink_eyes","args":{"count":4}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        catalog = FullCatalog()
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([raw]), catalog).resolve(request()))
        self.assertEqual(plan.planner_tier, "deep")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(catalog.scopes, ["all"])
        self.assertEqual(plan.metadata["attempt_count"], 1)

    def test_invalid_first_plan_is_revised_once_in_same_tier(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"steps":[
            {"skill_id":"soridormi.blink_eyes","args":{"count":99}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        revised = {"disposition":"execute","coverage":"complete","confidence":0.93,"steps":[
            {"skill_id":"soridormi.blink_eyes","args":{"count":4}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        ollama = SequencedOllama([invalid, revised])
        plan = asyncio.run(DeepPlannerResolver(ollama, FullCatalog(), max_replans=1).resolve(request("眨眼。")))
        self.assertEqual(plan.steps[0].args["count"], 4)
        self.assertEqual(plan.metadata["attempt_count"], 2)
        self.assertIn("invalid_args", ollama.prompts[1][0])
        self.assertNotIn("Fast Planner decides again", ollama.prompts[1][0])

    def test_repeated_invalid_plan_fails_closed_without_steps(self):
        invalid = {"disposition":"execute","coverage":"complete","confidence":0.92,"steps":[
            {"skill_id":"invented.skill","args":{}}
        ],"goal_satisfaction":{"score":1.0,"status":"exact"}}
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([invalid, invalid]), FullCatalog(), max_replans=1).resolve(request()))
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata["attempt_count"], 2)

    def test_missing_essential_parameter_can_return_specific_clarification(self):
        raw = {"disposition":"clarify","coverage":"partial","confidence":0.84,"goal_summary":"walk forward","response_text":"你希望我往前走多久？","steps":[],"unresolved":["walking duration"]}
        plan = asyncio.run(DeepPlannerResolver(SequencedOllama([raw]), FullCatalog()).resolve(request("往前走。")))
        self.assertEqual(plan.disposition, "clarify")
        self.assertEqual(plan.steps, [])
        self.assertIn("walking duration", plan.unresolved)

    def test_prompt_is_terminal_and_uses_skills_as_leaves(self):
        ollama = SequencedOllama([{"disposition":"clarify","coverage":"uncertain","confidence":0.7,"steps":[],"unresolved":["target"]}])
        asyncio.run(DeepPlannerResolver(ollama, FullCatalog()).resolve(request("看看门口。")))
        prompt = ollama.prompts[0][0]
        system = ollama.prompts[0][1]["system"]
        self.assertIn("Deep planning is terminal", prompt)
        self.assertIn("never call or return to the Fast Planner", system)


class OrchestratorDeepPlannerTests(unittest.TestCase):
    def test_fast_escalation_triggers_report_only_deep_planner(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as ODecision

        class Client:
            def __init__(self):
                self.deep_context = None
            async def resolve_fast_plan(self, *args, **kwargs):
                return CanonicalPlan(plan_id="fast", planner_tier="fast", disposition="escalate", coverage="partial", confidence=0.8, escalation_reason="compound", steps=[])
            async def resolve_deep_plan(self, *args, **kwargs):
                self.deep_context = kwargs["context"]
                return CanonicalPlan(plan_id="deep", planner_tier="deep", disposition="execute", coverage="complete", confidence=0.9, steps=[{"step_id":"s1","skill_id":"soridormi.blink_eyes","args":{"count":3}}], metadata={"attempt_count":1})

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.fast_planner_timeout_ms = 1000
            assistant.deep_planner_mode = "report_only"
            assistant.deep_planner_timeout_ms = 2000
            assistant.agent_client = Client()
            assistant.session_log = lambda *args, **kwargs: None
            decision = ODecision(route="robot_action", intent="semantic_capability_planning", confidence=0.0, source="llm")
            await assistant._run_fast_planner_report(object(), user_text="walk and blink", session_id="sid", context={"history":[]}, decision=decision)
            self.assertEqual(assistant.agent_client.deep_context["fast_plan_resolution"]["plan_id"], "fast")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
