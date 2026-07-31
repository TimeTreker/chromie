from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_router_removed import audit_removed_router

ROOT = Path(__file__).resolve().parents[1]


def test_router_architecture_guard_passes() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_router_removed.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_removed_router_service_and_client_are_absent() -> None:
    assert not (ROOT / "goal_interpretation").exists()
    assert not (ROOT / "orchestrator/clients/router_client.py").exists()


def test_current_api_reference_uses_cognitive_core_boundary() -> None:
    text = (ROOT / "docs/API_REFERENCE.md").read_text(encoding="utf-8")
    assert "## Router HTTP API" not in text
    assert "/cognitive-core/interpret" in text


class RouterRemovalGuardTests(unittest.TestCase):
    def test_ignored_bytecode_residue_is_not_maintained_router_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = root / "router" / "app" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "main.cpython-313.pyc").write_bytes(b"historical bytecode")

            self.assertEqual(audit_removed_router(root), [])

            source = root / "router" / "app" / "main.py"
            source.write_text("service = 'removed'\n", encoding="utf-8")
            self.assertIn(
                "removed Router path contains maintained content: router",
                audit_removed_router(root),
            )
