from __future__ import annotations

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
            scripts_dir.mkdir(parents=True)
            voice_logs.mkdir(parents=True)
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
                        printf 'fake compose output: %s\\n' "$*"
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


if __name__ == "__main__":
    unittest.main()
