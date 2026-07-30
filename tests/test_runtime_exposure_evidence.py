from __future__ import annotations

import unittest

from scripts.runtime_exposure_evidence import _published_ports, verify_reports


class RuntimeExposureEvidenceTests(unittest.TestCase):
    def test_resolved_compose_ports_are_parsed_with_loopback_hosts(self) -> None:
        payload = {
            "services": {
                "agent": {
                    "ports": [
                        {
                            "host_ip": "127.0.0.1",
                            "published": "8092",
                            "target": 8092,
                            "protocol": "tcp",
                        }
                    ]
                },
                "asr": {"ports": ["127.0.0.1:9001:9001"]},
            }
        }
        self.assertEqual(
            _published_ports(payload),
            [
                {
                    "service": "agent",
                    "host_ip": "127.0.0.1",
                    "published": 8092,
                    "target": 8092,
                    "protocol": "tcp",
                },
                {
                    "service": "asr",
                    "host_ip": "127.0.0.1",
                    "published": 9001,
                    "target": 9001,
                    "protocol": "tcp",
                },
            ],
        )

    def reports(self) -> tuple[dict, dict]:
        local = {
            "evidence_type": "local_runtime_exposure",
            "target_host": "192.0.2.10",
            "passed": True,
            "expected_ports": [5000, 8092, 9001, 11434],
            "source": {"revision": "revision-1", "dirty": False},
        }
        remote = {
            "evidence_type": "remote_runtime_exposure_probe",
            "target_host": "192.0.2.10",
            "passed": True,
            "expected_ports": [5000, 8092, 9001, 11434],
            "control_probe": {"reachable": True},
            "service_probes": [
                {"port": port, "reachable": False}
                for port in [5000, 8092, 9001, 11434]
            ],
        }
        return local, remote

    def test_matching_source_bound_reports_pass(self) -> None:
        local, remote = self.reports()
        report = verify_reports(local, remote, expected_revision="revision-1")
        self.assertTrue(report["passed"])
        self.assertFalse(report["release_qualified"])
        self.assertEqual(report["errors"], [])

    def test_remote_control_path_is_required(self) -> None:
        local, remote = self.reports()
        remote["control_probe"] = {"reachable": False}
        remote["passed"] = False
        report = verify_reports(local, remote, expected_revision="revision-1")
        self.assertFalse(report["passed"])
        self.assertTrue(any("control" in error for error in report["errors"]))

    def test_reachable_internal_service_fails(self) -> None:
        local, remote = self.reports()
        remote["service_probes"][1]["reachable"] = True
        remote["passed"] = False
        report = verify_reports(local, remote, expected_revision="revision-1")
        self.assertFalse(report["passed"])
        self.assertTrue(any("unreachable" in error for error in report["errors"]))

    def test_stale_revision_fails(self) -> None:
        local, remote = self.reports()
        report = verify_reports(local, remote, expected_revision="revision-2")
        self.assertFalse(report["passed"])
        self.assertTrue(any("revision" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
