from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "scripts" / "check_local_runtime_exposure.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_local_runtime_exposure", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


class LocalRuntimeExposureTests(unittest.TestCase):
    def test_maintained_compose_sources_are_loopback_only(self) -> None:
        compose_files = sorted(ROOT.glob("docker-compose*.yml"))
        self.assertTrue(compose_files)
        self.assertEqual(checker.audit_compose_sources(compose_files), [])

    def test_resolved_loopback_publication_is_accepted(self) -> None:
        config = {
            "services": {
                "chromie-agent": {
                    "ports": [
                        {
                            "host_ip": "127.0.0.1",
                            "published": "8092",
                            "target": 8092,
                            "protocol": "tcp",
                        }
                    ]
                }
            }
        }
        self.assertEqual(checker.audit_resolved_compose(config), [])

    def test_resolved_ipv6_loopback_publication_is_accepted(self) -> None:
        config = {
            "services": {
                "local": {
                    "ports": [
                        {"host_ip": "::1", "published": "9001", "target": 9001}
                    ]
                }
            }
        }
        self.assertEqual(checker.audit_resolved_compose(config), [])

    def test_resolved_unspecified_host_is_rejected(self) -> None:
        config = {
            "services": {
                "chromie-agent": {
                    "ports": [{"published": "8092", "target": 8092}]
                }
            }
        }
        findings = checker.audit_resolved_compose(config)
        self.assertEqual(len(findings), 1)
        self.assertIn("unspecified/wildcard", findings[0])

    def test_resolved_wildcard_hosts_are_rejected(self) -> None:
        for host in ("0.0.0.0", "::", "[::]"):
            with self.subTest(host=host):
                config = {
                    "services": {
                        "chromie-agent": {
                            "ports": [
                                {
                                    "host_ip": host,
                                    "published": "8092",
                                    "target": 8092,
                                }
                            ]
                        }
                    }
                }
                findings = checker.audit_resolved_compose(config)
                self.assertEqual(len(findings), 1)
                self.assertIn(host, findings[0])

    def test_host_network_mode_is_rejected(self) -> None:
        findings = checker.audit_resolved_compose(
            {"services": {"chromie-agent": {"network_mode": "host"}}}
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("host networking", findings[0])

    def test_source_shorthand_without_host_is_rejected(self) -> None:
        source = """services:
  chromie-agent:
    ports:
      - \"8092:8092\"
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "docker-compose.yml"
            path.write_text(source, encoding="utf-8")
            findings = checker.audit_compose_source(path)
        self.assertEqual(len(findings), 1)
        self.assertIn("unspecified/wildcard", findings[0])

    def test_source_loopback_publication_is_accepted(self) -> None:
        source = """services:
  chromie-agent:
    ports:
      - \"127.0.0.1:8092:8092\"
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "docker-compose.yml"
            path.write_text(source, encoding="utf-8")
            findings = checker.audit_compose_source(path)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
