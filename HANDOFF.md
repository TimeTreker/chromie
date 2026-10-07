# Chromie Handoff

## Current delivery — open-ended help, GA ownership and SC failure update, 2026-10-07

Checkout `/home/chromie/github/chromie`, branch `main`; fetched upstream base
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6`. The delivery commit includes
this file and [checkpoint](DEVELOPMENT_CHECKPOINT.md). The current source was
built into the Agent service for a diagnostic text aggregate, but the service
became unavailable mid-cohort and its runtime identity changed. Treat that
aggregate as incomplete, not as a fixed-identity release proof.

Originating text SID `d7e6f1a3`: after greeting and a thirst/help turn, the
person asked Chromie to bring a bottle of water. UMI accepted one complete
delivery Responsibility `r1` at confidence 1.0. SC delivered a short receipt
acknowledgement. GA's `chromie-gemma4-12b` primary response contained two
identical `continue` rows attaching `r1` to thirst Goal
`goal_b39473f14c95a7346417`. The canonical GA Host validator rejected the
duplicate (`expected=['r1']`, `actual=['r1','r1']`) and no Goal/Work commit
occurred. Concurrent speculative Fast planning was cancelled. The terminal
failure need then reached SC, whose recorded speech was “I'm sorry, I had a
little trouble processing that request. Could you say it again?” Meaning had
already been accepted, so the repeat request was false. A direct baseline
replay of that same SC packet instead reused its earlier “Got it.” act to cover
the later failure need, another invalid result-accounting path. Microphone and
ASR were not invoked for this text episode. Original bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_110927.tar.gz`.

Repair at existing owners: `agent/app/clients/sglang_protocol.py` derives the
current Responsibility-ref count from the canonical GA schema and applies a
per-array row bound only in the SGLang wire schema. This makes the existing
one-owner-per-ref limit visible to the native decoder without changing GA's
canonical request or weakening Host validation. `agent/app/social_cognition.py`
prevents a prior acknowledgement act from covering a later terminal result
need, requires a newly grounded result update, and tells the primary SC model
that accepted meaning with no input need is no reason to ask for repetition.
The Host continues to fail closed if the decoder produces a cross-array
duplicate or another invalid mapping. No new model call or semantic authority
was added.

Private evidence is retained in `.chromie/acceptance/ga-duplicate-20261007/`
and `.chromie/acceptance/sc-internal-failure-20261007/`. The three exact GA
packets replayed through the bound native decoder covered the expected refs
with no Schema errors. The original duplicate is in the recorded live bundle;
the baseline replay did not reproduce that stochastic output. The five-call SC
episode replay passed Schema and Host validation on current source, ending in
“I'm sorry, I couldn't bring the water bottle to you because of a technical
issue.” This is a truthful result update, not a claim of physical delivery.
Direct model replay is same-model, not independent or deployed integration proof.

Focused tests: 68 selected GA/SC/workflow replay tests pass. The final restored
source passed `python scripts/check_repository_policies.py`,
`./scripts/run_tests.sh` and `python scripts/check_docs.py`; the full test script
exited 0 with 169 benchmark, 3,983 main, five skipped, 1,023 subtests and 20
legacy Agent tests. Test ownership, pinned Ruff/mypy, configuration and runtime
checks passed within the canonical gate. Four relevant Level A ability classes
passed 22/22 (human-like continuity 4, natural uncertainty 6, robust intent 8,
truthful embodied speech 6); the
strict frozen workflow replay passed 6,000/6,000. An earlier experimental
`run_tests.sh` invocation failed workflow request comparisons while prompt
experiments were active; those experiments were reverted before the final pass.

