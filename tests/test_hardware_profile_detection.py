from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HardwareProfileDetectionTests(unittest.TestCase):
    def _detect(self, **values: str) -> str:
        defaults = {
            "CHROMIE_IS_JETSON": "0",
            "CHROMIE_JETSON_MODEL": "",
            "CHROMIE_NVIDIA_GPU_NAME": "",
            "CHROMIE_NVIDIA_COMPUTE_CAP": "",
            "CHROMIE_NVIDIA_MEMORY_TOTAL_MIB": "0",
            "CHROMIE_MEM_TOTAL_MIB": "32768",
        }
        defaults.update(values)
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            for key, value in defaults.items():
                handle.write(f"{key}={value!r}\n")
            path = handle.name
        try:
            result = subprocess.run(
                [str(ROOT / "scripts" / "detect_hardware_profile.sh")],
                cwd=ROOT,
                env={**os.environ, "CHROMIE_SYSTEM_INFO_FILE": path},
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        finally:
            Path(path).unlink()

    def test_detects_rtx_4090_laptop_before_desktop_family(self) -> None:
        self.assertEqual(
            self._detect(
                CHROMIE_NVIDIA_GPU_NAME="NVIDIA GeForce RTX 4090 Laptop GPU",
                CHROMIE_NVIDIA_COMPUTE_CAP="8.9",
            ),
            "rtx4090_laptop",
        )

    def test_detects_rtx_5090(self) -> None:
        self.assertEqual(
            self._detect(
                CHROMIE_NVIDIA_GPU_NAME="NVIDIA GeForce RTX 5090",
                CHROMIE_NVIDIA_COMPUTE_CAP="12.0",
            ),
            "rtx5090",
        )

    def test_detects_rtx_5080_as_conservative_blackwell(self) -> None:
        self.assertEqual(
            self._detect(
                CHROMIE_NVIDIA_GPU_NAME="NVIDIA GeForce RTX 5080",
                CHROMIE_NVIDIA_COMPUTE_CAP="12.0",
                CHROMIE_NVIDIA_MEMORY_TOTAL_MIB="16304",
            ),
            "nvidia_blackwell",
        )

    def test_compute_capability_fallback_uses_gpu_memory(self) -> None:
        self.assertEqual(
            self._detect(
                CHROMIE_NVIDIA_COMPUTE_CAP="8.9",
                CHROMIE_NVIDIA_MEMORY_TOTAL_MIB="16384",
            ),
            "nvidia_ada",
        )

    def test_jetson_model_wins_over_shared_compute_capability(self) -> None:
        self.assertEqual(
            self._detect(
                CHROMIE_IS_JETSON="1",
                CHROMIE_JETSON_MODEL="NVIDIA Jetson AGX Thor Developer Kit",
                CHROMIE_NVIDIA_COMPUTE_CAP="12.0",
            ),
            "jetson_thor",
        )


if __name__ == "__main__":
    unittest.main()
