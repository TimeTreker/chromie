# Chromie Benchmark Suite

Status: Approved target design
Applies to: model reasoning, prompts, contracts, interaction, tools, memory,
Social Attention, embodiment, safety, and release qualification

## 1. Purpose

The Chromie Benchmark Suite is the durable evaluation system for Chromie's
robot intelligence. It measures whether models, prompts, contracts, runtime
boundaries, and providers produce useful, natural, safe, and evidence-grounded
behavior across representative interactions.

The suite is not a collection of phrase-trigger rules and is not an alternate
runtime policy engine.

```text
real interaction, reported failure, or capability requirement
-> reviewed benchmark scenario
-> model and runtime execution
-> contract, invariant, evidence, and distribution evaluation
-> prompt, model, contract, or architecture improvement
-> retained regression evidence
```

## 2. Constitutional rule: evaluation must not become behavior policy

Cognitive and social choices belong to LLM reasoning over prompts, bounded
context, capability descriptions, task state, memory, and owner-approved
personality guidance. The Host may validate schemas, authorization, safety,
resource conflicts, timing, evidence, and observable outcomes. It must not add
phrase tables, regular expressions, scenario IDs, or fixed input-to-action
mappings to make a benchmark pass.

A benchmark scenario expresses an acceptable behavior region and required
invariants. It should not require one arbitrary model output when several
outputs are reasonable.

Bad expectation:

```text
input: "Hello"
required auxiliary skill: nod
```

Good expectation:

```text
primary outcome: acknowledge the greeting naturally
allowed auxiliary outcomes: none, one bounded greeting-compatible cue
forbidden outcomes: unrelated motion, repeated cue, delayed speech, unsupported claim
```

`none` is a first-class valid Social Attention decision. Courtesy, expression,
initiative, and restraint influence model judgment; they do not define a fixed
gesture frequency or deterministic lookup table.

## 3. Benchmark versus tests

The repository keeps both conventional tests and benchmarks.

- Unit and contract tests prove deterministic code properties, schema behavior,
  validation, authorization, and safety invariants.
- Benchmarks evaluate model-dependent semantic quality, interaction behavior,
  distribution drift, latency, and end-to-end outcomes.
- A benchmark may reuse deterministic assertions, but deterministic assertions
  must guard boundaries rather than replace semantic reasoning.
- A live LLM is the system under evaluation, not the sole pass/fail judge.
  Machine-checkable contracts and retained evidence provide the primary gates;
  optional model critique may support reviewed qualitative analysis.

## 4. Layered architecture

The target repository layout is:

```text
benchmarks/
├── modules/
├── integration/
├── e2e/
├── stress/
├── regression/
├── datasets/
├── reports/
├── manifests/
├── README.md
└── benchmark.schema.json
```

### 4.1 Module benchmarks

Exercise one reasoning or contract-producing component with controlled
surroundings. Examples:

- Cognitive Gateway attention/admission review;
- Goal-Driven Cognitive Core goal interpretation and association;
- Goal segmentation and association;
- Fast and Deep Planner output;
- Response Composer and Social Attention choice;
- MindProfile and Social Interaction Style prompt projection;
- capability retrieval and model-facing catalog projection;
- tool-result interpretation.

Module benchmarks may replay recorded model output to isolate validators, but
model-quality runs must also support a live configured model.

### 4.2 Integration benchmarks

Exercise meaningful component chains without requiring the entire deployed
system. Examples:

```text
MindProfile -> Response Composer -> Social Attention proposal
Cognitive Gateway -> Goal-Driven Cognitive Core -> Planner
Capability catalog -> Planner -> Skill Runtime validation
Tool result -> interpretation -> truthful final speech
```

### 4.3 End-to-end benchmarks

Exercise the maintained interaction path and retain correlated evidence:

```text
text or audio
-> Cognitive Gateway
-> Goal-Driven Cognitive Core
-> tool and/or named-skill execution
-> Response Composer
-> speech and optional auxiliary behavior
-> terminal evidence
```

E2E levels remain evidence-scoped. Text-only, virtual audio, simulator, and
supervised physical-device runs must not be reported as equivalent evidence.