Diagnostic deployed text aggregate:
`.chromie/acceptance/thirst-offer-20261007/live-baseline/summary.json` and
`case_review.json` in that evidence root. All 79 cases were attempted in one
invocation: 13 automatic passes, 66 failures, 59 integrity failures, 79 semantic
reviews retained; `cohort_complete=false` and `qualification_complete=false`.
Agent port 8092 became unavailable during the run; the cause is unknown. Exactly
one post-cohort bundle was collected:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_121723.tar.gz`.

For `thirsty_then_water_delivery`, the first turn offered help, but after “Sure,
water is perfect!” UMI's primary output reduced the accepted request to speech
instead of a physical get/deliver Responsibility. The exact private packet is
`.chromie/acceptance/thirst-offer-20261007/umi-water-acceptance-raw.json`.
For `accepted_water_offer_executes`, UMI and GA carried the accepted “sure” to
Fast Planner, whose primary output gave a provider-resolved source with an
unsupported description and missing `argument_sources.source`; Schema/Host
rejected it before Capability dispatch. The exact packet is
`.chromie/acceptance/thirst-offer-20261007/planner-accepted-water-raw.json`.
These are distinct new earliest boundaries. Host containment was correct; the
user-visible apology was downstream. Contrast variants that repaired one example
caused unauthorized action or provenance errors elsewhere, so they were reverted.
The canonical semantic contract amendment needed for a broader repair has not
been approved or implemented.

Resume from stable services and a bound runtime identity. Diagnose the retained
UMI/Planner packets; obtain owner approval before changing the canonical semantic
contract; implement and prove a general boundary repair. Rerun focused scenarios,
their ability classes, local gates and the complete directory-discovered live
cohort before a revision-level claim. Then run narrow current-revision supervised
voice proof and continue default target-evidence closure. Physical microphone,
speaker and robot evidence is absent. The earlier UMI patch and frozen workflow
archive remain part of this delivery.

## Previous patch — open-ended help interpretation, 2026-10-07

Checkout `/home/chromie/github/chromie`, branch `main`, remote
`https://github.com/TimeTreker/chromie.git`. Fetched pre-edit base
`073abb4daad94c8bb419db6b05ba8f6310c4a0a6` matched `origin/main`.
At this earlier handoff, this patch was uncommitted and unpushed. The current
resume revision is the newest commit containing this file and
[checkpoint](DEVELOPMENT_CHECKPOINT.md).

Originating live text SID `a87066b5` admitted “I am a little thirsty, can you
help me?” on the original source. UMI call
`llmcall_user_meaning_interpreter_0e8b52fbe1db4a4b` used
`chromie-gemma4-12b` through `sglang.chat`, completed with `done_reason=stop`,
then failed Host source-span validation because `r1` cited `t1–t10` and `r2`
cited `t6–t10`. Core returned 503 and Host selected the non-semantic retry
notice; GA, Planner and SC were not invoked for that turn. The original private
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20261007_093607.tar.gz`
and its extracted files are under `.chromie/debug/debug_bundle_20261007_093607/`.
Review and redact complete prompts before sharing either artifact.

The existing UMI system prompt now makes a reported need plus open-ended help
request one Responsibility, excluding an invented information request to choose
help. No schema/DTO/Host, model or profile change was made. The selected prompt
is SHA256 `7e68853c4cd682dc410aae4f56a66f8400af2a9be37f808ee45148ae6d620152`
after trimming the trailing newline. The frozen contrast evidence is under
`.chromie/acceptance/umi-help-split-20261007/`: `scenarios/`, `baseline/`,
`candidate2_focused/`, `candidate2/`. Baseline 6/8 and selected candidate 8/8
passed Schema/Host; both baseline failures were overlapping English/Chinese
open-ended help outputs. The exact English turn now retains one complete speech
Responsibility and Planner/GA requests. Chinese still produced an English
outcome, despite mechanical acceptance; this is not bilingual qualification.
Later prompt experiments were rejected and restored to the selected hash.

Five prototypes were request-only captured from actual production packets;
`prototype-capture/` retains them. All 6,000 workflow requests were captured
against the same unchanged source using saved reference responses;
`full-request-capture/summary.json` reports zero failures. Only UMI packets
changed. The final archive is freeze revision 17, SHA256
`b8bc872fe60854a59bd982744aeeb05cc5c114701fe2e0c6fc22f158184281c8`.
`recapture-final-summary.json` records 6,200 primary and 300 Deep request
captures, all non-request fields identical. Previously ignored stale freeze
files are preserved in `preexisting-frozen-extra-artifacts/` and
`preexisting-stale-frozen-corpus/`, not deleted.

Observed checks:

- `python -m benchmarks.regression restore-fixtures`: 6,050 verified, zero restored
  after recapture.
- `python scripts/run_workflow_replay.py --workers 8 --evidence-dir
  .chromie/acceptance/umi-help-split-20261007/strict-full`: 6,000/6,000 pass,
  zero candidate calls, fixed source; see `strict-full/summary.json`.
- `pytest -q tests/test_workflow_replay.py`: 104 pass; focused UMI: 44 pass,
  77 subtests; robust-intent Level A: 8/8.
- `./scripts/benchmark_check.sh`: 169 pass; `pytest -q tests`: 3,981 pass,
  five environment skips, 1,023 subtests; legacy Agent: 20 pass. Policy,
  ownership, pinned static, configuration, runtime and docs checks passed.
- `./scripts/run_tests.sh` itself did not finish successfully here: initial
  ignored freeze files blocked restore, a second invocation ended at exit 143,
  and a later standalone main run exposed 83 stale request packets before the
  recapture. The final component checks above passed, but the single-command
  gate remains unverified.

The current operator text console remains active and `chromie-agent:latest`
still serves the pre-patch image. Do not describe the direct SGLang model calls
as deployed Host, audible voice, simulator or physical evidence. Next, from an
uninterrupted shell, run `./scripts/run_tests.sh`; bind a freshly built current
Agent source identity and run the existing
`scenarios/general_ability/must_pass/robust_intent_understanding/thirsty_then_water_delivery.json`
two-turn scenario when the operator Host is free. Review SC speech, Goal state,
Planner Work and follow-up continuity, then retain one bundle after any aggregate
live cohort. Qualify the Chinese language/need-retention slice separately.

## Previous delivery — UMI/Planner and historical Memory, 2026-10-05

Checkout `/home/chromie/github/chromie`, branch `main`, remote
`https://github.com/TimeTreker/chromie.git`. Pre-delivery base
`0848b07d14886a0238ca71ceae3aa65fd0bcd103` matches fetched `origin/main` before
edits and after the native aggregate. Expected resume revision is the newest commit
containing both this file and [checkpoint](DEVELOPMENT_CHECKPOINT.md).
Owner authorization: fix non-model defects, commit and push; UMI must not author
bindings. Principles and module responsibilities are unchanged; earlier contradictory
Charter allowance was removed. UMI and Planner prompt changes enforce this approved
contract, not general semantic tuning. Model/profile and SC prompt are unchanged.

