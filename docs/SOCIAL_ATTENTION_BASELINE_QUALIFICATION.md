# Social Attention Baseline Qualification

## Purpose

This issue uses the completed Benchmark Suite to qualify the current Chromie
Social Attention behavior. It does not add behavior policy to Benchmark or move
semantic decisions into the Host Runtime.

> Thinking belongs to the LLM. Benchmark evaluates intelligence; it must not
> implement intelligence.

The LLM remains responsible for the optional Social Attention proposal. The Host
validates and materializes trusted work. The Provider accepts, rejects, and
executes embodiment-specific work. Benchmark only selects scenarios, records
identity and evidence, checks declared deterministic boundaries, and preserves
review artifacts.

## Implemented qualification foundation

The repository now provides:

- `benchmarks/manifests/social_attention_qualification_v1.json`, the versioned
  identity and hard-gate contract;
- explicit run provenance for effective model topology, MindProfile, Social
  Interaction Style, apply lanes, semantic authority, runtime topology, and
  sample count;
- first-party E2E adapter profiles that resolve one configured URL or Python
  callable without embedding deployment endpoints or behavior rules;
- cohort selection by Social Attention mode, style, language, cohort, invariant,
  and forbidden-behavior labels;
- explicit proposal, Host materialization, Provider acceptance/completion, and
  safe-idle lifecycle observations;
- a deterministic qualification report that fails closed on missing identity,
  missing lifecycle evidence, failed invariants, forbidden behavior, or missing
  scenario results.

The qualification report always retains:

```json
{
  "release_qualified": false,
  "human_approval_required": true
}
```

## Effective runtime identity

Qualification records the launcher-effective topology rather than assuming that
a static hardware profile is the active topology. A run should identify at
least:

- code and Prompt revision;
- summary model identity and per-component effective model topology;
- MindProfile and Social Interaction Style;
- semantic authority owner and effective apply lanes;
- runtime topology, provider revision, hardware profile, and sample count;
- evidence profile and operator identity where supervision is required.

For example, compact cognition may override a profile-declared Response Composer
model. The Benchmark report must record the resolved model actually used.

## First-party adapter boundary

`benchmarks/manifests/e2e_adapters.json` declares environment variable names for
model-only, deployed text, virtual-audio, MuJoCo, and supervised physical
harnesses. It contains no URL, port, backend identity, model choice, Prompt, or
scenario-specific behavior.

A configured callable receives the unchanged normalized scenario, run identity,
evidence profile, artifact directory, and partial-evidence path. It must return
the existing E2E adapter response contract. The adapter is not allowed to infer
an action from the user phrase or scenario ID.

Example model-only run:

```bash
export CHROMIE_BENCHMARK_LIVE_MODEL_CALLABLE=qualification_harness.live_model:invoke

python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_model_text \
  --adapter live_model_text \
  --dataset social_attention \
  --model qwen3:4b \
  --effective-model response_composer=qwen3:4b \
  --effective-model social_attention=qwen3:4b \
  --prompt-revision response-composer-prompt-v1 \
  --code-revision <commit-sha> \
  --mind-profile <approved-profile-revision> \
  --social-style mixed-by-scenario \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology launcher-effective-compact-cognition \
  --sample-count 1 \
  --run-id social-attention-live-model-baseline \
  --output benchmarks/reports/social-attention-live-model-baseline.json
```

Example deployed-service run adds the effective lanes, provider, and hardware:

```bash
export CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE=qualification_harness.live_service:invoke

python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --adapter live_service_text \
  --dataset social_attention \
  --apply-lane chat \
  --apply-lane robot_action \
  --provider-revision <provider-revision> \
  --hardware-profile rtx5090 \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology cognitive-runtime-apply \
  --code-revision <commit-sha> \
  --prompt-revision <prompt-revision> \
  --effective-model response_composer=<resolved-model> \
  --mind-profile <approved-profile-revision> \
  --social-style mixed-by-scenario \
  --output benchmarks/reports/social-attention-live-service.json
```

## Lifecycle evidence

An E2E observation may include:

```json
{
  "social_attention_lifecycle": {
    "proposal_state": "none",
    "materialization_state": "not_applicable",
    "provider_acceptance_state": "not_applicable",
    "provider_completion_state": "not_applicable",
    "safe_idle_state": "not_applicable",
    "semantic_class": null
  }
}
```

These fields record facts. They do not instruct the LLM to choose an action.
`proposed`, `accepted`, and `completed` remain distinct. Missing lifecycle
evidence fails the hard gates that require it rather than being inferred from
final speech or motion.

## Deterministic hard-gate report

After an E2E run, build the hard-gate report with:

```bash
python -m benchmarks.social_attention \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --report benchmarks/reports/social-attention-live-service.json \
  --output benchmarks/reports/social-attention-hard-gates.json
```

The maintained gates cover:

- off-mode proposal and execution isolation;
- report-only execution isolation;
- explicit stillness;
- stop and emergency priority;
- explicit action priority;
- Provider, unavailable-capability, rejection, and schema fail-closed behavior;
- primary-response and primary-work non-blocking behavior;
- backend and calibration neutrality.

The report checks only declared scenario invariants, reported forbidden behavior,
explicit lifecycle evidence, execution status, and run identity. It does not
score naturalness, empathy, personality quality, or model preference. Those
remain reviewed qualitative dimensions.

## Remaining evidence work

The next repository increment should connect the first-party adapter contract to
the maintained model-only and authoritative cognitive-runtime harnesses, then
retain the first 128-case baseline. After that, the same fixed scenarios and
identity contract can be used for model comparison, stress distribution,
selected MuJoCo evidence, earliest-error-boundary classification, and reviewed
regression promotion.
