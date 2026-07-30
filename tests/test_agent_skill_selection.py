from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from agent.app.agent_skills import (
    AgentSkillSelectionService,
    compute_agent_skill_content_digest,
    load_agent_skill_registry,
)
from agent.app.capabilities.local import build_chromie_registry
from shared.chromie_contracts import (
    AgentSkillSelectionModelOutput,
    AgentSkillSelectionRequest,
)


class ScriptedModel:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.prompts = []
        self.model = "qwen3:test"

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if not self.payloads:
            raise AssertionError("unexpected model call")
        value = self.payloads.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class ContextAwareModel:
    model = "context-aware-test"

    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        payload = json.loads(prompt)
        descriptions = " ".join(
            item["description"] for item in payload.get("goals", [])
        ).casefold()
        if "weather" in descriptions:
            candidate = next(
                item
                for item in payload["candidate_agent_skills"]
                if item["agent_skill_id"] == "chromie.weather-information"
            )
            return {
                "decision": "select_skills",
                "selected_agent_skills": [
                    {
                        "agent_skill_id": candidate["agent_skill_id"],
                        "version": candidate["version"],
                        "projection": payload["agent_role"],
                        "relevant_goal_ids": [payload["goals"][0]["goal_id"]],
                        "rationale": "The current Goal needs a weather method.",
                        "confidence": 0.91,
                    }
                ],
                "confidence": 0.91,
                "reason_summary": "Weather method is useful for this Goal.",
            }
        return {
            "decision": "no_skill",
            "selected_agent_skills": [],
            "confidence": 0.93,
            "reason_summary": "No listed method is relevant to this Goal.",
        }


