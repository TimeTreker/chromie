from __future__ import annotations

import asyncio
import unittest

from agent.app.agent_skills.disclosure import (
    AgentSkillDisclosureService,
    AgentSkillProgressiveDisclosureCoordinator,
)
from agent.app.agent_skills.loader import AgentSkillRegistry
from shared.chromie_contracts.agent_skill import AgentSkillProjectionName
from tests.cognitive_work_test_support import cognitive_work_request


class PlannerDisclosureTopologyTests(unittest.TestCase):
    def test_removed_duplicate_semantic_roles_are_not_projection_names(self) -> None:
        allowed = set(AgentSkillProjectionName.__args__)
        self.assertNotIn("response_composer", allowed)
        self.assertNotIn("tool_result_interpreter", allowed)
        self.assertIn("fast_planner", allowed)
        self.assertIn("deep_planner", allowed)

    def test_disabled_disclosure_keeps_fast_planner_request_clean(self) -> None:
        registry = AgentSkillRegistry({})
        coordinator = AgentSkillProgressiveDisclosureCoordinator(
            None,
            AgentSkillDisclosureService(registry),
            enabled=False,
        )
        request = cognitive_work_request(
            sid="planner-disclosure",
            text="Will it rain?",
            language="en-US",
        )

        prepared, disclosure = asyncio.run(
            coordinator.prepare_agent_request(request, "fast_planner")
        )

        self.assertEqual(disclosure.agent_role, "fast_planner")
        self.assertEqual(disclosure.status, "no_skill")
        self.assertNotIn("agent_skill_disclosure", prepared.context)

    def test_evidence_reentry_reuses_fast_planner_role(self) -> None:
        allowed = set(AgentSkillProjectionName.__args__)
        result_stage_roles = [role for role in allowed if "result" in role]
        self.assertEqual(result_stage_roles, [])


if __name__ == "__main__":
    unittest.main()
