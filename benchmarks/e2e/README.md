# End-to-End Benchmark Execution

The E2E runner reuses normalized semantic scenarios without changing their
behavior contract. An evidence profile controls only how the scenario is
executed and what evidence may support a claim.

Profiles deliberately distinguish replay, model-only, deployed text, virtual
audio, MuJoCo simulation, and supervised physical execution. A lower evidence
profile cannot report a simulator or physical execution claim. No automatic run
is final release qualification; profiles that require human approval remain
`human_review_required` even after complete evidence is collected.

## Adapter protocols

External command adapters receive one JSON request on stdin. Maintained first-party adapters use the same payload through one configured URL or Python callable and retain request/response artifacts directly:

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

Run the maintained deployed-text adapter boundary:

```bash
export CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE=qualification_harness.live_service:invoke

python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --adapter live_service_text \
  --dataset social_attention \
  --effective-model fast_planner=qwen3:4b \
  --mind-profile owner-profile-v1 \
  --social-style courteous \
  --social-attention-mode on \
  --style courteous \
  --mode on \
  --apply-lane chat \
  --apply-lane robot_action \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology cognitive-runtime-apply \
  --sample-count 1 \
  --run-id local-text-e2e \
  --output benchmarks/reports/local-text-e2e.json
```

The first-party adapter manifest stores only environment variable names. It does
not embed deployment endpoints, models, Prompts, backend identity, or behavior
policy. `--command` remains available for explicit external harnesses.

Physical profiles require explicit `--operator` metadata and always remain
subject to human approval.

## Social Attention lifecycle evidence

Qualification adapters may return `social_attention_lifecycle` inside the
observation. Proposal, Host materialization, Provider acceptance, Provider
completion, and safe idle are recorded as separate facts. The E2E runner reports
their distributions but does not choose an action or change Runtime policy.

Use `--cohort`, `--style`, `--mode`, `--language`, `--invariant`, and
`--forbidden-behavior` to select declared scenario metadata and contracts. These
selectors choose evaluation assets only; they are never forwarded as semantic
action rules.
