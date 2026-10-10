# Chromie Development Checkpoint

## Current delivery — Need-first Planner (stage A), 2026-10-10

Base: `origin/main` `08c93650d`. The owner approved the Charter draft and its implementation
on 2026-10-10. Stage A is this commit; stage B (Deep removal) follows on the same delivery
line.

Observed: library-only abilities are never looked up. Live, 0/10 library requests were
correct and every one substituted a loaded skill. The model could use a loaded contract (9/10)
but did not judge coverage correctly.

| Order | Module / owner | Actual (before) | Expected | Verdict |
|---|---|---|---|---|
| 1 | Planner decoder contract | lookup offered as an alternative top-level shape; the model writes a plan instead | the need-first prefix judged after a restatement | incorrect (earliest) |
| 2 | Planner model | substitutes a loaded skill (clock → weather) | flags the unmet need | symptom of 1 |
| 3 | Host / Agent | no search | search with the Planner's wording, one re-plan | missing |

Repair (stage A):
- `ability_needs` prefix: `PlannerAbilityNeed`, `parse_ability_needs`, `take_ability_needs`,
  `need_first_response_schema` (every closed exposed shape).
- Streaming early stop: `complete_ability_needs`.
- `search_capability_library`: BM25, usable and unrestricted entries only.
- Second pass: never stops early.
- Non-streaming path: discards its first pass.
- Prompt: `CAPABILITY_NEED_PROMPT`, Fast tier only.
- Test fixtures: `declared_ability_needs`.
- Charter: PLANNER-AUTHORITY-001, need-first amendment, principles 28, 33 and 34, role list.
  API reference and the architecture doc updated.

Evidence (`.chromie/acceptance/need-first-20261010/`):
- Corpus freeze 22.
- Strict replay 6,000/6,000 with zero model calls, verdicts unchanged.
- Canonical gate in a clean worktree: see HANDOFF.
- Design evidence: `.chromie/acceptance/skill-lookup-20261010/`.

Known failures: carried forward from the previous delivery. Absent abilities still escalate
to a failing Deep until stage B.

Next (stage B):
1. Remove the Deep Planner: the agent resolver and `/deep-plan`; the Fast `escalate` and
   `deep_planner` continuation; orchestrator Deep paths, settings and environment
   variables.
2. Add an honest Fast unavailable outcome.
3. Migrate the 20 Deep corpus families (2,000 cases).
4. Update the remaining Deep docs (~110 mentions in 28 docs).
5. Then deploy and run a live cohort (the skill-lookup cohort plus the standard cases).

## Previous delivery — SGLang image: XGrammar int32 rule IDs, 2026-10-10

Base: `origin/main` `03f4e7e20`.

Owner direction (2026-10-10, not yet implemented):
- Remove the Deep Planner as a second planner.
- The one Planner first lists the abilities it needs and whether loaded skills cover them.
  If a need is uncovered, the Agent searches the catalog, loads the candidates, and the
  Planner plans once more (at most once, with no plan in the first pass).
- Order: fix the XGrammar failure first, then a frozen contrast of that need-first contract.
- Charter changes (PLANNER-AUTHORITY-001, ~line 747, ~line 1312) still need explicit
  owner approval of the drafted text.

Observed failure: with library skills loaded, the decoder request failed as HTTP 400
before inference (B 1/12; D 14/22).

| Order | Module / owner | Actual | Expected | Verdict |
|---|---|---|---|---|
| 1 | Planner decoder Schema (Agent) | valid JSON Schema; 34k–41k compiled rules | same | correct (large; burden noted) |
| 2 | XGrammar 0.2.1 native compile (SGLang image) | int16 rule ID wraps past 32767 → `per_rule_fsm_hashes` check / segfault | compile | incorrect (earliest) |
| 3 | SGLang → Agent | HTTP 400; Planner stage fails | decoded output | symptom |

Repair: backport the upstream #652 C++ diff in `llm/sglang/Dockerfile`, add an image-build
regression test, and document it in `docs/CONFIGURATION.md`. Upstream #963 (hasher order)
is not needed and is not applied.

Evidence (`.chromie/acceptance/skill-lookup-20261010/`, README.md):
- Reproduction and isolation: probes in the scratch area, summarized in README.
- Neutrality (fresh lifetimes, new vs old image): A 22/22 and Deep baseline 56/56
  byte-identical; B 11/11 identical, and 1 former 400 decodes.
- D: 14 former 400s decode, and 8 changed because the old lifetime contained failures. Host
  check: library 9/10 correct (excluding the two UMI speech-typed celebrate cases), controls
  6/6, absent cases still escalate to Deep (3) or are rejected (1).
- Canonical gate: see HANDOFF.
- No live cohort on the new image.

Skill-lookup findings (report-only, old image):
- Live: one Fast call per turn and the lookup never fired. Library requests 0/10 correct,
  all substitutions; Chromie's speech after a substitution was misleading.
- Deep was reached twice (backflip) and failed both times.

Known failures carried forward:
1. "同时" chaining (LoRA later).
2. Invented clarification in walk → turn.
3. UMI span-overlap 503s.
4. GA merged walk + sing.
5. Soridormi `source` and multiple-bottle refusal.
6. Planner decoration.
7. Library lookup never fires.
8. Absent abilities escalate to a failing Deep.
9. SC answered "Got it." to Chinese turns.
10. Single-goal timed requests on streaming Fast are unverified.

