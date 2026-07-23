from __future__ import annotations

import unittest

from pydantic import ValidationError

from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillRequest,
    SkillResult,
    SkillTrace,
    output_schema_sha256,
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

    def test_low_level_field_name_variants_are_rejected(self) -> None:
        variants = (
            "motorCommand",
            "motor command",
            "motor-command",
            "motor.command",
            "RAWMotorCommands",
            "raw motor commands",
            "jointTargets",
            "positions-by-name",
            "actuator Ctrl",
            "torque/commands",
            "action14D",
        )

        for field_name in variants:
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(
                    ValidationError,
                    "forbidden low-level field",
                ):
                    SkillResult(
                        request_id="unsafe-result",
                        skill_id="soridormi.unsafe",
                        status="completed",
                        output={"nested": {field_name: [0.0]}},
                    )

    def test_output_schema_commitment_is_digest_only_and_strictly_validated(
        self,
    ) -> None:
        schema = {
            "type": "object",
            "properties": {"completed": {"type": "boolean"}},
            "additionalProperties": False,
        }
        digest = output_schema_sha256(schema)
        request = SkillRequest(
            skill_id="soridormi.nod_yes",
            committed_output_schema_sha256=digest,
        )

        restored = SkillRequest.model_validate_json(request.model_dump_json())

        self.assertEqual(restored.committed_output_schema_sha256, digest)
        self.assertEqual(len(digest), 64)
        self.assertNotIn("properties", request.model_dump_json())
        with self.assertRaises(ValidationError):
            SkillRequest(
                skill_id="soridormi.nod_yes",
                committed_output_schema_sha256="not-a-sha256",
            )

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
