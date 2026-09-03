# Planner Daily-Life Qualification Corpus

Audience: reviewers and operators qualifying Chromie's Fast/Deep Planner
transaction under [Issue #35](https://github.com/TimeTreker/chromie/issues/35).
This is offline evaluation input, not production behavior policy or approved SFT
data.

## What the corpus covers

The Fast corpus contains 204 current-production-shaped scenarios. Its count is
derived from the design, not chosen as a scale target:

- 17 Planner capacities derived from the Charter, interaction contract, DTOs,
  Host validation, and Capability contracts;
- three materially different daily-life families per capacity;
- one supported and one boundary condition per family;
- an English and Chinese realization of every semantic cell.

That produces 51 one-axis contrast sets and `17 * 3 * 2 * 2 = 204` cases. The
matrix covers all 15 maintained daily-life families: greetings/presence,
feelings support, meals/wellbeing, identity/body truth, play/creativity,
preferences/boundaries, shared-space etiquette, uncertainty repair, casual
chat/curiosity, family/home, friends/social life, multi-turn continuity,
practical information/tools, routines/plans, and school/learning.

The 17 capacity classes describe what Planner must do according to Chromie's
design:

1. authoritative scope coverage and prospective satisfaction;
2. direct Communicative Activity authorship;
3. Capability grounding without semantic substitution;
4. parameter resolution and provenance;
5. Work topology and sequential/parallel coordination;
6. per-Goal disposition and mixed outcomes;
7. user-resolvable uncertainty and honest limit outcomes;
8. Plan relation and confirmation proposals;
9. truthful response staging and deduplication;
10. retained-Work revision without replay;
11. Evidence re-entry interpretation;
12. temporal-readiness planning;
13. resource-contract composition;
14. output-mode fidelity;
15. optional subordinate social decoration;
16. atomic Plan integrity and safe alternatives;
17. Fast completion versus genuine Deep-HOW escalation.

The matrix also varies the real transaction boundaries: 52
`streaming_advance`, 72 `canonical_primary`, and 80 `canonical_reentry` cases;
102 cases per language; 102 supported and 102 boundary cases. Splits are 120
`train_candidate`, 44 `validation`, and 40 `frozen_test`. A split name is only
a partition: every case remains `training_eligible=false` and
`independent_semantic_review=false`.

The separate Deep corpus contains 40 cases across ten Deep/shared capacities,
with 24 primary and 16 re-entry transactions, equal English/Chinese coverage,
and supported/boundary contrasts. Deep is qualified separately because it sees
the authoritative source/context for deeper HOW cognition; it never receives or
repairs a Fast candidate Plan.

## What the corpus deliberately does not claim

Daily-life situations are test contexts, not proxy abilities. The actual
coverage claim is limited to the declared capacity/state-space cells and their
one-axis contrasts. The corpus does not prove exhaustive human life, emergent
world knowledge, target-provider compatibility, voice quality, simulator or
hardware behavior, safety certification, release readiness, or independent
semantic validity.

The authority map excludes provider-neutral WHAT (Goal Interpretation),
canonical Goal identity/continuity (Goal Association), GA/Fast scheduling,
confirmation grants, authorization, atomic commit, execution, Evidence
manufacture, emergency controls, TTS realization, and provider-internal motion
planning. A difficult case belonging to one of those owners must not be counted
as Planner coverage.

`streaming_advance` owns one two-frame HOW result over GI Responsibility refs
before GA joins. It cannot invent Goal IDs, satisfaction, Plan relation, or time
conditions. `canonical_primary` owns the complete semantic Plan over GA-owned
Goals. `canonical_reentry` sees only the admitted still-open Goal/Evidence scope
and must not replay completed Work or narrate excluded siblings.

The 204-case tree replaced a historical 1,500-case cross-product. That older
inventory was invalid qualification input: 720/1,000 canonical/re-entry
contexts failed the current GA DTO, the remaining 280 did not equal the current
projection, material bindings were absent, only five Capabilities were exposed,
and reminder/weather dominated the targets. Its count was never evidence of
daily-life or Planner-logic coverage.

## Validation and immutable qualification

Validate the checked-in corpus and focused dataset contracts:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification validate
python -m pytest -q benchmarks/tests/test_fast_planner_daily_life_dataset.py
```

Run a new target-blind Fast cohort without editing source or the harness between
steps:

```bash
RUN_DIR=.chromie/benchmarks/fast-planner/NEW_RUN_ID
python -m benchmarks.datasets.fast_planner_daily_life.qualification prepare \
  --label fast-qualified-full --output-dir "$RUN_DIR"
python -m benchmarks.datasets.fast_planner_daily_life.qualification run \
  --output-dir "$RUN_DIR" --concurrency 4 --timeout-s 180
python -m benchmarks.datasets.fast_planner_daily_life.qualification adjudicate \
  --output-dir "$RUN_DIR"
```

Run Deep through the sibling `deep_qualification` command after Fast closes.
Every scenario gets exactly one target-blind candidate call, no hidden retry,
and real Schema/DTO/Host adjudication. A non-zero process, timeout, missing
output, or source/harness change makes the batch incomplete; successful cases
from different batches are never spliced together.

All inference and optimization follows `optimize-chromie-llm-prompt`: freeze
the coverage-designed corpus and transaction, infer without targets, adjudicate
the earliest boundary, make only an authorized minimal repair, rerun focused
proof, then rerun the complete frozen cohort. A prompt changes only when the
evidence identifies it as the earliest defective owner. Host rewriting,
same-tier semantic repair/review, validator weakening, and example-answer
libraries are forbidden.

Codex CLI qualification is an offline same-model surrogate, not the deployed
Ollama/vLLM transport and not an independent semantic reviewer. Local artifacts
under `.chromie/benchmarks/` do not transfer with Git. No scenario may enter
QLoRA/SFT until an independent reviewer accepts its semantic target and the
owner explicitly changes `training_eligible`.
