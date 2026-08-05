from __future__ import annotations

from types import SimpleNamespace
import unittest

from orchestrator.runtime.runtime_ready_greeting import (
    execute_default_runtime_ready_orientation,
)
from orchestrator.runtime.skill_runtime import SkillDefinition


class _OrientationRuntime:
    def __init__(self) -> None:
        self.requested: list[str] = []
        self.executed = []

    async def ensure_skill_definitions(self, skill_ids) -> None:
        self.requested.extend(list(skill_ids))

    def skill_definition(self, skill_id: str) -> SkillDefinition:
        return SkillDefinition(
            capability_id=skill_id,
            provider_id="soridormi.mcp",
            description="Untargeted startup attention.",
            input_schema={
                "type": "object",
                "properties": {
                    "style": {"type": "string", "enum": ["neutral"]},
                    "duration_s": {"type": "number"},
                    "hold_fraction": {"type": "number"},
                },
                "required": ["style", "duration_s", "hold_fraction"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"completed": {"type": "boolean"}},
                "required": ["completed"],
                "additionalProperties": False,
            },
            available=True,
            requires_confirmation=False,
            timeout_ms=3000,
            metadata={"behavior_domains": ["social_attention"]},
        )

    async def execute(self, response, *, session_id):
        self.executed.append((response, session_id))
        return SimpleNamespace(status="completed")


class RuntimeReadyOrientationTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_orientation_is_silent_untargeted_and_capability_grounded(self) -> None:
        runtime = _OrientationRuntime()

        result = await execute_default_runtime_ready_orientation(
            runtime,
            enable_soridormi_skills=True,
            social_attention_mode="on",
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["capability_id"], "soridormi.express_attention"
        )
        self.assertEqual(runtime.requested, ["soridormi.express_attention"])
        response, session_id = runtime.executed[0]
        self.assertIsNone(session_id)
        self.assertEqual(response.speech, [])
        self.assertEqual(len(response.skills), 1)
        request = response.skills[0]
        self.assertEqual(request.capability_id, "soridormi.express_attention")
        self.assertEqual(
            request.args,
            {"style": "neutral", "duration_s": 1.2, "hold_fraction": 0.2},
        )
        self.assertTrue(request.metadata["untargeted"])
        self.assertTrue(response.metadata["suppress_body_failure_speech"])

    async def test_startup_orientation_skips_when_social_attention_is_off(self) -> None:
        runtime = _OrientationRuntime()

        result = await execute_default_runtime_ready_orientation(
            runtime,
            enable_soridormi_skills=True,
            social_attention_mode="off",
        )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "social_attention_not_on")
        self.assertEqual(runtime.executed, [])


if __name__ == "__main__":
    unittest.main()
