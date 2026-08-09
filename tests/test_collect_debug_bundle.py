from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = REPO_ROOT / "scripts" / "collect_debug_bundle.sh"


class CollectDebugBundleTest(unittest.TestCase):
    def test_collects_paired_launcher_and_soridormi_container_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "chromie"
            home = Path(temp_dir) / "home"
            bin_dir = Path(temp_dir) / "bin"
            scripts_dir = root / "scripts"
            voice_logs = root / ".chromie" / "voice-mujoco" / "logs"
            workflow_reports = (
                root
                / ".chromie"
                / "evidence"
                / "cognitive-runtime"
                / "session-workflows"
            )
            scripts_dir.mkdir(parents=True)
            voice_logs.mkdir(parents=True)
            workflow_reports.mkdir(parents=True)
            home.mkdir()
            bin_dir.mkdir()

            collector = scripts_dir / COLLECTOR.name
            shutil.copy2(COLLECTOR, collector)
            collector.chmod(0o755)
            (voice_logs / "soridormi.log").write_text(
                "paired Soridormi launcher marker\n", encoding="utf-8"
            )
            (voice_logs / "chromie.log").write_text(
                "paired Chromie launcher marker\n", encoding="utf-8"
            )
            (root / ".chromie" / "voice-mujoco" / "run.env").write_text(
                "SORIDORMI_REPO=/tmp/soridormi\nSORIDORMI_TOKEN=secret\n",
                encoding="utf-8",
            )
            (workflow_reports / "20260810-session1.json").write_text(
                '{"schema_version":1,"sid":"session1"}\n',
                encoding="utf-8",
            )
            (workflow_reports / "20260810-session1.md").write_text(
                "# Session workflow\n",
                encoding="utf-8",
            )

            fake_docker = bin_dir / "docker"
            fake_docker.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail

                    command_name="${1:-}"
                    shift || true
                    case "$command_name" in
                      compose)
                        if [[ "$*" == "logs chromie-agent --tail=5000" ]]; then
                          printf '%s\\n' 'chromie-agent | llm_call_evidence {"schema_version":1,"event":"chromie.llm_call_evidence","call_id":"llmcall_test_bundle","purpose":"goal_association","stage":"goal_association.primary","transport":"ollama.generate","status":"accepted","request":{"model":"gemma4:12b","system":"complete system prompt","prompt":"complete user prompt"},"response":{"raw_model_output":"{\\"decision\\":\\"continue\\"}"},"correlations":{"turn_id":"daily-case"}}'
                        else
                          printf 'fake compose output: %s\\n' "$*"
                        fi
                        ;;
                      ps)
                        if [[ " $* " == *" --filter name=soridormi "* ]]; then
                          printf '%s\\n' soridormi-runtime-mcp soridormi-simulator
                        else
                          printf 'container-id\\tchromie-agent\\tchromie-agent:test\\tUp\\tcom.docker.compose.project=chromie\\n'
                          printf 'soridormi-id\\tsoridormi-runtime-mcp\\tsoridormi:test\\tExited (1)\\tcom.docker.compose.project=soridormi\\n'
                        fi
                        ;;
                      inspect)
                        if [[ "${1:-}" == "--format" ]]; then
                          shift 2
                          container="${1:?container required}"
                          printf 'Name=/%s\\nStatus=exited\\nExitCode=1\\n' "$container"
                        else
                          exit 0
                        fi
                        ;;
                      logs)
                        container="${*: -1}"
                        printf 'fresh docker log marker for %s\\n' "$container"
                        ;;
                      port)
                        printf '8000/tcp -> 127.0.0.1:8000\\n'
                        ;;
                      *)
                        printf 'unsupported fake docker command: %s %s\\n' "$command_name" "$*" >&2
                        exit 2
                        ;;
                    esac
                    """
                ),
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
            subprocess.run(
                ["bash", str(collector)],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            archives = list((home / "Downloads").glob("chromie_debug_bundle_*.tar.gz"))
            self.assertEqual(len(archives), 1)
            with tarfile.open(archives[0], "r:gz") as archive:
                members = {member.name for member in archive.getmembers()}
                bundle_root = next(iter(members)).split("/", 1)[0]

                expected = {
                    f"{bundle_root}/soridormi-launcher.log",
                    f"{bundle_root}/chromie-launcher.log",
                    f"{bundle_root}/soridormi-runtime-mcp.docker.log",
                    f"{bundle_root}/soridormi-runtime-mcp.docker.inspect.txt",
                    f"{bundle_root}/soridormi-simulator.docker.log",
                    f"{bundle_root}/soridormi_docker_containers.txt",
                    f"{bundle_root}/voice_mujoco_run.env.redacted.txt",
                    f"{bundle_root}/llm_calls.jsonl",
                    f"{bundle_root}/session-workflows/20260810-session1.json",
                    f"{bundle_root}/session-workflows/20260810-session1.md",
                }
                self.assertTrue(expected.issubset(members))

                launcher = archive.extractfile(
                    f"{bundle_root}/soridormi-launcher.log"
                )
                self.assertIsNotNone(launcher)
                self.assertIn(
                    "paired Soridormi launcher marker",
                    launcher.read().decode("utf-8"),
                )

                docker_log = archive.extractfile(
                    f"{bundle_root}/soridormi-runtime-mcp.docker.log"
                )
                self.assertIsNotNone(docker_log)
                self.assertIn(
                    "fresh docker log marker for soridormi-runtime-mcp",
                    docker_log.read().decode("utf-8"),
                )

                redacted = archive.extractfile(
                    f"{bundle_root}/voice_mujoco_run.env.redacted.txt"
                )
                self.assertIsNotNone(redacted)
                redacted_text = redacted.read().decode("utf-8")
                self.assertIn("SORIDORMI_TOKEN=<redacted>", redacted_text)
                self.assertNotIn("SORIDORMI_TOKEN=secret", redacted_text)

                llm_calls = archive.extractfile(f"{bundle_root}/llm_calls.jsonl")
                self.assertIsNotNone(llm_calls)
                llm_record = json.loads(llm_calls.read().decode("utf-8").strip())
                self.assertEqual(llm_record["call_id"], "llmcall_test_bundle")
                self.assertEqual(
                    llm_record["request"]["system"], "complete system prompt"
                )
                self.assertEqual(
                    llm_record["response"]["raw_model_output"],
                    '{"decision":"continue"}',
                )
                self.assertIn("chromie-agent.log", llm_record["_bundle_sources"])


if __name__ == "__main__":
    unittest.main()
