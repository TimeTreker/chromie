# Chromie Latest Handoff

## Current delivery — remaining-Issue repairs, 2026-09-12

Repository `/home/chromie/github/chromie`, branch `main`, pre-delivery base/fetched
origin `8aa3f499151e4d25e8aed3fec74dec486f12b9cd` for this documentation-only publication
update. Implementation was delivered at that commit from base `c142f16c`; all runtime,
prompt, corpus and evidence identities below remain bound to that implementation. Python:
`/home/chromie/miniconda3/bin/python`. Resume from the latest main commit containing
this file and [DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md). The owner authorized
implementation, principle decisions, bounded maintenance, normal commit/push and
closure of solved Issues. The [audit report](ARCHITECTURE_AUDIT.md) owns the issue map
and actual module I/O. Verified closed Issues: #35 and #52–#58. Only #24/#32 remain
open for failed qualification; they are not permission blockers.

## Implemented workflow and authority

| Issue / earliest boundary | Changed module I/O and proof |
| --- | --- |
| #52 cancellation scope | Exact trusted status + original effect Goal + catalog availability enter Planner independently. Prompt/Schema/Host now admit truthful `respond` at satisfaction0 with zero owned Work, timer, auxiliary action or fresh confirmation. Actual named cancellation revokes stale tokens, preserves a sibling's token/Goal, and fake-provider Runtime speech cannot fulfill the cancelled reminder. |
| #53/#54 Reflection | Aggregate outcome → eligible result Planner → one optional background Reflection worker. Actual Host requests carry the approved Mind allowlist. Timeout/cancel/shutdown/stale-generation/busy-slot tests preserve the existing task owner. Diagnostic advisories no longer bypass handled-Evidence suppression or cause Planner re-entry; only applied bounded Memory is adaptation. |
| #58 future intention | Typed `ready_at` → one captured clock comparison → waiting response with exact timer and original Goal unmet, zero current Work. At due, real persisted state/wake/Host request reuses exact open Goal snapshots under the matching opportunity. Prompt carries the already-arrived fact; a new primary decision performs acquisition, without a second timer or invented Goal/GA result. Repeated wake/restart cannot redispatch. |
| #55/#56 documentation and typing | Revision-label historical voice evidence; derive 7 Agent/27 tool records and use current registry owners. Existing pinned Mypy scope now includes all 30 contract files plus 3 tools, automatically including future package files. No broad ignores. |
| #57 lifecycle seam | Acquisition → immutable correlated outcome → derived continuation → Host re-entry → effect or delivered explanation remains under existing atomic state ownership. Serialization and both Host projections preserve the derived property; model override and duplicate-Evidence bypass fail. No extraction justified. VoiceAssistant7,549→7,524 lines/104→105 methods; ConversationState6,172 lines/105 methods unchanged. |

The owner's principle choices are recorded in Charter/API/interaction authority:
reporting cancellation does not perform the original effect; remembering future
work does not dispatch it now; optional learning follows ready result planning.
One primary semantic authority, original Responsibility/Goal/Plan provenance,
confirmation, cancellation and Runtime Evidence remain intact. No standing document,
runtime flag, architecture layer or model profile added (102 tracked Markdown,
15-document core path; both unchanged). The friend's numeric limits remain review
suggestions; owner-approved #45 forbids mechanical size gates.

## Reproducible evidence

R = `.chromie/acceptance/remaining-issues-20260912/`, private and ignored. Exact raw
outputs, packets, source/corpus/oracle hashes, semantic judgments, failed attempts and
live identities require the separate archive. Public tests/corpora are tracked.

