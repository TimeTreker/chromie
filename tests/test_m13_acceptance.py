from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.m13_voice_acceptance import (
    FULL_CASE_ORDER,
    analyze_case,
    capability_probe_invocation,
    endpoint_for_container,
    parse_case_list,
    redact_env_file,
)
from scripts.verify_m13_evidence import REQUIRED_FILES, verify_bundle
import scripts.prepare_alpha_release as release_module


def event(name: str, message: str, sid: str = "sid-1") -> dict[str, object]:
    return {"event": name, "message": message, "sid": sid}


class M13AcceptanceTests(unittest.TestCase):
    def test_parse_all_cases_preserves_release_order(self) -> None:
        self.assertEqual(parse_case_list("all"), list(FULL_CASE_ORDER))

    def test_container_endpoint_translates_host_loopback(self) -> None:
        self.assertEqual(
            endpoint_for_container("http://127.0.0.1:8000/mcp"),
            "http://host.docker.internal:8000/mcp",
        )
        self.assertEqual(
            endpoint_for_container("http://localhost:8000/mcp?mode=sim"),
            "http://host.docker.internal:8000/mcp?mode=sim",
        )
        self.assertEqual(
            endpoint_for_container("http://soridormi:8000/mcp"),
            "http://soridormi:8000/mcp",
        )

    def test_container_probe_uses_agent_runtime_and_mounted_manifest(self) -> None:
        command, environment, endpoint = capability_probe_invocation(
            runtime="container",
            endpoint="http://127.0.0.1:8000/mcp",
        )
        self.assertIsNone(environment)
        self.assertEqual(endpoint, "http://host.docker.internal:8000/mcp")
        self.assertIn("chromie-agent", command)
        self.assertIn("SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp", command)
        self.assertEqual(command[-2:], ["--manifest", "/app/capabilities/soridormi.json"])

    def test_host_probe_remains_an_explicit_development_option(self) -> None:
        command, environment, endpoint = capability_probe_invocation(
            runtime="host",
            endpoint="http://127.0.0.1:8000/mcp",
        )
        self.assertEqual(command[0], __import__("sys").executable)
        self.assertEqual(endpoint, "http://127.0.0.1:8000/mcp")
        self.assertEqual(environment["PYTHONPATH"], "agent")
        self.assertEqual(
            environment["SORIDORMI_MCP_URL"],
            "http://127.0.0.1:8000/mcp",
        )

    def test_speech_only_checks_require_native_zero_skill_completion(self) -> None:
        checks = analyze_case(
            "speech-only",
            [
                event("asr_final", "asr_final: text='hello'"),
                event("router_done", "router_done: route=chat"),
                event("interaction_done", "interaction_done: speech=1 skills=0"),
                event("session_done", "session_done: played_tts=1"),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_followup_requires_two_utterances_in_same_conversation(self) -> None:
        checks = analyze_case(
            "follow-up",
            [
                event("asr_final", "asr_final: text='remember blue'", "sid-1"),
                event("router_done", "router_done: route=chat", "sid-1"),
                event("interaction_done", "interaction_done: speech=1 skills=0", "sid-1"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=0", "sid-1"),
                event("asr_final", "asr_final: text='what color'", "sid-2"),
                event("router_done", "router_done: route=chat", "sid-2"),
                event("interaction_done", "interaction_done: speech=1 skills=0", "sid-2"),
                event("context_snapshot", "context_snapshot: conversation_id=conv-1 history_turns=2", "sid-2"),
            ],
        )
        self.assertTrue(all(item.passed for item in checks))

    def test_redaction_removes_secret_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.env"
            target = Path(temp_dir) / "target.env"
            source.write_text("MODEL=test\nAPI_KEY=secret\nAUTHORIZATION_TOKEN=abc\n")
            redact_env_file(source, target)
            text = target.read_text()
            self.assertIn("MODEL=test", text)
            self.assertNotIn("secret", text)
            self.assertNotIn("abc", text)
            self.assertEqual(text.count("<redacted>"), 2)

    def test_complete_evidence_bundle_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            metadata = {
                "status": "passed",
                "event_count": 40,
                "acceptance_id": "test",
                "runner": {"dry_run": False},
                "chromie": {"revision": "abc123", "version": "0.1.0-alpha.1", "dirty": False},
                "soridormi_manifest": {"upstream_commit": "def456"},
                "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
            }
            cases = [
                {
                    "case_id": case_id,
                    "operator_verdict": "pass",
                    "event_count": 2,
                    "session_ids": [f"sid-{index}"],
                    "checks": [{"name": "check", "passed": True}],
                }
                for index, case_id in enumerate(FULL_CASE_ORDER)
            ]
            (root / "metadata.json").write_text(json.dumps(metadata))
            (root / "cases.json").write_text(json.dumps(cases))
            (root / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_SKILLS=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
            )
            report = verify_bundle(root, require_clean=True)
            self.assertTrue(report["passed"], report)


    def test_release_preview_creates_non_publishable_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            evidence = temp / "evidence"
            output = temp / "output"
            repo.mkdir()
            evidence.mkdir()

            (repo / "release").mkdir()
            (repo / "VERSION").write_text("0.1.0-alpha.1\n")
            (repo / "release" / "v0.1.0-alpha.1.md").write_text("# Notes\n")
            (repo / "release" / "compatibility.json").write_text(
                json.dumps(
                    {
                        "chromie": {"version": "0.1.0-alpha.1"},
                        "m13_closure_blockers": ["confirmation pending"],
                    }
                )
            )
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            for name in REQUIRED_FILES:
                (evidence / name).write_text("placeholder\n")
            (evidence / "metadata.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "event_count": 20,
                        "acceptance_id": "fixture",
                        "runner": {"dry_run": False},
                        "chromie": {
                            "revision": subprocess.check_output(
                                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                            ).strip(),
                            "version": "0.1.0-alpha.1",
                            "dirty": False,
                        },
                        "soridormi_manifest": {"upstream_commit": "soridormi-fixture"},
                        "soridormi_mcp_url": "http://127.0.0.1:8000/mcp",
                    }
                )
            )
            (evidence / "cases.json").write_text(
                json.dumps(
                    [
                        {
                            "case_id": case_id,
                            "operator_verdict": "pass",
                            "event_count": 2,
                            "session_ids": [f"sid-{index}"],
                            "checks": [{"name": "check", "passed": True}],
                        }
                        for index, case_id in enumerate(FULL_CASE_ORDER)
                    ]
                )
            )
            (evidence / "acceptance-overrides.env").write_text(
                "ORCH_ENABLE_INTERACTION_RESPONSE=1\n"
                "ORCH_ENABLE_SORIDORMI_SKILLS=1\n"
                "AGENT_INTERACTION_OUTPUT_MODE=native\n"
                "AGENT_NATIVE_INTERACTION_FALLBACK=0\n"
            )

            args = SimpleNamespace(
                evidence_dir=str(evidence),
                output_root=str(output),
                skip_tests=True,
                allow_dirty=False,
                require_clean_evidence=True,
                preview=True,
                overwrite=False,
            )
            with mock.patch.object(release_module, "ROOT", repo):
                bundle = release_module.prepare_release(args)

            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertFalse(manifest["publishable"])
            self.assertTrue((bundle / "chromie-0.1.0-alpha.1.tar.gz").is_file())
            self.assertTrue((bundle / "SHA256SUMS").is_file())

    def test_dry_run_evidence_cannot_close_m13(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in REQUIRED_FILES:
                (root / name).write_text("placeholder\n")
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "status": "dry-run",
                        "event_count": 0,
                        "runner": {"dry_run": True},
                        "chromie": {"revision": "abc", "dirty": False},
                        "soridormi_manifest": {"upstream_commit": "def"},
                        "soridormi_mcp_url": "http://example/mcp",
                    }
                )
            )
            (root / "cases.json").write_text("[]")
            report = verify_bundle(root)
            self.assertFalse(report["passed"])
            self.assertTrue(any("Dry-run" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
