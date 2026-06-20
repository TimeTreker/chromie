from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

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


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_evidence_bundle(
    root: Path,
    payload: dict[str, object],
    *,
    calibration_content: str = '{"joint_zero": true}\n',
    provider_revision: str | None = None,
) -> Path:
    revisions = payload["revisions"]  # type: ignore[index]
    upstream_commit = provider_revision or revisions["soridormi"]  # type: ignore[index]
    provider_manifest = {
        "schema_version": 1,
        "metadata": {"upstream_commit": upstream_commit},
    }
    _write(
        root / "capabilities" / "soridormi.json",
        json.dumps(provider_manifest, sort_keys=True) + "\n",
    )
    _write(root / "evidence" / "estop-procedure.md", "press e-stop\n")
    _write(root / "evidence" / "estop-test.json", '{"stopped": true}\n')
    calibration = _write(root / "evidence" / "calibration.json", calibration_content)
    _write(root / "evidence" / "stop.md", "stop\n")
    _write(root / "evidence" / "recovery.md", "recover\n")
    _write(root / "evidence" / "comms-loss.md", "fail closed\n")
    return calibration


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

    def test_selected_candidate_evidence_files_can_be_verified(self) -> None:
        payload = selected_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calibration = _write_evidence_bundle(root, payload)
            payload["calibration_artifacts"][0]["sha256"] = _sha256(calibration)  # type: ignore[index]

            report = verify_candidate(
                payload,
                evidence_root=root,
                verify_evidence_files=True,
            )

        self.assertTrue(report["valid"])
        self.assertTrue(report["selected_for_pilot"])
        self.assertTrue(report["evidence_files_verified"])
        self.assertFalse(report["physical_motion_authorized"])

    def test_evidence_file_verification_rejects_missing_files(self) -> None:
        payload = selected_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            report = verify_candidate(
                payload,
                evidence_root=Path(temp_dir),
                verify_evidence_files=True,
            )

        self.assertFalse(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("file does not exist" in item for item in report["blockers"]))

    def test_evidence_file_verification_rejects_calibration_hash_mismatch(self) -> None:
        payload = selected_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_evidence_bundle(
                root,
                payload,
                calibration_content='{"joint_zero": false}\n',
            )

            report = verify_candidate(
                payload,
                evidence_root=root,
                verify_evidence_files=True,
            )

        self.assertFalse(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("sha256 does not match" in item for item in report["blockers"]))

    def test_evidence_file_verification_rejects_provider_revision_mismatch(self) -> None:
        payload = selected_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calibration = _write_evidence_bundle(root, payload, provider_revision="c" * 40)
            payload["calibration_artifacts"][0]["sha256"] = _sha256(calibration)  # type: ignore[index]

            report = verify_candidate(
                payload,
                evidence_root=root,
                verify_evidence_files=True,
            )

        self.assertFalse(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("upstream_commit" in item for item in report["blockers"]))

    def test_evidence_file_verification_rejects_paths_outside_root(self) -> None:
        payload = selected_candidate()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            calibration = _write_evidence_bundle(root, payload)
            payload["calibration_artifacts"][0]["sha256"] = _sha256(calibration)  # type: ignore[index]
            payload["procedures"]["stop"] = "../stop.md"  # type: ignore[index]

            report = verify_candidate(
                payload,
                evidence_root=root,
                verify_evidence_files=True,
            )

        self.assertFalse(report["valid"])
        self.assertFalse(report["selected_for_pilot"])
        self.assertTrue(any("evidence root" in item for item in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
