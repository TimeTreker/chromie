from __future__ import annotations

import unittest

from pydantic import ValidationError

from agent.app.agent_skills import (
    attach_disclosure_metadata,
    attach_planner_disclosure_metadata_fail_closed,
    inherited_plan_agent_skill_provenance,
)
from orchestrator.runtime.cognitive_runtime import CanonicalPlanRuntimeAdapter

try:
    from chromie_contracts import (
        AgentSkillDisclosureResolution,
        CanonicalPlan,
        DisclosedAgentSkillProjection,
        PlanAgentSkillProvenance,
        canonical_plan_fingerprint,
    )
except ImportError:  # pragma: no cover - repository test path
    from shared.chromie_contracts import (
        AgentSkillDisclosureResolution,
        CanonicalPlan,
        DisclosedAgentSkillProjection,
        PlanAgentSkillProvenance,
        canonical_plan_fingerprint,
    )


class AgentSkillPlanProvenanceTests(unittest.TestCase):
    @staticmethod
    def _disclosure(
        role: str,
        *,
        skill_id: str,
        goal_ids: tuple[str, ...] = ("goal-1",),
        digest_char: str = "a",
    ) -> AgentSkillDisclosureResolution:
        projection = DisclosedAgentSkillProjection(
            selection_id=f"selection-{role}-{skill_id}",
            selected_by_agent_role=role,
            agent_skill_id=skill_id,
            version="1.0.0",
            projection=role,
            content="Passive planner method.",
            content_digest="sha256:" + digest_char * 64,
            projection_digest="sha256:" + chr(ord(digest_char) + 1) * 64,
            relevant_goal_ids=goal_ids,
            selection_rationale="The model selected this method for the named Goal.",
            selection_confidence=0.93,
            source="ignored/by/plan/provenance.md",
            char_count=len("Passive planner method."),
        )
        disclosure_id = f"disclosure-{role}-{skill_id}"
        disclosure_digest = AgentSkillDisclosureResolution.compute_disclosure_digest(
            selection_id=projection.selection_id,
            agent_role=role,
            status="loaded",
            projections=(projection,),
            failures=(),
            max_projection_chars=3000,
            max_total_chars=6000,
            projection_count_limit=4,
        )
        return AgentSkillDisclosureResolution(
            disclosure_id=disclosure_id,
            selection_id=projection.selection_id,
            sid="sid-plan-provenance",
            turn_id="turn-plan-provenance",
            agent_role=role,
            status="loaded",
            projections=(projection,),
            failures=(),
            total_chars=projection.char_count,
            max_projection_chars=3000,
            max_total_chars=6000,
            projection_count_limit=4,
            disclosure_digest=disclosure_digest,
        )

    @staticmethod
    def _plan(*, tier: str = "fast") -> CanonicalPlan:
        return CanonicalPlan(
            plan_id=f"plan-{tier}",
            planner_tier=tier,
            disposition="respond",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-1"],
            goal_summary="Answer one grounded Goal.",
            response_text="Done.",
        )

    def test_fast_plan_binds_content_free_exact_provenance(self) -> None:
        disclosure = self._disclosure(
            "fast_planner",
            skill_id="chromie.grounded-method",
        )
        plan = attach_disclosure_metadata(self._plan(), disclosure)

        self.assertEqual(len(plan.selected_agent_skills), 1)
        provenance = plan.selected_agent_skills[0]
        self.assertEqual(provenance.selection_id, disclosure.selection_id)
        self.assertEqual(provenance.disclosure_id, disclosure.disclosure_id)
        self.assertEqual(provenance.disclosure_digest, disclosure.disclosure_digest)
        self.assertEqual(provenance.selected_by_agent_role, "fast_planner")
        self.assertEqual(provenance.relevant_goal_ids, ("goal-1",))
        encoded = plan.model_dump(mode="json")
        self.assertNotIn("content", encoded["selected_agent_skills"][0])
        self.assertNotIn("source", encoded["selected_agent_skills"][0])

    def test_deep_plan_preserves_fast_provenance_and_appends_its_own(self) -> None:
        fast = attach_disclosure_metadata(
            self._plan(tier="fast"),
            self._disclosure(
                "fast_planner",
                skill_id="chromie.fast-method",
                digest_char="a",
            ),
        )
        inherited = inherited_plan_agent_skill_provenance(
            {"fast_plan_resolution": fast.model_dump(mode="json")}
        )
        deep = attach_disclosure_metadata(
            self._plan(tier="deep"),
            self._disclosure(
                "deep_planner",
                skill_id="chromie.deep-method",
                digest_char="c",
            ),
            inherited_plan_provenance=inherited,
        )

        self.assertEqual(
            [item.agent_skill_id for item in deep.selected_agent_skills],
            ["chromie.fast-method", "chromie.deep-method"],
        )
        self.assertEqual(
            [item.selected_by_agent_role for item in deep.selected_agent_skills],
            ["fast_planner", "deep_planner"],
        )

    def test_fast_plan_rejects_deep_planner_provenance(self) -> None:
        payload = self._plan().model_dump(mode="python")
        payload["selected_agent_skills"] = [
            PlanAgentSkillProvenance(
                selection_id="selection-deep",
                disclosure_id="disclosure-deep",
                disclosure_digest="sha256:" + "a" * 64,
                selected_by_agent_role="deep_planner",
                agent_skill_id="chromie.deep-method",
                version="1.0.0",
                projection="deep_planner",
                content_digest="sha256:" + "b" * 64,
                projection_digest="sha256:" + "c" * 64,
                relevant_goal_ids=("goal-1",),
                selection_rationale="Deep-only method.",
                selection_confidence=0.9,
            ).model_dump(mode="python")
        ]
        with self.assertRaisesRegex(ValidationError, "planner_tier"):
            CanonicalPlan.model_validate(payload)

    def test_plan_rejects_provenance_for_unknown_goal(self) -> None:
        disclosure = self._disclosure(
            "fast_planner",
            skill_id="chromie.wrong-goal-method",
            goal_ids=("goal-unknown",),
        )
        with self.assertRaisesRegex(ValidationError, "unknown goal IDs"):
            attach_disclosure_metadata(self._plan(), disclosure)

    def test_planner_boundary_fails_closed_for_unknown_provenance_goal(self) -> None:
        disclosure = self._disclosure(
            "fast_planner",
            skill_id="chromie.stale-weather-method",
            goal_ids=("goal-weather-complete",),
        )

        plan = attach_planner_disclosure_metadata_fail_closed(
            self._plan(),
            disclosure,
        )

        self.assertEqual(plan.disposition, "escalate")
        self.assertEqual(plan.coverage, "uncertain")
        self.assertEqual(plan.steps, [])
        self.assertEqual(
            plan.escalation_reason,
            "agent_skill_provenance_invalid",
        )
        self.assertFalse(
            plan.metadata["agent_skill_provenance_attachment"][
                "execution_allowed"
            ]
        )

    def test_plan_fingerprint_includes_skill_provenance(self) -> None:
        plain = self._plan()
        informed = attach_disclosure_metadata(
            plain,
            self._disclosure(
                "fast_planner",
                skill_id="chromie.fingerprint-method",
            ),
        )
        self.assertNotEqual(
            canonical_plan_fingerprint(plain),
            canonical_plan_fingerprint(informed),
        )

    def test_derived_goal_subset_narrows_provenance_without_inventing_goals(self) -> None:
        disclosure = self._disclosure(
            "deep_planner",
            skill_id="chromie.multi-goal-method",
            goal_ids=("goal-1", "goal-2"),
        )
        parent = CanonicalPlan(
            plan_id="plan-parent",
            planner_tier="deep",
            disposition="respond",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-1", "goal-2"],
            goal_summary="Answer both Goals.",
            response_text="Done.",
            goal_outcomes=[
                {
                    "goal_id": "goal-1",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "First answer.",
                },
                {
                    "goal_id": "goal-2",
                    "disposition": "respond",
                    "coverage": "complete",
                    "response_text": "Second answer.",
                },
            ],
        )
        parent = attach_disclosure_metadata(parent, disclosure)
        narrowed = parent.agent_skill_provenance_for_goals(["goal-2"])
        self.assertEqual(len(narrowed), 1)
        self.assertEqual(narrowed[0].relevant_goal_ids, ("goal-2",))
        self.assertEqual(narrowed[0].selection_id, parent.selected_agent_skills[0].selection_id)

    def test_no_skill_disclosure_keeps_plan_provenance_empty(self) -> None:
        disclosure = AgentSkillDisclosureResolution(
            disclosure_id="disclosure-none",
            selection_id="selection-none",
            sid="sid-none",
            turn_id="turn-none",
            agent_role="fast_planner",
            status="no_skill",
            projections=(),
            failures=(),
            total_chars=0,
            max_projection_chars=3000,
            max_total_chars=6000,
            projection_count_limit=4,
            disclosure_digest=AgentSkillDisclosureResolution.compute_disclosure_digest(
                selection_id="selection-none",
                agent_role="fast_planner",
                status="no_skill",
                projections=(),
                failures=(),
                max_projection_chars=3000,
                max_total_chars=6000,
                projection_count_limit=4,
            ),
        )
        plan = attach_disclosure_metadata(self._plan(), disclosure)
        self.assertEqual(plan.selected_agent_skills, [])
        self.assertNotIn("agent_skill_disclosure", plan.metadata)

    def test_execution_lane_ignores_agent_skill_provenance(self) -> None:
        base = CanonicalPlan(
            plan_id="plan-tool",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.95,
            goal_ids=["goal-1"],
            goal_summary="Look up weather.",
            steps=[
                {
                    "step_id": "step-weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "Neixiang"},
                    "source_goal_ids": ["goal-1"],
                }
            ],
        )
        informed = attach_disclosure_metadata(
            base,
            self._disclosure(
                "fast_planner",
                skill_id="chromie.method-only",
            ),
        )
        self.assertEqual(
            CanonicalPlanRuntimeAdapter.lane_for_plan(base),
            CanonicalPlanRuntimeAdapter.lane_for_plan(informed),
        )
        self.assertEqual(
            [step.capability_id for step in base.steps],
            [step.capability_id for step in informed.steps],
        )


if __name__ == "__main__":
    unittest.main()