The current local gate passes. Current-revision voice proof and default target closure
remain open. This is a bounded contract/projection repair, not a release or overall
behavior qualification. Attention second-call and SC silence/provenance findings remain
open. Do not repair UMI activation/meaning through GA, Planner or Host.

## Implemented workflow and provenance

- UMI primary/Deep Schema, parser and Decision reject even empty `bindings` keys.
  Complete WHAT, current-turn spans, uncertainty and initial activation remain UMI.
  Core rejects nonempty bindings; shared internal empty defaults/read-only retained
  canonical bindings are not fresh UMI authorship.
- Planner extracts arguments and cites original speech or exact owning accepted
  outcome tokens. `source_responsibility_ref` is an argument provenance selector,
  not another semantic owner. Host binds the exact quote only to that GA Goal;
  unknown tokens, owners and sibling citations fail closed. Typed retained constraints
  cannot be overridden. Valid coordinates alone do not prove semantic conversion.
- Provider-resolved resource sources may retain cited reported search clues. Perception
  verifies current conditions; a user report is not an observed object. Historical
  Memory remains Planner context outside sight, with original creation/update times
  and source refs. The controlled projection test does not prove search execution,
  automatic persistence of robot actions or that yesterday's water still exists.
- Stale UMI references/template are reconciled. Strict6000 records and5 prototypes
  change only captured production request packets; original inputs, reference decisions,
  meaning, relationships, parameters, prior Goals, provider/fault outcomes, assertions
  and splits are unchanged. No permissive replay or candidate-fitted answers.

## Evidence actually retained

Root `/home/chromie/github/chromie/.chromie/acceptance/umi-no-bindings-20261005/`
is ignored private evidence and does not travel with Git. Preserve/copy it before
cross-machine resume; review private prompts/payloads before external transfer.

