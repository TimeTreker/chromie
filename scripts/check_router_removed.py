#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = [
    ROOT / "router",
    ROOT / "orchestrator/clients/router_client.py",
]
FORBIDDEN_TOKENS = (
    "chromie-" + "router",
    "Router" + "Client",
    "CHROMIE_BENCHMARK_" + "ROUTER_",
)
ALLOW = {
    ROOT / "scripts/check_router_removed.py",
    ROOT / "tests/test_router_removal_r2_core_path.py",
    ROOT / "tests/test_router_removal_r3_service_deleted.py",
    ROOT / "CHANGELOG.md",
    ROOT / "docs/COGNITIVE_GATEWAY.md",
    ROOT / "docs/ROADMAP.md",
}
errors=[]
for path in FORBIDDEN_PATHS:
    if path.exists(): errors.append(f"forbidden Router path exists: {path.relative_to(ROOT)}")
for path in ROOT.rglob('*'):
    if not path.is_file() or '.git' in path.parts or path in ALLOW or path.suffix in {'.pyc','.patch','.zip'}: continue
    try:text=path.read_text(encoding='utf-8')
    except (UnicodeDecodeError,OSError): continue
    for token in FORBIDDEN_TOKENS:
        if token in text: errors.append(f"{path.relative_to(ROOT)} contains {token}")
if errors:
    print('\n'.join(errors), file=sys.stderr); raise SystemExit(2)
print('Router removal guard passed')
