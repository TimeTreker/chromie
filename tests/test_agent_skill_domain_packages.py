from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from agent.app.agent_skills import (
    AgentSkillDisclosureService,
    AgentSkillSelectionService,
    attach_disclosure_metadata,
    load_agent_skill_registry,
)
from agent.app.capabilities.local import build_chromie_registry
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter

try:
    from chromie_contracts import (
        AgentSkillDisclosureRequest,
        AgentSkillSelectionRequest,
        CanonicalPlan,
    )
except ImportError:  # pragma: no cover - repository test path
    from shared.chromie_contracts import (
        AgentSkillDisclosureRequest,
        AgentSkillSelectionRequest,
        CanonicalPlan,
    )


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "agent-skills"
ROLES = (
    "goal_association",
    "fast_planner",
    "deep_planner",
)
BASE_ID = "chromie.grounded-external-information"
WEATHER_ID = "chromie.weather-information"


class ScriptedModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []
        self.model = "qwen3:test"

    async def generate(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        if not self.payloads:
            raise AssertionError("unexpected model call")
        return self.payloads.pop(0)


class AgentSkillDomainPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_agent_skill_registry([SKILL_ROOT]).registry
        cls.summaries = {
            item.agent_skill_id: item for item in cls.registry.list_summaries()
        }

    @staticmethod
    def _request(role: str, *, candidate_ids=()) -> AgentSkillSelectionRequest:
        return AgentSkillSelectionRequest(
            sid="sid-domain-skills",
            turn_id=f"turn-{role}",
            agent_role=role,
            text="河南省内乡县今天下雨了吗？体感温度怎么样？",
            language="zh-CN",
            goals=[
                {
                    "goal_id": "goal-weather",
                    "description": "查询今天河南省内乡县是否下雨并说明体感温度。",
                    "bindings": [
                        "location=河南省内乡县",
                        "date=today",
                        "weather_aspects=rain,apparent_temperature",
                    ],
                    "success_criteria": [
                        "使用与当前地点和日期匹配的可信天气证据回答。"
                    ],
                    "output_mode": "capability_work",
                    "information_domain": "weather_forecast",
                    "resource_kind": "information",
                }
            ],
            context_summary=[
                "Goal Association has already resolved the location binding.",
                "A previous result for another city is historical only.",
            ],
            candidate_agent_skill_ids=list(candidate_ids),
        )

    def test_external_information_skills_are_not_candidates_for_robot_action(self):
        model = ScriptedModel([])
        service = AgentSkillSelectionService(model, self.registry)

        selection = asyncio.run(
            service.select(
                AgentSkillSelectionRequest(
                    sid="sid-physical",
                    turn_id="turn-physical",
                    agent_role="deep_planner",
                    text="Walk while blinking.",
                    language="en-US",
                    goals=[
                        {
                            "goal_id": "goal-walk",
                            "description": "Walk forward.",
                        }
                    ],
                    context_summary=["route=robot_action"],
                )
            )
        )

        self.assertEqual(selection.status, "no_candidates")
        self.assertEqual(selection.selected_agent_skills, ())
        self.assertEqual(model.calls, [])

    def test_declared_goal_applicability_excludes_external_skills_without_route_hint(self):
        model = ScriptedModel([])
        service = AgentSkillSelectionService(model, self.registry)

        selection = asyncio.run(
            service.select(
                AgentSkillSelectionRequest(
                    sid="sid-physical-output",
                    turn_id="turn-physical-output",
                    agent_role="fast_planner",
                    text="Walk forward for ten seconds.",
                    language="en-US",
                    goals=[
                        {
                            "goal_id": "goal-walk",
                            "description": "Move forward for ten seconds.",
                            "output_mode": "body_action",
                        }
                    ],
                )
            )
        )

        self.assertEqual(selection.status, "no_candidates")
        self.assertEqual(selection.selected_agent_skills, ())
        self.assertEqual(model.calls, [])

    def _both_skill_output(self, role: str) -> dict:
        return {
            "decision": "select_skills",
            "selected_agent_skills": [
                {
                    "agent_skill_id": BASE_ID,
                    "version": self.summaries[BASE_ID].version,
                    "projection": role,
                    "relevant_goal_ids": ["goal-weather"],
                    "rationale": "Use the reusable evidence-grounding method first.",
                    "confidence": 0.95,
                },
                {
                    "agent_skill_id": WEATHER_ID,
                    "version": self.summaries[WEATHER_ID].version,
                    "projection": role,
                    "relevant_goal_ids": ["goal-weather"],
                    "rationale": "Apply the weather-specific method to the bound Goal.",
                    "confidence": 0.96,
                },
            ],
            "confidence": 0.95,
            "reason_summary": "The base method and weather specialization both apply.",
        }

    def test_repository_loads_exact_owner_approved_domain_packages(self) -> None:
        self.assertEqual(set(self.summaries), {BASE_ID, WEATHER_ID})
        for summary in self.summaries.values():
            self.assertTrue(summary.owner_approved)
            self.assertEqual(summary.authority, "agent_method_only")
            self.assertEqual(summary.execution_authority, "none")
            self.assertEqual(set(summary.available_projections), set(ROLES))
            self.assertRegex(summary.content_digest, r"^sha256:[0-9a-f]{64}$")

        weather = self.summaries[WEATHER_ID]
        self.assertEqual(weather.extends, (BASE_ID,))
        self.assertEqual(weather.required_capabilities, ("chromie.weather.lookup",))
        self.assertEqual(
            weather.optional_capabilities,
            ("chromie.memory.retrieve_verified_tool_result",),
        )
        self.assertEqual(weather.applicable_output_modes, ("capability_work",))
        self.assertEqual(
            weather.applicable_information_domains,
            ("weather_forecast",),
        )

    def test_external_information_summary_excludes_deterministic_local_reads(self) -> None:
        description = self.summaries[BASE_ID].description
        self.assertIn("outside information source", description)
        self.assertIn("local clock", description)
        self.assertIn("direct visual or auditory observation", description)
        self.assertIn("Do not select", description)

        system_prompt = AgentSkillSelectionService._system_prompt("fast_planner")
        self.assertIn("Fresh runtime evidence alone", system_prompt)
        self.assertIn("local clock", system_prompt)

    def test_registry_summaries_do_not_expose_skill_or_projection_content(self) -> None:
        for summary in self.registry.list_summaries():
            encoded = summary.model_dump(mode="json")
            self.assertNotIn("content", encoded)
            self.assertNotIn("source", encoded)
            self.assertNotIn("path", encoded)

    def test_model_authors_base_then_weather_for_all_semantic_agents(self) -> None:
        for role in ROLES:
            with self.subTest(role=role):
                model = ScriptedModel([self._both_skill_output(role)])
                selection = asyncio.run(
                    AgentSkillSelectionService(model, self.registry).select(
                        self._request(role)
                    )
                )
                self.assertEqual(selection.status, "selected")
                self.assertEqual(
                    [item.agent_skill_id for item in selection.selected_agent_skills],
                    [BASE_ID, WEATHER_ID],
                )
                system_prompt = model.calls[0][1]["system"]
                self.assertIn("extends field is dependency metadata", system_prompt)
                self.assertIn("selecting a specialization never loads", system_prompt)
                self.assertIn("base method before the specialization", system_prompt)

                disclosure = AgentSkillDisclosureService(self.registry).disclose(
                    AgentSkillDisclosureRequest(selection=selection)
                )
                self.assertEqual(disclosure.status, "loaded")
                self.assertEqual(
                    [item.agent_skill_id for item in disclosure.projections],
                    [BASE_ID, WEATHER_ID],
                )
                self.assertTrue(all(item.projection == role for item in disclosure.projections))
                self.assertLessEqual(disclosure.total_chars, disclosure.max_total_chars)

    def test_generic_external_goal_can_select_only_the_base_method(self) -> None:
        role = "fast_planner"
        model = ScriptedModel(
            [
                {
                    "decision": "select_skills",
                    "selected_agent_skills": [
                        {
                            "agent_skill_id": BASE_ID,
                            "version": self.summaries[BASE_ID].version,
                            "projection": role,
                            "relevant_goal_ids": ["goal-weather"],
                            "rationale": "Only the reusable evidence strategy is needed.",
                            "confidence": 0.91,
                        }
                    ],
                    "confidence": 0.91,
                    "reason_summary": "Use one generic external-information method.",
                }
            ]
        )
        selection = asyncio.run(
            AgentSkillSelectionService(model, self.registry).select(
                self._request(role, candidate_ids=(BASE_ID,))
            )
        )
        self.assertEqual(
            [item.agent_skill_id for item in selection.selected_agent_skills],
            [BASE_ID],
        )

    def test_non_external_goal_has_no_applicable_skill_candidates(self) -> None:
        model = ScriptedModel([])
        payload = self._request("fast_planner").model_dump(mode="python")
        payload.update(
            {
                "text": "Tell me a short joke.",
                "goals": [
                    {
                        "goal_id": "goal-weather",
                        "description": "Tell a short joke.",
                        "bindings": [],
                        "success_criteria": ["Respond conversationally."],
                        "output_mode": "speech",
                    }
                ],
            }
        )
        request = AgentSkillSelectionRequest.model_validate(payload)
        selection = asyncio.run(
            AgentSkillSelectionService(model, self.registry).select(request)
        )
        self.assertEqual(selection.status, "no_candidates")
        self.assertEqual(selection.selected_agent_skills, ())
        self.assertEqual(model.calls, [])

    def test_declared_applicability_excludes_external_skills_for_vocal_work(self) -> None:
        model = ScriptedModel([])
        selection = asyncio.run(
            AgentSkillSelectionService(model, self.registry).select(
                AgentSkillSelectionRequest(
                    sid="sid-singing",
                    turn_id="turn-singing",
                    agent_role="deep_planner",
                    text="Sing while walking.",
                    language="en-US",
                    goals=[
                        {
                            "goal_id": "goal-sing",
                            "description": "Sing.",
                            "output_mode": "singing",
                        },
                        {
                            "goal_id": "goal-walk",
                            "description": "Walk.",
                            "output_mode": "body_action",
                        },
                    ],
                )
            )
        )

        self.assertEqual(selection.status, "no_candidates")
        self.assertEqual(selection.selected_agent_skills, ())
        self.assertEqual(model.calls, [])

    def test_real_fast_planner_projections_bind_content_free_plan_provenance(self) -> None:
        role = "fast_planner"
        selection = asyncio.run(
            AgentSkillSelectionService(
                ScriptedModel([self._both_skill_output(role)]), self.registry
            ).select(self._request(role))
        )
        disclosure = AgentSkillDisclosureService(self.registry).disclose(
            AgentSkillDisclosureRequest(selection=selection)
        )
        base_plan = CanonicalPlan(
            plan_id="plan-weather-domain-skills",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-weather"],
            goal_summary="查询今天河南省内乡县天气。",
            steps=[
                {
                    "step_id": "step-weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {
                        "location": "河南省内乡县",
                        "date": "today",
                        "units": "metric",
                    },
                    "source_goal_ids": ["goal-weather"],
                }
            ],
        )
        informed = attach_disclosure_metadata(base_plan, disclosure)
        self.assertEqual(
            [item.agent_skill_id for item in informed.selected_agent_skills],
            [BASE_ID, WEATHER_ID],
        )
        encoded = informed.model_dump(mode="json")
        self.assertNotIn("content", encoded["selected_agent_skills"][0])
        self.assertNotIn("source", encoded["selected_agent_skills"][0])
        self.assertEqual(
            CanonicalPlanRuntimeAdapter.lane_for_plan(base_plan),
            CanonicalPlanRuntimeAdapter.lane_for_plan(informed),
        )

    def test_skill_loading_does_not_modify_capability_registry(self) -> None:
        capability_registry = build_chromie_registry()
        before = [item.name for item in capability_registry.list_tools()]
        _ = load_agent_skill_registry([SKILL_ROOT]).registry.snapshot(
            roots=(str(SKILL_ROOT),),
            package_files=(),
        )
        after = [item.name for item in capability_registry.list_tools()]
        self.assertEqual(before, after)
        self.assertIn("chromie.weather.lookup", after)
        self.assertIn("chromie.memory.retrieve_verified_tool_result", after)

    def test_grounded_method_covers_memory_fresh_lookup_clarify_and_failure(self) -> None:
        fast = self.registry.load_projection(BASE_ID, "fast_planner").content
        deep = self.registry.load_projection(BASE_ID, "deep_planner").content
        method = self.registry.load_document(BASE_ID).content
        self.assertIn("chromie.memory.retrieve_verified_tool_result", fast)
        self.assertIn("fresh read", fast)
        self.assertIn("clarify", fast.lower())
        self.assertIn("report the unsupported need honestly", deep.lower())
        self.assertIn("Before evidence exists", method)
        self.assertIn("provider/network failures", method)
        self.assertIn("exact Evidence references", method)
        self.assertNotIn("if user_text", "\n".join((fast, deep, method)))

    def test_weather_method_preserves_binding_and_typed_weather_outcomes(self) -> None:
        goal = self.registry.load_projection(WEATHER_ID, "goal_association").content
        fast = self.registry.load_projection(WEATHER_ID, "fast_planner").content
        deep = self.registry.load_projection(WEATHER_ID, "deep_planner").content
        method = self.registry.load_document(WEATHER_ID).content
        self.assertIn("Resolve “there,”", goal)
        self.assertIn("args.location", fast)
        self.assertIn("exactly equal to the canonical Goal binding", fast)
        self.assertIn("entity_type=date", fast)
        self.assertIn("args.date", fast)
        self.assertIn("entity_type=day_part", fast)
        self.assertIn("args.period", fast)
        self.assertIn("probability, not certainty", fast)
        self.assertIn("forecast_period", fast)
        self.assertIn("value `today`", goal)
        self.assertIn("value `night`", goal)
        self.assertIn("mismatched location", deep)
        self.assertIn("location_not_found", method)
        self.assertIn("no-rain/no-snow", method)
        self.assertIn("apparent temperature", method)

    def test_domain_packages_fit_default_progressive_disclosure_budgets(self) -> None:
        for role in ROLES:
            total = sum(
                len(self.registry.load_projection(skill_id, role).content)
                for skill_id in (BASE_ID, WEATHER_ID)
            )
            with self.subTest(role=role):
                self.assertLessEqual(total, 6000)
                for skill_id in (BASE_ID, WEATHER_ID):
                    self.assertLessEqual(
                        len(self.registry.load_projection(skill_id, role).content),
                        3000,
                    )


if __name__ == "__main__":
    unittest.main()
