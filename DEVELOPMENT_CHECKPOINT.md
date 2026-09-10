# Chromie Development Checkpoint

## Current delivery — bounded repair complete; live readiness blocked

Active Issue #35. Worktree `/home/chromie/github/chromie`, branch
`codex/live-readiness`, base `41bd7dcbdb99320147f08e3c799f48003e632e62`.
The owner authorized implementation, commit, push and merge to `main`, with a
maximum of 30 candidate iterations and no main-architecture change without a
prior report. Expected resume branch is `main` at the latest commit containing
this checkpoint and handoff. All 30 candidate slots are exhausted. The existing
Goal-driven single-authority architecture remains unchanged and binding.

**Implemented:** the repairs below. **Automatically verified:** retained local,
provider and simulator evidence at the stated revisions. **Target validated:**
no. **Release ready:** no. The current work is not a readiness or deployment
approval: the final cohort qualified zero of 51 cases. No physical microphone,
audible speaker or physical robot evidence was produced; ASR remains stopped.

### Implemented scope and actual workflow

| Owner / observed handoff | Reproduced failure | Repair and current evidence |
|---|---|---|
| Laptop profile -> Planner preflight | Complete preserved re-entry packets exceed the declared 32K context | Existing Fast/Deep/default profile budget becomes 48K; 21 retained preflight rejections become zero. GPU/TTS residency measured; no universal cross-profile capacity claim |
| CosyVoice voice selection -> native synthesis | Every request recomputes validated voice-reference conditioning, delaying first PCM roughly 18–19s | Prepare all committed profiles in native memory before readiness, reuse exact selected conditioning. Eight paired ordinary waveforms were byte-identical; first PCM about 0.94–1.68s |
| Runtime terminal event -> dispatch closure -> Planner | A successful single Capability re-enters before Host adds required provider postcondition | Successful single and multi-Capability results wait for existing dispatch closure. Failure/progress remain immediate. Focused live blink receives qualified postcondition before re-entry; source regression and broader gates pass |
| Gateway quiet compound -> Host admission -> Core | Host acknowledges every interrupt and returns, dropping the unchanged residual request | Urgent cancellation remains first; only pure controls return. Existing reflex-and-admit envelope carries the whole original turn once. Early/terminal/failure/confirmation/re-entry paths preserve speech prohibition; residual body work still requires valid Core output |
| Protective receipt -> conversation boundary/history | Receipt refreshes activity before hard-idle evaluation and can appear as prior dialogue | Prepare the residual conversation boundary before receipt, preserve active-Goal conversation state, omit only the current receipt from GI prior history. Bilingual fresh/expired/active-Goal contrasts pass |
| Live acceptance -> residual Core/Runtime result | Harness projects an empty reflex result and can falsely pass a dropped residual | Observe actual continued Core resolution, dispatch and completion; retain correlated receipt and restore wrappers after the case. Mechanical silence is no longer complete semantic coverage |
| CosyVoice native request state -> next request | Native token-hop state grows from 25 to 100 and leaks into later utterances | Restore the validated initial hop at each serialized request. Within-request native growth stays intact. Long/short contrasts retained; this alone did not fix cancellation |
| Host cancellation -> process worker -> native token loop | Cancelled native generation ignores cancellation, bounded drain expires and next request waits through cold reload | Signal shared process Event under the existing request lock, close token stream and skip cancelled acoustic work, retain native thread join/request cleanup and bounded restart fallback. Clear Event before next send so early cancellation cannot be lost |
| Canonical Fast re-entry -> response prompt | Request language is present at the API but omitted from both canonical Fast prompt branches; Chinese completions become English | Preserve the existing caller language in the same primary prompt. Frozen ten Chinese/English completion contrasts improve from 5/10 to 10/10 for language, Schema/DTO, completed facts and zero repeated Work; no translation call |

The original input, module I/O, regression evidence and limits are retained in
`.chromie/acceptance/live-readiness-20260910/iteration-*/manifest.json`,
`investigation.md`, and the per-case reviews. Main semantic authorities, the
single-call tagged Fast stream, deterministic safety controls, sequential
physical Work, and Soridormi ownership are unchanged. No public environment
variable, current document or architectural term was added.

