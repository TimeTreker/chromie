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
from benchmarks.integration.model_replay import ModelReplay, load_case  # noqa: E402


def source_identity():
    paths = [p for area in ('agent', 'orchestrator', 'shared') for p in (ROOT/area).rglob('*.py')]
    paths += [ROOT/name for name in (
        'scripts/run_workflow_replay.py', 'benchmarks/integration/model_replay.py',
        'tests/workflow_replay_support.py', 'tests/capability_runtime_test_support.py',
        'tests/test_cognitive_runtime_pr7.py', 'benchmarks/datasets/fast_planner_daily_life/qualification.py',
    )]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-root', type=Path, default=ROOT/'benchmarks/integration/workflow_scenarios')
    parser.add_argument('--family', action='append', help='Focused diagnostic family; omit for an aggregate')
    parser.add_argument('--evidence-dir', type=Path, required=True, help='New, unused output directory')
    parser.add_argument('--candidate-role', choices=('gi', 'ga', 'fast', 'deep'))
    parser.add_argument('--candidate-url', help='Explicit Ollama-compatible service base URL; only the selected role is forwarded')
    parser.add_argument('--candidate-model')
    parser.add_argument('--candidate-timeout', type=float, default=60)
    args = parser.parse_args()
    selected = (args.candidate_role, args.candidate_url, args.candidate_model)
    if any(selected) and not all(selected):
        parser.error('candidate role, URL and model must be supplied together')
    candidate = {'role':args.candidate_role, 'url':args.candidate_url, 'model':args.candidate_model,
                 'timeout':args.candidate_timeout} if all(selected) else None
    if sys.flags.optimize:
        parser.error('run without -O: executable assertions are required')
    paths = sorted(args.case_root.glob('workflow-*.json'))
    if not paths:
        parser.error('no workflow cases discovered')
    manifest_path = args.case_root/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} != manifest['case_sha256']:
        parser.error('frozen case identity mismatch; review and freeze explicitly')
    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    for name in list(logging.Logger.manager.loggerDict):
        logging.getLogger(name).setLevel(logging.ERROR)
    source_files = source_identity()
    rows = []
    excluded = []
    for path in paths:
        case = load_case(path)
        if args.family and case.get('coverage_family',case['family']) not in args.family:
            continue
        if candidate and (any(step.get('fixture_kind', 'authored_reference') != 'authored_reference' for step in case['model_steps'])
                          or not any(step.get('role',step['name'].split('-')[0]) == candidate['role'] for step in case['model_steps'])):
            excluded.append(case['id'])
            continue
        replay = ModelReplay(case, candidate=candidate)
        state = args.evidence_dir/path.stem
        state.mkdir()
        try:
            result = asyncio.run(run_case(case, state, replay))
        except Exception as exc:
            result = {'case':case['id'], 'passed':False, 'error':f'{type(exc).__name__}: {exc}'}
            failure_path = state/'failure.json'
            if failure_path.exists():
                failure = json.loads(failure_path.read_text())
                result['boundary'] = failure.get('boundary')
                result['verdict'] = failure.get('verdict', 'unexpected_failure')
                result['contract_failure'] = failure.get('contract_failure')
        result['external_candidate_calls'] = replay.candidate_calls
        result.update(family=case.get('coverage_family',case['family']), split=case.get('split','prototype'))
        result.setdefault('verdict', 'pass' if result['passed'] else 'unexpected_failure')
        result['case_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        (state/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        rows.append({k:v for k,v in result.items() if k not in {'events','model_records'}})
        print(f"{case['id']}: {result['verdict']}", flush=True)
    summary = {
        'evidence_level':'offline_architecture_replay', 'model_ability_evaluated':False,
        'physical_evidence':False, 'native_model_calls':None if candidate else 0,
        'candidate':candidate, 'excluded_candidate_cases':excluded,
        'external_candidate_calls':sum(row['external_candidate_calls'] for row in rows),
        'source_base':subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'source_files':source_files, 'source_unchanged':source_identity() == source_files,
        'cases':rows, 'passed':bool(rows) and all(row['passed'] for row in rows),
        'cohort_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'aggregate':not bool(args.family or candidate),
        'counts':{verdict:sum(row['verdict']==verdict for row in rows) for verdict in sorted({row['verdict'] for row in rows})},
    }
    summary['passed'] = summary['passed'] and summary['source_unchanged']
    (args.evidence_dir/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
