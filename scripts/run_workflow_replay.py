#!/usr/bin/env python3
"""Run frozen offline architecture episodes; no native model or hardware qualification."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.workflow_replay_support import run_case  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, default=ROOT/'benchmarks/integration/scenarios')
    parser.add_argument('--evidence-dir', type=Path, required=True, help='New, unused output directory')
    args = parser.parse_args()
    if sys.flags.optimize:
        parser.error('run without -O: executable assertions are required')
    paths = sorted(args.case_root.glob('workflow-*.json'))
    if not paths:
        parser.error('no workflow cases discovered')
    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    for name in list(logging.Logger.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.ERROR)
    rows = []
    for path in paths:
        case = json.loads(path.read_text())
        state = args.evidence_dir/path.stem
        state.mkdir()
        try:
            result = asyncio.run(run_case(case, state))
        except Exception as exc:
            result = {'case':case['id'], 'passed':False, 'error':f'{type(exc).__name__}: {exc}'}
        result['case_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        (state/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        rows.append({k:v for k,v in result.items() if k not in {'events','model_records'}})
        print(f"{case['id']}: {'PASS' if result['passed'] else 'FAIL'}")
    summary = {
        'evidence_level':'offline_architecture_replay', 'model_ability_evaluated':False,
        'physical_evidence':False, 'native_model_calls':0,
        'source_base':subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'source_files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for area in ('agent','orchestrator','shared') for p in sorted((ROOT/area).rglob('*.py'))},
        'cases':rows, 'passed':all(row['passed'] for row in rows),
    }
    (args.evidence_dir/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
