from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.app.tool_invocation import ToolCallOutcome
from scripts.provider_conformance import (
    CONFORMANCE_VERSION,
    TRACE_VERSION,
    NoMotionProviderStub,
    compare_evidence,
    compare_profiles,
    run_conformance,
    run_profiles,
)


class ProviderConformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_profiles_share_the_same_contract(self) -> None:
        payload = await run_profiles(
            ["sim", "hardware_shadow", "hardware_dry_run"]
        )

        self.assertEqual(payload["conformance_version"], CONFORMANCE_VERSION)
        self.assertEqual(payload["trace_version"], TRACE_VERSION)
        self.assertTrue(payload["passed"])
        self.assertTrue(payload["profile_parity"]["passed"])
        self.assertEqual(
            payload["profile_parity"]["compared_modes"],
            ["sim", "hardware_shadow", "hardware_dry_run"],
        )
        self.assertEqual(
            [profile["mode"] for profile in payload["profiles"]],
            ["sim", "hardware_shadow", "hardware_dry_run"],
        )
        for profile in payload["profiles"]:
            self.assertEqual(profile["trace_version"], TRACE_VERSION)
            self.assertEqual(
                [entry["tool_name"] for entry in profile["trace"]],
                [
                    "soridormi.skill.list",
                    "soridormi.skill.create_plan",
                    "soridormi.safety.monitor_motion",
                    "soridormi.skill.execute_plan",
                    "soridormi.motion.cancel",
                    "soridormi.robot.get_status",
                ],
            )
            self.assertTrue(
                next(
                    check
                    for check in profile["checks"]
                    if check["name"] == "safe idle"
                )["passed"]
            )
        shadow = payload["profiles"][1]
        self.assertTrue(
            next(
                check
                for check in shadow["checks"]
                if check["name"] == "shadow no-motion proof"
            )["passed"]
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
                    {"name": "dry-run no-motion proof", "passed": True},
                ],
            },
        ]

        parity = compare_profiles(reports)

        self.assertFalse(parity["passed"])
        self.assertEqual(len(parity["mismatches"]), 1)
        self.assertIn("execute call", parity["mismatches"][0])

    def test_profile_parity_reports_high_level_trace_drift(self) -> None:
        common_checks = [{"name": "catalog call", "passed": True}]
        reports = [
            {
                "mode": "sim",
                "checks": common_checks,
                "trace": [
                    {
                        "tool_name": "soridormi.skill.list",
                        "args": {},
                        "authorization": {"allow_side_effects": False},
                        "outcome": {"status": "success"},
                    }
                ],
            },
            {
                "mode": "hardware_shadow",
                "checks": common_checks,
                "trace": [
                    {
                        "tool_name": "soridormi.skill.list",
                        "args": {"unexpected": True},
                        "authorization": {"allow_side_effects": False},
                        "outcome": {"status": "success"},
                    }
                ],
            },
        ]

        parity = compare_profiles(reports)

        self.assertFalse(parity["passed"])
        self.assertEqual(
            parity["mismatches"],
            ["hardware_shadow high-level trace differs from sim"],
        )

    async def test_retained_profile_evidence_can_be_compared(self) -> None:
        payload = await run_profiles(
            ["sim", "hardware_shadow", "hardware_dry_run"]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for profile in payload["profiles"]:
                path = Path(temp_dir) / f"{profile['mode']}.json"
                path.write_text(
                    json.dumps(
                        {
                            "conformance_version": CONFORMANCE_VERSION,
                            "trace_version": TRACE_VERSION,
                            "passed": profile["passed"],
                            "profiles": [profile],
                        }
                    ),
                    encoding="utf-8",
                )
                paths.append(path)

            comparison = compare_evidence(paths)

        self.assertTrue(comparison["passed"])
        self.assertTrue(comparison["profile_parity"]["passed"])
        self.assertEqual(
            comparison["profile_parity"]["compared_modes"],
            ["sim", "hardware_shadow", "hardware_dry_run"],
        )

    def test_retained_evidence_rejects_duplicate_modes(self) -> None:
        payload = {
            "conformance_version": CONFORMANCE_VERSION,
            "trace_version": TRACE_VERSION,
            "passed": True,
            "profiles": [{"mode": "sim", "passed": True, "checks": []}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.json"
            second = Path(temp_dir) / "second.json"
            rendered = json.dumps(payload)
            first.write_text(rendered, encoding="utf-8")
            second.write_text(rendered, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate"):
                compare_evidence([first, second])


if __name__ == "__main__":
    unittest.main()
