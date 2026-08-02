from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_service_configuration_ownership import check


class ServiceConfigurationOwnershipTests(unittest.TestCase):
    def test_repository_services_use_typed_settings_owners(self) -> None:
        self.assertEqual(check(), [])

    def test_direct_environment_read_outside_owner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for service in ("asr", "tts"):
                (root / service).mkdir()
                (root / service / "settings.py").write_text(
                    "import os\nVALUE = os.getenv('VALUE')\n",
                    encoding="utf-8",
                )
                (root / service / "worker.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "agent" / "app").mkdir(parents=True)
            (root / "agent" / "app" / "settings.py").write_text(
                "import os\nVALUE = os.getenv('VALUE')\n", encoding="utf-8"
            )
            (root / "agent" / "app" / "worker.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            (root / "shared" / "chromie_runtime").mkdir(parents=True)
            (root / "shared" / "chromie_runtime" / "settings.py").write_text(
                "import os\nVALUE = os.getenv('VALUE')\n", encoding="utf-8"
            )
            (root / "shared" / "chromie_runtime" / "worker.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            (root / "tts" / "worker.py").write_text(
                "import os\nVALUE = os.getenv('TTS_PORT')\n",
                encoding="utf-8",
            )
            findings = check(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "tts/worker.py")


if __name__ == "__main__":
    unittest.main()