| Artifact | Observed result and ceiling |
| --- | --- |
| `frozen-manifest.json`, `scenarios/`, `boundary.before.json`, `boundary.final-current.json` | Frozen bilingual20, initial8/20 → final20/20 through actual Schema/Host, one primary reference per case, zero external inference. |
| `grammar-conditional-wire-packets.json`, `native-grammar.conditional-wire.log` | Exact production response-format codec and pinned native decoder20/20; isolated container/network-none/2GB, no inference. Cross-field source/citation condition is Host enforced, not claimed native decoder semantics. |
| `memory.before.log`, `focused.owner-final.log` | Original Memory regression fails on missing created_ms; final runtime/Memory84 tests pass. No live water search. |
| `focused.pre-live.log`, `final-fixture-check.log` |215 focused tests/78 subtests pass; final2 fixture/hash checks pass. |
| `umi-corpus.after.log`, `fast-corpus.after.log`, `level-a/`, `level-a.log` | UMI1496/Fast204 references mechanically valid; Level A19/19 across3 relevant classes. No native behavior claim. |
| `capture-full-summary.json`, `workflow-invariant-review.json`, `prototype-request-capture.json` |6000+5 request-only maintenance; every non-request field unchanged, zero candidate inference. Original archive/cache/prototypes retained privately. |
| `strict-full/summary.json`, `strict-full.log` |6000/6000 pass, fixed production source, zero candidate calls:1400 complete workflows,1800 expected states,2500 expected rejections,300 safe nonexecuting rejections. |
| `canonical.final.log` | Exit0:169 benchmark tests,3981 main tests/5 environment skips/1023 subtests,20 legacy Agent tests pass; policy/ownership/pinned Ruff+mypy/configuration/runtime/docs pass. Initial `canonical.log`19 failures were a missing Unit source_text and stale5 prototype requests; original failed log retained. |
| `runtime.before.json`, `runtime.after-baseline.json`, `live-baseline/`, `llm_calls.baseline.jsonl`, `live-adjudication.baseline.json` | Unchanged-source native79,22 automatic pass/57 fail; same-agent review6 pass/10 partial/61 fail/2 insufficient. Nine primary nonempty binding outputs admitted by stale contract. |
| `runtime.native.before.json`, `runtime.native.after.json`, `live-after/`, `llm_calls.after-window.jsonl`, `live-adjudication.after.json` | Changed-source native79,13 automatic pass/66 fail; review5 pass/7 partial/67 fail. All cases attempted/zero skipped; blocked followups mean cohort/qualification incomplete. Native86 UMI primary outputs have zero binding keys. Source and service identities fixed. No overall behavioral gain established. |

Exactly one bundle per aggregate:

- Baseline: `/home/chromie/Downloads/chromie_debug_bundle_20261005_183008.tar.gz`.
- Changed source: `/home/chromie/Downloads/chromie_debug_bundle_20261005_192414.tar.gz`.

Native milk SID71d2b376 retains ahead/about50meters but requests GA only; Planner/
provider absent. Native walk/right-turn SIDb26d7667 completes simulator actions but
Planner call `llmcall_agent_6e97211283764259` falsely cites three-second walk tokens
for turn duration2s. This automatic pass is a semantic provenance failure, not a
proof of correct argument grounding. Current-time Planner is invoked (SID2b093bbb)
but authors response-only Work; no clock acquisition. Raw errors do not establish
intrinsic model incapacity. No model tuning, semantic lexer or second-call repair added.

Freeze revision16 archive: `benchmarks/integration/workflow_scenarios/frozen.tar.xz`,
1,294,716 bytes, SHA256
`17003c9696a28553d6ca1b888ede28c2ba76c9de79ecc6829837f98f90d9bb58`.
Strict cohort manifest SHA256
`51d9e344eb593d2fb474435fb3685a4fdf32b22318386d0732ea961094fd96fa`.
Original archive/cache remain in `workflow-frozen.before.tar.xz`,
`workflow-cache.before/`, with5 originals in `prototypes.before/`.
Final document consolidation follows the frozen native run; production bytes remain
identical. Do not treat the final documentation tree as that pre-document full-tree identity.

## Runtime and probe incident

Native frozen full tree:4492 paths, SHA256
`cc5de677facde4bc441fa9d141ee477339038b3d847796e046cb0939e5b1b273`;
identity SHA256 `d13bb2ac5787364a605da161735281784be71df48549f4492180dccf468bd671`.