The legacy `Router` service name and wire contract remain compatibility details
during migration. They are not a substitute name for Cognitive Gateway. Existing
`scenarios/goal_interpretation/` and `scenarios/cognitive_core_dialogue/` assets are retained as
compatibility regressions so historical evidence is not lost. New benchmark
architecture must name the actual boundary under evaluation: Cognitive Gateway
for ingress/admission, or Goal-Driven Cognitive Core for semantic goal reasoning
and planning.

### 4.4 Stress benchmarks

Evaluate behavior under repetition, concurrency, long sessions, interruption,
timeouts, provider degradation, multi-user context, and resource pressure.
Stress benchmarks report rates and distributions instead of pretending one run
proves stability.

### 4.5 Regression benchmarks

Every confirmed historical behavior bug receives a retained scenario at the
earliest layer that reproduces it, plus stronger integration or E2E coverage
when required. Regression scenarios are not deleted merely because the current
model passes them.

### 4.6 Reports

Reports compare runs by model, prompt revision, MindProfile, provider revision,
hardware profile, evidence level, and code revision. They retain individual
scenario artifacts as well as aggregate metrics.

## 5. Dataset taxonomy

Scenario content is classified independently from execution layer. One dataset
case may run at module, integration, and E2E layers.

```text
benchmarks/datasets/
├── greeting_and_farewell/
├── daily_conversation/
├── information_qa/
├── tools/
├── robot_actions/
├── multi_goal/
├── multi_turn/
├── interruption_and_control/
├── emotion_and_support/
├── silence_and_ambient_input/
├── repetition_and_cooldown/
├── social_attention/
├── style_matrix/
├── user_preferences/
├── uncertainty_and_clarification/
├── safety_and_authorization/
├── failure_and_recovery/
├── bilingual_and_asr_noise/
└── historical_regressions/
```

Tags are multi-valued. A polite bilingual weather request can belong to
`information_qa`, `tools`, `style_matrix`, and `bilingual_and_asr_noise`
without duplicating the scenario body.

## 6. Scenario contract

Each reviewed benchmark case should carry, as applicable:

- stable scenario ID and schema version;
- layer and dataset tags;
- evidence level and execution mode;
- user input or multi-turn transcript;
- bounded conversation, task, memory, and recent-action context;
- owner-approved robot interaction style;
- user communication attributes such as politeness, impatience, urgency,
  emotional tone, and explicit preferences;
- available semantic capabilities and provider result fixtures;
- primary required outcome;
- acceptable semantic outcome region;
- forbidden effects and invariant violations;
- observable evidence requirements;
- latency or resource budgets where relevant;
- distribution cohort and aggregation rules;
- provenance: generated, mined, reported bug, or manually authored;
- reviewer status and rationale.

User politeness is contextual evidence, not a direct action command. A polite
user does not require a gesture; a rude or impatient user does not authorize
retaliatory, submissive, decorative, or unsafe behavior. The owner-approved
robot personality remains stable while adapting its wording and restraint to
the interaction.

## 7. Evaluation model

### 7.1 Hard gates

Hard gates remain deterministic and architecture-owned:

- primary task and explicit user action priority;
- stop, cancel, emergency, and user-requested stillness;
- authorization and confirmation;
- schema validity and live capability grounding;
- no `report_only` execution leakage;
- no unsupported execution claims;
- no provider-identity or calibration leakage into cognition;
- no auxiliary behavior that blocks speech or primary work;
- no invalid resource conflict;
- complete retained evidence and LLM integrity.

### 7.2 Acceptable behavior regions

Model-dependent semantics are evaluated against constraints and alternatives,
not a single expected string or gesture. A scenario may define:

- required communicative function;
- allowed skill families or `none`;
- maximum auxiliary count;
- prohibited unrelated behavior;
- required explanation or clarification properties;
- style-consistency requirements;
- evidence-backed truthfulness requirements.

Exact wording should be asserted only when the text itself is a contract, such
as an explicit safety notice or protocol token.

### 7.3 Distribution metrics

Repeated and cohort runs report behavior distributions. Initial metric families
include:

- primary-outcome success rate;
- exact tool and named-skill grounding rate;
- explicit-action priority violations;
- safety and authorization violations;
- unsupported-claim rate;
- auxiliary behavior frequency by style and scenario class;
- duplicate auxiliary rate and cooldown violations;
- user-stillness violations;
- `report_only` execution leakage;
- clarification quality and unnecessary-clarification rate;
- personality consistency;
- model, prompt, and profile behavior drift;
- stage and end-to-end latency percentiles.

