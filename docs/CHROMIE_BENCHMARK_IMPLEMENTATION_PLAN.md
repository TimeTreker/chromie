# Chromie Benchmark Suite Implementation Plan

Status: Approved staged plan
Depends on: current scenario runner, general-ability acceptance framework,
Social Attention closure, runtime evidence contracts

## Goal

Build the Chromie Benchmark Suite without turning evaluation cases into Host
behavior rules, without invalidating existing scenario evidence, and without
requiring a live model for every deterministic repository test.

## Delivery principles

1. Document and schema first.
2. Index before moving files.
3. Preserve stable scenario IDs and provenance.
4. Separate deterministic gates from model-quality measurements.
5. Keep live-model, live-service, simulator, and physical evidence distinct.
6. Optimize prompts for general principles, never named benchmark cases.
7. Add one independently reviewable patch and commit per phase.

## Phase 0 - Constitution and design

Scope:

- add the Benchmark constitutional principle to the Project Charter;
- establish the target architecture, taxonomy, scenario contract, and metrics;
- classify existing scenario sources;
- publish this implementation plan.

Exit criteria:

- documentation checks pass;
- no runtime or test behavior changes;
- Roadmap and Development Checkpoint point to Phase 1.

## Phase 1 - Benchmark manifest and inventory

Deliverables:

```text
benchmarks/
├── README.md
├── benchmark.schema.json
├── manifests/
│   ├── suites.json
│   └── existing_scenarios.json
└── reports/.gitkeep
```

Add a dependency-light inventory tool that:

- discovers existing scenario JSON and acceptance manifests;
- assigns layer and dataset tags without moving source files;
- rejects duplicate IDs, missing provenance, unknown tags, and invalid paths;
- prints coverage counts by layer, dataset, language, evidence level, and source;
- never evaluates semantic output or makes runtime decisions.

Exit criteria:

- every maintained scenario appears exactly once in the inventory;
- one scenario may have multiple tags without file duplication;
- inventory generation is deterministic and CI-safe;
- existing runners continue to pass unchanged.

Suggested commit:

```text
Add benchmark manifest and scenario inventory
```

## Phase 2 - Common scenario contract and adapters

Deliverables:

- versioned benchmark case schema;
- adapters from legacy routing path, interaction, dialogue, and general-ability
  scenario formats, preserving their source IDs without presenting Router as the
  settled cognitive ingress architecture;
- normalized result envelope containing inputs, outputs, evidence, invariant
  results, latency, and provenance;
- no physical file migration yet.

The common contract distinguishes:

- hard deterministic invariants;
- acceptable semantic outcome regions;
- cohort/distribution expectations;
- optional qualitative-review prompts.

Exit criteria:

- representative cases from every current suite normalize successfully;
- adapters preserve original IDs and source paths;
- existing scenario runners and new normalized replay agree on hard gates.

Suggested commit:

```text
Add common benchmark scenario and result contracts
```

## Phase 3 - Module and integration runners

Deliverables:

- `benchmarks/modules/` runner entrypoints for Cognitive Gateway, Goal-Driven
  Cognitive Core boundaries, Planner, Composer, Social Attention, MindProfile,
  catalog projection, and tool interpretation;
- `benchmarks/integration/` entrypoints for maintained component chains;
- replay mode and live-model mode;
- retained JSON reports.

The runner must not contain semantic phrase tables. It may select adapters,
validate contracts, compare effects, and aggregate evidence.

Exit criteria:

- deterministic replay remains part of normal CI;
- live-model mode is opt-in and records model/prompt revisions;
- failures identify the earliest wrong boundary;
- no benchmark-specific runtime branch is introduced.

Suggested commit:

```text
Add module and integration benchmark runners
```

Architecture terminology rule:

- Cognitive Gateway is the settled ingress/admission boundary;
- Goal-Driven Cognitive Core owns semantic goal interpretation and planning;
- legacy Router paths and wire contracts may be indexed only as compatibility or
  historical-regression evidence;
- no new generic `router` benchmark component, dataset authority, or architectural
  diagram may be introduced.

