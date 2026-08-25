# Social Attention Baseline Qualification

## Purpose

This specialized track is coordinated by [Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

This target-evidence track uses the completed Benchmark Suite to qualify the current Chromie
Social Attention behavior. It does not add behavior policy to Benchmark or move
semantic decisions into the Host Runtime.

> Thinking belongs to the LLM. Benchmark evaluates intelligence; it must not
> implement intelligence.

The LLM remains responsible for the optional Social Attention proposal. The Host
validates and materializes trusted work. The Provider accepts, rejects, and
executes embodiment-specific work. Benchmark only selects scenarios, records
identity and evidence, checks declared deterministic boundaries, and preserves
review artifacts.

## Repository audit

### Benchmark CLI

The maintained CLI already separates scenario normalization, E2E execution,
evidence-profile validation, stress analysis, and Social Attention hard-gate
reporting. It can select by dataset, mode, style, cohort, language, invariant,
and forbidden-behavior label. First-party adapters receive the unchanged
normalized scenario and resolve only a configured URL or Python callable.

The audit found one qualification-orchestration defect: the original foundation
accepted one global E2E `run` while the 128-case dataset intentionally spans
three launcher-effective Social Attention modes and four owner-approved
interaction styles. A deployed Runtime does not become `off`, `report_only`, or
`on` because Benchmark metadata says so, and an owner-approved MindProfile is not
`mixed-by-scenario`. The qualification contract now accepts a bundle of repeated
`--report` inputs. Each report must be homogeneous for one effective mode and one
interaction style, and every result is checked against its scenario scope.
Missing, duplicate, unexpected, or scope-mismatched results fail closed.

### Default model topology

The RTX 5090 hardware profile declares `qwen3.5:9b` for Goal Interpretation,
Fast Planning, terminal Evidence re-entry, and Social Attention; Goal Association
and Deep Planning use `gemma4:12b`. It explicitly opts out of CosyVoice compact cognition and keeps
two Ollama models resident. Other profiles may retain the one-model compact
topology when their committed profile leaves that setting enabled. Qualification
therefore records launcher-effective component identities; a static
hardware-profile name is not sufficient evidence.

### Social Attention runtime entrances

The authoritative goal-driven path is:

```text
Cognitive Gateway
→ Goal-Driven Cognitive Core
→ anchored interaction-state event
→ background Social Attention planner
→ Host validation/materialization
→ Provider acceptance/completion
```

The goal-driven Runtime coalesces current-turn background events and supplies
primary-progress context, owner-approved Social Interaction Style, bounded
recent-decoration evidence, target evidence, and the reviewed live Capability
set. Candidate preparation removes any explicit primary Capability from the
model's allowed enum. The Host independently repeats duplicate-primary and
resource-conflict checks before the Trusted Capability Runtime.

Every Social Attention opportunity is attached to one concrete observable Main
Activity and retains that Activity ID. The Planner does not author a duplicate
decoration, `decision=none` remains valid, and a late proposal cannot become
standalone motion. The maintained live-service harness must prove that the goal-driven
runtime acquired the turn and that the background planner was the proposal
source.

### Evidence and execution profiles

The available Benchmark evidence profiles remain:

```text
replay_text
live_model_text
live_service_text
live_service_virtual_audio
simulated_mujoco
physical_supervised
```

Hardware profiles and validation overlays configure deployment resources and
models; they do not raise an evidence level. In particular, a run on an RTX 5090
is not live-service or MuJoCo evidence unless the selected E2E profile retains
its required correlated observations.

## Semantic implementation sequence

- Freeze the homogeneous mode/style run matrix and launcher-effective identity.
- Connect the maintained model-only and authoritative goal-driven live-service
  harnesses without adding scenario interpretation to Benchmark.
- Retain the complete 128-case current-default-model baseline and deterministic
  hard-gate bundle.
- Review courteous, neutral, reserved, and custom behavior distributions,
  including `none`, repetition, restraint, drift, and latency.
- Classify each important failure at its earliest cognitive, composition,
  materialization, Provider, or evidence boundary.
- Compare candidate models with identical scenarios, Prompt revision, MindProfile,
  runtime topology, and evidence profile; preserve human model selection.
- Retain selected live-service and MuJoCo evidence for execution-sensitive cohorts.
- Promote only reviewed recurring failures into regressions, audit documents and
  architecture, and close the Issue after human approval.

## Implemented qualification foundation

The repository now provides:

- `benchmarks/manifests/social_attention_qualification_v1.json`, the versioned
  identity and hard-gate contract;
- explicit run provenance for effective model topology, MindProfile, Social
  Interaction Style, semantic authority, runtime topology, provider/capability surface, and
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
- semantic authority owner and effective provider/capability surface;
- runtime topology, provider revision, hardware profile, and sample count;
- evidence profile and operator identity where supervision is required.

For example, compact cognition may override a profile-declared Fast Planner
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
  --effective-model fast_planner=qwen3:4b \
  --effective-model social_attention=qwen3:4b \
  --prompt-revision planner-activity-prompt-v1 \
  --code-revision <commit-sha> \
  --mind-profile <approved-profile-revision> \
  --social-style courteous \
  --social-attention-mode on \
  --style courteous \
  --mode on \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology launcher-effective-compact-cognition \
  --sample-count 1 \
  --run-id social-attention-live-model-on-courteous \
  --output benchmarks/reports/social-attention-live-model-on-courteous.json
```

Example deployed-service run adds provider and hardware identity:

```bash
export CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE=qualification_harness.live_service:invoke

python -m benchmarks.e2e.run \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --profile live_service_text \
  --adapter live_service_text \
  --dataset social_attention \
  --provider-revision <provider-revision> \
  --hardware-profile rtx5090 \
  --semantic-authority-owner goal_driven_cognitive_core \
  --runtime-topology cognitive-runtime-apply \
  --code-revision <commit-sha> \
  --prompt-revision <prompt-revision> \
  --effective-model fast_planner=<resolved-model> \
  --mind-profile <approved-profile-revision> \
  --social-style courteous \
  --social-attention-mode on \
  --style courteous \
  --mode on \
  --run-id social-attention-live-service-on-courteous \
  --output benchmarks/reports/social-attention-live-service-on-courteous.json
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

After all homogeneous mode/style E2E runs are retained, build one hard-gate bundle with repeated `--report`:

```bash
python -m benchmarks.social_attention \
  --normalized benchmarks/reports/normalized_scenarios.json \
  --report benchmarks/reports/social-attention-live-service-off-courteous.json \
  --report benchmarks/reports/social-attention-live-service-off-custom.json \
  --report benchmarks/reports/social-attention-live-service-off-neutral.json \
  --report benchmarks/reports/social-attention-live-service-off-reserved.json \
  --report benchmarks/reports/social-attention-live-service-on-courteous.json \
  --report benchmarks/reports/social-attention-live-service-on-custom.json \
  --report benchmarks/reports/social-attention-live-service-on-neutral.json \
  --report benchmarks/reports/social-attention-live-service-on-reserved.json \
  --report benchmarks/reports/social-attention-live-service-report-only-custom.json \
  --report benchmarks/reports/social-attention-live-service-report-only-neutral.json \
  --report benchmarks/reports/social-attention-live-service-report-only-reserved.json \
  --output benchmarks/reports/social-attention-hard-gates.json
```

The maintained gates cover:

- off-mode proposal and execution isolation;
- report-only execution isolation;
- explicit stillness;
- stop and emergency priority;
- explicit action priority;
- explicit-action preservation with optional different compatible decoration;
- duplicate-primary and resource-conflict suppression;
- Provider, unavailable-capability, rejection, and schema fail-closed behavior;
- primary-response and primary-work non-blocking behavior;
- backend and calibration neutrality.

The report checks only declared scenario invariants, reported forbidden behavior,
explicit lifecycle evidence, execution status, run identity, homogeneous mode/style
scope, and complete one-result-per-scenario coverage. It does not
score naturalness, empathy, personality quality, or model preference. Those
remain reviewed qualitative dimensions.

## Closure state and remaining evidence

The Social Attention behavior design and source implementation are closed for
this increment. Focused source tests cover background request identity, primary
Capability exclusion, optional compatible decoration, duplicate/resource
rejection, non-blocking/coalescing behavior, style, and evidence grounding.

Formal target qualification is not closed. Rebuilt working-tree planner probes
accepted greeting, exact blink, and playful-blink inputs; explicit primary blink
was absent from the auxiliary candidate enum and the model safely selected no
decoration. Retained full-path diagnostics then completed both exact blink and
“Blink twice and be cute” through Soridormi/MuJoCo. The latter retained one
`body_action` Goal, executed `soridormi.blink_eyes(count=2)` exactly once, and
returned standing/safe-idle. Intermediate failed runs exposed and closed upstream
Goal-segmentation, extra-candidate coverage, contradictory-decision, and
clarification-escape defects. These dirty-working-tree artifacts are diagnostic
evidence, not a source-bound baseline.

To close formal qualification, connect the first-party adapter contract to the
authoritative cognitive-runtime harness, commit/rebuild the exact source, retain
the 128-case homogeneous mode/style bundle, and complete fingerprint-bound human
review. The same fixed scenarios can then support model comparison, stress
distribution, selected MuJoCo evidence, earliest-error classification, and
reviewed regression promotion.
