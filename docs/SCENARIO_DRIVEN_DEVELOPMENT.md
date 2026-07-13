# Scenario-Driven Development

Status: Proposed development policy
Applies to: interaction, planning, memory, tools, embodiment, audio, and safety

## 1. Purpose

Chromie behavior must be developed from observable interactions and explicit
contracts, not from isolated prompt intuition.

The required loop is:

```text
interaction or requirement
→ retained scenario
→ failing reproduction
→ design and implementation
→ passing scenario
→ full regression
→ evidence-qualified claim
```

A scenario is not merely a unit test. It is a durable statement of what Chromie
should understand, plan, say, execute, and retain across one or more turns.

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
- speech and social attention;
- task and goal continuity.

A retained scenario preserves the complete interaction contract across these
boundaries.

## 3. Scenario classes

### 3.1 Contract scenarios

Dependency-light tests of schemas, versions, lifecycle, validation, and replay.

### 3.2 Router scenarios

Model outputs are mocked or replayed to verify goal-preserving routing,
coverage, escalation, and normalization.

### 3.3 Interaction scenarios

A Router decision is passed through the Agent interaction runtime and checked
for speech, plans, skills, confirmations, and metadata.

### 3.4 Dialogue scenarios

Multiple turns share goal and conversation state. They verify association,
clarification, confirmation, modification, cancellation, and resumption.

### 3.5 Audio-boundary scenarios

Synthetic VAD/ASR fixtures test short replies, overlong segments, interruption,
queueing, and degraded input handling.

### 3.6 Live-text scenarios

The deployed Router, Agent, tools, and simulator are exercised with text input
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
- evidence level.

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
4. Verify that the scenario fails on the current candidate revision.
5. Implement the architectural fix.
6. Verify the new scenario and all existing scenarios.
7. Record the evidence level honestly.

A patch should not claim to fix a live behavior if only an unrelated unit test
was added.

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

Real Router and Agent models, real tool/provider interfaces, text input, and
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
- it passes after the fix;
- existing scenario and general-ability gates pass;
- documentation and status claims are updated;
- the target evidence level is stated;
- clean patch application or revision reproduction is verified.
