from __future__ import annotations

import asyncio
import unittest

from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.goal_association import GoalAssociationResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution


class FakeOllama:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def request(text: str, *, active_goals=None, history=None, language="zh-CN"):
    return AgentRunRequest(
        sid="sid-pr2",
        text=text,
        language=language,
        route_decision=RouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm"),
        context={"active_goal_snapshots": active_goals or [], "history": history or []},
    )


def active_goal(goal_id: str, description: str):
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "status": "open",
        "goal": {
            "goal_id": goal_id,
            "version": 1,
            "description": description,
            "source_text": description,
            "beneficiary": "user",
            "constraints": {},
            "success_criteria": [],
            "metadata": {},
        },
        "open_information_gaps": [],
        "commitment_state": "none",
        "last_user_update": description,
        "metadata": {},
    }


class GoalAssociationResolverTests(unittest.TestCase):
    def test_associates_followup_before_creating_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.96, "reason_summary": "The user refined the coffee goal."}], "new_goals": [], "confidence": 0.96, "reason_summary": "Continuity before creation."})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual([item.relationship for item in result.associations], ["modify"])
        self.assertEqual(result.associations[0].target_goal_ids, ["goal-coffee"])
        self.assertEqual(result.new_goals, [])
        self.assertEqual(result.metadata["authority"], "advisory")

    def test_can_update_existing_goal_and_create_independent_new_goal(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-coffee"], "confidence": 0.91}], "new_goals": [{"description": "Report the current weather.", "source_text": "顺便查一下天气。", "beneficiary": "user", "constraints": {}, "success_criteria": ["Current weather is reported."], "metadata": {}}], "confidence": 0.91})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("咖啡要冰的，顺便查一下天气。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(len(result.new_goals), 1)
        self.assertEqual(result.new_goals[0].description, "Report the current weather.")
        self.assertTrue(result.new_goals[0].goal_id.startswith("goal_"))

    def test_ambiguous_reference_returns_natural_clarification_only(self):
        ollama = FakeOllama({"associations": [], "new_goals": [], "clarification": "你是说咖啡不用了，还是天气也不用查了？", "confidence": 0.58})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("算了，不用了。", active_goals=[active_goal("goal-coffee", "Get coffee"), active_goal("goal-weather", "Check weather")])))
        self.assertEqual(result.clarification, "你是说咖啡不用了，还是天气也不用查了？")
        self.assertEqual(result.associations, [])
        self.assertNotIn("goal-coffee", result.clarification)

    def test_unknown_goal_target_is_rejected_and_falls_back_to_clarification(self):
        ollama = FakeOllama({"associations": [{"relationship": "modify", "target_goal_ids": ["goal-invented"], "confidence": 0.99}], "new_goals": [], "confidence": 0.99})
        result = asyncio.run(GoalAssociationResolver(ollama).resolve(request("冰的。", active_goals=[active_goal("goal-coffee", "Get coffee")])))
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)
        self.assertEqual(result.metadata["status"], "needs_clarification")

    def test_prompt_requires_continuity_before_creation_and_no_plan_step_goals(self):
        ollama = FakeOllama({"new_goals": [{"description": "Greet the user.", "source_text": "你好", "beneficiary": "user", "constraints": {}, "success_criteria": [], "metadata": {}}], "confidence": 0.9})
        asyncio.run(GoalAssociationResolver(ollama).resolve(request("你好")))
        prompt = ollama.prompts[0][0]
        self.assertIn("Resolve continuity before creation", prompt)
        self.assertIn("Do not split implementation steps into goals", prompt)
        self.assertIn("never internal IDs", prompt)

    def test_model_failure_is_safe_and_advisory(self):
        result = asyncio.run(GoalAssociationResolver(FakeOllama(RuntimeError("offline"))).resolve(request("继续。", active_goals=[active_goal("goal-a", "Do A")])))
        self.assertEqual(result.metadata["status"], "model_unavailable")
        self.assertEqual(result.associations, [])
        self.assertTrue(result.clarification)

    def test_truncation_failure_reports_domain_without_causal_attribution(self):
        error = OllamaGenerationError(
            "structured JSON output was truncated",
            failure_class="output_truncated",
            failure_domain="llm_budget",
            architecture_attribution="not_evaluated",
            retryable=True,
            details={"done_reason": "length", "num_predict": 512},
        )

        result = asyncio.run(
            GoalAssociationResolver(FakeOllama(error)).resolve(request("继续。"))
        )

        self.assertEqual(result.metadata["status"], "model_unavailable")
        self.assertEqual(result.metadata["failure_class"], "output_truncated")
        self.assertEqual(result.metadata["failure_domain"], "llm_budget")
        self.assertEqual(result.metadata["architecture_attribution"], "not_evaluated")
        self.assertEqual(result.metadata["done_reason"], "length")

    def test_resolution_contract_rejects_clarification_mixed_with_changes(self):
        with self.assertRaises(ValueError):
            GoalAssociationResolution(turn_id="turn-1", clarification="Which one?", new_goals=[{"goal_id": "goal-new", "description": "New goal", "source_text": "New goal", "beneficiary": "user", "constraints": {}, "success_criteria": [], "metadata": {}}])


class OrchestratorGoalAssociationTests(unittest.TestCase):
    def test_report_only_schedules_without_changing_route(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision

        class Client:
            async def resolve_goal_association(self, *args, **kwargs):
                return GoalAssociationResolution(turn_id="turn-report", associations=[{"association_id": "assoc-report", "relationship": "continue", "target_goal_ids": ["goal-a"], "confidence": 0.9}], confidence=0.9)

        async def run():
            assistant = VoiceAssistant.__new__(VoiceAssistant)
            assistant.goal_association_mode = "report_only"
            assistant.goal_association_timeout_ms = 1000
            assistant.enable_agent = True
            assistant.agent_client = Client()
            assistant.goal_association_report_tasks = set()
            assistant.session_log = lambda *args, **kwargs: None
            decision = OrchestratorRouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm")
            reviewed = assistant._schedule_goal_association_report(object(), user_text="继续。", session_id="sid", context={"history": [], "active_goal_snapshots": [active_goal("goal-a", "Do A")]}, decision=decision)
            self.assertEqual(reviewed.route, "chat")
            self.assertEqual(reviewed.metadata["goal_association_resolution"]["status"], "scheduled")
            pending = list(assistant.goal_association_report_tasks)
            if pending:
                await asyncio.gather(*pending)
        asyncio.run(run())

    def test_off_is_noop(self):
        from orchestrator.orchestrator import VoiceAssistant
        from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.goal_association_mode = "off"
        assistant.enable_agent = True
        decision = OrchestratorRouteDecision(route="chat", intent="conversation", confidence=0.8, source="llm")
        reviewed = assistant._schedule_goal_association_report(object(), user_text="hello", session_id="sid", context={"active_goal_snapshots": []}, decision=decision)
        self.assertIs(reviewed, decision)


if __name__ == "__main__":
    unittest.main()