Frequency ranges are evaluation cohorts, not runtime quotas. Chromie must not
add counters or forced gesture schedules merely to move an aggregate metric.

## 8. Social Attention benchmark matrix

The Social Attention dataset should cover at least these axes:

- robot style: `courteous`, `neutral`, `reserved`, and reviewed `custom`;
- user politeness: high, ordinary, terse, impatient, hostile but non-emergency;
- interaction: greeting, farewell, thanks, request, question, correction,
  disagreement, praise, frustration, sadness, celebration, silence;
- primary lane: conversation, tool, memory, robot action, multi-goal;
- history: no recent cue, same cue recent, repeated turn, interrupted cue;
- policy mode: `off`, `report_only`, `on`;
- explicit preference: normal, low-social-attention, no gesture, temporary
  stillness;
- capability state: relevant cue available, no safe cue available, provider
  rejection, confirmation-required candidate;
- evidence level: deterministic replay, live model, live text integration,
  simulator, supervised target.

The matrix must demonstrate that:

- style changes tendencies without becoming a phrase/action mapping;
- `none` remains valid in every ordinary style;
- explicit user requests and primary tasks dominate personality expression;
- recent evidence suppresses mechanical repetition;
- Social Attention does not delay speech, tools, emergency handling, or primary
  execution;
- provider rejection remains truthful and does not trigger Host substitution.

## 9. Existing scenario classification and migration

Existing scenarios remain valid evidence while the Benchmark Suite is built.
They are indexed first, then migrated without changing their semantic IDs.

| Current location | Initial benchmark classification |
|---|---|
| `scenarios/goal_interpretation/` | `modules/router` and semantic-routing datasets |
| `scenarios/cognitive_turn_loop/` | `integration/cognitive_turn_loop` |
| `scenarios/cognitive_runtime/` | `integration/goal_driven_runtime` |
| `scenarios/interaction/` | `integration/interaction` and selected `e2e/text` |
| `scenarios/dialogue/` | `integration/multi_turn` |
| `scenarios/cognitive_core_dialogue/` | `integration/router_dialogue` |
| `scenarios/adapter/` | contract/compatibility regression |
| `tests/scenarios/` | module, integration, or historical-regression datasets according to behavior |
| `scripts/general_ability_acceptance.py` manifests | E2E ability cohorts and evidence qualification |
| voice-milestone and MuJoCo acceptance paths | E2E audio/simulator cohorts |
| Social Attention closure scenarios | `social_attention`, `style_matrix`, `user_preferences`, and regression cohorts |

Migration begins with a generated index that points to existing files. Physical
moves happen only after runner compatibility, history preservation, and CI
coverage are proven. No scenario is copied into multiple directories solely to
represent multiple tags.

## 10. Authoring and review policy

LLMs may generate candidate scenarios, variations, perturbations, tags, and
qualitative critiques. Generated cases are never automatically authoritative.
A reviewer must verify that each accepted case:

- protects a general capability or historical regression;
- does not encode a phrase-trigger implementation;
- defines boundaries rather than an arbitrary single answer;
- uses realistic context and non-duplicative coverage;
- has a suitable execution layer and evidence claim;
- cannot be passed by weakening safety, truthfulness, or semantic authority.

When a benchmark fails, the first response is root-cause analysis. The permitted
fix classes are model choice, prompt principles, context quality, contract
clarity, capability description, architecture, provider behavior, or genuine
validation defects. Adding an input-specific Host rule is prohibited except for
narrow deterministic operational controls already defined by the Charter.

## 11. Relationship to existing documents

- [Project Charter](PROJECT_CHARTER.md) owns stable principles and authority.
- [Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md) owns the
  development loop from observed interaction to retained scenario.
- [General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md)
  owns current evidence levels and ability-class qualification.
- [Acceptance](ACCEPTANCE.md) owns release and target evidence claims.
- [Test Suite Maintenance](TEST_SUITE_MAINTENANCE.md) owns conventional test
  hygiene and duplicate removal.
- This document owns the target benchmark architecture, taxonomy, scenario
  contract, metric model, and migration strategy.
