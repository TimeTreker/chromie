from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_runtime_env.py"
MODEL_KEYS = (
    "AGENT_MODEL",
    "OLLAMA_MODEL",
    "ROUTER_MODEL",
    "ROUTER_REVIEW_MODEL",
    "AGENT_GOAL_ASSOCIATION_MODEL",
    "AGENT_FAST_PLANNER_MODEL",
    "AGENT_DEEP_PLANNER_MODEL",
    "AGENT_RESPONSE_COMPOSER_MODEL",
    "AGENT_TASK_CONTINUITY_MODEL",
    "AGENT_SOCIAL_ATTENTION_MODEL",
    "AGENT_RESPONSE_REVIEW_MODEL",
)


def parse_env(path: Path) -> dict[str, str]:
    command = [
        "bash",
        "-lc",
        f"set -a; source {path!s}; set +a; env -0",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    values: dict[str, str] = {}
    for item in result.stdout.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        values[key.decode()] = value.decode()
    return values


class AutomaticProfileEnvironmentTests(unittest.TestCase):
    def _minimal_root(self, directory: str) -> Path:
        root = Path(directory)
        (root / "scripts").mkdir(parents=True)
        (root / "env").mkdir()
        shutil.copy2(ROOT / ".env.common", root / ".env.common")
        shutil.copytree(ROOT / "env" / "profiles", root / "env" / "profiles")
        shutil.copytree(ROOT / "env" / "validation", root / "env" / "validation")
        shutil.copy2(ROOT / "scripts" / "detect_hardware_profile.sh", root / "scripts")
        return root

    def _system_info(self, path: Path, *, gpu: str, compute: str, memory: str, cuda_arch: str) -> None:
        path.write_text(
            "\n".join(
                (
                    "CHROMIE_OS_KERNEL='Linux test'",
                    "CHROMIE_CPU_ARCH=x86_64",
                    "CHROMIE_CPU_MODEL='Test CPU'",
                    "CHROMIE_CPU_CORES=24",
                    "CHROMIE_MEM_TOTAL_MIB=65536",
                    "CHROMIE_IS_JETSON=0",
                    "CHROMIE_JETSON_MODEL=''",
                    f"CHROMIE_NVIDIA_GPU_NAME={gpu!r}",
                    f"CHROMIE_NVIDIA_COMPUTE_CAP={compute}",
                    f"CHROMIE_NVIDIA_MEMORY_TOTAL_MIB={memory}",
                    f"CHROMIE_DETECTED_CUDA_ARCH={cuda_arch}",
                    "",
                )
            ),
            encoding="utf-8",
        )

    def _generate(
        self,
        root: Path,
        system_info: Path,
        *,
        check: bool = True,
        strict: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        # A stale inherited marker must not control selection.
        env["CHROMIE_HARDWARE_PROFILE"] = "rtx4090_laptop"
        if strict:
            env["CHROMIE_ENV_STRICT"] = "1"
        else:
            env.pop("CHROMIE_ENV_STRICT", None)
        return subprocess.run(
            [
                "python3",
                str(GENERATOR),
                "--root",
                str(root),
                "--system-info-file",
                str(system_info),
            ],
            cwd=root,
            env=env,
            check=check,
            capture_output=True,
            text=True,
        )

    def test_every_profile_owns_the_complete_model_plan(self) -> None:
        for profile in sorted((ROOT / "env" / "profiles").glob("*.env")):
            values = {}
            for raw in profile.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
            with self.subTest(profile=profile.name):
                self.assertEqual(set(MODEL_KEYS) - values.keys(), set())
                self.assertTrue(all(values[key] for key in MODEL_KEYS))

    def test_rtx5090_is_detected_and_generates_26b_quality_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            result = self._generate(root, system_info)
            values = parse_env(root / ".env.runtime")
            manifest = json.loads((root / ".chromie" / "runtime_profile.json").read_text())

        self.assertIn("Auto-detected hardware profile: rtx5090", result.stdout)
        self.assertEqual(values["CHROMIE_ACTIVE_PROFILE"], "rtx5090")
        self.assertEqual(values["AGENT_DEEP_PLANNER_MODEL"], "gemma4:26b")
        self.assertEqual(values["AGENT_RESPONSE_COMPOSER_MODEL"], "gemma4:26b")
        self.assertEqual(values["AGENT_FAST_PLANNER_MODEL"], "qwen3:4b")
        self.assertEqual(manifest["active_profile"], "rtx5090")
        self.assertEqual(manifest["fingerprint"], values["CHROMIE_RUNTIME_ENV_FINGERPRINT"])
        self.assertEqual(
            manifest["cognitive_budgets"]["CHROMIE_COGNITIVE_BUDGET_PROFILE"],
            "qualification",
        )
        self.assertEqual(
            manifest["cognitive_budgets"]["ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS"],
            "900000",
        )

    def test_rtx4090_laptop_is_detected_without_manual_profile_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 4090 Laptop GPU",
                compute="8.9",
                memory="16384",
                cuda_arch="89",
            )
            self._generate(root, system_info)
            values = parse_env(root / ".env.runtime")

        self.assertEqual(values["CHROMIE_ACTIVE_PROFILE"], "rtx4090_laptop")
        self.assertEqual(values["AGENT_DEEP_PLANNER_MODEL"], "gemma4:e2b")
        self.assertEqual(values["AGENT_RESPONSE_COMPOSER_MODEL"], "gemma4:e2b")

    def test_primary_gpu_profiles_use_long_qualification_budgets(self) -> None:
        required = {
            "CHROMIE_COGNITIVE_BUDGET_PROFILE": "qualification",
            "AGENT_TIMEOUT_MS": "240000",
            "ORCH_AGENT_TIMEOUT_MS": "300000",
            "AGENT_GOAL_ASSOCIATION_TIMEOUT_MS": "120000",
            "AGENT_FAST_PLANNER_TIMEOUT_MS": "120000",
            "AGENT_DEEP_PLANNER_TIMEOUT_MS": "120000",
            "AGENT_RESPONSE_COMPOSER_TIMEOUT_MS": "120000",
            "ORCH_GOAL_ASSOCIATION_TIMEOUT_MS": "150000",
            "ORCH_FAST_PLANNER_TIMEOUT_MS": "150000",
            "ORCH_DEEP_PLANNER_TIMEOUT_MS": "150000",
            "ORCH_RESPONSE_COMPOSER_TIMEOUT_MS": "150000",
            "ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS": "900000",
        }
        for profile_name in ("rtx5090", "rtx4090_laptop"):
            values: dict[str, str] = {}
            profile = ROOT / "env" / "profiles" / f"{profile_name}.env"
            for raw in profile.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key] = value
            with self.subTest(profile=profile_name):
                for key, expected in required.items():
                    self.assertEqual(values.get(key), expected, key)
                self.assertGreater(
                    int(values["ORCH_DEEP_PLANNER_TIMEOUT_MS"]),
                    int(values["AGENT_DEEP_PLANNER_TIMEOUT_MS"]),
                )
                self.assertGreater(
                    int(values["ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS"]),
                    sum(
                        int(values[key])
                        for key in (
                            "ORCH_GOAL_ASSOCIATION_TIMEOUT_MS",
                            "ORCH_FAST_PLANNER_TIMEOUT_MS",
                            "ORCH_DEEP_PLANNER_TIMEOUT_MS",
                            "ORCH_RESPONSE_COMPOSER_TIMEOUT_MS",
                        )
                    ),
                )

    def test_generated_runtime_env_has_one_assignment_per_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            self._generate(root, system_info)
            assignments = [
                line.split("=", 1)[0]
                for line in (root / ".env.runtime").read_text().splitlines()
                if line and not line.startswith("#") and "=" in line
            ]

        self.assertEqual(len(assignments), len(set(assignments)))

    def test_profile_owned_local_values_are_ignored_and_safe_local_values_still_win(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            (root / ".env.local").write_text(
                "CHROMIE_HARDWARE_PROFILE=rtx4090_laptop\n"
                "ROUTER_REVIEW_MODEL=stale-router-model\n"
                "AGENT_RESPONSE_REVIEW_MODEL=stale-agent-model\n"
                "LOG_LEVEL=DEBUG\n",
                encoding="utf-8",
            )
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            result = self._generate(root, system_info)
            values = parse_env(root / ".env.runtime")
            manifest = json.loads((root / ".chromie" / "runtime_profile.json").read_text())

        self.assertIn("[env][warning] Ignoring .env.local values", result.stderr)
        self.assertIn("AGENT_RESPONSE_REVIEW_MODEL", result.stderr)
        self.assertIn("ROUTER_REVIEW_MODEL", result.stderr)
        self.assertEqual(values["CHROMIE_ACTIVE_PROFILE"], "rtx5090")
        self.assertEqual(values["CHROMIE_HARDWARE_PROFILE"], "rtx5090")
        self.assertNotEqual(values["ROUTER_REVIEW_MODEL"], "stale-router-model")
        self.assertNotEqual(values["AGENT_RESPONSE_REVIEW_MODEL"], "stale-agent-model")
        self.assertEqual(values["LOG_LEVEL"], "DEBUG")
        self.assertEqual(
            manifest["ignored_local_overrides"],
            [
                "AGENT_RESPONSE_REVIEW_MODEL",
                "CHROMIE_HARDWARE_PROFILE",
                "ROUTER_REVIEW_MODEL",
            ],
        )
        self.assertFalse(manifest["strict_local_conflicts"])

    def test_strict_mode_rejects_profile_owned_local_values_before_writing_runtime_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            (root / ".env.local").write_text(
                "ROUTER_REVIEW_MODEL=stale-router-model\n",
                encoding="utf-8",
            )
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            result = self._generate(root, system_info, check=False, strict=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".env.local overrides hardware/validation-owned settings", result.stderr)
            self.assertFalse((root / ".env.runtime").exists())
            self.assertFalse((root / ".env").exists())

    def test_ignored_local_profile_values_do_not_change_runtime_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            local_path = root / ".env.local"
            local_path.write_text("ROUTER_REVIEW_MODEL=stale-one\n", encoding="utf-8")
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            self._generate(root, system_info)
            first = json.loads((root / ".chromie" / "runtime_profile.json").read_text())

            local_path.write_text("ROUTER_REVIEW_MODEL=stale-two\n", encoding="utf-8")
            self._generate(root, system_info)
            second = json.loads((root / ".chromie" / "runtime_profile.json").read_text())

        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["ignored_local_overrides"], ["ROUTER_REVIEW_MODEL"])
        self.assertEqual(second["ignored_local_overrides"], ["ROUTER_REVIEW_MODEL"])

    def test_profile_cuda_arch_must_match_detected_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._minimal_root(directory)
            profile = root / "env" / "profiles" / "rtx5090.env"
            profile.write_text(profile.read_text().replace("TTS_CUDA_ARCH=120", "TTS_CUDA_ARCH=89"))
            system_info = root / "system.env"
            self._system_info(
                system_info,
                gpu="NVIDIA GeForce RTX 5090",
                compute="12.0",
                memory="32607",
                cuda_arch="120",
            )
            result = self._generate(root, system_info, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hardware detection reported 120", result.stderr)

    def test_compose_passes_fast_and_deep_planner_profile_values(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        agent = compose.split("  chromie-agent:", 1)[1].split("\nnetworks:", 1)[0]
        for fragment in (
            "CHROMIE_ACTIVE_PROFILE: ${CHROMIE_ACTIVE_PROFILE:?",
            "CHROMIE_RUNTIME_ENV_FINGERPRINT: ${CHROMIE_RUNTIME_ENV_FINGERPRINT:?",
            "AGENT_FAST_PLANNER_MODEL: ${AGENT_FAST_PLANNER_MODEL:-qwen3:4b}",
            "AGENT_DEEP_PLANNER_MODEL: ${AGENT_DEEP_PLANNER_MODEL:-gemma4:e2b}",
            "AGENT_DEEP_PLANNER_TIMEOUT_MS: ${AGENT_DEEP_PLANNER_TIMEOUT_MS:-9000}",
            "AGENT_DEEP_PLANNER_NUM_CTX: ${AGENT_DEEP_PLANNER_NUM_CTX:-8192}",
        ):
            self.assertIn(fragment, agent)
        tts = compose.split("  chromie-tts:", 1)[1].split("  chromie-llm:", 1)[0]
        self.assertIn("CHROMIE_BUILD_PROFILE: ${CHROMIE_ACTIVE_PROFILE:?", tts)
        self.assertIn("TTS_CUDA_ARCH: ${TTS_CUDA_ARCH:?", tts)
        dockerfile = (ROOT / "tts" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('org.chromie.tts-cuda-arch="${TTS_CUDA_ARCH}"', dockerfile)
        self.assertIn('org.chromie.hardware-profile="${CHROMIE_BUILD_PROFILE}"', dockerfile)

    def test_supported_build_and_start_paths_regenerate_and_verify_profile(self) -> None:
        sources = {
            name: (ROOT / "scripts" / name).read_text(encoding="utf-8")
            for name in (
                "compose.sh",
                "start_services.sh",
                "start_chromie.sh",
                "start_orchestrator.sh",
                "deploy_chromie.sh",
                "warm_ollama.sh",
            )
        }
        for name, source in sources.items():
            with self.subTest(script=name):
                self.assertIn("build_runtime_env.sh", source)
        self.assertIn("verify_runtime_profile.sh", sources["start_services.sh"])
        self.assertIn('docker compose "${COMPOSE_ARGS[@]}" config --quiet', sources["start_services.sh"])
        self.assertNotIn("--hardware-profile", (ROOT / "scripts" / "start_voice_mujoco.sh").read_text())

    def test_startup_warms_complete_active_model_inventory(self) -> None:
        orchestrator = (ROOT / "scripts" / "start_orchestrator.sh").read_text()
        warm = (ROOT / "scripts" / "warm_ollama.sh").read_text()
        self.assertIn("list_runtime_ollama_models.sh", orchestrator)
        self.assertIn("list_runtime_ollama_models.sh", warm)
        self.assertNotIn('WARM_MODELS=("${AGENT_MODEL:-gemma4:e2b}")', orchestrator)


if __name__ == "__main__":
    unittest.main()
