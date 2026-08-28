# General Ability Test Reconstruction

This document is the reconstruction plan for Chromie's behavior and acceptance
framework. It exists because single visible failures can currently be fixed
without proving the broader robot ability that failed.

The governing interaction rules remain in
[Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md). The
evidence-level vocabulary remains in [Acceptance and Evidence](ACCEPTANCE.md).

## Decision

Chromie keeps the existing unit, contract, and behavior scenario tests, but
adds a claim-oriented general ability acceptance layer above them.

The new layer treats every reported utterance as a probe into a reusable ability
class, such as robust intent understanding, capability grounding, uncertainty
handling, composable planning, truthful embodied speech, lane discipline,
deterministic controls, or evidence coverage. A case may be narrow, but the
claim it supports must be broad and explicit.

The first implemented slice is:

- [`../scenarios/general_ability/`](../scenarios/general_ability/) as the live
  scenario library, with exactly one self-describing scenario per file under
  `must_pass`, `core`, or `challenge`; maintained Level-A files declare their
  own `general_ability.memberships`;
- [`../scripts/general_ability_acceptance.py`](../scripts/general_ability_acceptance.py)
  as the directory-discovery checker, Level A runner, and live-text runner;
- [`../tests/test_general_ability_acceptance.py`](../tests/test_general_ability_acceptance.py)
  as the Level A guard for the new framework;
- `python scripts/test_matrix.py general-ability` as the focused command group.

This is implemented and automatically verifiable at Level A. It is not target
validation and it does not prove microphone, speaker, simulator execution, or
physical hardware behavior.

The current live library contains 73 cases: 50 `must_pass`, 15 `core`, and 8
`challenge`. The first stage includes the retained 25-case regression cohort and
25 independently generated common-scene probes covering ordinary language,
supported body skills, composition, safety controls, uncertainty, evidence, and
conversation continuity. The generated files declare scenario-local authoring
provenance so later database extraction can distinguish them from migrated or
user-reported probes. This count is a reviewed cohort, not a permanent target.
The stage directory is the execution gate; `difficulty=easy|medium|hard` remains
independent metadata inside each file. A future cluster scheduler can assign
individual files or case ids to isolated service deployments without changing
the scenario contract. The local runner remains sequential because one live
Host owns the exclusive Orchestrator lock.

There is deliberately no central scenario index. File discovery, counts, stage
membership, ability membership, oracle policy, and review metadata come from
the directories and scenario files themselves. Adding or removing a scenario
therefore changes the executable cohort without a second registry edit.

## Removed And Demoted Standalone Tools

Stale standalone behavior tools were removed instead of kept as first-class
commands. Release-specific voice/device evidence tooling remains because it
serves separate Level C/D claims, not general behavior quality.

| Tool | Current status | Replacement for behavior claims |
|---|---|---|
| `scripts/scenario_runner.py` | Low-level deterministic fixture engine for authoring and focused debugging. | `scripts/general_ability_acceptance.py --mode level-a` |
| `scripts/interaction_text_scenario_suite.py` | Removed stale standalone live-text suite. | `scripts/general_ability_acceptance.py --mode live-text` |
| `scripts/interaction_text_skill_sweep.py` | Removed stale standalone live skill sweep; too easy to confuse prompt coverage with ability coverage. | `scripts/general_ability_acceptance.py --mode live-text` |
| `scripts/interaction_text_acceptance.py` | Removed fixture-like named-skill smoke that could be mistaken for acceptance evidence. | General ability live text probes or `interaction_text_mujoco_check.py` for retained simulator evidence |

Voice and target evidence tools such as `scripts/voice_acceptance.py`,
`scripts/verify_voice_evidence.py`, provider conformance, and provider fault
matrix tooling are not general behavior-quality gates. Keep them only for the
specific Level C/D evidence claims they document.

## Problem To Fix

The old failure mode was:

1. A user reports one awkward or wrong conversation.
2. A patch changes a prompt, fallback sentence, or fixture for that visible
   symptom.
3. A local test passes.
4. The same kind of failure returns in a slightly different conversation.

