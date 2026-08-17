# Scenario-Driven Development

Status: Required development policy
Applies to: interaction, planning, memory, tools, embodiment, audio, and safety

## 1. Purpose

Chromie behavior must be developed from observable interactions and explicit
contracts, not from isolated prompt intuition.

The required loop is:

```text
interaction or requirement
→ retained scenario
→ failing reproduction
→ root cause at the earliest responsible boundary
→ explained fix mechanism
→ design and implementation
→ passing scenario
→ full regression
→ evidence-qualified claim
```

A scenario is not merely a unit test. It is a durable statement of what Chromie
should understand, plan, say, execute, and retain across one or more turns.


## Benchmark relationship

Scenario-driven development supplies the durable cases; the
[Chromie Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md) organizes those cases by
execution layer, semantic dataset, evidence level, and aggregate metric.

A scenario is not permission to add an input-specific implementation rule.
Model-dependent behavior should be expressed as an acceptable outcome region
plus deterministic safety, authorization, truthfulness, and evidence
invariants. LLMs may help generate and diversify candidate scenarios, but a
reviewer must reject cases that encode phrase-to-action mappings or teach the
runtime to the test.

Scenario truth is hybrid where appropriate. Simple module, contract, transport,
and lifecycle facts keep exact fixture/assertion authority. Semantic interaction
quality is reviewed by an LLM or human from retained evidence. A scenario must
not use phrase lists as a substitute for judging intent or naturalness. See
[Hybrid oracle execution](CHROMIE_BENCHMARK_SUITE.md#73-hybrid-oracle-execution).

When fixed expected responses would overconstrain valid model behavior, use the
[Chromie-specific semantic qualification workflow](CHROMIE_BENCHMARK_SUITE.md#chromie-specific-semantic-qualification-workflow).
Generate the cohort from Chromie's actual identity, Goal state, execution lanes,
capabilities, interaction contract, and retained failures rather than from
generic assistant prompts. Record the acceptable meaning and forbidden region,
run the real module or integration boundary, retain the unedited result, and
have a declared reviewer judge only the semantic dimensions. Exact DTO and
safety facts still use deterministic assertions. One-session LLM judgment is
diagnostic evidence, not independent qualification, and must be labeled as
such.

Existing scenario directories remain authoritative during staged migration.
The benchmark inventory will index and classify them before any physical move.

## 2. Why scenarios are required

Model-based systems can pass narrow tests while failing conversationally because
behavior spans several boundaries:

- audio capture and ASR;
- goal association;
- multi-goal segmentation;
- fast versus deep planning;
- capability retrieval;
- parameter resolution;
- validation and confirmation;
- provider execution;
- speech and optional Social Attention body decoration;
- task and goal continuity.

A retained scenario preserves the complete interaction contract across these
boundaries.

## 3. Scenario classes

### 3.1 Contract scenarios

Dependency-light tests of schemas, versions, lifecycle, validation, and replay.

### 3.2 Goal Interpretation scenarios

Model outputs are mocked or replayed to verify goal-preserving routing,
coverage, escalation, and normalization.

### 3.3 Interaction scenarios

A Goal Interpretation decision is passed through the Agent interaction runtime and checked
for speech, plans, skills, confirmations, and metadata.

### 3.4 Dialogue scenarios

Multiple turns share goal and conversation state. They verify association,
clarification, confirmation, modification, cancellation, and resumption.

### 3.5 Audio-boundary scenarios

Synthetic VAD/ASR fixtures test short replies, overlong segments, interruption,
queueing, and degraded input handling.

### 3.6 Live-text scenarios

The deployed Agent/Cognitive Core, tools, and simulator are exercised with text input
and retained traces.

### 3.7 Simulator and physical evidence

Real providers are used. These scenarios support stronger claims only when the
exact revisions, environment, and artifacts are retained.

## 4. Required scenario contents

Each scenario should define:

- a stable scenario ID;
- the originating interaction or design requirement;
- initial goal, task, environment, and provider state;
- one or more user turns;
- mocked model outputs where applicable;
- expected goal associations;
- expected new goals;
- expected planner tier and escalation;
- expected canonical plan or information gap;
- expected confirmation state;
- expected skills and arguments;
- forbidden skills or claims;
- expected speech properties;
- expected retained state after each turn;
- expected direct, Fast, or Deep path and the specific reason when Deep is
  required;
- latency checkpoints when responsiveness is part of the requirement: first
  valid speech commitment, `tts_request_start`, first PCM chunk, first audible
  playback, plan ready, execution start, terminal evidence, and final playback;
- model-call, queue/evaluation, and contract-repair counts and durations for a
  diagnosed cognitive delay;
- evidence level.

Latency scenarios must keep request classes separate: direct non-effectful
conversation, complete bounded capability work, and uncertain, complex, or
work whose safety/resource reasoning needs the wider planner. Compare warm and
cold p50/p95 within a class; never average a fast greeting together with a
compound physical plan to hide either failure. Goal omission, unsafe execution,
ungrounded speech, critical schema or LLM integrity failure, service failure,
or unsafe-idle failure is a hard failure and cannot be traded for a better
latency score.

When asynchronous work can finish during other speech or another ordinary turn,
retain cases for urgent safety/control pre-emption, ordered ordinary-result
delivery, internal-only evidence with no speech, and a slow earlier Goal whose
result is delivered exactly once after the newer Communicative Act. A barge-in
case must distinguish invalidating current/queued audio from cancelling the
underlying Goal; only explicit cancellation or supersession may discard its
future result response, with any broader semantic interruption requiring the
Core-authorized scope recorded by the scenario.

## 5. Multi-turn scenario example

```text
Turn 1: 给我拿杯咖啡。
Expected: create coffee goal.

Turn 2: 冰的。
Expected: modify coffee goal; no new goal.

Turn 3: 顺便查一下天气。
Expected: retain coffee goal and create weather goal.

Turn 4: 算了，不用了。
Expected: ambiguity between active goals; ask naturally which one.
```

The scenario must not accept a response that creates four unrelated goals.

## 6. Compound-goal scenario example

```text
User: 往前走十五秒，同时眨眼。
```

Required assertions:

- walking and blinking both remain in the semantic goal;
- fast planning cannot execute only walking;
- deep planning receives the original utterance and full candidate surface;
- low-consequence blink count may be model-resolved within schema;
- unsupported concurrency produces a complete alternative;
- a material alternative executes nothing before confirmation;
- invalid second step cannot leak the first step;
- final speech reflects the validated plan rather than raw ASR wording.

## 6.1 Complex cognitive scenario matrix

Architecture changes must include scenarios that combine independent goals and
lifecycle transitions, not only isolated utterances. At minimum, the maintained
matrix should cover:

- one goal executing while another asks a specific clarification;
- one goal succeeding while another is unavailable or refused;
- ambiguous cancellation with multiple active goals;
- an alternative plan revised before confirmation;
- a side conversation while an earlier goal remains `waiting_for_user`;
- a later parameter answer resuming the original goal after an idle interval;
- host preparation or validation failure leaving all staged goal state unchanged;
- a multi-goal provider request updating every source goal but no auxiliary
  social-attention lifecycle.

Each scenario must assert goal IDs, per-goal dispositions, information gaps,
confirmation state, effectful skills, speech commitments, and final lifecycle.
Testing only the top-level route or global plan disposition is insufficient.

## 7. Scenario-before-fix policy

For a reported behavioral defect:

1. Preserve the relevant log or interaction transcript.
2. Remove private or irrelevant data.
3. Create the smallest scenario that reproduces the failure across the earliest
   incorrect boundary.
4. Name the violated contract and the component responsible for enforcing it.
5. Establish the causal chain from the initiating trigger to the earliest wrong
   decision or state transition. Separate the root cause from downstream
   symptoms, unrelated failures, and contributing conditions.
6. Explain the fix mechanism: why the proposed change belongs at that boundary,
   how it restores the contract, and what behavior remains unchanged.
7. When the report is "slow," retain and score the complete stage timeline so
   model generation, validation, repair, TTS synthesis, and playback are not
   conflated.
8. Verify that the scenario fails on the current evaluated revision.
9. Implement the architectural fix.
10. Verify the new scenario and all existing scenarios.
11. Record the evidence level honestly.

A patch should not claim to fix a live behavior if only an unrelated unit test
was added. A patch is also incomplete when it omits the causal explanation or
only restates the changed code.

### 7.1 Required repair record

The retained defect report must contain:

- observed and expected behavior;
- reproduction evidence and evaluated revision;
- violated contract and owning component;
- earliest responsible boundary and evidence-backed root cause;
- the trigger-to-failure causal chain;
- the fix mechanism and intended scope;
- pre-fix and post-fix scenario results;
- broader regression gates and the exact evidence ceiling;
- unresolved assumptions or evidence gaps.

When evidence supports only a hypothesis, label it as an inference and retain the
next test needed to confirm or reject it. Do not present correlation, a nearby
error, or the last visible symptom as the root cause.

### 7.2 Daily-life generated-voice repair loop

Use the maintained daily-life voice cohort when qualifying ordinary household,
school, routine, shared-space, uncertainty, and continuity behavior:

```bash
BUILD=1 python scripts/closed_loop_e2e.py \
  --manifest benchmarks/manifests/daily_life_voice_e2e_v1.json \
  --workflow-only \
  --workflow-input tts-asr \
  --start-services \
  --capture auto \
  --require-current-agent-source \
  --collect-debug-bundle
```

This is one qualification run with isolated scenario conversations. Isolation
prevents one case from leaking state into another; ordered turns within a
scenario retain one bounded conversation. For every user turn the runner asks
TTS to generate speech, saves the WAV, sends that audio to ASR, and routes only
the ASR transcript into Chromie. It then captures Chromie's actual playback and
uses ASR to compare it with the delivered speech event. The input WAV,
transcript, response events, playback WAV, session evidence, and per-case result
are retained under one output directory.

`BUILD=1` rebuilds the maintained service images, and
`--require-current-agent-source` compares the deployed Agent source digest with
the current worktree before the first workflow case. A Git revision recorded by
the host is not proof that an older service image runs that revision.

The runner invokes `scripts/collect_debug_bundle.sh` exactly once after all
selected cases finish. Inspect `summary.json`, `semantic-review-bundle.json`,
each `workflow/<scenario-id>/result.json`, and the debug archive before changing
code. Correlate scenario, session, turn, trace, stage, and call IDs. Compare the
exact prompt, context, schema, raw model output, parsed or repaired value, next
workflow state, delivered speech, and playback transcript at the earliest wrong
boundary.

Mechanical success is necessary but not a conversational pass. Judge the
declared outcome, rubric, acceptable region, forbidden behaviors, and invariants
for every case. Chromie should understand the intended everyday request,
preserve corrections and prior turns, ground claims in available evidence and
capabilities, express uncertainty naturally, stay concise, and sound like
Chromie rather than customer support, a schema, or an internal workflow. Judge
meaning rather than exact wording. Unsupported effects, invented facts, lost
Goals, unsafe behavior, critical LLM-integrity or service failures, and missing
safe idle are hard failures that cannot be averaged away.

For each fail or partial verdict, retain the observed turn and classify the
initiating trigger, earliest responsible boundary, root cause, downstream
symptoms, contributing conditions, and remaining evidence gaps. Add the
smallest focused regression, make a general architecture, contract, context,
prompt, provider, or validation fix at that boundary, and never add a phrase
rule for the fixture. Rerun the focused case with repeatable `--case`, then the
whole daily-life cohort, its applicable general-ability class, and the canonical
repository gates. Repeat until every deterministic boundary passes and every
semantic case has an evidence-grounded pass verdict.

This path is automated generated-speech evidence. It does not exercise VAD or
prove arbitrary human speech, a physical microphone, room acoustics, or robot
hardware. Use the maintained voice-acceptance profiles and supervised evidence
for those stronger claims.

## 8. Model mocking policy

Mocked model outputs should reproduce both successful and pathological cases:

- high-confidence narrowed skill;
- malformed JSON;
- generic clarification;
- partial compound plan;
- stale task reference;
- unsupported identity claim;
- invented target;
- correct exact or alternative plan.

Tests should validate the runtime contract around model output, not assert hidden
chain-of-thought.

## 9. No rule substitution

A scenario failure must not be fixed by adding a phrase-specific branch for the
fixture text.

Reviewers should search for:

- literal fixture phrases in runtime code;
- regexes mapping normal language to skills;
- hardcoded action counts or durations;
- identity-question branches;
- response tables that bypass semantic models.

Deterministic checks may validate structure, schema, evidence, lifecycle,
versions, authorization, and signal quality.

## 10. Evidence levels

### Level A — Dependency-light automated evidence

Contracts, mocked models, simulated providers, and local deterministic tests.

### Level B — Deployed live-text evidence

Real Goal Interpretation and Agent models, real tool/provider interfaces, text input, and
retained traces.

### Level C — Simulator evidence

Live Soridormi and MuJoCo execution with retained video/trace artifacts.

### Level D — Physical supervised evidence

Real microphone, speaker, sensors, and robot under operator supervision.

A scenario must state its level. Passing Level A does not imply Level C or D.

## 11. Regression gates

A cognition or interaction patch should run, as applicable:

```bash
python scripts/check_docs.py
./scripts/run_tests.sh
python scripts/scenario_runner.py --no-write
python scripts/general_ability_acceptance.py --mode level-a --no-write
```

Target-specific work must also run the corresponding live evidence workflow.

## 12. Review questions

- Does the scenario reproduce the earliest incorrect boundary?
- Does it preserve the complete user goal?
- Does it test continuity across turns when relevant?
- Does it assert forbidden partial execution?
- Does it distinguish model proposal from runtime commitment?
- Does it check natural clarification without internal IDs or schema language?
- Does it check evidence before completion claims?
- If latency is in scope, does it measure first truthful audible response and
  identify the earliest slow boundary rather than only total runtime?
- Could the implementation pass only because the fixture wording was hardcoded?
- Is the evidence level explicit?
- Are the resulting files and revisions reproducible?

## 13. Scenario lifecycle

Scenarios are retained unless:

- the user-facing requirement is intentionally removed;
- an architecture decision explicitly supersedes it;
- a newer scenario strictly covers the same behavior and the removal is
  documented.

Scenarios should be renamed or migrated carefully because their IDs become part
of development history and evidence.

## 14. Definition of done

A behavioral change is not complete until:

- the originating scenario is retained;
- it failed before the fix or is an explicit new requirement;
- the retained report explains the evidence-backed root cause and fix mechanism
  in plain language rather than only describing the diff;
- it passes after the fix;
- existing scenario and general-ability gates pass;
- documentation and status claims are updated;
- the target evidence level is stated;
- clean patch application or revision reproduction is verified.

For a user-reported defect, the responsible coding agent must also run and
inspect the originating scenario rather than delegating log collection back to
the user. The retained report must include deterministic hard-gate results, an
acceptance-only diagnostic score, the earliest suspect boundary, and the exact
evidence ceiling. Scoring is diagnostic: Goal omission, stale provenance,
unsafe or unwanted execution, service failure, critical LLM-integrity failure,
or failure to return safe idle always fails the scenario regardless of the
average score.

The maintained general-ability live runner supports ordered `turns` in one
bounded conversation. This is the required form for failures caused by stale
Goals, earlier tools, clarification state, confirmation state, or dialogue
continuity. Use `--only-case` to rerun the originating episode while debugging;
then run its complete ability class before the canonical repository gate.
