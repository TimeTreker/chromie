from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


class ContainerImportPathTests(unittest.TestCase):
    def test_container_layouts_import_shared_runtime_packages(self) -> None:
        cases = (
            (
                "agent",
                ROOT / "agent" / "app",
                "import app.clients.ollama_client; "
                "import app.agents.capability; print('ok')",
            ),
            (
                "router",
                ROOT / "router" / "app",
                "import app.llm_router; print('ok')",
            ),
        )

        for service, source, command in cases:
            with self.subTest(service=service), tempfile.TemporaryDirectory() as temp_dir:
                app_root = Path(temp_dir) / f"{service}_app"
                _copy_tree(source, app_root / "app")
                _copy_tree(
                    ROOT / "shared" / "chromie_contracts",
                    app_root / "chromie_contracts",
                )
                _copy_tree(
                    ROOT / "shared" / "chromie_runtime",
                    app_root / "chromie_runtime",
                )

                env = os.environ.copy()
                env["PYTHONPATH"] = str(app_root)
                result = subprocess.run(
                    [sys.executable, "-c", command],
                    cwd=app_root,
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("ok", result.stdout)

    def test_router_dockerfile_copies_runtime_package(self) -> None:
        dockerfile = (ROOT / "router" / "Dockerfile").read_text()
        self.assertIn("COPY shared/chromie_runtime ./chromie_runtime", dockerfile)

    def test_semantic_authority_audit_runs_from_repository_root(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/semantic_authority_audit.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_declared_test_dependencies_cover_orchestrator_imports(self) -> None:
        requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")

        self.assertIn("numpy==2.3.5", requirements)
        self.assertIn("scipy==1.17.0", requirements)


if __name__ == "__main__":
    unittest.main()
