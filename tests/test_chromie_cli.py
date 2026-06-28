from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.chromie_cli.__main__ import main
from tools.chromie_cli.output import CommandResult, ExitCode, write_result


class ChromieCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(args, stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_exits_successfully(self) -> None:
        code, stdout, stderr = self.run_cli("--help")
        self.assertEqual(code, int(ExitCode.OK))
        self.assertIn("Chromie developer usability tools.", stdout)
        self.assertIn("status", stdout)
        self.assertEqual(stderr, "")

    def test_unknown_command_fails_with_usage_code_and_clear_message(self) -> None:
        code, stdout, stderr = self.run_cli("unknown")
        self.assertEqual(code, int(ExitCode.USAGE))
        self.assertEqual(stdout, "")
        self.assertIn("invalid choice: 'unknown'", stderr)

    def test_status_reports_structured_mujoco_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(
                Path(directory),
                """
                ORCH_ENABLE_INTERACTION_RESPONSE=1
                ORCH_ENABLE_SORIDORMI_SKILLS=1
                SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
                ORCH_SORIDORMI_MANIFEST=capabilities/soridormi.json
                ORCH_ACTION_DRY_RUN=true
                AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=0
                AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=0
                ROUTER_TIMEOUT_MS=1500
                ORCH_ROUTER_TIMEOUT_MS=3000
                AGENT_TIMEOUT_MS=30000
                ORCH_AGENT_TIMEOUT_MS=40000
                """,
            )
            code, stdout, stderr = self.run_cli("--root", str(root), "--json", "status")
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(stdout)
        self.assertEqual(payload["details"]["mode"], "structured_mujoco")
        self.assertEqual(payload["details"]["soridormi_skills"], "enabled")
        self.assertEqual(stderr, "")

    def test_nested_commands_are_registered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, stderr = self.run_cli(
                "--root",
                directory,
                "trace",
                "view",
            )
        self.assertEqual(code, int(ExitCode.WARNING))
        self.assertIn("WARNING:", stdout)
        self.assertIn("no retained trace artifacts", stdout)
        self.assertEqual(stderr, "")

    def test_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, stderr = self.run_cli(
                "--root",
                directory,
                "--json",
                "trace",
                "view",
            )
        self.assertEqual(code, int(ExitCode.WARNING))
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["exit_code"], int(ExitCode.WARNING))
        self.assertEqual(payload["details"]["artifacts_matched"], 0)
        self.assertEqual(stderr, "")

    def test_trace_view_reads_session_jsonl_and_filters_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_dir = root / ".chromie" / "acceptance" / "voice" / "case-1"
            events_dir.mkdir(parents=True)
            (events_dir / "events.jsonl").write_text(
                "\n".join(
                    json.dumps(record)
                    for record in (
                        {
                            "timestamp_utc": "2026-06-27T00:00:00+00:00",
                            "sid": "sid-1",
                            "elapsed_ms": 0.0,
                            "event": "session_start",
                            "message": "session_start",
                        },
                        {
                            "timestamp_utc": "2026-06-27T00:00:01+00:00",
                            "sid": "sid-1",
                            "elapsed_ms": 100.0,
                            "event": "router_done",
                            "message": "router_done: route=chat confidence=0.91",
                        },
                        {
                            "timestamp_utc": "2026-06-27T00:00:02+00:00",
                            "sid": "sid-2",
                            "elapsed_ms": 0.0,
                            "event": "session_start",
                            "message": "session_start",
                        },
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "trace",
                "view",
                "--session",
                "sid-1",
            )
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(stdout)
        self.assertEqual(payload["details"]["matched_records"], 2)
        artifact = payload["details"]["artifacts"][0]
        self.assertEqual(artifact["kind"], "session_events_jsonl")
        self.assertEqual(artifact["identifiers"]["session"], ["sid-1", "sid-2"])
        messages = [record["message"] for record in artifact["records"]]
        self.assertIn("router_done: route=chat confidence=0.91", messages)
        self.assertEqual(stderr, "")

    def test_trace_view_summarizes_task_graph_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace_dir = root / ".chromie" / "acceptance" / "text-mujoco" / "case-1"
            trace_dir.mkdir(parents=True)
            (trace_dir / "trace.json").write_text(
                json.dumps(
                    {
                        "graph_id": "graph-1",
                        "status": "failed",
                        "summary": "Check task",
                        "outcome_summary": "TaskGraph failed: node submit blocked.",
                        "node_results": [
                            {
                                "node_id": "submit",
                                "tool": "soridormi.task.submit",
                                "status": "blocked",
                                "error": "blocked_subsystem",
                                "blocked_by": ["locomotion"],
                            }
                        ],
                        "events": [
                            {
                                "type": "node_blocked",
                                "node_id": "submit",
                                "tool": "soridormi.task.submit",
                                "message": "locomotion unavailable",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "trace",
                "view",
                "--graph",
                "graph-1",
            )
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(stdout)
        artifact = payload["details"]["artifacts"][0]
        self.assertEqual(artifact["kind"], "task_graph_trace")
        self.assertEqual(
            artifact["summary"]["outcome_summary"],
            "TaskGraph failed: node submit blocked.",
        )
        self.assertEqual(
            artifact["summary"]["node_results"][0]["tool"],
            "soridormi.task.submit",
        )
        self.assertEqual(stderr, "")

    def test_trace_view_warns_when_filters_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_dir = root / ".chromie" / "acceptance" / "voice" / "case-1"
            events_dir.mkdir(parents=True)
            (events_dir / "events.jsonl").write_text(
                json.dumps(
                    {
                        "sid": "sid-present",
                        "elapsed_ms": 0.0,
                        "event": "session_start",
                        "message": "session_start",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "trace",
                "view",
                "--session",
                "sid-missing",
            )
        self.assertEqual(code, int(ExitCode.WARNING))
        payload = json.loads(stdout)
        self.assertEqual(payload["details"]["artifacts_scanned"], 1)
        self.assertEqual(payload["details"]["artifacts_matched"], 0)
        self.assertIn("none matched", payload["message"])
        self.assertEqual(stderr, "")

    def test_config_show_uses_runtime_file_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(
                Path(directory),
                """
                CHROMIE_ACTIVE_PROFILE=test_profile
                ORCH_ENABLE_INTERACTION_RESPONSE=0
                ORCH_ENABLE_SORIDORMI_SKILLS=0
                ORCH_ACTION_DRY_RUN=true
                """,
                runtime=True,
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "config",
                "show",
            )
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(stdout)
        self.assertTrue(payload["details"]["runtime_file_used"])
        self.assertEqual(payload["details"]["active_profile"], "test_profile")
        self.assertEqual(payload["details"]["sources"], [".env.runtime"])
        self.assertEqual(stderr, "")

    def test_config_validate_fails_closed_on_unsafe_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(
                Path(directory),
                """
                ORCH_ENABLE_INTERACTION_RESPONSE=0
                ORCH_ENABLE_SORIDORMI_SKILLS=1
                AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=1
                AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=0
                ORCH_ACTION_DRY_RUN=false
                ROUTER_TIMEOUT_MS=1500
                ORCH_ROUTER_TIMEOUT_MS=3000
                AGENT_TIMEOUT_MS=30000
                ORCH_AGENT_TIMEOUT_MS=40000
                """,
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "config",
                "validate",
            )
        self.assertEqual(code, int(ExitCode.FAILURE))
        payload = json.loads(stdout)
        codes = {item["code"] for item in payload["details"]["diagnostics"]}
        self.assertIn("soridormi_requires_interaction", codes)
        self.assertIn("missing_soridormi_url", codes)
        self.assertIn("physical_execution_unsupported", codes)
        self.assertIn("legacy_action_dry_run_disabled", codes)
        self.assertEqual(stderr, "")

    def test_doctor_reports_classified_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(
                Path(directory),
                """
                CHROMIE_ACTIVE_PROFILE=test_profile
                ORCH_ENABLE_INTERACTION_RESPONSE=0
                ORCH_ENABLE_SORIDORMI_SKILLS=0
                ORCH_ACTION_DRY_RUN=true
                AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=0
                AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=0
                ROUTER_URL=
                AGENT_URL=
                ACTION_EXECUTOR_URL=
                ASR_URL=
                TTS_URL=
                LLM_URL=
                SORIDORMI_MCP_URL=
                ROUTER_TIMEOUT_MS=1500
                ORCH_ROUTER_TIMEOUT_MS=3000
                AGENT_TIMEOUT_MS=30000
                ORCH_AGENT_TIMEOUT_MS=40000
                """,
                runtime=True,
                compose_env=True,
            )
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "doctor",
            )
        self.assertIn(code, {int(ExitCode.OK), int(ExitCode.WARNING)})
        payload = json.loads(stdout)
        self.assertIn("diagnostics", payload["details"])
        codes = {item["code"] for item in payload["details"]["diagnostics"]}
        self.assertIn("manifest_json_valid", codes)
        self.assertIn("audio_input_unconfigured", codes)
        self.assertEqual(stderr, "")

    def test_capability_check_accepts_safe_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(Path(directory), "ORCH_ACTION_DRY_RUN=true\n")
            self.write_manifest(root, self.safe_manifest())
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "capability",
                "check",
            )
        self.assertEqual(code, int(ExitCode.OK))
        payload = json.loads(stdout)
        self.assertEqual(payload["details"]["summary"]["tool_count"], 1)
        codes = {item["code"] for item in payload["details"]["diagnostics"]}
        self.assertIn("tool_count", codes)
        self.assertEqual(stderr, "")

    def test_capability_check_rejects_duplicate_and_low_level_fields(self) -> None:
        manifest = self.safe_manifest()
        tool = manifest["agents"][0]["tools"][0]
        manifest["agents"][0]["tools"].append(dict(tool))
        manifest["agents"][0]["tools"][0]["input_schema"]["properties"][
            "joint_targets"
        ] = {"type": "array"}
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(Path(directory), "ORCH_ACTION_DRY_RUN=true\n")
            self.write_manifest(root, manifest)
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "capability",
                "check",
            )
        self.assertEqual(code, int(ExitCode.FAILURE))
        payload = json.loads(stdout)
        codes = {item["code"] for item in payload["details"]["diagnostics"]}
        self.assertIn("duplicate_tool_name", codes)
        self.assertIn("forbidden_low_level_field", codes)
        self.assertEqual(stderr, "")

    def test_evidence_bundle_discovers_metadata_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(
                Path(directory),
                """
                ORCH_ENABLE_INTERACTION_RESPONSE=0
                ORCH_ENABLE_SORIDORMI_SKILLS=0
                ORCH_ACTION_DRY_RUN=true
                """,
            )
            evidence_dir = root / ".chromie" / "acceptance" / "voice" / "case-1"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "acceptance_id": "case-1",
                        "status": "passed",
                        "runner": {"mode": "synthetic"},
                        "chromie": {"revision": "abc123"},
                    }
                ),
                encoding="utf-8",
            )
            output = root / ".chromie" / "evidence-bundles" / "bundle.json"
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "evidence",
                "bundle",
                "--output",
                str(output),
            )
            self.assertEqual(code, int(ExitCode.OK))
            payload = json.loads(stdout)
            self.assertEqual(payload["details"]["evidence_counts"]["A"], 1)
            self.assertEqual(
                payload["details"]["evidence_items"][0]["release_ready"],
                False,
            )
            self.assertTrue(output.exists())
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["evidence_items"][0]["acceptance_id"], "case-1")
            self.assertEqual(stderr, "")

    def test_evidence_bundle_warns_when_no_evidence_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.write_repo_env(Path(directory), "ORCH_ACTION_DRY_RUN=true\n")
            code, stdout, stderr = self.run_cli(
                "--root",
                str(root),
                "--json",
                "evidence",
                "bundle",
            )
        self.assertEqual(code, int(ExitCode.WARNING))
        payload = json.loads(stdout)
        self.assertEqual(payload["details"]["evidence_items"], [])
        self.assertIn("does not convert", payload["details"]["claim_note"])
        self.assertEqual(stderr, "")

    def test_output_helper_writes_sorted_json(self) -> None:
        stream = io.StringIO()
        write_result(
            CommandResult(
                status="warning",
                message="check me",
                details={"b": 2, "a": 1},
                exit_code=ExitCode.WARNING,
            ),
            stream=stream,
            json_output=True,
        )
        self.assertEqual(
            stream.getvalue(),
            '{"details": {"a": 1, "b": 2}, "exit_code": 1, '
            '"message": "check me", "status": "warning"}\n',
        )

    def write_repo_env(
        self,
        root: Path,
        env_text: str,
        *,
        runtime: bool = False,
        compose_env: bool = False,
    ) -> Path:
        (root / "env" / "profiles").mkdir(parents=True)
        (root / "capabilities").mkdir()
        (root / "capabilities" / "soridormi.json").write_text("{}", encoding="utf-8")
        (root / "env" / "profiles" / "default.env").write_text(
            "CHROMIE_HARDWARE_PROFILE=default\n",
            encoding="utf-8",
        )
        target = root / (".env.runtime" if runtime else ".env.common")
        target.write_text(
            "\n".join(line.strip() for line in env_text.strip().splitlines()) + "\n",
            encoding="utf-8",
        )
        if not runtime:
            (root / ".env.common").write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            (root / ".env.common").write_text("ORCH_ACTION_DRY_RUN=true\n", encoding="utf-8")
        if compose_env:
            (root / ".env").write_text(
                "# Generated by scripts/build_runtime_env.sh\n",
                encoding="utf-8",
            )
        return root

    def safe_manifest(self) -> dict:
        return {
            "schema_version": "0.1",
            "source": "soridormi",
            "metadata": {
                "upstream_repository": "https://github.com/TimeTreker/soridormi.git",
                "upstream_commit": "a" * 40,
            },
            "agents": [
                {
                    "agent_id": "soridormi.robot",
                    "tools": [
                        {
                            "name": "soridormi.robot.get_status",
                            "agent_id": "soridormi.robot",
                            "input_schema": {"type": "object", "properties": {}},
                            "output_schema": {
                                "type": "object",
                                "properties": {"safe_idle": {"type": "boolean"}},
                            },
                            "effects": ["read_only"],
                            "safety_class": "safe_read",
                        }
                    ],
                }
            ],
        }

    def write_manifest(self, root: Path, manifest: dict) -> None:
        (root / "capabilities" / "soridormi.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