Selected Agent image `chromie-agent:umi-boundary-memory-source-20261005` /
`bc6577e4b8996a55c3ea9ae6d996f757c8584460cd66a8a227871d3d4b17e9c7`;
container `1d73c9d3f87348308ee1f9d986aab5cec6adf0212cf71566b3e65661cdea59d3`.
Source-only rebuild preserves the original124a02f6… dependency layers. Environment
changed keys=[]; healthy/restart0. Packaged/host digest
`8140dcc34fdade7d6291bcb92b9dc5bd29f8a464ff4d7d1c35fd26d7dada0b25`
matches before/after in `agent-source.native.before.log` and `.after.log`.
The full official Agent build completed but was not deployed because its transitive
dependency resolution was outside the fixed-source comparison.

LLM remains `chromie-sglang:qwen35-4b-awq`, image2330d155… and model/options
unchanged. An initial manual grammar probe inside the running LLM omitted production
Schema sharing/shape codec, triggered OOM and automatic container recovery (exit137,
2026-10-05T10:46:14Z). `llm-service-after-probe.log` retains failure/recovery.
No manual LLM rebuild/restart or profile change. Native run binds the recovered
service identity; final healthy/restart1/start time unchanged. Subsequent grammar
proof is isolated/network-none/2GB and uses exact production transport. Experimental
three-branch source Schema failed pinned compilation and was rejected; final canonical
conditional plus existing transport shape passes. Never repeat heavyweight probes
inside the serving LLM. `services.native.after.log` retains final service states.

ASR42d3df2e…, TTSa56b2486… remain unchanged. TTS started2026-10-04T07:57:44Z,
ASR2026-10-04T01:08:44Z, both healthy/restart0. No microphone, audible speaker,
camera, grasp or physical robot qualification. Simulator acquisition is mock evidence.
Soridormi HEAD `2af3034a91842ecb9964a45ce24e9bdc18fcde58` has unrelated dirty owner
work; do not stage/reset it. Existing simulator and keepalive remain running.
Private `compose-files.private.json` and `agent-proof.private.json` retain the exact
Agent source proof service chain; use generated runtime env, never edit `.env.runtime`.

## Resume from Git

Fetch latest source and preserve dirty work before integrating. The current archive
restores complete exact records through existing checks; preserve a changed ignored
cache before replacement, never regenerate expected answers. Run from repository root:

```bash
cd /home/chromie/github/chromie
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

Next evidence is narrow supervised current-revision voice proof, then default target
closure. New native diagnostic runs need a fresh identity/evidence directory and a
full directory-discovered cohort; do not reuse or overwrite this root. Bind one source
and runtime, judge every case, collect exactly one bundle after the aggregate, then
select a fix. Prior/native automatic scores cannot authorize model promotion.

## Earlier evidence retained, not current resume commands

| Root under `.chromie/acceptance/` | Retained purpose |
| --- | --- |
| `project-audit-20261004T011454Z/` | Initial design audit, dirty36-path backup, Attention two-call/SC silence probes. |
| `audit-repair-20261004T014950Z/` | Text admission chronology and Level A metadata repair, dirty55 backup. |
| `root-cause-audit-20261004T061558Z/` | Original blink omission, TTS OOM/encoder proof, native17/79; no intrinsic capacity proof. |
| `contract-fixture-repair-20261004T084054Z/` | Original UMI/GA bytes and reference/adapter/oracle reconciliation, dirty68 backup. |
| `ga-relationship-contract-20261004T111406Z/` | GA identity/relations and Planner media repair. |
| `planner-compound-contract-20261004T140758Z/` | Compound/count/source repairs and historical native cohorts; `delivery/` retains first staged snapshot failures, owned patch/path inventory and count test recovery. |
| `sc-language-policy-20261004T125029Z/` | Rejected language trials4/8,4/8,3/8; original SC bytes restored. |
| `non-model-delivery-20261005/` | Prior347 focused pass and historical83 replay failures. |
| `workflow-contract-audit-20261005/` |6000 strict replay repair, archive/cold restoration, all original inputs/assertions preserved. |
| `ga-history-fixture-audit-20261005/` |70 current-description type repairs,1500 invariants,100 before/after reference workflows; canonical3968 main pass at0848b07d…. |
| `text-model-comparison-20260930/` | Historical237-case three-model matrix; incorrect then-user chronology prevents intrinsic ranking. |

Earlier detailed operational narrative is recoverable from `0848b07d…` in Git and
`resume-docs.before/` in the current root. Original ignored evidence and dirty backups
were not deleted. Earlier hashes, red gates and proof limits remain bound to their own
revisions; this consolidation does not convert them into current or physical evidence.