The reconstructed framework must prevent that by making every test answer:

- Which general ability is protected?
- Which user-visible boundary is exercised?
- Which evidence level is being claimed?
- Would this have caught the original failure for the same reason?
- If it fails, which root-cause boundary should be inspected first?

## Evidence Layers

### Layer 1 - Unit And Contract Tests

Purpose: keep schemas, validators, deterministic controls, prompt builders, and
component policies stable.

Evidence level: Level A.

These tests are still necessary, but they are not sufficient to claim a live
robot conversation is fixed.

### Layer 2 - File-Backed Behavior Scenarios

Purpose: deterministic black-box or integrated checks for Goal Interpreter,
InteractionRuntime, adapter, and multi-turn dialogue behavior.

Evidence level: Level A.

These scenarios should be representative probes, not phrase-specific trophies.
Each file declares the broader abilities it protects.

### Layer 3 - General Ability Acceptance

Purpose: run and report behavior evidence by ability class, not by isolated
test file.

Primary command:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class deterministic_safety_controls
python scripts/general_ability_acceptance.py --mode live-text \
  --stage must_pass
```

The output must include the evidence level and claim scope. Level A output
means deterministic regression evidence only.

The ordered live-text policy is stage-complete, then gate. All selected
`must_pass` cases run even if an earlier case hard-fails, so the report shows the
whole basic-regression shape. After the stage ends, any hard deterministic
failure blocks `core` and `challenge`. If must-pass hard gates succeed, the
runner proceeds in order. A focused `--only-case` or explicit `--stage` run is a
diagnostic subset and does not prove that skipped prerequisite stages passed.

Every live-text file declares a `hybrid` oracle. Exact response text is not the
truth value: each case describes primary semantic outcomes, acceptable
variation, forbidden semantic outcomes, and reviewer dimensions. Deterministic
safety, authorization, capability, execution, provenance, timing, and
LLM-integrity evidence remains non-overridable. The run emits a standard
semantic-review bundle; pending semantic review keeps
`qualification_complete=false` even when deterministic evidence collection
succeeds.

### Layer 4 - Live Text Preview And Execution

Purpose: feed natural text into the same Goal Interpretation and downstream Agent boundary used after
ASR, with live Soridormi status preflight and optional MuJoCo execution.

Preview command:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

Focused goal-driven daily-life multi-goal preview:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

Execution command for supervised simulator runs:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --ability-class multi_goal_daily_life \
  --goal-driven-runtime apply \
  --execute \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

Preview mode is not execution evidence. Execution mode is simulator evidence
only when Soridormi is in `sim` mode and the retained summary shows successful
Trusted Capability Runtime completion and safe idle.
The declared `--soridormi-repo` is diagnostic provenance only; it does not bind
the MCP endpoint to that checkout.

### Layer 5 - Voice And Target Evidence

Purpose: prove the real microphone, ASR, TTS, playback, interruption, simulator,
or hardware path that a release claim depends on.

Evidence level: Level D for target device claims.

Synthetic and virtual-microphone modes remain useful regression evidence, but
supervised physical microphone/speaker evidence is required before claiming
human voice-device support.

## Ability Classes

The discovered scenario metadata tracks these classes:

| Ability class | Protected behavior |
|---|---|
| `robust_intent_understanding` | Preserve human meaning across phrasing, ASR-like noise, short fragments, Chinese/English, and context. |
| `stable_capability_grounding` | Ground exact supported requests to live catalog abilities without fragile timeout-dependent repair. |
| `natural_uncertainty_handling` | Ask about the real ambiguity instead of leaking generic missing-skill or internal fallback speech. |
| `composable_action_planning` | Preserve ordered high-level skills for supported multi-step body requests. |
| `multi_goal_daily_life` | Keep independent execute, respond, clarify, and unavailable outcomes separate while preserving exact step-to-goal ownership in ordinary daily requests. |
| `truthful_embodied_speech` | Speak only what proposal, confirmation, execution, cancellation, or provider evidence supports. |
| `tool_and_conversation_lane_discipline` | Keep conversation, memory, tools, and body actions in their proper lanes. |
| `deterministic_safety_controls` | Keep stop, cancel, emergency, silence, and unusable-audio paths deterministic. |
| `evidence_coverage_and_claim_discipline` | Prevent weak tests from being reported as stronger evidence than they are. |

New user-reported failures should either map to one of these classes or justify
adding a new class in the scenario metadata and governing interaction contract.

## Failure Report Rule

When a general ability acceptance case fails, the fix is not allowed to start
with a phrase patch. The failure report must name:

- observed user or ASR text;
- expected contract;
- earliest wrong component;
- fix class;
- regression boundary;
- evidence level;
- general ability protected.

The runner records `root_cause_report_required=true` when an ability-class run
fails. That flag is a process gate: someone must inspect the earliest wrong
boundary before claiming the failure is fixed.

## Reconstruction Plan

### PR 0 - Scenario Library And Runner

State: implemented in this patch.

Scope:

- create the self-describing one-file live scenario library;
- add directory discovery and per-file metadata validation;
- add Level A ability-class execution;
- add live text preview/execution support using the existing text-to-MuJoCo
  boundary;
- finish a stage before applying its gate, and block later stages after a
  must-pass hard failure;
- package natural-language outcomes for the existing hybrid semantic-review
  workflow instead of using exact response-string truth;
- add focused tests and test-matrix wiring;
- document claim rules.

Exit criteria:

- `python scripts/general_ability_acceptance.py --mode check --no-write` passes;
- `python scripts/general_ability_acceptance.py --mode level-a --ability-class deterministic_safety_controls --no-write` passes;
- focused unit tests for the runner pass;
- docs checker passes.

### PR 1 - Better Live Runner Diagnostics

Scope:

- make broad live sweeps print per-case progress before and after each run;
- enforce per-case wall-clock timeouts;
- write partial summaries when a case hangs or a service fails;
- expand exception reporting for grouped async failures;
- surface Goal Interpreter, Agent, review-model, and provider timeout causes separately.

Exit criteria:

- live text failures produce a retained summary without hanging the suite;
- failure summaries identify the likely first boundary instead of only showing
  `ExceptionGroup` or generic connection errors.

### PR 2 - Root-Cause Classifier

Scope:

- attach a first-pass failure classification to retained summaries:
  ASR/audio, Goal Interpretation/Responsibility, Goal Association, Planner contract,
  Prompt wording, Orchestrator policy, Trusted Capability Runtime/provider, or Test evidence;
- include Goal, Plan, response, speech, capability/skill, provider, and Evidence facts
  needed to inspect the classification;
- keep the classifier advisory and auditable.

Exit criteria:

- a failed live text case points to an inspectable earliest boundary;
- coding-agent final reports can cite the retained summary instead of guessing.

### PR 3 - Broader Live Ability Sampling

Scope:

- add more live text probes for each ability class;
- add bilingual, typo/noisy-ASR, follow-up, tool, unsupported body, compound
  body, stop/cancel, and truthful speech samples;
- keep live samples representative rather than overfitting one reported phrase.

Exit criteria:

- every class has at least one live text preview probe when live services are
  available;
- simulator execution samples exist for the body-action classes only.

### PR 4 - Voice Evidence Integration

Scope:

- connect synthetic, virtual-microphone, acoustic, and supervised voice evidence
  to the same ability-class vocabulary;
- make preflight fail clearly when an existing Orchestrator lock would block a
  full run;
- keep supervised physical microphone/speaker evidence separate from automated
  regression evidence.

Exit criteria:

- voice acceptance reports ability-class coverage and evidence level;
- no voice runner claims readiness when only preflight or synthetic evidence
  exists.

### PR 5 - Release Gate Alignment

Scope:

- require release notes and status updates to cite exact evidence levels;
- remove hardcoded test counts from claim documents or validate them
  automatically;
- keep implemented, automatically verified, target validated, and release ready
  separate.

Exit criteria:

- release candidates cannot cite Level A or preview evidence as target
  validation;
- status and acceptance docs match the current runner outputs.
