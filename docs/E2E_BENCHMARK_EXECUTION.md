# End-to-End Benchmark Execution and Evidence Profiles

Status: implemented Benchmark Phase 5 foundation

## Purpose

The E2E Benchmark layer executes one unchanged semantic scenario at different
evidence levels. The profile changes the transport, required evidence, and the
maximum claim a report may make; it does not change the scenario's acceptable
behavior region or add runtime behavior policy.

The maintained profiles are:

| Profile | Input | Embodiment | Maximum claim |
|---|---|---|---|
| `replay_text` | retained text observation | none | replayed contract only |
| `live_model_text` | text | none | configured model output |
| `live_service_text` | text | none | deployed service execution |
| `live_service_virtual_audio` | virtual audio | none | deployed audio pipeline execution |
| `simulated_mujoco` | text | simulated | MuJoCo provider execution |
| `physical_supervised` | physical audio | physical | supervised physical-provider execution |

A replay or model-only run cannot claim simulator or physical execution. A
simulator run cannot claim physical execution. Physical runs require explicit
operator metadata, hardware identity, provider evidence, safe-idle evidence, and
human approval.

## Evidence contract

Every E2E evidence item declares:

- `kind`;
- `source`;
- the scenario/run `correlation_id`;
- status: `observed`, `succeeded`, `complete`, `partial`, `failed`, or
  `unavailable`;
- optional artifact, detail, and relative timestamp.

The profile manifest declares the evidence kinds and timing markers required for
its claim. Missing, failed, unavailable, or cross-correlated evidence fails the
profile even when the semantic output looks reasonable.

## Partial evidence retention

Command adapters receive an artifact directory and a `partial_evidence.jsonl`
path. They append evidence as boundaries complete. The runner reads that file
after successful completion, timeout, non-zero exit, or malformed final output.
This prevents a late failure from erasing useful Gateway, Core, provider, or
safe-idle evidence.

Partial evidence does not turn a failed run into a pass. It improves diagnosis
and preserves the strongest claim actually supported.

## Timing observations

Profiles require markers appropriate to their input and execution level. The
runner derives:

- input-to-primary-response latency;
- input-to-primary-execution latency when applicable;
- input-to-auxiliary timing;
- auxiliary offset from speech and primary execution.

These are observations. The Benchmark does not impose a gesture schedule or
runtime behavior quota. Scenario invariants continue to define whether primary
work, stop, emergency handling, or user-requested stillness was violated.

## Qualification

Automated reports use one of:

- `not_eligible`;
- `evidence_incomplete`;
- `evidence_complete`;
- `human_review_required`.

The runner always emits `release_qualified=false`. Final product qualification
requires the declared evidence level plus human review; a lower profile is never
promoted into a stronger claim by aggregation.

## Commands

Validate profiles:

```bash
python -m benchmarks.e2e.validate --check
```

Run a deployed text cohort:

```bash
python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --command "python scripts/my_e2e_adapter.py" \
  --dataset social_attention \
  --run-id local-text-e2e \
  --output benchmarks/reports/local-text-e2e.json
```

Run a supervised physical case:

```bash
python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile physical_supervised \
  --command "python scripts/my_physical_e2e_adapter.py" \
  --operator operator-id \
  --id scenario-id
```

The command adapter contract is documented in
[`benchmarks/e2e/README.md`](../benchmarks/e2e/README.md).
