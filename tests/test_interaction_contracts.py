from __future__ import annotations

import unittest

from pydantic import ValidationError

from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillResult,
    SkillTrace,
)


class InteractionContractTests(unittest.TestCase):
    def test_interaction_response_round_trip_supports_speech_and_skill(self) -> None:
        response = InteractionResponse(
            speech=[{"text": "Hello, nice to see you.", "timing": "immediate"}],
            skills=[
                {
                    "request_id": "nod-1",
                    "skill_id": "soridormi.nod_yes",
                    "skill_version": "1.0.0",
                    "args": {"count": 2, "amplitude": "small"},
                    "timing": "parallel",
                }
            ],
        )

        restored = InteractionResponse.model_validate_json(response.model_dump_json())

        self.assertEqual(restored.speech[0].text, "Hello, nice to see you.")
        self.assertEqual(restored.skills[0].skill_id, "soridormi.nod_yes")

    def test_skill_result_and_trace_round_trip(self) -> None:
        result = SkillResult(
            request_id="nod-1",
            skill_id="soridormi.nod_yes",
            status="completed",
            provider_id="soridormi.mcp",
            output={"completed": True},
            trace_id="trace-1",
        )
        trace = SkillTrace(
            trace_id="trace-1",
            interaction_id="interaction-1",
            request_id="nod-1",
            skill_id="soridormi.nod_yes",
            provider_id="soridormi.mcp",
            status="completed",
            events=[{"type": "completed"}],
        )

        self.assertEqual(
            SkillResult.model_validate_json(result.model_dump_json()).status,
            "completed",
        )
        self.assertEqual(
            SkillTrace.model_validate_json(trace.model_dump_json()).events[0].type,
            "completed",
        )

    def test_nested_low_level_fields_are_rejected(self) -> None:
        forbidden_payloads = [
            {"joint_targets": [0.1]},
            {"nested": {"motor_commands": [{"position": 1.0}]}},
            {"policy": {"action_14d": [0.0] * 14}},
            {"trajectory": [{"positions_by_name": {"head_pitch": 0.2}}]},
        ]

        for payload in forbidden_payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValidationError, "forbidden low-level field"):
                    SkillRequest(skill_id="soridormi.nod_yes", args=payload)

    def test_unknown_contract_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            InteractionResponse.model_validate(
                {
                    "speech": [],
                    "skills": [],
                    "raw_motor_commands": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