## Phase 4 - Social Attention benchmark expansion

Build the first comprehensive dataset because its architecture is now closed.
Target 120-150 reviewed cases, generated in batches and deduplicated by semantic
coverage rather than wording.

Initial cohorts:

- greetings, farewells, thanks, and ordinary conversation;
- factual questions and tools;
- explicit robot actions and multi-goal requests;
- multi-turn repetition and cooldown;
- interruption and user-requested stillness;
- emotion, support, praise, disappointment, and frustration;
- silence and ambient speech;
- user politeness and impatience matrix;
- robot style and user preference matrix;
- `off`, `report_only`, and `on` policy modes;
- provider availability, rejection, and resource conflict;
- bilingual and ASR-like perturbations;
- historical Social Attention regressions.

Each case defines behavior boundaries rather than requiring a fixed gesture.
Generated candidates require review before entering the authoritative manifest.

Exit criteria:

- at least 100 non-duplicate reviewed cases;
- every matrix axis has minimum coverage declared in the manifest;
- no expected result maps a phrase directly to a gesture;
- focused module and interaction runs pass;
- reports expose style-conditioned behavior distributions.

Suggested commit:

```text
Add comprehensive Social Attention benchmark dataset
```

## Phase 5 - End-to-end runner and evidence levels

Deliverables:

- text E2E runner using deployed Router, Agent, tools, and Skill Runtime;
- virtual-audio and supervised voice adapters;
- simulator and supervised target profiles;
- correlated trace and provider evidence retention;
- qualification summaries compatible with existing acceptance levels.

Exit criteria:

- one scenario ID can be evaluated at multiple evidence levels without changing
  its semantic contract;
- preview, simulated execution, and physical execution claims remain distinct;
- auxiliary behavior timing is measured against speech and primary execution;
- failures retain partial evidence instead of hanging the suite.

Suggested commit:

```text
Add end-to-end benchmark execution and evidence profiles
```

## Phase 6 - Stress and distribution evaluation

Deliverables:

- repeated-turn, long-session, concurrency, interruption, timeout, and degraded
  provider workloads;
- seeded repeated sampling where supported;
- aggregate metrics and confidence intervals or sample counts;
- drift comparison across model, prompt, profile, and code revisions.

Metrics are observational gates approved per release. They must not become
runtime quotas or forced-action schedules.

Exit criteria:

- reports make sample size and run conditions explicit;
- duplicate/cooldown, stillness, safety, and leakage violations remain zero;
- behavior-frequency changes are visible without prescribing one gesture rate.

Suggested commit:

```text
Add stress and behavior-distribution benchmark reports
```

## Phase 7 - Scenario migration and legacy cleanup

After adapters and inventory are stable:

- move or reference existing scenarios into the target hierarchy;
- retain redirects or compatibility manifests for old commands;
- consolidate duplicate wrappers and obsolete one-off scripts;
- preserve historical regression IDs and git provenance;
- update CI and documentation to the Benchmark Suite entrypoints.

Exit criteria:

- all prior maintained scenarios remain discoverable and runnable;
- old and new aggregate counts reconcile;
- no release claim loses its original evidence source;
- compatibility paths have an explicit removal schedule.

Suggested commit:

```text
Migrate maintained scenarios into the benchmark suite
```

## Phase 8 - Continuous scenario mining and review

Integrate runtime evidence and reported failures with the existing scenario
candidate data loop:

- propose candidates from retained episodes;
- cluster and deduplicate semantically similar cases;
- generate controlled variations for language, politeness, context, and failure
  conditions;
- require human review and provenance before promotion;
- track coverage gaps and historical bug recurrence.

The LLM may propose and critique. It does not silently modify authoritative
prompts, production personality, or pass/fail policy.

Suggested commit:

```text
Connect experience mining to reviewed benchmark authoring
```

## Recommended immediate next patch

Implement Phase 1 only: directory skeleton, schemas, deterministic inventory,
coverage report, tests, documentation, and CI entrypoint. Do not move existing
scenario files and do not add the 120-case dataset in the same patch. This keeps
the foundation reviewable before large generated content lands.
