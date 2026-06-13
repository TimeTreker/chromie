from __future__ import annotations

import subprocess
import sys
import unittest


class ClientImportTests(unittest.TestCase):
    def test_tts_client_import_does_not_require_aiohttp(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, types; "
                    "sys.modules['aiohttp'] = None; "
                    "sys.modules['websockets'] = types.ModuleType('websockets'); "
                    "from orchestrator.clients.tts_client import TTSClient; "
                    "assert TTSClient"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