### Evidence actually observed

Evidence root: `.chromie/acceptance/live-readiness-20260910/`.
`iteration-budget.json` counts rejected offline and CPU candidates conservatively
within the owner's 30 limit. All 30 slots are now used; candidate 30 is complete and rejected.
Candidate 29 was stopped incomplete after two output-budget failures. Do not
reset the counter on resume. `iterations.json` describes implementation/cohort iterations,
which are not the same count as evaluated candidates.

| Implementation iteration | Aggregate result after review | Retained bundle |
|---|---|---|
| 1: context budget | 51/51 completed; mechanical 4, corrected qualified 0 | `/home/chromie/Downloads/chromie_debug_bundle_20260910_021106.tar.gz` |
| 2: voice conditioning cache | 51/51 completed; mechanical 5, corrected qualified 0 | `/home/chromie/Downloads/chromie_debug_bundle_20260910_024418.tar.gz` |
| 3: completion ordering | Stopped on hard fabricated observation; 26/51 completed, qualified 0 | `/home/chromie/Downloads/chromie_debug_bundle_20260910_032151.tar.gz` |
| 4: quiet residual admission/history | 51/51 completed; mechanical 3, qualified 0; 166 calls, no log decode errors | `/home/chromie/Downloads/chromie_debug_bundle_20260910_040801.tar.gz` |
| 5: native chunk reset/idle order | Stopped during case 30 after delayed review found case 26 fabricated observation; 29/51 completed, mechanical 3, qualified 0; 95 calls, no decode errors | `/home/chromie/Downloads/chromie_debug_bundle_20260910_044031.tar.gz` |
| 6: cooperative cancellation/language | 51/51 completed and reviewed; mechanical 5, qualified 0; 167 calls, no decode errors | `/home/chromie/Downloads/chromie_debug_bundle_20260910_080006.tar.gz` |

Each completed or stopped aggregate retained exactly one debug bundle. The prior
iterations 1 and 2 sole qualified silence case actually dropped the residual request;
`qualification-review-correction.json` preserves the explicit correction rather
than treating silence as successful Goal coverage. Original mechanical results
remain historical evidence.

Iteration 6 cancellation proof: focused 20 tests/10 subtests; canonical 2,336 tests/
384 subtests, 140 benchmark and 20 legacy tests passed, with all required policy,
static, ownership, configuration and docs gates. Level A recovery/safety 6/6 passed.
That canonical run preceded the language projection. The language repair has
focused 136 tests/11 subtests passing; its four new regression contrasts failed
before the repair. The combined canonical rerun after the 06:59 laptop reboot
passed 2,337 tests, 388 subtests, 140 benchmark and 20 legacy tests
(`iteration-06/canonical-with-language.log`). All four final delivery commands
also passed: repository policies, `run_tests.sh` (the same counts), documentation
and test ownership. Exact commands, exit codes and logs are retained under
`iteration-06/final-gates/results.json`.

The combined full live cohort completed on fixed source/services; the after-run
source digest matches `iteration-06/combined-identity.json` exactly:
`645cadf2b4c33b60008846762141d4d471d856db2be85f6a9757c7cc5da17835`.
This binds dirty source at the pre-delivery base; final reporting edits follow
the cohort without changing runtime code. All 167 calls decoded and all 51
cases were reviewed. Five mechanical passes were date/weekday, filler blink2,
mixed-language nod2, plain blink1 and English quick walking for 15 seconds.
Their complete transactions remain unqualified because of raw GA Schema,
source span or binding violations. The nod2 case's remaining defect is a
trailing punctuation span, not wrong execution. No criterion was relaxed.

All seven scheduled TTS outputs reached the discard playback sink: zero skipped,
zero failed. Six summaries expose schedule-to-first-PCM anchors of 1.148–1.712s;
the multi-turn setup lacks that derived anchor. Chinese completions stayed
Chinese, the English walk stayed English, and no completed Work was replayed
in these observed cases. Final Soridormi status is safe idle with no active
tasks/lanes (`iteration-06/final-safe-idle.json`). The cohort exited 1 for failed
acceptance; its sole automatic debug bundle exited 0. This is automated live
text/simulator evidence, not physical voice or robot qualification.

