from __future__ import annotations

import unittest

from agent.app.tool_invocation import ToolCallOutcome
from scripts.provider_conformance import (
    CONFORMANCE_VERSION,
    NoMotionProviderStub,
    compare_profiles,
    run_conformance,
    run_profiles,
)


class ProviderConformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_sim_and_hardware_dry_run_share_the_same_contract(self) -> None:
        payload = await run_profiles(["sim", "hardware_dry_run"])

        self.assertEqual(payload["conformance_version"], CONFORMANCE_VERSION)
        self.assertTrue(payload["passed"])
        self.assertTrue(payload["profile_parity"]["passed"])
        self.assertEqual(
            payload["profile_parity"]["compared_modes"],
            ["sim", "hardware_dry_run"],
        )
        self.assertEqual(
            [profile["mode"] for profile in payload["profiles"]],
            ["sim", "hardware_dry_run"],
        )

    async def test_hardware_mode_is_refused_before_provider_calls(self) -> None:
        with self.assertRaisesRegex(ValueError, "restricted"):
            await run_conformance(
                NoMotionProviderStub("sim"),
                expected_mode="hardware",
            )

    async def test_low_level_provider_output_fails_conformance(self) -> None:
        class UnsafeStub(NoMotionProviderStub):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                outcome = await super().invoke(tool_name, args, context=context)
                if tool_name == "soridormi.skill.execute_plan":
                    return ToolCallOutcome.success(
                        {
                            **outcome.output,
                            "joint_targets": [0.1, 0.2],
                        }
                    )
                return outcome

        report = await run_conformance(
            UnsafeStub("hardware_dry_run"),
            expected_mode="hardware_dry_run",
        )

        self.assertFalse(report["passed"])
        failed = [check for check in report["checks"] if not check["passed"]]
        self.assertTrue(
            any(check["name"] == "execution abstraction" for check in failed)
        )

    def test_profile_parity_reports_shared_contract_drift(self) -> None:
        reports = [
            {
                "mode": "sim",
                "checks": [
                    {"name": "catalog call", "passed": True},
                    {"name": "execute call", "passed": True},
                ],
            },
            {
                "mode": "hardware_dry_run",
                "checks": [
                    {"name": "catalog call", "passed": True},
                    {"name": "execute call", "passed": False},
                    {"name": "no-motion proof", "passed": True},
                ],
            },
        ]

        parity = compare_profiles(reports)

        self.assertFalse(parity["passed"])
        self.assertEqual(len(parity["mismatches"]), 1)
        self.assertIn("execute call", parity["mismatches"][0])


if __name__ == "__main__":
    unittest.main()