class AgentSkillSelectionTests(unittest.TestCase):
    def _write_package(
        self,
        root: Path,
        name: str,
        *,
        projections=("fast_planner",),
        version="1.0.0",
    ) -> Path:
        package = root / name
        (package / "projections").mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"# {name}\n\nReusable passive method.\n",
            encoding="utf-8",
        )
        projection_map = {}
        for projection in projections:
            relative = f"projections/{projection}.md"
            projection_map[projection] = relative
            (package / relative).write_text(
                f"Method guidance for {projection}.\n",
                encoding="utf-8",
            )
        digest = compute_agent_skill_content_digest(package)
        metadata = {
            "schema_version": "1.0",
            "agent_skill_id": f"chromie.{name}",
            "version": version,
            "title": name.replace("-", " ").title(),
            "description": f"Passive methods for {name.replace('-', ' ')} tasks.",
            "authority": "agent_method_only",
            "execution_authority": "none",
            "owner_approved": True,
            "content_digest": digest,
            "required_capabilities": [],
            "optional_capabilities": [],
            "projections": projection_map,
        }
        (package / "skill.yaml").write_text(
            yaml.safe_dump(metadata, sort_keys=False),
            encoding="utf-8",
        )
        return package

    @staticmethod
    def _request(
        *,
        text="Please help with this.",
        description="Get the current weather.",
        agent_role="fast_planner",
        candidate_ids=(),
    ):
        return AgentSkillSelectionRequest(
            sid="sid-selection",
            turn_id="turn-selection",
            agent_role=agent_role,
            text=text,
            language="en-US",
            goals=[
                {
                    "goal_id": "goal-1",
                    "description": description,
                    "bindings": ["location=Neixiang"],
                    "success_criteria": ["Answer the user's need."],
                }
            ],
            context_summary=["The Goal binding is authoritative."],
            candidate_agent_skill_ids=list(candidate_ids),
        )

    def _registry(self, root: Path):
        return load_agent_skill_registry([root]).registry

    def test_selection_contract_requires_explicit_no_or_nonempty_selection(self):
        with self.assertRaises(ValidationError):
            AgentSkillSelectionModelOutput.model_validate(
                {
                    "decision": "select_skills",
                    "selected_agent_skills": [],
                    "confidence": 0.8,
                    "reason_summary": "Invalid empty selection.",
                }
            )
        with self.assertRaises(ValidationError):
            AgentSkillSelectionModelOutput.model_validate(
                {
                    "decision": "no_skill",
                    "selected_agent_skills": [
                        {
                            "agent_skill_id": "chromie.weather-information",
                            "version": "1.0.0",
                            "projection": "fast_planner",
                            "relevant_goal_ids": ["goal-1"],
                            "rationale": "Invalid retained item.",
                            "confidence": 0.8,
                        }
                    ],
                    "confidence": 0.8,
                    "reason_summary": "Invalid no-skill shape.",
                }
            )

    def test_empty_registry_returns_no_candidates_without_model_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = self._registry(Path(temp_dir))
            model = ScriptedModel([])
            result = asyncio.run(
                AgentSkillSelectionService(model, registry).select(self._request())
            )
        self.assertEqual(result.decision, "no_skill")
        self.assertEqual(result.status, "no_candidates")
        self.assertEqual(model.prompts, [])

    def test_model_can_author_explicit_no_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            model = ScriptedModel(
                [
                    {
                        "decision": "no_skill",
                        "selected_agent_skills": [],
                        "confidence": 0.88,
                        "reason_summary": "The current Goal does not need this method.",
                    }
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(model, self._registry(root)).select(
                    self._request(description="Tell a short joke.")
                )
            )
        self.assertEqual(result.status, "no_skill")
        self.assertEqual(result.selected_agent_skills, ())
        prompt = json.loads(model.prompts[0][0])
        self.assertEqual(len(prompt["candidate_agent_skills"]), 1)
        self.assertNotIn("content", prompt["candidate_agent_skills"][0])
        self.assertNotIn("source", prompt["candidate_agent_skills"][0])

    def test_model_selects_one_skill_with_registry_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = self._write_package(root, "weather-information")
            registry = self._registry(root)
            summary = registry.list_summaries()[0]
            model = ScriptedModel(
                [
                    {
                        "decision": "select_skills",
                        "selected_agent_skills": [
                            {
                                "agent_skill_id": summary.agent_skill_id,
                                "version": summary.version,
                                "projection": "fast_planner",
                                "relevant_goal_ids": ["goal-1"],
                                "rationale": "Weather evidence strategy is useful.",
                                "confidence": 0.93,
                            }
                        ],
                        "confidence": 0.93,
                        "reason_summary": "Use the weather method for this Goal.",
                    }
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(model, registry).select(self._request())
            )
        self.assertEqual(result.status, "selected")
        selected = result.selected_agent_skills[0]
        self.assertEqual(selected.content_digest, summary.content_digest)
        self.assertEqual(selected.projection, "fast_planner")
        self.assertNotIn("content", selected.model_dump())

    def test_model_can_select_multiple_skills_in_authored_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "grounded-information")
            self._write_package(root, "weather-information")
            registry = self._registry(root)
            summaries = {item.agent_skill_id: item for item in registry.list_summaries()}
            model = ScriptedModel(
                [
                    {
                        "decision": "select_skills",
                        "selected_agent_skills": [
                            {
                                "agent_skill_id": "chromie.weather-information",
                                "version": summaries["chromie.weather-information"].version,
                                "projection": "fast_planner",
                                "relevant_goal_ids": ["goal-1"],
                                "rationale": "Domain-specific weather method.",
                                "confidence": 0.94,
                            },
                            {
                                "agent_skill_id": "chromie.grounded-information",
                                "version": summaries["chromie.grounded-information"].version,
                                "projection": "fast_planner",
                                "relevant_goal_ids": ["goal-1"],
                                "rationale": "Reusable evidence-grounding method.",
                                "confidence": 0.90,
                            },
                        ],
                        "confidence": 0.92,
                        "reason_summary": "Both methods are useful.",
                    }
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(model, registry).select(self._request())
            )
        self.assertEqual(
            [item.agent_skill_id for item in result.selected_agent_skills],
            ["chromie.weather-information", "chromie.grounded-information"],
        )

    def test_unknown_model_selection_gets_one_bounded_repair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            registry = self._registry(root)
            summary = registry.list_summaries()[0]
            model = ScriptedModel(
                [
                    {
                        "decision": "select_skills",
                        "selected_agent_skills": [
                            {
                                "agent_skill_id": "chromie.unlisted",
                                "version": "1.0.0",
                                "projection": "fast_planner",
                                "relevant_goal_ids": ["goal-1"],
                                "rationale": "Not disclosed.",
                                "confidence": 0.9,
                            }
                        ],
                        "confidence": 0.9,
                        "reason_summary": "Invalid first output.",
                    },
                    {
                        "decision": "select_skills",
                        "selected_agent_skills": [
                            {
                                "agent_skill_id": summary.agent_skill_id,
                                "version": summary.version,
                                "projection": "fast_planner",
                                "relevant_goal_ids": ["goal-1"],
                                "rationale": "Use the disclosed weather method.",
                                "confidence": 0.91,
                            }
                        ],
                        "confidence": 0.91,
                        "reason_summary": "Repaired to an approved candidate.",
                    },
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(model, registry).select(self._request())
            )
        self.assertEqual(len(model.prompts), 2)
        self.assertTrue(result.contract_repair_attempted)
        self.assertTrue(result.contract_repair_succeeded)
        self.assertEqual(result.status, "selected")
        self.assertIn("chromie.unlisted", model.prompts[1][0])

    def test_invalid_output_after_repair_fails_to_no_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            model = ScriptedModel(
                [
                    {"decision": "select_skills"},
                    {"decision": "select_skills"},
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(model, self._registry(root)).select(
                    self._request()
                )
            )
        self.assertEqual(result.decision, "no_skill")
        self.assertEqual(result.status, "model_contract_failed")
        self.assertTrue(result.contract_repair_attempted)
        self.assertFalse(result.contract_repair_succeeded)

    def test_model_unavailable_fails_to_optional_no_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            result = asyncio.run(
                AgentSkillSelectionService(
                    ScriptedModel([RuntimeError("offline")]),
                    self._registry(root),
                ).select(self._request())
            )
        self.assertEqual(result.status, "model_unavailable")
        self.assertEqual(result.selected_agent_skills, ())

    def test_projection_availability_is_structural_candidate_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "fast-only", projections=("fast_planner",))
            self._write_package(root, "deep-only", projections=("deep_planner",))
            model = ScriptedModel(
                [
                    {
                        "decision": "no_skill",
                        "selected_agent_skills": [],
                        "confidence": 0.9,
                        "reason_summary": "No method selected.",
                    }
                ]
            )
            asyncio.run(
                AgentSkillSelectionService(model, self._registry(root)).select(
                    self._request(agent_role="deep_planner")
                )
            )
        prompt = json.loads(model.prompts[0][0])
        self.assertEqual(
            [item["agent_skill_id"] for item in prompt["candidate_agent_skills"]],
            ["chromie.deep-only"],
        )

    def test_unknown_explicit_candidate_fails_before_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            model = ScriptedModel([])
            with self.assertRaisesRegex(ValueError, "unknown Agent Skill candidate"):
                asyncio.run(
                    AgentSkillSelectionService(model, self._registry(root)).select(
                        self._request(candidate_ids=("chromie.unknown",))
                    )
                )
        self.assertEqual(model.prompts, [])

    def test_candidate_volume_is_bounded_without_semantic_keyword_choice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(5):
                self._write_package(root, f"method-{index}")
            model = ScriptedModel(
                [
                    {
                        "decision": "no_skill",
                        "selected_agent_skills": [],
                        "confidence": 0.9,
                        "reason_summary": "No method selected.",
                    }
                ]
            )
            result = asyncio.run(
                AgentSkillSelectionService(
                    model,
                    self._registry(root),
                    max_candidates=3,
                    max_selected=2,
                ).select(self._request(text="weather weather weather"))
            )
        self.assertEqual(result.candidate_total, 5)
        self.assertTrue(result.candidate_truncated)
        self.assertEqual(len(result.candidate_summaries), 3)
        self.assertEqual(
            [item.agent_skill_id for item in result.candidate_summaries],
            ["chromie.method-0", "chromie.method-1", "chromie.method-2"],
        )

    def test_same_phrase_can_produce_different_selection_from_goal_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            registry = self._registry(root)
            model = ContextAwareModel()
            service = AgentSkillSelectionService(model, registry)
            weather = asyncio.run(
                service.select(
                    self._request(
                        text="Please handle that.",
                        description="Get the current weather.",
                    )
                )
            )
            joke = asyncio.run(
                service.select(
                    self._request(
                        text="Please handle that.",
                        description="Tell a short joke.",
                    )
                )
            )
        self.assertEqual(weather.decision, "select_skills")
        self.assertEqual(joke.decision, "no_skill")

    def test_selection_cannot_mutate_capability_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_package(root, "weather-information")
            capability_registry = build_chromie_registry()
            before = capability_registry.model_dump()
            model = ScriptedModel(
                [
                    {
                        "decision": "no_skill",
                        "selected_agent_skills": [],
                        "confidence": 0.9,
                        "reason_summary": "No Skill is needed.",
                    }
                ]
            )
            asyncio.run(
                AgentSkillSelectionService(model, self._registry(root)).select(
                    self._request()
                )
            )
        self.assertEqual(capability_registry.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
