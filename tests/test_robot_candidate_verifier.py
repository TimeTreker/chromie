from __future__ import annotations

import copy
import unittest

from scripts.verify_robot_candidate import verify_candidate


def selected_candidate() -> dict[str, object]:
    sha40 = "a" * 40
    sha256 = "b" * 64
    return {
        "schema_version": 1,
        "candidate_id": "reference-robot-01",
        "candidate_state": "selected",
        "identity": {
            "vendor": "Example Robotics",
            "model": "ER-1",
            "serial_number": "ER1-0001",
            "controller": "Example Controller",
            "firmware": "1.2.3",
            "sensors": ["imu", "joint encoders"],
        },
        "host": {
            "os": "Ubuntu",
            "os_version": "24.04",
            "architecture": "arm64",
        },
        "network": {
            "topology": "isolated wired control LAN",
            "isolated_control_network": True,
        },
        "power_constraints": "manufacturer supply; supervised bench power",
        "revisions": {
            "chromie": sha40,
            "soridormi": sha40,
            "provider_manifest": "capabilities/soridormi.json",
            "provider_configuration_sha256": sha256,
        },
        "initial_low_risk_skill": {
            "skill_id": "nod_yes",
            "workspace": "marked 1m supervised test area",
            "max_speed": "10 percent of rated speed",
            "max_payload": "no payload",
            "supervision": "direct_operator",
            "abort_conditions": ["unexpected motion", "status loss"],
        },
        "unsupported": {
            "skills": ["walking"],
            "configurations": ["payload attachment"],
            "operating_conditions": ["unattended operation"],
        },
        "safety": {
            "physical_motion_enabled": False,
            "emergency_stop_independently_tested": True,
            "emergency_stop_procedure": "evidence/estop-procedure.md",
            "emergency_stop_evidence": "evidence/estop-test.json",
            "emergency_stop_tested_at": "2026-06-14T10:00:00Z",
            "emergency_stop_operator": "operator-a",
        },
        "calibration_artifacts": [
            {
                "name": "joint-zero-calibration",
                "path": "evidence/calibration.json",
                "sha256": sha256,
                "captured_at": "2026-06-14T09:00:00Z",
            }
        ],
        "procedures": {
            "stop": "evidence/stop.md",
            "recovery": "evidence/recovery.md",
            "communication_loss": "evidence/comms-loss.md",
            "observable_safe_idle": "standing=false, active_task=null",
        },
        "approvals": {
            "responsible_operator": "operator-a",
            "safety_reviewer": "reviewer-b",
            "reviewed_at": "2026-06-14T11:00:00Z",
        },
    }


class RobotCandidateVerifierTests(unittest.TestCase):
    def test_complete_selected_candidate_passes_without_authorizing_motion(self) -> None:
        report = verify_candidate(selected_candidate())

        self.assertTrue(report["valid"])
        self.assertTrue(report["ready_for_no_motion_review"])
        self.assertTrue(report["selected_for_pilot"])
        self.assertFalse(report["physical_motion_authorized"])

    def test_template_placeholder_and_missing_identity_block_review(self) -> None:
        payload = selected_candidate()
        payload["candidate_state"] = "draft"
        payload["candidate_id"] = "replace-me"
        payload["identity"]["serial_number"] = ""  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertTrue(report["valid"])
        self.assertFalse(report["ready_for_no_motion_review"])
        self.assertIn(
            "candidate_id must replace the template placeholder",
            report["blockers"],
        )

    def test_selected_claim_fails_when_emergency_stop_is_unverified(self) -> None:
        payload = selected_candidate()
        payload["safety"]["emergency_stop_independently_tested"] = False  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertFalse(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("independent emergency-stop" in item for item in report["blockers"]))

    def test_invalid_revisions_and_timestamps_are_blockers(self) -> None:
        payload = selected_candidate()
        payload["candidate_state"] = "draft"
        payload["revisions"]["chromie"] = "short"  # type: ignore[index]
        payload["approvals"]["reviewed_at"] = "yesterday"  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertTrue(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("40-character SHA" in item for item in report["blockers"]))
        self.assertTrue(any("ISO-8601" in item for item in report["blockers"]))

    def test_candidate_manifest_cannot_enable_physical_motion(self) -> None:
        payload = selected_candidate()
        payload["safety"]["physical_motion_enabled"] = True  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertFalse(report["valid"])
        self.assertFalse(report["physical_motion_authorized"])
        self.assertTrue(any("cannot authorize motion" in item for item in report["errors"]))

    def test_explicit_exclusions_and_abort_conditions_are_required(self) -> None:
        payload = copy.deepcopy(selected_candidate())
        payload["candidate_state"] = "draft"
        payload["unsupported"]["skills"] = []  # type: ignore[index]
        payload["initial_low_risk_skill"]["abort_conditions"] = []  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertFalse(report["ready_for_no_motion_review"])
        self.assertTrue(any("unsupported.skills" in item for item in report["blockers"]))
        self.assertTrue(any("abort_conditions" in item for item in report["blockers"]))

    def test_unknown_low_level_fields_are_rejected(self) -> None:
        payload = selected_candidate()
        payload["initial_low_risk_skill"]["joint_targets"] = [0.1, 0.2]  # type: ignore[index]

        report = verify_candidate(payload)

        self.assertFalse(report["valid"])
        self.assertTrue(
            any("joint_targets" in item for item in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
