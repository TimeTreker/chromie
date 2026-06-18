from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.provider_conformance import (
    CONFORMANCE_VERSION,
    TRACE_VERSION,
    run_profiles,
)
from scripts.provider_fault_matrix import MATRIX_VERSION, SCENARIOS
from scripts.verify_provider_readiness import manifest_preflight, verify_bundle


class ProviderReadinessVerifierTests(unittest.IsolatedAsyncioTestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _ready_manifest(self) -> dict[str, object]:
        scenario_ids = [scenario.scenario_id for scenario in SCENARIOS]

        def tool(name: str, *, llm_visible: bool = True) -> dict[str, object]:
            return {
                "name": name,
                "llm_visible": llm_visible,
                "availability": {
                    "modes": ["sim", "hardware_shadow", "hardware_dry_run"]
                },
            }

        tools = [
            *(tool(name) for name in sorted({
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
                "soridormi.motion.cancel",
                "soridormi.robot.get_status",
            })),
            tool("soridormi.testing.configure_fault", llm_visible=False),
            tool("soridormi.testing.clear_faults", llm_visible=False),
        ]
        return {
            "schema_version": "0.1",
            "agents": [{"tools": tools}],
            "metadata": {
                "upstream_commit": "soridormi-revision",
                "provider_readiness": {
                    "fault_injection": {
                        "configure_tool": "soridormi.testing.configure_fault",
                        "clear_tool": "soridormi.testing.clear_faults",
                        "supported_scenarios": scenario_ids,
                    }
                },
            },
        }

    def test_checked_in_manifest_passes_provider_readiness_preflight(self) -> None:
        report = manifest_preflight(Path("capabilities/soridormi.json"))

        self.assertTrue(report["passed"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(
            report["upstream_commit"],
            "2fa137ffd59ca7f5be347b09a1664ace0cbbf9c2",
        )

    def test_ready_manifest_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            self._write_json(path, self._ready_manifest())

            report = manifest_preflight(path)

        self.assertTrue(report["passed"])
        self.assertEqual(report["errors"], [])

    async def _write_valid_bundle(self, root: Path) -> None:
        profiles = await run_profiles(
            ["sim", "hardware_shadow", "hardware_dry_run"]
        )
        by_mode = {profile["mode"]: profile for profile in profiles["profiles"]}
        filenames = {
            "sim": "provider-sim.json",
            "hardware_shadow": "provider-shadow.json",
            "hardware_dry_run": "provider-dry-run.json",
        }
        retained = []
        for mode, filename in filenames.items():
            profile = {
                **by_mode[mode],
                "evidence_source": "live",
            }
            payload = {
                "conformance_version": CONFORMANCE_VERSION,
                "trace_version": TRACE_VERSION,
                "passed": True,
                "profiles": [profile],
            }
            retained.append(profile)
            self._write_json(root / filename, payload)
        self._write_json(
            root / "provider-parity.json",
            {
                "conformance_version": CONFORMANCE_VERSION,
                "trace_version": TRACE_VERSION,
                "passed": True,
                "profile_parity": {
                    "passed": True,
                    "compared_modes": list(filenames),
                    "mismatches": [],
                },
                "profiles": retained,
            },
        )
        self._write_json(
            root / "fault-matrix.json",
            {
                "matrix_version": MATRIX_VERSION,
                "evidence_source": "live",
                "passed": True,
                "results": [
                    {
                        "scenario_id": scenario.scenario_id,
                        "passed": True,
                        "safe_idle": True,
                        "threshold_violations": [],
                    }
                    for scenario in SCENARIOS
                ],
            },
        )
        self._write_json(
            root / "metadata.json",
            {
                "status": "passed",
                "target_name": "reference-linux",
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                "chromie": {"revision": "chromie-revision", "dirty": False},
                "soridormi": {
                    "revision": "soridormi-revision",
                    "dirty": False,
                },
            },
        )
        (root / "operator-notes.md").write_text(
            "Operator reviewed safe idle, cancellation, and recovery evidence.\n",
            encoding="utf-8",
        )

    async def test_complete_live_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            await self._write_valid_bundle(root)

            report = verify_bundle(root, require_clean=True)

        self.assertTrue(report["passed"])
        self.assertEqual(report["profile_count"], 3)
        self.assertEqual(report["required_scenario_count"], len(SCENARIOS))

    async def test_local_stub_and_unsafe_fault_result_fail_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            await self._write_valid_bundle(root)
            sim = json.loads((root / "provider-sim.json").read_text())
            sim["profiles"][0]["evidence_source"] = "local_stub"
            self._write_json(root / "provider-sim.json", sim)
            matrix = json.loads((root / "fault-matrix.json").read_text())
            matrix["results"][0]["safe_idle"] = False
            self._write_json(root / "fault-matrix.json", matrix)

            report = verify_bundle(root)

        self.assertFalse(report["passed"])
        self.assertIn(
            "provider-sim.json is not live provider evidence",
            report["errors"],
        )
        self.assertTrue(
            any("is not safe idle" in error for error in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
