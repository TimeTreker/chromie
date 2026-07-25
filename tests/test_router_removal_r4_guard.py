from pathlib import Path
import subprocess
import sys

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
    assert not (ROOT / "router").exists()
    assert not (ROOT / "orchestrator/clients/router_client.py").exists()


def test_current_api_reference_uses_cognitive_core_boundary() -> None:
    text = (ROOT / "docs/API_REFERENCE.md").read_text(encoding="utf-8")
    assert "## Router HTTP API" not in text
    assert "/cognitive-core/interpret" in text
