# End-to-End Benchmark Execution

The E2E runner reuses normalized semantic scenarios without changing their
behavior contract. An evidence profile controls only how the scenario is
executed and what evidence may support a claim.

Profiles deliberately distinguish replay, model-only, deployed text, virtual
audio, MuJoCo simulation, and supervised physical execution. A lower evidence
profile cannot report a simulator or physical execution claim. No automatic run
is final release qualification; profiles that require human approval remain
`human_review_required` even after complete evidence is collected.

## Command adapter protocol

For command-backed profiles, the runner writes one JSON request to stdin:

```json
{
  "schema_version": 1,
  "scenario": {},
  "run": {"correlation_id": "run:scenario"},
  "evidence_profile": {},
  "artifact_dir": "/absolute/path",
  "partial_evidence_path": "/absolute/path/partial_evidence.jsonl"
}
```

The adapter should append one evidence object per line to
`partial_evidence_path` as boundaries complete. That file is retained even when
the adapter times out, exits non-zero, or returns invalid JSON.

A successful adapter returns:

```json
{
  "schema_version": 1,
  "scenario_id": "...",
  "correlation_id": "...",
  "execution_state": "completed",
  "execution_claims": ["deployed_service_execution"],
  "timing": {
    "input_received_ms": 0,
    "primary_response_started_ms": 350,
    "terminal_ms": 900
  },
  "evidence": [],
  "observation": {
    "primary_task_passed": true,
    "auxiliary_behavior": "none",
    "behaviors": [],
    "invariant_results": {}
  }
}
```

Evidence items require `kind`, `source`, `correlation_id`, and a status from
`observed`, `succeeded`, `complete`, `partial`, `failed`, or `unavailable`.

## Examples

Replay a retained E2E observation:

```bash
python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile replay_text \
  --replay-file /path/to/e2e-replay.json \
  --id sa.v1.greetings_farewells.friendly_morning
```

Run a deployed text adapter:

```bash
python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --command "python scripts/my_e2e_adapter.py" \
  --dataset social_attention \
  --run-id local-text-e2e \
  --output benchmarks/reports/local-text-e2e.json
```

Physical profiles require explicit `--operator` metadata and always remain
subject to human approval.