| Final evidence | Observed result / location |
| --- | --- |
| Canonical local gate | `policy-final.log`, `canonical-final.log`:3,105 tests/794 subtests,145 benchmarks,20 legacy; pinned static/config/policy/ownership pass; two existing FastAPI warnings. |
| Focused future workflow | `reached-packet-proof.log`:50 passing tests, including bilingual real persistence/restart/Host/Runtime,14 invalid-scope pre-inference checks, and before/at-due actual prompt contrasts. |
| General ability Level A | `level-a-complete/`:45 distinct cases, all 15 classes pass. Scripted/source evidence, not live robot behavior. |
| Final Fast | `fast-full-5/`:204 one-call cases, all Schema/Host/frozen hard/semantic pass. One allowed parameter-provenance normalization, no disallowed semantic normalization. `control-fast-final_ready/`:16/16; `retained-fast-3/`:6/6 due-wake cases. |
| Final Deep | `deep-full-2/`:40/40 Schema/Host/frozen hard/semantic pass; `control-deep-final_ready/`:16/16; `deep-future-2/`:6/6; `retained-deep-3/`:6/6. |
| Model → Runtime proof | `future-readiness-after.json`:six waiting outputs, zero early dispatch, open Goal after speech, one wake. `retained-fast-runtime-replay.json` and `retained-deep-runtime-replay.json`:six final due model Plans per tier dispatch one exact lookup through actual adapter/Runtime with fake providers. Real bilingual restart tests separately prove source Plan/Responsibility continuity and one-shot behavior. |
| Documentation / delivery | Final local docs/policy/ownership pass. [Python 3.11/3.12 CI](https://github.com/TimeTreker/chromie/actions/runs/34691856596) passes on implementation commit `8aa3f499`: each job reports 3,105 tests/794 subtests,145 benchmarks,20 legacy and Mypy33 files. #56 is closed with that link. |

Final offline candidate: `gpt-5.6-sol/high`, one target-blind primary invocation per
case, 600-second deadline, no retries/repair. Full Fast concurrency 12, Deep 6;
supplemental contrasts 4. Complete Fast inference/adjudication/semantic review finished
before final Deep began. No production/harness/corpus edits or commit during either
frozen inference cohort. Final Fast's204 packets are identical to full4; rerun still
performed against final source. Corpus inputs were preserved; staged/readiness oracle
amendments were frozen before new calls, with old failures retained.

Tracked coverage:204 Fast (17 capacities ×3 families ×2 conditions ×2 languages),
40 Deep (10 capacities ×2 conditions ×2 languages), plus cancellation and retained
wake contrasts. This coverage-based corpus replaces #35's earlier 600-case proposal;
600 was not run. Surrogate success does not qualify GI/GA, native transport, Agent
Skill selection, audible/physical behavior or the combined target profile.

Retained failures are not passing evidence:

- `fast-full-1`:197 semantic passes,6 early-dispatch failures,1 malformed JSON.
  Unchanged `fast-full-2`:198 passes,6 early dispatches; no claimed JSON repair.
  `fast-full-3` passes204 after waiting repair. `fast-full-4` passes204 before the
  newly frozen persisted-wake cases reveal another missing prompt fact.
- `deep-full-1` passes40 before the final wake fix. `deep-future-1`'s initial oracle
  invocation used the wrong nesting and was a no-op; only
  `oracle-adjudication-final.json` correctly checks the nonempty waiting reference.
  All six then pass against unchanged raw outputs. The final driver fixes the call.
- `retained-fast-1` and `retained-fast-2`:6 Schema passes but0 Host/semantic each.
  First primary packets omitted arrived-time truth; the first repair changed helper
  text without invoking it at due. Actual-packet contrast tests caught the missing
  hook. Final `retained-fast-3` passes6; original failures remain unchanged.
- Earlier focused/harness failures remain in R: future contract red tests, external
  Evidence guard ordering, fake speech receipt ownership, missing typed media fixture,
  tuple/list test mismatch and pre-freeze Chinese location fixture. They are distinct
  from candidate failures and were corrected at their responsible boundaries.

## Native-model and final live failure — #24/#32

`gi-qwen9b-budget2048/`:44 frozen complete-Mind cases,63 actual calls,34 final decisions,
2 strict dimension passes, one2,048-token truncation. All 44 outputs reviewed. The
experiment changes only512→2,048 output tokens against the earlier exact packets;
`think:false`,Qwen3.5:9b,16,384 context remain fixed. Self-deliberation in `unresolved`,
merged effects, wrong binding/mode and omitted siblings remain. Literal span/wording
mismatches are scored separately from those concrete semantic defects. Budget alone
does not fix them; no model intelligence ceiling or production promotion is claimed.
Qwen9b digest:`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
GPU128 samples at2s:maximum11,549MiB used/minimum4,397MiB free, one resident model.
TTS healthy but not concurrently exercised; combined-profile acceptance stays open.

Final Agent rebuilt/recreated from the final behavior source. All 113 deployed
Agent/shared Python/text files match local bytes (`live-final/source-verification.json`).
The generated32k qualification environment is
`.chromie/acceptance/laptop-iterations-20260910/orchestrator.env`, with existing
`.chromie/voice-runtime/compose.voice-mujoco.yaml`. Do not reuse the stale alternative
`.chromie/voice-runtime/orchestrator.env` or edit generated `.env.runtime`.

Final diagnostic runtime identity:
`ccb85b7e47fd86467f143fa6c7cbc4f2cd596494724659c779ccf4ba985c9470`.
Dirty source-tree SHA256:
`b0af916d102ddcd5fa14383bb0ccc7a252132b2376a5eaf8e3ae71105da1a6ea`.
This precedes final documentation edits/commit and is explicitly not clean-revision
release evidence. Agent/TTS/LLM bound; ASR absent; deployed roles Qwen3.5:4b/Ollama.

`run-live-final.py final` invokes the complete discovered51-case must-pass live-text
cohort once. Input:walk ahead at0.2 speed for10seconds, nod twice, then turn left.
GI call`llmcall_goal_interpreter_d2278e1d3bfa4a1b`,session`6df0558e`, emits one body
responsibility with the whole admitted turn in `subtype`. Validator correctly rejects
`invalid_primary_goal_interpretation_semantics`; HTTP503 `goal_interpreter_unavailable`.
GA, Planner and Runtime are not invoked. One failed case, next startup interrupted,
49 unrun; all 51 slots reviewed. Source/provider identities unchanged during cohort.
Raw response SHA256:`dd300bc80a67ea0064a99d3b0b685134d0ad86c0f1513c46f63503451d63bf91`.

Exactly one final-cohort bundle, collection exit0:
`/home/chromie/Downloads/chromie_debug_bundle_20260912_193424.tar.gz`.
Earlier repaired-source cohort in `live-after/` has identity
`51454bae425d2a12bd1f901824229fce444177bcac74495809a43040dd393bc1`,same failure, its
single bundle`/home/chromie/Downloads/chromie_debug_bundle_20260912_185848.tar.gz`.
Original unchanged audit baseline/one bundle remain in the previous handoff.
Do not collect extra bundles or relabel incomplete cohorts as passing.

Final simulator status:safe_idle=true,standing=true,no active task/fall/emergency.
Owned MCP and simulator`soridormi-sim-run-d987b4fa02a3` stopped. Agent/TTS/LLM remain
healthy development services. Soridormi:`/home/chromie/github/soridormi`,branch
`codex/turn-count`,revision`284273bc`; preserve pre-existing untracked
`workspace/Open_Duck_Playground`. No microphone, audible speaker, executed simulator
capability or physical robot proof. Native stream/voice/default target closure open.

## Verified publication state

Implementation commit: `8aa3f499151e4d25e8aed3fec74dec486f12b9cd` on `origin/main`.
GitHub #35 and #52–#58 are closed with individual workflow, acceptance and evidence
comments. #35's body explicitly preserves the original600-case proposal as history
and records the accepted coverage-based replacement; it does not claim600 cases ran.
Only #24/#32 remain open, each with fresh native failure reports and next steps.
This subsequent documentation-only commit records the observed publication/CI result
and preserves both handoff owners; it makes no newer live-runtime claim.

## Transfer and next commands

Private archive: `/home/chromie/Downloads/chromie_remaining_issues_evidence_20260912.tar.gz`,
48,344,022 bytes, SHA256:
`604b801d6331c0356c0541d47bc0fb37eca91793454bda7d75e58e724c3ecd78` (companion `.sha256` file).
It contains R, preserved GI corpus/packets, all 74 discovered live scenario files
(51 selected must-pass), and copies of the two single-cohort debug bundles under
`retained-debug-bundles/`. Publication drafts/caches are excluded. Restore its
repository-relative `.chromie/` tree, then adapt recorded machine-local paths.
Raw private prompts/outputs must remain outside GitHub.

On another machine, inspect local changes before fast-forwarding main. Recreate
runtime environments through the existing profile owner; verify exact deployed bytes
and capture a new identity. Transfer private evidence separately, never publish raw
Mind/prompts/provider payloads to the public repository. Previous #51 private artifacts
from the other machine remain absent here and are not presented as fresh results.

```bash
git status --short --branch
git pull --ff-only origin main
gh issue view 24
gh issue view 32
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir .chromie/acceptance/resume-level-a
```

For a new frozen offline run, use unused output directories and the tracked
`benchmarks.datasets.fast_planner_daily_life.qualification` or `deep_qualification`
module's `prepare`, `run --concurrency 6 --timeout-s 600`, then `adjudicate` commands.
Review all Fast outputs before Deep; after Deep source changes rerun both. Do not
rerun `control_matrix.py freeze` or overwrite any retained case/oracle identity.
Private `qualify_retained_wakes_rendered.py` demonstrates exact due-clock packet
capture/replay; adapt its output path before a new batch. Its injected 2099 time is a
test fact, not wall-clock deployment evidence.

Next native work starts at the primary GI failure and its 44-case comparison, not a
bypass to Planner. Before new live claims rebuild/verify source, launch Soridormi with
`--backend mujoco --profile open_duck_forward --no-viewer` and the existing MCP service,
verify Host idle, capture fresh identity, then run one whole discovered cohort. Use
`live-final/cohort-command.json` and `run-live-final.py` as reviewed references with a
new directory and valid machine-local paths. No edits/restarts/substitutions between
cases; exactly one bundle at completion/hard stop; inspect all cases. Physical
microphone/speaker proof remains supervised. No follow-up scheduled.

The [preceding handoff](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/HANDOFF.md)
and [checkpoint](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/DEVELOPMENT_CHECKPOINT.md)
retain the external review, all earlier workflows, failures and transfer identities.
Historical narrative is preserved in Git rather than a new current document.