Need-first frozen experiment (done, report-only, new image; README "Need-first contract
experiment"; 26 cases including 4 indirect ones):
- The Planner's need texts are accurate, but its own `covered_by` judgment substitutes
  (library 11/15). Do not trust model self-assessment of coverage.
- An Agent-side check (BM25 of the Planner's need text over the catalog; a gap exists when the
  top match is not loaded) found 15/15 library gaps with the target first, and gave 6/6
  controls no false gap.
- Second call with the searched contracts: target chosen in 13/13 library cases, 9/13
  Host-accepted. The remaining rejections are pre-existing decoration or empty source refs.
- Latency is unchanged or lower.
- Open: a no-match need (backflip) must become an honest unavailable instead of escalating
  to Deep; "make coffee" drifts to "acquire and deliver" (meaning).

Next:
1. Owner review of the experiment and the Charter draft. Proposed contract: needs-first
   without `covered_by`; Agent check by search; at most one re-plan; no-match is unavailable;
   Deep removed.
2. Implement it with Deep removal, migrate the replay corpus, run the gate and a live cohort.
3. Rebuild and qualify the laptop profile image.

## Previous delivery — Deep Planner Work is WorkDAG dependency topology, 2026-10-09

Base: `origin/main` `ede7acc15` (Fast WorkDAG). Owner decisions on 2026-10-09:
- Converge the Deep Planner next.
- Ignore the "同时" chaining (model ability, LoRA later).

Problem: `PlannerModelStep` is shared by Deep, multi-goal Fast and Evidence re-entry
`new_work`, and it still carried a model-authored `timing` label. The Deep decoder also
removed `parallel` for Capabilities not declared parallel-safe
(`nonparallel_capability_ids`). So a Deep Plan could not state a dependency. It could only
say "with the neighbour", and physical Work was forced sequential. This is the same
contract defect as the Fast one, which is corrected by Charter principle 43 and the
owner's concurrency rule.

| Order | Module / owner | Actual (before) | Expected | Verdict |
|---|---|---|---|---|
| 1 | Deep/multi-goal decoder contract (`planner_schema`, `PlannerModelStep`) | `timing` S/P, P removed for non-parallel Capabilities | `depends_on` WorkDAG topology | incorrect (earliest) |
| 2 | Host materialization (`materialize_planner_output`) | passes model timing through | derive groups from dependencies and Capability resources | symptom of 1 |
| 3 | Resource `plan_requires` check | "must be sequential" | a provides from a dependency ancestor | symptom of 1 |
| 4 | Runtime | executes timing groups | unchanged: executes Host groups, never merges adjacent ones | correct |

Repair:
- `PlannerModelStep.depends_on` replaces `timing`. It may cite earlier steps, or completed
  retained Work, which counts as already satisfied.
- `materialize_planner_output(..., capabilities=)` calls
  `planner_validation.schedule_planner_steps`. This validates references (later or unknown
  references fail closed), applies the shared `work_execution_groups` (DAGEngine waves with
  a resource split, the same function as Fast), and records `depends_on`/`execution_group`.
- The resource `plan_requires` check uses dependency ancestry.
- `parallel_plan_contract_errors` checks each `execution_group`.
- The decoder requires `depends_on`. `nonparallel_capability_ids` is removed.
- Prompts: the Deep and re-entry guidance now gives dependencies instead of "Physical Work
  remains sequential".
- Host-authored fallback Plans keep explicit timing.
- Docs: `work_dag.md`, `EXECUTION_LANES_AND_COORDINATION.md`,
  `COGNITIVE_RUNTIME_ROLLOUT.md`, `HUMAN_LIKE_INTERACTION_CONTRACT.md` and
  `COGNITIVE_TURN_LOOP.md` (stale "remain sequential" text corrected).
- Replay corpora migrated and re-frozen at revision 21:
  - `workflow_scenarios`: 1,700 Deep, 1,800 Fast and 100 `new_work` replies migrated;
    requests recaptured.
  - The `plan_conflicting_resource` family (100) now expects `complete`, because
    conflicting resources serialize instead of being rejected.
  - `benchmarks/integration/scenarios` (5 cases).

Evidence (`.chromie/acceptance/workdag-deep-20261009/`):
- Canonical gate from a clean worktree (HEAD + this patch): policies 0, docs 0, test
  ownership 0. `run_tests.sh` exit 0: 169 / 4,040 / 5 skips / 1,065 subtests / 20 legacy.
- Strict replay on the exact patch: 6,000/6,000, zero model calls
  (`strict-replay-final/`; `expected_nonexecuting_rejection` 200, `expected_rejection` 2,500,
  `observed_expected_state` 1,800, `pass` 1,500).
- Main-checkout pytest: only `test_documentation_authority` fails (7). The cause is the
  peer's nested `.claude/worktrees/` checkout, not this patch.
- Frozen native Deep contrast (`deep_contrast.py`): 56 Deep requests (7 families × 4
  actions × 2 forms), baseline (old requests) vs candidate vs candidate_repeat. Each arm runs
  on a fresh SGLang lifetime. **In progress at commit time; not adjudicated.**
  - Observed so far: baseline outputs reproduce byte-identically across a restart (23/23
    against the aborted first run).
  - Baseline cross-field schema failures (e.g. `clarify` with steps) exist before this change.
  - Adjudicate with `deep_adjudicate.py`.
- Live: **not run**. The deployed Agent (`workdag-deps-20261009`) does not contain this patch.

Known failures:
1. The Planner chains "同时" Activities (owner: model ability, LoRA later).
2. Invented clarification in walk → turn.
3. UMI overlapping-span 503s.
4. GA merged walk + sing.
5. Soridormi ignores `source` and refuses when several water bottles are visible.
6. Planner decoration.

Next:
1. Adjudicate the Deep contrast.
2. Rebuild and deploy the Agent; tag the current image `pre-workdag-deep-20261009` as rollback.
3. Live cohort on a fresh lifetime: the 12 rev7 cases plus `nod_and_say_hello`,
   `walk_then_report_completion`, `multi_goal_nod_then_blink`,
   `debug_bundle_run_15_while_singing` and `weather_then_chinese_walk_blink_song`.
   Deep runs only on Fast escalation or continuation, so check the trace for `/deep-plan`.
4. Collect one bundle and judge every case.

## Previous delivery — Fast Work is WorkDAG dependency topology, 2026-10-09

Base: `origin/main` `690bee160`. Owner request: fix the lone-`parallel` failure. On review the
owner set the design: Planner authors a WorkDAG, and DAGEngine semantics decide execution.
Also: "Physical WorkDAG nodes remain sequential" is wrong; actions run concurrently when their
resources do not conflict.

Observed: 6/16 retained Fast plans that used `parallel` failed Host's "contiguous group of 2
or more" rule. This included must-pass "看着我三秒，同时眨两下眼睛", planned as [look S, blink P].
7 plans "passed" but ran the gestures after the delivery instead of alongside it. The model
uses P to mean "with the previous Activity"; the contract meant "every member marked".

| Order | Module / owner | Actual | Expected | Verdict |
|---|---|---|---|---|
| 1 | UMI | one Responsibility, no typed relation | same | correct |
| 2 | Fast DTO/decoder contract | per-Activity timing label; groups = contiguous P | WorkDAG `depends_on` (Charter 43, work_dag.md) | incorrect (earliest) |
| 3 | Fast Planner model | [look S, blink P] | dependencies | symptom of 2 |
| 4 | Host | rejects the lone P; the whole turn fails | validate the DAG, derive groups | symptom |

Repair:
- `FastPlannerCapabilityActivity.depends_on` replaces `timing`.
- The decoder requires `depends_on`. A Capability that cannot run in parallel is not offered to
  both ends of a typed `parallel_with`, so that case escalates.
- Host checks: dependency references, typed relations, and `fast_activity_execution_groups`
  (DAGEngine waves with a resource split).
- `FastPlannerAdvance.metadata.execution_groups`.
- Canonical steps are ordered by group, with `depends_on` and `execution_group` metadata.
- Runtime flushes on a group change, in plan validation and in execution.
- Early safe reads are parallel only when independent and parallel-safe.
- Reuse identity drops timing.
- Duplicate idempotent reads collapse regardless of dependencies.
- The prompt gives dependency guidance.
- Fixtures: `scripts/behavior_scenarios.canonical_step_dependencies`.
- Docs: Charter, AGENTS, work_dag, EXECUTION_LANES, COGNITIVE_RUNTIME_ROLLOUT.

Evidence (`.chromie/acceptance/provider-source-branches-20261009/`):
- Clean-worktree gate exit 0: 169/4,040/5 skips/1,065 subtests/20 legacy
  (`run_tests_rev7_clean.log`).
- Strict replay 6,000/6,000 (`strict-replay-rev7/`).
- Frozen `contrast3.py`, rev7 vs rev6 on fresh lifetimes: 37/37 reproducible, 0 invalid
  dependencies. Near-tie flips go both ways.
- Live `live-rev7/` (12 cases, bundle `chromie_debug_bundle_20261009_190505`): 6/12 pass.
  - Concurrent delivery ∥ blink observed.
  - Sequences ran in order.
  - The lone-parallel class is gone.
- Focused rewording (`deps-focus/`) left simultaneity chained. It was rejected; prompt
  iteration stopped.

Known failures:
1. The Planner chains Activities asked to happen together (look → blink). Both run, but not
   together. The likely lever is UMI typed `parallel_with` or a stronger model.
2. Invented clarification in walk → turn.
3. UMI overlapping-span 503s.
4. GA merged walk + sing.
5. Soridormi ignores `source` and refuses when several water bottles are visible.
6. Planner decoration (blink, wave) persists.
7. Deep Plans still use timing labels.

Next: owner decision on the simultaneity lever, then Deep convergence.

## Previous delivery — Perception can ground a provider-owned resource source, 2026-10-09

Base: `origin/main` `08f018296`. Owner-requested defect: the Planner marked the water
`source` `known` without evidence. Owner decisions: option A (a source may cite what
Chromie sees) and "trust what you see" when a stated place and an observation disagree.

Observed (live, HEAD, ambient perception running): for "sure" and "Chromie, please bring
me some water." the Planner wrote the observed "5.32 m in front" or "4.039 m behind" into
`source` and cited the person's "sure"/"bring". Host accepted, because it checks only that
a span exists. Native decoding also ignored the `allOf if/then`, so uncited
`{"status":"known"}` reached Host and failed.

| Order | Module / owner | Input → actual output | Expected | Verdict |
|---|---|---|---|---|
| 1 | Ambient perception → Situation | scene → established "bottle of water, 4.039 m behind" | same | correct |
| 2 | UMI | turn → resource Responsibility, no place | same | correct |
| 3 | Fast decoder contract | user spans the only citation path; `if/then` unenforced | status + span or observation | incorrect (earliest) |
| 4 | Fast Planner model | copies the observed place, cites "bring" | cite the observation | symptom of 3 |
| 5 | Host grounding | accepts (span exists) | reject observed values cited to the person | gap, now closed |
| 6 | Soridormi | ignores `description`/`bindings`, finds the object itself | same | correct |

Repair:
- `FastPlannerSituationArgumentSource` (`shared/chromie_contracts/plan.py`).
- `situation_source_observations()` (`agent/app/planner_context.py`): established,
  perception-only interpretations, shared by the decoder and the Host.
- `_provider_source_status_branches` (`agent/app/planner_schema.py`): `{"status":"unknown"}`
  with no citation, or `{"status":"known"}` with a span or observation. The Planner never
  retypes a place.
- Host checks (`agent/app/planner_fast_validation.py`).
- `observed_context` resolution (`orchestrator/runtime/cognitive_runtime.py`).
- Scoped prompt guidance (`agent/app/planner_prompt.py`).
- Docs: `docs/RESOURCE_ACQUISITION_AND_DELIVERY.md`, `docs/HUMAN_LIKE_INTERACTION_CONTRACT.md`.

Evidence (`.chromie/acceptance/provider-source-branches-20261009/`, README.md):
- 18 regressions in `tests/test_intent_only_handoff.py`, red on `08f018296`.
- Canonical gate in a clean worktree: exit 0, 169/4,031/5 skips/1,065 subtests/20 legacy
  (`run_tests_rev6_clean.log`); docs recheck with these records passes. The main
  checkout's docs check scanned another session's `.claude/worktrees/` and failed for that
  reason only.
- Strict replay 6,000/6,000 with zero model calls (`strict-replay-rev6/`).
- Frozen contrast `contrast2.py` / `manifest2.json` (37 requests). Six candidates were tried;
  rev1–rev5 left perception numbers cited to the person or drifted weather. rev6 runs on a
  fresh SGLang lifetime and reproduces 37/37 (`c2_candidate_rev6_fresh*`):
  - water visible: 4/4 cite the observation;
  - weather and speech: byte-identical to the baseline;
  - b15: cites the milk it sees.
- Live (`live-water-rev6/`, bundle `chromie_debug_bundle_20261009_144736`): 4/4 delivery turns
  cite the correct observation; 1/4 cases pass end to end.

Known failures:
1. A lone `parallel` auxiliary Activity (blink) fails Host's "parallel group of 2 or more"
   check. This is a pre-existing decoder/Host mismatch, in bundles since 2026-10-07, and it
   failed 3/4 live cases.
2. Milk is cited for water when only milk is visible (synthetic, 3/3).
3. "known" plus "sure" when nothing is observed (legacy no-Situation captures, 7/9).
4. SC latency/TTS start (case 1).
5. SGLang greedy outputs depend on server-lifetime history. Restart before each contrast
   arm; `--enable-deterministic-inference` is an unqualified owner decision.

Next: encode the parallel-group invariant in the Fast decoder (same class as this fix),
then rerun the live water cohort.

## Previous delivery — Text harness runs live ambient perception, 2026-10-08

Base: local commit `89de55fb5`. Owner-requested defect: the text acceptance Host never
started the ambient scene poll (only `VoiceAssistant.run()` did), so every live text turn
planned with `situation: {}`. Repair: `VoiceAssistant.start_soridormi_ambient_perception()`
is the one idempotent starter used by `run()`. `scripts/interaction_text_mujoco_check.py`
primes one read after a passing preflight, starts the same poll and records
`ambient_perception.json`/summary `ambient_perception`. Regressions in
`tests/test_soridormi_scene_perception.py` are red→green; the canonical gate passes
(169/4,013/5/1,065/20, `.chromie/acceptance/ambient-perception-text-20261008/run-tests.log`).
Live proof is NOT done. The default Soridormi scene has zero objects. The
`thirst_water_delivery` scene fails to start: its scenario runner opens GLFW on `:0`
even with `--no-viewer` and with `MUJOCO_GL=egl`. That is a Soridormi environment defect,
not edited here. The simulator and MCP runtime were stopped by `run_scenario.sh` and must be
restarted before any live run.

Next (owner-requested): the water source is marked `known` without evidence. Replace the
decoder-ignored `allOf if/then` in `agent/app/planner_schema.py` with two `oneOf` branches:
unresolved forbids the source span, known requires it. Then run strict replay; a freeze
recapture is likely, using `.chromie/acceptance/water-context-repair-20261007/` tooling.

## Previous delivery — Information-query free text must cite its source span, 2026-10-08

Pre-delivery base: local commit `20e394a3c` on pushed `origin/main` `23d924ee2`. The
expected resume revision is the latest commit containing this checkpoint and
[Handoff](HANDOFF.md). The owner chose option A: required free-text inputs cite spans like
numbers.

Defect: "今天北京下雨了没有？" planned `location: "Beijing"` with no span. The Host admits
an ungrounded required string only as an exact literal or with a span, so it rejected the
plan; the person heard "no location". This was the most frequent live Planner rejection
(8 on Oct 8).

| Order | Module / owner | Actual | Expected | Verdict |
|---|---|---|---|---|
| 1 | UMI | information Responsibility with the city in its outcome | same | correct |
| 2 | Fast decoder contract | `argument_sources` optional; strings excluded from forced spans | require the span the Host needs | incorrect (first wrong boundary) |
| 3 | Fast Planner model | translated city, no span (the prompt already asks for a span or a literal) | span or literal | symptom of 2 |
| 4 | Host grounding | rejects the unbound input | same | correct |

Repair:
- `agent/app/planner_schema.py`: for `fast_capability_acquires_information` Capabilities,
  required non-enum strings join `required_source_inputs`. Trusted-grounded inputs
  (`target_ref`, memory IDs) and provider-resolved `source` stay excluded.
- `agent/app/planner_fast_validation.py`: a same-script cited value must appear in its
  span (Latin is word-bounded); cross-script renderings stay allowed, since they cannot
  be checked mechanically.

Evidence (`.chromie/acceptance/string-input-provenance-20261008/`):
- Native contrast (`contrast.py`, frozen `manifest.json` + `corpus/`, 20 requests):
  baseline/repeat identical. Genuine weather cases with Host-accepted provenance 10/16 →
  16/16, and all 56 candidate citations pass the new Host check.
  Known weakness: three clock questions misrouted to weather can now cite the whole
  sentence for `current_location`, which passes cross-script and fails later at the
  provider.
- First broad attempt (all required free-text strings): the canonical gate caught
  Planner-authored vocal `text` and was narrowed to information queries.
- Tests:
  - `test_translated_required_location_must_cite_its_source_span` asserts the decoder
    schema itself; red→green.
  - `test_fast_query_location_cites_span_of_own_intent_and_original_source` replaces the
    literal-only test; same-script negatives remain rejected.
  - One fixture now cites its span.
- Strict replay 6,000/6,000 with zero calls; canonical gate exit 0 (169/4,011/5/1,065/20).
- Live (Agent rebuilt, same 13 cases): 8/13 (4/13 before); 10/11 weather answers correct.
  Remaining: SC latency ×2, 内乡县 mistranslated ("Xiang County"), date/time misrouted to
  weather. Bundle `/home/chromie/Downloads/chromie_debug_bundle_20261008_174448.tar.gz`.

Next, as owner-requested, one item each:
1. The text harness never starts the ambient perception loop, so live text Situation is
   empty.
2. The provider-owned water `source` is marked `known` without evidence, because the
   decoder ignores the `if/then`.
3. The clock-vs-weather Capability choice.
Live water proof needs Soridormi's `thirst_water_delivery` scene; the default scene has
no objects.

## Previous delivery — SC answers ordered after body Work are spoken again, 2026-10-08

Pre-delivery base `23d924ee2debbf0a9588984641a1c6bf2ba78ae7` (pushed `origin/main`).
The expected resume revision is the latest commit containing this checkpoint and
[Handoff](HANDOFF.md). One defect, one focused fix.

Defect: "Blink twice and tell me a short joke." and "点两下头，再跟我说声你好。" executed
the body action, but the SC answer ordered after it was never played. Two such cases
passed mechanically. An A/B on earlier source reproduced it
(`.chromie/acceptance/sc-act-identity-20261008/ab-original-code/`).

| Order | Module / owner | Actual | Expected | Verdict |
|---|---|---|---|---|
| 1 | Fast Planner | blink step, then a `complete_response` need after it | same | correct |
| 2 | SC | joke act, `final`, `context_grounded`, need covered | same | correct |
| 3 | Response projection | `timing=after_capabilities`, `ordered_context_grounded_after_work=True`, `source=social_cognition` | same | correct |
| 4 | Interaction coordinator | speech dropped as result-deferred, because the exemption still required `source=planner_communicative_activity` | keep it after the blink | incorrect (first wrong boundary; stale since the Sep 14 SC split, `ec4a5c268`) |
| 5 | Re-entry | none, since no result Evidence was needed | — | the answer was lost |

Repair: `orchestrator/runtime/interaction_coordinator.py` exempts the trusted
`social_cognition` source too. The trusted projection sets that flag only for
context-grounded speech whose Goals are not executable, so result claims about Work stay
deferred to terminal Evidence.

Evidence (`.chromie/acceptance/after-work-speech-20261008/`):
- New regression `test_social_cognition_answer_ordered_after_body_work_is_spoken`
  red→green.
- Strict replay 6,000/6,000 with zero model calls; Level A `multi_goal_daily_life` 10/10;
  canonical gate exit 0 (169/4,007/5/1,065/20).
- Live class (simulator executed): 5/6 automatic passes. Both originating answers are now
  played after the body action. The joke case still fails because the initial "Got it."
  first PCM took 4,786 ms against the 3,500 ms start deadline. It was cancelled, SC
  delivery was reported failed, and the scenario counted two speech outputs where it
  allows one. That TTS start latency is the known Oct 7 issue and is not repaired here.
  Bundle `/home/chromie/Downloads/chromie_debug_bundle_20261008_162840.tar.gz`.

Next: Planner provenance/readiness repair, the dominant live failure (water source binding,
weather location, clock vs weather choice, "exact owned Goal source quote"). After that,
latency, including the TTS start deadline above.

## Previous delivery — GA-triggered Planner revision no longer erases a valid first plan, 2026-10-08

Pre-delivery base: local commit `05af832a4` (SC act identity) on top of fetched
`origin/main` `601b73f09`. The expected resume revision is the latest commit containing
this checkpoint and [Handoff](HANDOFF.md). This implements the owner's two-Planner decision
recorded in the SC act-identity delivery below. One defect, one focused fix.

Defect: when GA requested another Planner pass while the UMI-triggered plan was still
running, the Host took whichever plan finished first. A GA plan that failed fast (HTTP 400,
Oct 7 turns `3e47eecb` "把那个拿给我" and `81b5ee51` water "sure") cancelled the still-valid
UMI plan, and the person heard a technical-error apology. A UMI failure also ended the turn
before a requested GA plan could finish. This violated Charter "concurrent model completion
order never establishes semantic priority" and line 725.

| Order | Module / owner | Actual (old) | Expected | Verdict |
|---|---|---|---|---|
| 1 | UMI → Fast Planner stream | valid plan still running | finish | correct |
| 2 | GA → Fast Planner primary | HTTP 400 after 0.3 s | — | failed (separate decoder defect, fixed in `4208f001a`) |
| 3 | Host plan settlement | first finisher wins: cancels UMI plan, raises GA failure | GA success supersedes; GA failure keeps the valid UMI plan | incorrect (first wrong boundary) |
| 4 | SC | truthful failure update | the planned answer | symptom |

Repair in `orchestrator/runtime/cognitive_runtime.py` (`_resolve`):
- The early wait never cancels by completion order. A running or failed UMI plan is
  settled after GA.
- Settlement runs after the goal-state SC launch, so communication is never blocked
  behind planning. A successful GA plan supersedes; a failed GA plan (exception or
  contract-failure escalation) falls back to a valid UMI plan when it covers the
  GA-requested refs.
- Metadata `ga_revision_failure_contained`; the failure of either plan is retained in
  `stage_diagnostics`.

`docs/COGNITIVE_TURN_LOOP.md` states the failure rule.

Evidence (`.chromie/acceptance/ga-revision-containment-20261008/`):
- Four new regressions in `IndependentPlanningTests`: red on original, green now.
- `test_silent_goal_update_keeps_delivered_initial_response_on_late_work_failure`
  previously had a valid first plan and asserted the old erase-on-GA-failure outcome.
  It now fails both plans so it keeps covering the delivered-response containment it
  was written for.
- First canonical attempt failed: a deadlock, because settlement awaited the GA plan
  before goal-state SC started. It was fixed by moving settlement; the final strict
  replay and gate are recorded in Handoff.
- Live (3 retained race episodes): the race path ran once (water "sure", `90114e51`).
  The UMI plan was rejected by Host stream validation and the GA plan by readiness
  ("exact owned Goal source quote"), so the turn failed honestly after waiting for both.
  Before this fix the turn would have ended at the UMI failure. Keeping a valid first
  plan is not yet live-proven. The other two cases failed in Fast clarification
  contract and LLM transport (`Server disconnected`). Bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20261008_160823.tar.gz`.

Next, one item each: deliver `final`-phase SC speech after body Work; then the Planner
provenance/readiness repair (now the dominant failure in every live run); then latency.

## Previous delivery — SC act identity no longer copies Planner Work IDs, 2026-10-08

Pre-delivery base `601b73f09dfbcb0175233219f96d7b6ee11f8f89` (fetched `origin/main`
matched). The expected resume revision is the latest commit containing this checkpoint
and [Handoff](HANDOFF.md). Audit follow-up item 2a: one defect, one focused fix.

Owner decision (2026-10-08): keep both Planner triggers. The UMI-triggered Planner acts
on the current state. The GA-triggered Planner runs only when continuity changes Work, and
must revise without erasing a valid first plan. This conforms to Charter lines 559-585 and
725, so no amendment is needed. It replaces the pending Oct 7 request to keep one primary
Planner per scope.

Defect: SC repeated delivered words under a new act ID (two real playbacks). Retained
SID `6f08c738`: initial SC delivered `greet_and_status`; a later work-state SC request
carried the Planner need fact `"activity_id": "resp_001"` and SC returned the same words
as new act `resp_001`.

| Order | Module / owner | Actual output | Expected | Verdict |
|---|---|---|---|---|
| 1 | Fast Planner / HOW | `complete_response` activity `resp_001` | Work-side identity | correct |
| 2 | Host need projection | SC need `facts` = whole activity, including `activity_id` | obligation facts only | incorrect (first wrong boundary) |
| 3 | SC / communication | copies `resp_001` as its own act ID with delivered words | reuse `greet_and_status` or stay silent | incorrect given misleading input |
| 4 | Host delivery | new act ID, so it is played again | — | correct per identity contract |

Repair: in `orchestrator/runtime/cognitive_runtime.py` (Fast streaming-advance Need
producer), the Host omits `activity_id` from the Need `facts`. The identity stays in
`need_id` and before/after step order, and no consumer read it.

Evidence (`.chromie/acceptance/sc-act-identity-20261008/`):
- Native contrast: all 16 retained SC requests carrying the fact, model fixed, temperature 0.
  The candidate removes only that key; baseline repeated identically. Planner ID copied
  7→0, fresh-ID duplicates 4→0, Schema errors 0→0. c03, c06 and c15 now reuse the
  delivered act. c00, c05, c07 and c09 keep equivalent meaning. c11 avoids the duplicate
  but chooses `silence` with its need pending instead of reusing `ask_help_type`; this
  SC need-accounting choice remains open.
- Unit regression red→green; strict workflow replay 6,000/6,000 with zero model calls
  (no freeze recapture); canonical gate exit 0: 169/4,003/5 skips/1,063 subtests/20 legacy.
- Live (dirty diagnostic identity; Agent `2b4f2298…` verified; simulator executed): 11
  former duplicate cases; 34 SC calls with 0 copied IDs, 0 duplicate replays and 7
  delivered-ID reuses; 3/11 automatic passes; no same-scope Planner race occurred.
  Failures:
  - water ×3: Fast `acquire_and_deliver_resource` contract invalid;
  - no-motion identity: Fast terminal contract;
  - reminder: Deep structured output;
  - three identity/greeting latency misses (SC 5.2–10.0 s).
  Bundle `/home/chromie/Downloads/chromie_debug_bundle_20261008_153201.tar.gz`.
- New pre-existing defect: SC answers ordered after body Work (`delivery_phase=final`,
  `after_step_ids`) are authored but never scheduled for TTS in executed runs. The joke
  and "你好！" after blink/nod were never heard; two cases nonetheless passed mechanically.
  An A/B on the original code (`ab-original-code/`) reproduces it with the copied IDs.
  No earlier executed run ever exercised this path.

Next, one item each:
1. GA-triggered Planner as a non-destructive revision. Priority comes from newer
   continuity state, not completion order; GA plan failure falls back to the valid UMI
   plan; UMI plan failure waits for a requested GA plan.
2. Deliver `final`-phase SC speech after body Work completes.
3. Provenance repair (UMI typing nondeterminism; Planner clock/weather choice).
4. Latency from end of input.

## Previous delivery — Evidence-bound claim oracle, 2026-10-08

Checkout `main`, pre-delivery base `4208f001a841abb86d852398d088f6da82a0c62f`
(fetched `origin/main` matched before edits). The expected resume revision
is the latest commit containing this checkpoint and [Handoff](HANDOFF.md). This is the
first item of the owner-approved audit follow-up order: (1) keep unsupported changing-fact
answers as hard failures, (2) SC act identity and live proof, (3) a qualified provenance
repair, (4) latency measured from end of input. One defect and one focused fix per delivery.

Defect: in the Oct 7 cohort (SID `a0437395`), "今天几号，星期几？" received
"今天是2025年5月22日，星期四。" with `inform/context_grounded`, no Evidence and no clock
call. The SC prompt contained no date or time source. The harness recorded only a missing
clock observation, and the same-agent triage filed it as a possible profile gap.

| Order | Module / owner | Actual output | Expected | Verdict |
|---|---|---|---|---|
| 1 | UMI / WHAT | r1 `speech/turn`, Planner requested | `information/goal` per prompt line 150 (UMI typed it so on Sep 23 and Oct 8) | incorrect, nondeterministic |
| 2a | SC / communication (concurrent) | fabricated date as `inform/context_grounded`, no Evidence | pre-evidence receipt or silence | incorrect |
| 2b | Fast Planner / HOW (concurrent) | `clock.local` with empty source refs → `fast_stream_contract_invalid` | clock activity bound to r1 | incorrect |
| 3 | Host / containment | Planner failure suppressed as optional because r1 was speech-only and SC had spoken | correct under the speech typing it received | correct given input |
| 4 | Acceptance harness / test evidence | `missing expected observation` only | hard provenance failure | incorrect (repaired here) |

Repair, test-evidence owner only: scenario turns whose answer must come from capability
Evidence declare `require_evidence_bound_claims`. In those turns, an SC `respond` or `inform`
act that cites neither Evidence nor a Host-established need is a hard
`provenance:unsupported_evidence_claim` failure. This is a typed-field check; wording is
never read. Thirteen pure clock/weather lookup turns declare it; mixed social+lookup turns
do not. UMI, SC, Planner, Host, prompts, Schemas and the workflow freeze are unchanged.

Evidence (`.chromie/acceptance/evidence-bound-claims-20261008/`):
- Focused: 40 tests pass. The original harness fails the six evidence-bound regressions
  (hard failure, two integrity-stop variants, three controls).
- Canonical `./scripts/run_tests.sh` exit 0: 169 benchmark, 4,002 main, 5 skips,
  1,063 subtests, 20 legacy. Evidence-class Level A 6/6; library check 15 classes,
  45 Level A, 79 live.
- Retroactive re-score of 713 retained flagged-turn summaries flags only the Oct 7
  fabrication. Only 19 of those summaries contain SC acts, so the false-positive check is narrow.
- Live (dirty-source diagnostic identity; Agent source `2b4f2298…` matched; simulator
  executed, `--keep-going`): 13/13 attempted, 4 automatic passes, 0 unsupported claims
  across 24 SC acts. Seven cases failed at Fast Planner `chromie.weather.lookup.location`
  provenance, including clock questions routed to weather lookup and a follow-up that lost
  the prior city. One SC delivery failure (scheduled 2, played 0); one weather provider
  failure for 河南省内乡县. Same-agent review: Chongqing ×3 passes grounded; Shanghai partial
  (temperatures, no cold judgment). Failure updates cite an internal "no location" cause
  that the user had in fact supplied. First playback was 13.2–15.5 s after input.
  Bundle `/home/chromie/Downloads/chromie_debug_bundle_20261008_134254.tar.gz`.

Not established: no production repair of UMI typing, SC fabrication or Planner provenance,
and no voice, physical or release qualification.

Next (item 2, one focused fix): the SC duplicate-speech identity defect. The Host projects
the whole Fast Planner communicative activity into SC need `facts`
(`orchestrator/runtime/cognitive_runtime.py`, streaming-advance need producer), including
the Planner's own `activity_id`. In retained Oct 7 calls, 6 of 12 SC requests carrying that
fact reused it as the SC act ID. Both observed different-ID duplicate playbacks coincide
with that reuse. Freeze an SC contrast corpus from retained requests before changing the
projection. Owner approval for same-scope Planner consolidation is still pending, and it
blocks the water live proof.

## Previous isolation — decoder profile and late SC failure, 2026-10-07

Checkout `main`, pre-delivery base `ee74ee8f9cc76982e5a06170e50f2601d06f5788`;
fetched `origin/main` matches. The owner authorized commit and push of this
in-progress patch; the delivery revision is the commit containing this checkpoint
and handoff. This records local repairs and open qualification, not a complete fix.
Fixed deployed candidate `chromie-gemma4-12b`; no model promotion or scheduler change.

Implemented scope: UMI accepted-effect prompt/context projection (all facts retained),
explicit default array `items={}` in the shared decoder projection, preservation of the
primary Planner title through readiness/lookup wrappers, and typed Social Cognition
request/validation failures at the existing Host containment boundary. Canonical
semantic authority, DTO cardinality, confirmation and fail-closed Work remain intact.
The proposed relocation of native `oneOf`/`anyOf` behind `allOf` was withdrawn:
actual XGrammar admitted forbidden silence/covered. Current projection keeps those
alternatives intact; exact grammar proof rejects covered silence and accepts pending silence.

Observed failures: the original `sure` is now physical water intent, but two same-scope
Planner calls race and the canonical call previously failed HTTP 400 before inference.
The readiness wrapper had dropped the role title, bypassing array/shape/format settings.
An exact native replay with the retained title now returns HTTP 200, stop, complete JSON
in 22.959s; raw Schema and semantics still fail (invented location gaps and deferral).
All provider-owned source-resolution metadata was present in that request; missing
capability projection is not established. Planner correctness remains open.

The next bound aggregate stopped at compound UMI r4 relation-only/overlapping provenance
(1/79 attempted, 78 unrun; bundle `chromie_debug_bundle_20261007_171342.tar.gz`).
Focused water then stopped at its greeting: SC delivered the greeting, later emitted
forbidden silence/covered, Agent returned 422, and Host appended a generic apology.
Its bundle is `chromie_debug_bundle_20261007_172100.tar.gz`; water turns were unrun.
The Host repair classifies thrown RuntimeError/ValueError as `social_cognition` failure:
existing containment preserves a completed speech-only response while retaining failure
telemetry; body Work still fails and cannot dispatch. Four valid red regressions pass green;
combined focused suites pass 42 tests and 85 subtests. No corrected live proof yet.

Qualification: accepted-effect UMI 14 native contrasts pass that narrow scope, with
Chinese open-help language still unqualified. Frozen 25 compound/need contrasts:
baseline has six Schema/Host failures; the first candidate is mechanically valid but
loses relations/grouping. A later focused prompt improves ordering but does not qualify
independent effect/body-family coverage. Neither candidate is promoted. Field-order
experiment suffered global host OOM killing the provider scheduler at 17:35:27 +08
(112449912 kB anonymous RSS); causative compiler growth is unproven. It is an incomplete
service-integrity run, not five semantic failures. One bundle
`chromie_debug_bundle_20261007_173617.tar.gz`; provider auto-recovered with changed runtime
identity. Further syntax probes use isolated bounded containers, no GPU inference.

Historical freeze 19 strict replay passed 6000/6000, zero candidate calls; its full gate
passed 169 benchmark, 3985 main, five skips, 1063 subtests and 20 legacy tests, but covers
the withdrawn decoder projection. Final-source request capture passes 6000/6000 and five
prototypes; freeze 20 retains every non-request field and strict replay and the first full canonical gate passed; latest Host repair gates are recorded below. Agent was rebuilt and source-verified before the latest diagnostic live runs; final Host live proof remains pending.
No current voice, physical microphone/speaker/robot, release or target qualification.

Evidence root: `/home/chromie/github/chromie/.chromie/acceptance/water-context-repair-20261007/`.
Bundles above are under `/home/chromie/Downloads/`. Native receipts are in
`mixed-decoder-branches/`; red/green containment logs and request-only capture are retained.
Open blockers: UMI obsolete sibling-ref instructions versus natural WHAT, Planner semantic
completeness/provenance, same-scope invocation race (explicit owner scheduling approval
pending), and provider source-binding truth (provider not invoked in blocked episodes).

### Follow-up isolation — silent SC state erases a completed response

Corrected Agent source digest `2b4f22989ef91b38b4ec210d85c83ab77f8dbd40af999ac0b7062d897791d7c8`
matched the checkout before the next bound aggregate. That aggregate's first compound
case executed walk10s/vx0.2, default-count2 nod, then left turn in simulation and ended
safe_idle. It still fails: UMI omitted explicit ordering in outcomes, and a7-char
acknowledgement's first PCM took4883.5ms against3500ms start deadline. One bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261007_181405.tar.gz`.
1/79 attempted,78unrun; reviewed fail, not qualification. Provider performance cause
beyond this observed deadline miss remains unproven.

Same-runtime focused water attempted greeting and thirst, not accepted-water turn.
Greeting is mechanically accepted but SC authors identical words under `greet_and_status`
and later `resp_001`, causing two real synthetic playback occurrences. Thirst UMI is
one turn-scoped speech Responsibility; SC delivered `offer_water_help`. GA then requests
goal-state SC, which correctly chooses silence. Host replaces its sole social-task handle
with that silence. The redundant canonical Planner's score/status DTO fails; completed
speech containment now sees only silence, requests a failure update and leaves the
already addressed interaction Goal open/planning. One bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261007_181616.tar.gz`.
Every attempted turn reviewed fail; turn03unrun. No water provider invocation.

Current Host repair retains the initial task handle and joins original/current state tasks
without replacing delivered speech by silence. For newly materialized speech-only Goals,
it invokes the existing source-ref/Goal-ID completion join from SC respond + actual delivery.
Two regression cases prove retained speech and actual Goal closure versus non-speech
receipt: body Work remains error/open, no dispatch. Valid red pointer failure and separate
red lingering-Goal assertion are retained; green combined suites44 tests/85subtests,
adjacent8 tests pass. No scheduling, semantic re-authoring or text deduplication introduced.
The corrected Host source still needs renewed live evidence.

Freeze20: changed2700Fast/1900Deep requests, four prototype Planner requests; all6000+5
non-request records identical, zero candidate calls. Archive SHA256
`6f4c7e7986ead2a6b3bad5b0c2b00e1ecf7398fa69e55f9b69c992319a6ad052`.
Strict6000/6000 and first full gate20 pass:169 benchmark,3991 main,5skips,1063subtests,
20legacy. Those gates precede silent-state retention/closure. Pointer-only strict6000 also
passed. Its full gate was intentionally terminated before completion for the reproduced
Goal-closure repair; it is not a pass. Final-source canonical rerun passed:169 benchmark,3993 main,5 skips,1063 subtests,20 legacy. Final strict replay passed6000/6000 with source unchanged and zero model calls; Level A passed30 distinct cases across six ability classes. Policy, docs, test ownership and diff checks passed. Receipts: `run-tests-sc-final.log`, `strict-sc-final/`, `level-a-sc-final/`. These are local proofs, not live qualification.

Another private compound prompt candidate completed all25 fixed-model primary transactions:
source-language and retained order improve, but four hard cases fail (politeness creates
an extra speech result; mixed body-family grouping; one missing joke plus overlapping
provenance). Candidate rejected, source prompt unchanged. Same-agent post-hoc ledgers are
retained, not independent evaluation or a Runtime repair. The duplicate greeting has a focused namespace contrast in `live-current-water/identity-namespace/`: changing only Planner Need fact `activity_id` to existing name `fast_activity_id` in all three prompt mirrors changed the primary SC output from duplicate `resp_001` to existing delivered act `greet_and_status`. Both native grammars accept either ID. This supports context ambiguity, but the wider SC corpus is unrun and no source projection fix is applied. Pending owner approval is still
required for narrow same-scope Planner consolidation; no scheduler change applied.

Owner scope correction: keep subsequent turns to one defect and one focused fix.
The owner subsequently authorized delivery of the current patch without expanding it.
Resume with one defect and one focused fix per turn. Next candidate is SC act-ID
namespace qualification; do not bundle it with Planner scheduling or compound UMI work.
Final Host live proof remains pending; source and evidence gaps above remain open.

Resume from `/home/chromie/github/chromie`; inspect the retained SC namespace
contrast first, freeze its complete contrast matrix before another native batch, and
keep Planner scheduling and compound UMI repair out of that turn. Local receipts
above already cover the delivered source; do not rerun them just to restate a pass.

```bash
cd /home/chromie/github/chromie
git status --short
rg -n 'activity_id|fast_activity_id|communication_needs' agent/app/social_cognition.py
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

For subsequent live proof, bind a fresh identity and a new evidence directory; do not
reuse `runtime-identity-current.json` or overwrite the retained `live-current-*` runs.
Private evidence and bundles are local artifacts, not distributed by this commit.
Run the frozen full cohort without source changes, stop on hard integrity failure,
collect one bundle and judge every attempted case. No scheduler change is approved.

## Previous resume snapshot — water acceptance still fails, 2026-10-07

Delivery base `main` / fetched `origin/main` was
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6`. This revision combines the
open-ended-help UMI prompt repair, the GA native wire ownership-row bound, the
SC terminal-failure result-accounting repair, regression tests and request-only
workflow fixture recapture. Canonical Schema/Host authority is unchanged. The
delivered revision is the commit containing this checkpoint and [Handoff](HANDOFF.md).

The original text episodes crossed two different boundaries. In SID `a87066b5`,
UMI split “I am a little thirsty, can you help me?” into overlapping speech and
invented information Responsibilities; Host rejected it before GA/Planner/SC. In
SID `d7e6f1a3`, UMI accepted the water delivery request, GA duplicated ownership
of its one source ref, Host rejected it and cancelled speculative planning, and
SC falsely asked for repetition after an internal failure. The source repair
addresses those earliest observed boundaries without creating a second semantic
authority. Direct same-model contrasts/replays passed their reported Schema/Host
checks, but do not establish general live behavior.

The canonical local gate now passes: `./scripts/run_tests.sh` exited 0 (169
benchmark, 3,983 main, five environment skips, 1,023 subtests, 20 legacy Agent
tests); repository policy and docs checks pass. Four relevant Level A ability
classes pass 22/22. Strict request-only workflow replay passed 6,000/6,000.
Evidence is private under `.chromie/acceptance/umi-help-split-20261007/`,
`.chromie/acceptance/ga-duplicate-20261007/`,
`.chromie/acceptance/sc-internal-failure-20261007/` and
`.chromie/acceptance/thirst-offer-20261007/`.

A deployed text aggregate attempted all 79 discovered cases on the current dirty
source; 13 passed automatically and 66 failed, including 59 integrity failures.
The cohort and qualification are incomplete. The Agent endpoint became unavailable
partway through the run, and its runtime identity changed; outage cause is unknown.
One bundle was collected afterward:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_121723.tar.gz`. On the
water dialogue, Chromie offered help on the first turn but UMI reduced “Sure,
water is perfect!” to speech on a follow-up; separately, Fast Planner emitted an
invalid provider-resolved source for accepted “sure”. No physical work was
authorized in those failures. Candidate prompt/decoder experiments were rejected
and reverted because they introduced unsafe or ungrounded results; their retained
contrasts are in the thirst-offer evidence root. No safe general repair of these
new boundaries is claimed.

Next: establish a stable deployed identity and service, diagnose the UMI and
Planner acceptance boundaries from retained packets, and obtain owner approval
before any canonical semantic contract change. Repair the earliest boundary,
rerun focused scenarios and the complete live cohort, then perform narrow
current-revision supervised voice proof and default target-evidence closure.
Physical microphone, speaker and robot proof is still absent.

## Previous patch — open-ended help interpretation, 2026-10-07

Pre-delivery base `main` / `073abb4daad94c8bb419db6b05ba8f6310c4a0a6`
matched fetched `origin/main` before edits. Expected resume revision is the latest
commit containing this checkpoint and [Handoff](HANDOFF.md). At the time of that
patch's initial handoff it was not committed or pushed. The historical planned
delivery sequence was local gate, narrow current-revision voice proof, then
default target-evidence closure; current blockers and resume order are above.

The live text turn “I am a little thirsty, can you help me?” failed at primary UMI:
one response/acknowledgement Responsibility and one internal help-selection
`information` Responsibility cited overlapping source words. The UMI validator
correctly rejected that semantic split; Core returned 503 and Host spoke the safe
retry notice. The existing UMI prompt now states that an open-ended request with
a reported need is one conversational Responsibility unless the person separately
requests an effect, fact or speech act. UMI still owns WHAT; SC owns wording,
Planner owns HOW, GA owns continuity and Host does not repair semantics. No new
model, runtime switch, authority, document or environment variable was added.

Current evidence root: `.chromie/acceptance/umi-help-split-20261007/` (ignored,
private). A frozen eight-case English/Chinese contrast baseline had two primary
source-overlap failures; the selected prompt produced eight Schema/Host-valid
outputs, including the exact English originating turn. Its Chinese open-ended
help outcome remained in English, so bilingual semantic qualification is open.
No current-revision deployed Host/voice claim follows from these direct model calls.
The existing `thirsty_then_water_delivery` general-ability scenario already retains
the original two-turn episode; its full live run remains due.

The five prototypes and complete 6,000-case workflow archive were recaptured
request-only at freeze revision 17. Full replay passed 6,000/6,000 with zero
candidate calls and identical non-request fields; focused workflow replay passed
104/104. The robust-intent Level A class passed 8/8, UMI focused tests passed
44/44 with 77 subtests, benchmark tests passed 169/169, main tests passed
3,981 with five environment skips and 1,023 subtests, and 20 legacy Agent tests
passed. Policy, ownership, pinned Ruff/mypy, configuration, runtime and docs checks
passed. `./scripts/run_tests.sh` did not itself exit 0 in this session: it first
met pre-existing stale ignored freeze files, then a command termination (143),
then 83 stale request-packet failures. Those files were preserved and the pinned
archive restored; the final benchmark and main components passed separately after
request recapture. Do not report the single-command canonical gate as passed.

Next: run the single-command gate in an uninterrupted shell; then run the existing
two-turn thirst/water scenario with the current source and a bound service identity
when the active operator text console can be left undisturbed. Judge the complete
speech, Goal and Work path, not only UMI acceptance. Qualify Chinese outcome-language
and material-need retention before claiming a bilingual UMI fix or default-target
closure. Physical microphone, speaker and robot proof remains supervised.

## Previous delivery — UMI/Planner and historical Memory contracts

Pre-delivery base `main` / `0848b07d14886a0238ca71ceae3aa65fd0bcd103` matches
fetched `origin/main`; upstream was checked before source edits and again after the
native cohort. Expected resume revision is the latest `main` commit containing this
checkpoint and [Handoff](HANDOFF.md). The owner authorized non-model repairs, commit
and push, and explicitly forbids UMI-authored `bindings`.

The current focus remains Goal-driven single-authority architecture.
The active delivery line remains canonical local verification → current-revision
voice proof → default target-evidence closure. Local verification passes; voice and
target closure remain open. No new feature line, semantic owner, Memory store,
runtime switch or model/profile change is introduced.

## Implemented at existing owners

- UMI keeps complete natural WHAT, current-turn provenance, uncertainty and initial
  cognition requests. Primary/Deep Schema, parser and Decision reject the `bindings`
  key, including empty objects. Core rejects nonempty bindings; the shared DTO's
  empty default and read-only retained canonical Goal projections remain internal.
  Earlier Charter prose allowing sparse UMI bindings is removed to follow existing
  principle30. The principle and module responsibilities are unchanged.
- Planner alone extracts Capability parameters. Fast arguments may cite current-turn
  tokens or exact owning accepted outcome tokens with `source_responsibility_ref`.
  Host materializes the selected quote and binds it only to that Responsibility's
  GA Goal; it cannot infer missing meaning, borrow a sibling or fabricate a source.
  Provider-owned source resolution accepts cited reported search clues, while bare
  unresolved source cannot claim a citation. Retained typed constraints remain binding.
- Historical object/location Memory remains Planner context outside current sight.
  Both prompt-entry and cognitive projections retain existing creation/update times
  and source references. A past living-room water delivery suggests where to search;
  it does not prove current presence. This is a controlled projection regression,
  not proof of automatic action persistence, an executed search or actual acquisition.
- Stale UMI scenario/fixture outputs and the template are reconciled without dropping
  material meaning. All6000 workflow records and5 prototypes are request-only
  recaptured: inputs, raw reference decisions, complete meaning, parameters, prior
  Goals, faults, provider outcomes, assertions and splits remain unchanged. Strict
  replay and oracles are not weakened. The complete archive is freeze revision16.
- Superseded checkpoint/handoff narratives and resume commands are consolidated here
  and in Handoff. Historical evidence remains retained and recoverable from Git.
  No maintained document, environment variable or architectural owner is added.

## Current evidence ceiling

Evidence root: `.chromie/acceptance/umi-no-bindings-20261005/`.

| Axis | Observed result |
| --- | --- |
| Implementation | UMI binding authority conflict, Fast source/contextual provenance restriction and Memory timestamp projection loss are repaired at existing owners. Model, initial activation ownership and GA/SC/Host boundaries remain. Other conformance findings remain open. |
| Automatic verification | Frozen bilingual20 before8/20 → final20/20 Schema/Host; exact production wire/pinned native decoder20/20 without inference. UMI1496/Fast204 references valid. Focused215+84 tests pass. Level A19/19 across3 relevant classes. Strict6000/6000 replay passes with zero candidate calls; request-only6000+5 invariants hold. Canonical169 benchmarks,3981 main tests/5 environment skips/1023 subtests and20 legacy Agent tests pass; policy, ownership, pinned static, configuration and docs pass. |
| Target validation | Unchanged baseline79:22 automatic pass/57 fail, same-agent review6 pass/10 partial/61 fail/2 insufficient. Changed-source full79:13 automatic pass/66 fail, review5 pass/7 partial/67 fail. All cases attempted, zero skipped; blocked later turns make cohort/qualification incomplete. Overall behavior improvement is not established.86 native UMI primary outputs contain zero binding keys, but activation/meaning omissions remain. No independent, current voice, physical/audible or default-target qualification. |
| Deployment state | Agent-only source imagebc6577e4… retains original dependency layers; packaged/host source8140dcc3… matches before/after. Model/profile/environment unchanged. Native source/tree and service identities fixed for each aggregate. One pre-cohort grammar probe caused LLM OOM/automatic recovery; the changed-source cohort uses its recovered identity, with no further restart. No promotion/release; TTS dependency rebuild remains unqualified. |

The raw milk result now retains ahead/about50meters but requests GA only; Planner
and resource provider are not invoked. Controlled complete-WHAT references prove
only the downstream program repair. Native walk3s/right-turn2s completes in simulation,
but Planner falsely cites the walk's three-second phrase for its turn duration2s;
semantic provenance review therefore fails despite the automatic pass. Valid source
coordinates do not prove correct parameter mapping. Raw omissions or incorrect choices
are not proof of an intrinsic model-capacity limit and were not tuned or repaired downstream.

## Next work and blockers

1. Preserve the green canonical gate and exact workflow freeze. Next delivery evidence
   is narrow current-revision voice proof, then default target closure. Physical
   microphone/speaker/robot evidence remains supervised; text, discarded TTS and mock
   acquisition/handover do not replace it.
2. Preserve all79 before/after primary packets and adjudications. Do not claim a native
   semantic pass, motion/stop proof for unexecuted cases, or a behavioral improvement.
   UMI activation/result-type, accepted-offer continuity and genuine uncertainty remain
   unqualified; GA/Host cannot fill omissions. The owner excludes model-ability tuning.
3. Review retained Attention same-authority second-call and SC fresh-turn silence/
   provenance findings under the current Issue and existing Charter. They are not
   fixed by this patch. Broad/compound exact-Goal-count oracles and historical-memory
   search-to-execution coverage also need qualification; they must not dictate a new
   upstream split or promote historical candidates to current facts.
4. Resume only from fetched current source; preserve Soridormi's unrelated dirty work,
   running simulator and ignored evidence. Detailed identities, artifacts, failed
   iterations and copy-ready checks are in Handoff. No new architecture or authority
   amendment is authorized by this delivery.

Earlier delivery mechanisms and evidence are summarized in Handoff and
[the audit](ARCHITECTURE_AUDIT.md). Their older green/red totals and service identities
remain historical, not current qualification or commands to deploy retired images.
