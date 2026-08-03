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

## Hybrid oracle evaluation

E2E evidence profiles own transport and evidence strength, not semantic truth.
Objective facts such as provider completion, correlation, playback lifecycle,
audio transcript similarity, safe idle, and exactly-once delivery are evaluated
deterministically. Intent understanding, relevance, naturalness, continuity,
and identity/style quality use the declared semantic-review rubric.

The same E2E run may therefore be mechanically complete while its scenario
status remains `review`. Package the retained result and artifacts with
`python -m benchmarks.review package`, then apply the reviewed JSON with
`python -m benchmarks.review apply`. See
[Hybrid oracle execution](CHROMIE_BENCHMARK_SUITE.md#73-hybrid-oracle-execution).

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

Run the maintained comprehensive collector from a clean committed checkout:

```bash
./scripts/qualification/run_comprehensive_test.sh \
  --strict-exit \
  --capture auto \
  --languages zh,en
```

`auto` prefers a speaker-monitor source; `acoustic` plays Chromie's generated
TTS through the physical speaker and records it through the microphone. Neither
mode asks the operator to speak. The collector runs the existing deterministic
and E2E entrypoints, retains partial failure evidence, captures all Compose logs
and bounded host/GPU/audio diagnostics, writes a check ledger and artifact hash
index, and creates one `chromie-comprehensive-<revision>-<run-id>.tar.gz`
archive. Semantic results remain pending review and deterministic failures remain
non-overridable. The live workflow cohort includes stable knowledge, session
recall, weather follow-up and correction, multi-part requests, long ordered
playback, and Chinese/English interaction. Use `--strict-exit` (or `--ci`) when a
failed, timed-out, incomplete, dirty, or required-unreviewed run must return
nonzero after the archive is safely written. Use `--dry-run` to inspect the plan
or `--collect-only` to package an already-running system without executing tests.

Optionally run independent semantic judges during the same comprehensive
collection. This is opt-in because bounded scenario evidence is sent to the
configured external providers:

```bash
./scripts/qualification/run_comprehensive_test.sh \
  --capture auto \
  --languages zh,en \
  --semantic-reviewers .chromie/semantic-reviewers.json
```

The reviewer configuration declares protocols, base URLs, model names, explicit
model-family identities, and API key environment-variable names. It contains no
keys. The collector invokes the
same `benchmarks.review judge` boundary used for standalone review, retains every
individual verdict and raw response, generates consensus when the configured
minimum succeeds, and packages failures without converting them into runtime
failures. See
[Independent multi-LLM adjudication](CHROMIE_BENCHMARK_SUITE.md#731-independent-multi-llm-adjudication)
and
[Big-change capability-degradation protocol](CHROMIE_BENCHMARK_SUITE.md#732-big-change-capability-degradation-protocol).

Replay a single retained closed-loop case after a comprehensive failure:

```bash
python -m benchmarks.regression replay \
  --archive ~/Downloads/chromie-comprehensive-REV-RUN.tar.gz \
  --scenario SCENARIO_ID \
  --output-dir .chromie/replay/SCENARIO_ID \
  --start-services
```

Use `python -m benchmarks.regression minimize` for a multi-turn failure. The
default oracle minimizes only a reproduced mechanical failure. Pass an explicit
`--oracle-command` for meaning-based failure; it must return a typed boolean and
its result is retained with every attempt.

The comprehensive collector also runs the repository-owned provider-client fault
manifest. For flakiness evidence, wrap the full collector rather than trusting a
single run:

```bash
python -m benchmarks.faults repeat \
  --count 5 \
  --timeout 7200 \
  --output-dir .chromie/repeats/comprehensive \
  -- ./scripts/qualification/run_comprehensive_test.sh --strict-exit
```

The command adapter contract is documented in
[`benchmarks/e2e/README.md`](../benchmarks/e2e/README.md).
