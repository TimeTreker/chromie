# Stress and Behavior-Distribution Benchmarks

This package repeats unchanged normalized scenarios under explicit workload and
E2E evidence profiles. It observes behavior drift; it does not add online
behavior policy.

The maintained workloads cover:

- long continuous sessions;
- repetition and cooldown pressure;
- stop, cancel, and interruption bursts;
- concurrent independent sessions and multi-goal work;
- provider degradation and recovery controlled by the benchmark adapter;
- synthetic multi-user context isolation.

Workload metadata is sent only to the explicit benchmark adapter under
`run.metadata.stress`. Production Runtime code must not branch on workload IDs,
sample indices, turn counts, or target rates. The manifest rejects policy-like
quota, forced-action, prompt-override, and runtime-rule fields.

## Validate workloads

```bash
python -m benchmarks.stress.validate --check
```

## Run a workload

```bash
python -m benchmarks.stress.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --workload long_session_social_attention \
  --command "python scripts/my_e2e_adapter.py" \
  --model local-model \
  --prompt-revision prompt-v1 \
  --mind-profile courteous \
  --run-id long-session-v1 \
  --output benchmarks/reports/long-session-v1.json
```

The adapter contract is the Phase 5 E2E adapter contract. For degradation
workloads, only the benchmark adapter may inject the declared failure pattern.
Chromie production services remain unaware of workload IDs.

## Compare compatible reports

```bash
python -m benchmarks.stress.compare \
  --input benchmarks/reports/model-a.json \
  --input benchmarks/reports/model-b.json \
  --output benchmarks/reports/model-comparison.json
```

Comparison requires the same workload and E2E evidence profile. It reports
absolute metrics and deltas from the first input. It does not select a winner or
automatically promote a model.

## Distribution report

Reports retain explicit sample/session counts, run conditions, evidence states,
status and primary-task rates, auxiliary and semantic behavior distributions,
consecutive duplicate-cue observations, violation families, latency p50/p95,
session drift, and 95% Wilson intervals for key proportions.

No gesture or `none` frequency is a built-in pass threshold. Zero-tolerance
architectural invariants continue to fail at the per-scenario E2E boundary; the
distribution analyzer only aggregates what those executions reported.
