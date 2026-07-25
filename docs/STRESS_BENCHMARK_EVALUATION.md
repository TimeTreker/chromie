# Stress and Behavior-Distribution Evaluation

Status: implemented Benchmark Phase 6 foundation

## Purpose

Stress evaluation repeats existing semantic scenarios to expose drift that one
case cannot reveal: long-session context degradation, repeated decorative cues,
interruption failures, stale output under concurrency, provider-degradation
behavior, and cross-participant context leakage.

It does not tell Chromie how often to gesture. Workload IDs, sample indices,
turn counts, and observed rates are Benchmark-side conditions and measurements;
they are not Runtime policy or Prompt instructions.

## Maintained workload families

| Family | Main observation |
|---|---|
| Long session | semantic success, evidence, latency, auxiliary-rate drift |
| Repetition/cooldown | repeated cue and cooldown-contract violations |
| Interruption | stop/cancel priority and stale speech or auxiliary work |
| Concurrency | session isolation, resource conflicts, latency under load |
| Provider degradation | truthful fallback, partial evidence, recovery |
| Multi-user context | participant-bound preference and context isolation |

The multi-user workload uses synthetic participant IDs. It does not claim that
ASR currently performs speaker identification.

## Workload and adapter boundary

`benchmarks/manifests/stress_workloads.json` defines deterministic sampling,
session count, concurrency, evidence profile, selectors, descriptive stress
conditions, and observation dimensions. The manifest explicitly declares:

```text
runtime_policy_authority = false
metrics_are_observational = true
release_qualification = human_approval_required
```

The runner passes conditions to the explicit E2E benchmark adapter under
`run.metadata.stress`. A provider failure pattern is implemented by that test
adapter or fixture, never by production Runtime branches.

## Distribution metrics

The analyzer reports:

- sample, session, status, and evidence counts;
- primary-task success over observed verdicts;
- `none` and semantic auxiliary-decision distributions;
- behavior-label distributions;
- consecutive duplicate non-`none` cues within a session;
- explicit invariant and forbidden-behavior failures;
- cooldown, stillness, safety, execution-leakage, and participant-isolation
  violation families;
- observation and derived timing min/mean/p50/p95/max;
- first-half versus second-half auxiliary-rate drift per session;
- 95% Wilson intervals with explicit denominators.

These metrics are observations. There is no built-in target gesture rate,
quota, or model winner. Release gates may later reference reviewed distributions,
but they must remain outside production behavior policy and must retain sample
conditions and human approval.

## Model and revision comparison

Compatible reports can be compared when workload and evidence profile match.
The comparison exposes model, Prompt, MindProfile, provider, and code identities,
absolute metrics, and deltas from a chosen baseline. It deliberately sets
`ranking_or_winner_selected=false`.

## Commands

Validate manifests:

```bash
python -m benchmarks.stress.validate --check
```

Run a stress workload:

```bash
python -m benchmarks.stress.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --workload repetition_cooldown_pressure \
  --command "python scripts/my_e2e_adapter.py" \
  --run-id repetition-v1 \
  --output benchmarks/reports/repetition-v1.json
```

Compare two runs:

```bash
python -m benchmarks.stress.compare \
  --input benchmarks/reports/repetition-model-a.json \
  --input benchmarks/reports/repetition-model-b.json
```

Automatic reports always retain `release_qualified=false`.
