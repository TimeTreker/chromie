from pathlib import Path
import subprocess, sys

def test_router_removal_guard() -> None:
    root=Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root/'scripts/check_router_removed.py')], cwd=root, check=True)
