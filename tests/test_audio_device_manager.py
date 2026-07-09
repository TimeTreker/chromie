from __future__ import annotations

import subprocess
import sys
import unittest


class AudioDeviceManagerTests(unittest.TestCase):
    def test_constructor_does_not_import_sounddevice(self) -> None:
        script = (
            "import sys; "
            "sys.modules['sounddevice'] = None; "
            "from orchestrator.audio_device_manager import AudioDeviceManager; "
            "AudioDeviceManager(); "
            "print('ok')"
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