The 12 frozen GPU TTS trials on iteration 6 all completed. Ten ordinary first-PCM
latencies were 0.8207–1.3075s. Long-cancellation recovery was 1.0311/1.1863s,
versus 68.6584/62.2316s on iteration 5; recovery queue wait was 0.1031/0.1036s.
Both cancelled requests drained cooperatively; zero restarts, worker ready/warm.
See `iteration-06/after/summary.json`, WAVs, provider logs and `identity.json`.
These are transport/provider results with no audible playback. Hop-reset audio
is not claimed byte-equivalent; the earlier voice-cache-only comparison was.

### Open failures and remaining work

1. GI still merges or omits independent effects, translates source bindings,
   misclassifies time/location, reverses question roles, or invents actor and
   execution uncertainty. New model/Schema/prompt candidates are not promoted
   merely because JSON parses. All evaluated 24/36-case role screens retain
   complete calls and reviewed Schema/DTO/Host outcomes.
2. Fast still emits malformed two-frame plans, ungrounded arguments, unrelated
   repeated capabilities or 2048-token truncation; required pending-work speech
   is often absent. The frozen 39-call Fast profile and structural comparisons are complete
   and rejected: zero-presence Ollama 13 versus historical 14 frame passes;
   SGLang constrained 6 versus matched baseline 11. Its API preserves the
   canonical schemas, but compiled grammar accepts an invalid output; native
   allOf support is incomplete. No streaming-protocol or backend default has changed.
3. Case 26 remains a hard provenance failure. SID `d0ef81f7` in iteration 5:
   user asks whether anyone is outside -> GI changes this to asking the user ->
   Fast identifies absent observation and escalates -> Deep fabricates having
   looked outside -> Host accepts -> TTS plays the invented observation.
   No perception provider was invoked. Faster playback is not its cause.
   See `iteration-05/provenance-failure-workflow.md`. Do not patch this with
   utterance-specific rules, another semantic critic or silent Goal rewriting.
   In iteration 6 this case fails earlier at Fast: Deep is not invoked and
   speech is not scheduled. Case 51 Deep also claims an unperformed lookup,
   but its invalid DTO is rejected before playback. Neither repairs the earlier
   admitted fabrication. Case 47's harness message about crossing validation
   is also qualified by the actual trace: no Work started; the required deferral
   evidence is absent, not an observed execution breach.
4. The 30-candidate limit is exhausted; the final aggregate, one bundle and
   complete review are retained. Further changed-candidate evaluation requires
   an owner decision on a new budget. Evidence has not established that a
   main-architecture amendment is necessary. Any proposed amendment must first
   report the conflicting invariant, reproducing evidence, module I/O impact
   and expected regression boundary for owner approval. Do not reset the counter
   or count containment as successful behavior. Authorized Git integration of
   verified repairs does not close live readiness.
5. Supervised live microphone/speaker evidence and the default target-evidence
   profile remain open. Do not infer them from live text, discarded audio or
   the headless simulator.

## Retained baseline and claim boundary

Historical migration baseline `9df52609` selected shared Gemma4-12B on SGLang and left the then-current laptop configuration unchanged. The current laptop changes are listed above. The previous Ollama Gemma Q4 full preview also had 0/51 qualified cases.
Earlier Qwen/SGLang versus Ollama latency trials used different model/precision/topology
and are not a controlled backend comparison. See HANDOFF.md and retained comparison
reports under `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/` and
`.chromie/acceptance/sglang-switch-rtx5090-20260909/` for exact inputs and results.

GI binding-schema ordering, frozen primary-screen corpus, raw-output/termination retention
and the 1496-reference audit remain preserved. The current candidate milestone is defined
above; rejected field-layout/global-format experiments remain evidence only. Keep source
and deployed identity distinct. Never count containment as successful behavior or reuse an
old cohort as proof for a changed revision. Current-revision physical voice and default
target-evidence closure remain open. The one-authority architecture remains binding.
