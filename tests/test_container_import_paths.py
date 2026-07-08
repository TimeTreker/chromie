from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def test_agent_container_layout_imports_runtime_and_perception_helpers(tmp_path: Path) -> None:
    app_root = tmp_path / "agent_app"
    _copy_tree(ROOT / "agent" / "app", app_root / "app")
    _copy_tree(ROOT / "shared" / "chromie_contracts", app_root / "chromie_contracts")
    _copy_tree(ROOT / "shared" / "chromie_runtime", app_root / "chromie_runtime")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_root)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.clients.ollama_client; import app.agents.capability; print('ok')",
        ],
        cwd=app_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_router_container_layout_imports_llm_diagnostics(tmp_path: Path) -> None:
    app_root = tmp_path / "router_app"
    _copy_tree(ROOT / "router" / "app", app_root / "app")
    _copy_tree(ROOT / "shared" / "chromie_contracts", app_root / "chromie_contracts")
    _copy_tree(ROOT / "shared" / "chromie_runtime", app_root / "chromie_runtime")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_root)
    result = subprocess.run(
        [sys.executable, "-c", "import app.llm_router; print('ok')"],
        cwd=app_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_router_dockerfile_copies_runtime_package() -> None:
    dockerfile = (ROOT / "router" / "Dockerfile").read_text()
    assert "COPY shared/chromie_runtime ./chromie_runtime" in dockerfile
