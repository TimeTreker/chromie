# Chromie Handoff

## Phase 1E Social Cognition model-view handoff — 2026-09-16 (current)

The full trusted SC request remains unchanged and digest-validated. `social_cognition_prompt`
now removes execution-realization plumbing from canonical/source Plan projections before
model inference: Capability IDs and args, parameter resolutions, selected Agent Skills,
auxiliary/retired communicative fields and Planner response wording do not enter SC. High-
level Plan disposition/coverage/Goal scope plus step identity, timing, purpose, expected
outcome and reason remain available alongside Work/Evidence/Situation/Memory/interaction
facts.

The authority prompt explicitly distinguishes prohibited raw motor fields in SC-authored
social expression from legitimate high-level requested Work. This closes the reproduced
architectural contributor to SC inventing a body-control capability/safety limitation.
Host validation still sees the full Plan and semantic-artifact lineage. Next work may begin
the semantic Capability facade; do not restore provider realization details to SC to make
a prompt case pass.

# Chromie Latest Handoff

## Phase 1D UserTurn source-span handoff — 2026-09-16 (current)

Continue after owner-applied Phase 1C. Fast model output now cites immutable UserTurn token spans in
`argument_sources` rather than copying source strings. GI and Fast share the same deterministic source
token coordinate system. Trusted validation enforces span existence/order and owning-Responsibility
containment; Host materializes the exact canonical quote and Goal ownership. Old string-valued Fast
argument sources are intentionally not accepted.

Next coherent slice: simplify SC's model-facing snapshot so low-level/provider plumbing cannot be
misread as a capability limitation, while keeping full authoritative request state for Host validation.
After that begin the semantic Capability facade with the retained left/right turn failure.

## Phase 1C live semantic-artifact lineage handoff — 2026-09-16 (current)

Continue from owner-applied Phases 1A/1B. Live original-turn Runtime now creates one
content-addressed lineage from the admitted `UserTurnEnvelope`, accepted GI result and each
Responsibility, carries it through the existing Work-request context to GA/Fast, appends GA/new
Goal refs after continuity resolves, appends the accepted Plan before SC/Capability Runtime, and
appends accepted SC/Communicative-Activity refs before interaction delivery. Runtime interaction
and capability metadata retain the same lineage; Cognitive Evidence verifies the transported
refs against archived packets. Model prompts do not receive digest/ID bookkeeping.

Next: Phase 1D replaces Fast model-copied `argument_sources` strings with immutable
`UserTurnEnvelope` token/span references and Host materialization of the exact excerpt/digest.
Do not weaken provenance or remove original source access; remove only the model transcription
burden. After that continue the SC projection diet and semantic Capability facade.


## Semantic Artifact Envelope handoff — 2026-09-16 (current)

Continue after the UserTurnEnvelope source-identity slice. The owner explicitly extended the same
message-conservation rule to accepted GI/GA/Goal/Planner/SC outputs and asked terminal Goals/
Responsibilities/talk to land in retained history. The new generic `SemanticArtifactEnvelope` is
a mechanical integrity/lineage wrapper, not another semantic owner or store. It protects the exact
typed payload with a SHA-256 and parent refs rooted at `UserTurnEnvelope`; existing Cognitive
Evidence JSONL archives immutable envelopes and, when text-retention policy permits, exact
packets; existing lifecycle/Evidence records append terminal facts. Active Goal/Work/Interaction
owners are unchanged.

Next source slice: carry artifact refs across actual Agent↔Host GI/GA/Planner/SC boundaries without
putting digest/ID bookkeeping into model prompts. After that, migrate Planner `argument_sources` to
UserTurnEnvelope token/span refs and trusted quote materialization. Do not skip directly to prompt,
model or SGLang tuning.

## UserTurnEnvelope source-identity handoff — 2026-09-16 (current)

Continue from the owner-applied semantic-simplification design patch. The next implemented
source slice makes `UserTurnEnvelope` the typed source reference across the original-turn
GI/GA/Planner path without changing the frozen `CognitiveWorkRequest` wire. GI receives the
typed envelope directly; GA/Planner resolve the full already-transported envelope through the
request's typed accessor. Text/session/language mismatch fails closed, and model-facing source
projections are derived from the same envelope identity/digest rather than another semantic
summary. Re-entry may use its existing validated provenance projection and does not pretend to
be a fresh user turn.

Do **not** delete `argument_sources`: its purpose is valid end-to-end provenance. The next patch
should replace model-authored exact-quote copying with an Envelope token/span reference and
trusted exact materialization, while retaining Planner ownership of semantic realization and all
Host grounding checks. Then finish the SC model-input burden audit; do not jump to model/SGLang
optimization yet.

Focused proof: 135 tests / 147 subtests passed. Missing `benchmarks/` in the supplied archive
prevents benchmark-dependent test collection. One unrelated existing SC test expects the primary
and deep prompt text to be identical, but the archive already appends different constrained
output contracts for the two decoder schemas.

## Archive-baseline semantic simplification design handoff — 2026-09-16 (current)

Use the owner-supplied `chromie_20260916_archive.zip` as the source baseline for this line.
The archive has no `.git` directory; do not infer a baseline commit from chat or remote
`main`. Archive SHA-256: `885226c691dcd89aa83f9c71a1981bf2b4993113e5b0832ea73f985a45dad4ad`. The extracted tree already contains the latest
Planner argument-source ordering and SC output-contract/empty-object decoder fixes.

The owner approved this exact order before more prompt/model/backend optimization:

`Planner/SC contract diet -> semantic Capability facade -> generalization + continuous
episode qualification -> current-model requalification -> model/SGLang/latency work`.

This handoff accompanies a documentation-only design patch. No runtime/source behavior is
claimed. Canonical details are in `docs/PROJECT_CHARTER.md`,
`docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md`,
`docs/LLM_PROMPT_QUALIFICATION_METHOD.md`, `docs/ACCEPTANCE.md`, and `ROADMAP.md`.
No new design document, service, flag, semantic owner or compatibility path is introduced.

**Next implementation slice:** inspect the actual production Fast Planner and Social
Cognition request/response contracts and produce a field-by-field burden inventory plus
red regressions for the currently retained native failures. Do not alter prompt/model
selection during that audit. The first intended code changes after the audit are only the
mechanically justified projections/deletions; semantic decisions stay with their existing
owners. The first Capability migration should make turn direction semantic at the Core
boundary and keep Soridormi/provider yaw sign/frame realization below it.

All prior evidence paths, native failures, target-evidence gaps and safe-idle containment
recorded below remain historical/current evidence for the supplied tree; they are not
converted into passes by this design amendment.

## Project audit delivery — 2026-09-16 (current)

Owner authorized project-wide audit/repairs, at most 18 loops, commit and push.
Repo `/home/chromie/github/chromie`, `main`; pre-delivery base
`f90dff450357cd49358bb49f03a4930a4d33a8d4`. Resume from the newest commit containing
this file and DEVELOPMENT_CHECKPOINT.md. Initial fetch was current, 0/0 divergence;
the repeated pre-delivery fetch also found 0/0 divergence. Preserve local work and
never force-push. Soridormi remains
`codex/turn-count` at `fa6331f1344ce26154b197ca7d7c49badea292ad`; unrelated dirty
playground content is preserved.

### Delivered scope and evidence

Fast Schema now represents an independently ready Goal alongside a newly scheduled
Goal; Deep adequacy respects the future Goal's deliberately unmet outcome after
source validation. Actual controlled SC/Runtime/restart proof dispatches only ready
Work and retains a one-shot future wake. GI still authors no parameters/timestamps.
Removed unused contradictory Planner wording constant and duplicate SC Protocol
method. Existing authority/interaction/API documentation is reconciled. See the
[audit](ARCHITECTURE_AUDIT.md) for the actual module workflow and reviewed coverage.

The tested Planner prompt cleanup was **rejected and reverted**: 12-case baseline
1 semantic pass, candidate 2 but two new truncations; 9B comparison 2 and an accepted
wrong-direction result. No profile change. Native qualification remains open.

**A = `.chromie/acceptance/full-audit-20260916-f90dff450/`**, ignored local evidence:

- `iterations.json`, `loop-01/`, `loop-02/`: complete local gates plus each immutable
  all-74-case live invocation, both stopped at first hard failure. Loop 1 canonical
  3,461 / 1,017 subtests, 145 benchmarks, 20 legacy; 6,000 strict outcomes; Level A
  45/45. Loop 2 has four canonical and 400 replay request-Schema mismatches; these
  are retained failures, not behavioral oracle changes. Level A remains 45/45.
- `readiness-red.log`, `readiness-green.log`, `readiness-runtime-green-complete.log`:
  fail-first 2/10, related 99-pass proof and final 10-case Runtime/restart proof.
  Earlier adapter/mock-output-schema fixture failures are retained separately.
- `fast-corpus/`, `fast-baseline/`, `fast-candidate/`, `fast-qwen9b/`: exact frozen
  inputs/catalog and target-blind raw primary requests/results; `adjudication.json`
  reviews every case. Same-agent/non-independent, no runtime effects or promotion.
- `packet-migration.json` records the initially captured rejected-prompt candidate;
  `refreeze-final/packet-migration.json` records its removal. Both explicitly assert
  unchanged scenario inputs, model replies, fault injections and behavior oracles.
  Only request contracts and their hashes are updated. `final-request-only-proof.json`
  independently compares Git HEAD: exactly 400 workflow cases change, no prototype
  cases change, every input/reference/fault/oracle is preserved. Unchanged prototype
  manifest metadata is restored. Final workflow manifest SHA256:
  `6c7454a8c50ec440f2079afdd7d29ebd100bb8e6bd65372818671fdb2097ecd0`.
- `loop-03/canonical.log`: **3,471 tests / 1,017 subtests, 145 benchmarks,
  20 legacy tests** pass, including policy, ownership, Ruff/mypy, configuration and
  docs. Two existing FastAPI deprecation warnings. `workflow/summary.json`:
  **6,000/6,000**, source unchanged (1,400 pass, 1,800 observed state, 2,500 expected
  rejection, 300 expected nonexecuting rejection). `level-a/`: **45/45**.
- `loop-03/live/`: all 74 discovered cases selected, hard stop at first: **0/1,
  73 unrun**, SID `9a5a54b0`. GI/GA correct; Fast decorated/missing argument sources
  and wrong left-turn sign; SC silence based on an invented low-level-control
  prohibition/capability limitation. Host rejects, zero body calls, safe idle true.
  Only harness error speech exists. Each `loop-*/adjudication.json` records review
  of all attempted cases and native packets; raw harness summaries are retained.

Exactly one bundle was collected after each completed/stopped aggregate:

1. `/home/chromie/Downloads/chromie_debug_bundle_20260916_034645.tar.gz` — SID `c0c5a0b6`.
2. `/home/chromie/Downloads/chromie_debug_bundle_20260916_040258.tar.gz` — SID `84b2e74d`.
3. `/home/chromie/Downloads/chromie_debug_bundle_20260916_042954.tar.gz` — SID `9a5a54b0`.

### Evaluated identity and shutdown state

Three full candidate loops completed out of the maximum eighteen; native comparison
runs are separately labelled. Final `loop-03/runtime-identity.json` SHA256:
`4234c4680eddc377c2128ae8cd355a7ae960be66db95dac2ccf17af66b03c416`;
evaluated dirty tree `17db4289803184b679862e0e277681d50d6c384423669622584bedc7440c8365`.
`candidate.patch` retains that evaluated change. Final handoff/document edits and
restoring unchanged prototype manifest metadata follow it; executable source does
not change. Rebuilt Agent checkout/container digests match:
`fdebbdf7ae894d6d63a47a0de3a1836d2f773cc1a02ecec30bb224cde79ef0cf`.
`agent-source.json`, `build.log`, `services.log` and `identity.log` retain verification.

Local RTX 4090 Laptop, Ollama 0.33.2 / existing Qwen3.5 4B profile. Context/output:
GI 16,384/512; GA 32,768/2,048; Fast/Deep 49,152/4,096; SC 49,152/1,024.
Final primary elapsed times: GI 6.93 s, GA 7.80 s, SC 14.85 s, Fast 26.37 s;
these overlap after GI and include provider load. No priority/latency qualification.
No profile, weights or training promotion; remote Gemma evidence not reproduced.

After retained safe idle, the owned headless Soridormi launcher was terminated and
simulator/MCP containers stopped. Agent/ASR/LLM/TTS remain healthy; no persistent
Host Orchestrator, physical microphone, audible speaker or robot session. Generated
runtime env is untouched by hand edits. No native, audible, physical or release
success is inferred from controlled tests. #24/#32 and current-revision target
closure remain open. Existing owner-reported microphone/ASR acceptance is unchanged.

### Cross-machine resume commands

Use fresh evidence directories and first fetch/reconcile the configured upstream.
Do not reuse rejected prompt packets as the current baseline.

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir /tmp/chromie-audit-next-replay
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir /tmp/chromie-audit-next-level-a
```

For automated live evidence, start `./scripts/start_soridormi_mujoco.sh --no-viewer`
from the paired repo. From Chromie, rebuild Agent when source differs using the
generated `.env.runtime` and `.chromie/voice-runtime/compose.voice-mujoco.yaml`, then
`./scripts/start_chromie.sh --no-orchestrator --keep-services`. Verify source:
`python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent`.
Capture a new identity with `--orchestrator-env .chromie/voice-runtime/orchestrator.env
--capability-manifest capabilities/soridormi.json --compose-override
.chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`;
use `--allow-dirty` only for explicitly retained diagnostic changes. Source the
generated Orchestrator env with export enabled. Run
`python scripts/general_ability_acceptance.py --mode live-text --execute
--soridormi-repo /home/chromie/github/soridormi --runtime-identity
NEW/runtime-identity.json --evidence-dir NEW/live` **without a stage filter** to
discover all 74 current cases. Keep source/services immutable during the cohort;
collect `./scripts/collect_debug_bundle.sh` exactly once after completion/hard stop
and review every attempted case. A hard stop leaves the remaining cohort unrun.

## Intent ownership and capability library delivery — 2026-09-16 (historical)

Owner authorized implementation and commit/push. Repo `/home/chromie/github/chromie`,
branch `main`, pre-delivery base `6fca5be2b590a4b1ca83d49fb197cdd74b50b2d0`.
Resume from the latest commit containing this handoff and DEVELOPMENT_CHECKPOINT.md.
Fetch was repeated before delivery with 0/0 divergence; never force-push. Paired
Soridormi remains `codex/turn-count` at
`fa6331f1344ce26154b197ca7d7c49badea292ad`; its dirty playground content is untouched.
Prior source-unchanged baselines and rejected experiments below are historical.

### Delivered boundary and remaining failure

GI owns complete intent plus provider-neutral result type/source evidence; no
capability arguments or Goal relationships. GA owns continuity and new Goal refs;
Host inherits GI text/type. Fast/Deep own realization and time conditions. Fast has
all-capability index plus full common contracts and one bounded missing-detail
lookup before a complete Plan. SC owns words/Social Attention and existing highest
request priority; any relevant owner can supply communication facts. The checkpoint
contains the actual concurrent module I/O, regression mechanism and claim limits.

**Native qualification still fails.** Latest SID `888a52e9`: GI and GA preserve the
complete compound; Fast now emits the explicit source map but decorates quotes with
canonical-DTO notation, omits speed/yaw provenance, and chooses negative yaw for
left. SC returns silence with incorrect task-state/control reasoning. Host rejects
before Work; zero body calls, safe idle true. No acknowledgement or live execution
success is established. Do not strip/repair quotes or override the direction in Host.
Next semantic work starts from these retained packets and frozen role contrasts.

N = `.chromie/acceptance/intent-authority-20260916/` (local ignored evidence):

- `canonical-r19.log`: **3,461 tests / 1,017 subtests, 145 benchmarks, 20 legacy**
  pass; policy, ownership, static, configuration and docs included; two existing
  FastAPI warnings. `focused-r19.log`: 246 tests / 68 subtests.
- `workflow-strict-r19/summary.json`: **6,000/6,000** declared outcomes, aggregate
  source unchanged; counts 1,400 pass / 1,800 observed state / 2,500 expected
  rejection / 300 expected nonexecuting rejection. Manifest
  `9ebcef14e70dfab229441fc6a38ed7b3a793fcbe8c96efd09c581befccff6449`.
  `level-a-r19/summary.json`: **45/45**, all 15 ability classes. Subsequent changes
  finalize documentation only; final documentation/policy checks are retained below.
- `asset-contract-migration.json`, `primary-intent-migration.json`,
  `ga-test-migration.json`, `workflow-freeze-ledger.json`, `seed-migration.json`
  record authorized wire/reference migration with original inputs, contrast sets,
  splits and provider/safety outcomes retained. Four readiness fault families move
  GI → Planner. Strict ModelReplay request comparison is unchanged.
- `retained-goal-reference-limitations.json`: 200 of 1,500 GA references are explicit
  Schema/DTO-valid Host rejections for old typed-state updates. Use an explicitly
  sourced replacement Goal; do not preserve stale typed parameters. The other
  1,300 are Host-accepted references. None is native-model/training qualification.
- `native-gi-r5/adjudication.json`: **19/24 semantic, 24/24 mechanical**. R6 is
  rejected (14/24 semantic), R5 prompt restored. `native-ga-current/summary.json`:
  **24/24 native new-Goal** transactions using controlled correct GI input; no
  native continuity or 1,500-case GA claim. Reviews are non-independent.
- `live/`, `live-r16/`, `live-r19/`: three complete discovered 51-case invocations,
  each stopped at first hard failure, **0/1, 50 unrun**. Native packets and all-call
  adjudication are in `live-native/`, `live-r16-native/`, `live-r19-native/`.
  Exactly one bundle per stopped aggregate, respectively:
  `/home/chromie/Downloads/chromie_debug_bundle_20260916_014540.tar.gz`,
  `/home/chromie/Downloads/chromie_debug_bundle_20260916_032148.tar.gz`,
  `/home/chromie/Downloads/chromie_debug_bundle_20260916_033536.tar.gz`.
  Raw private evidence is not committed or suitable for publication without review.
- `runtime-identity-r19.json`: identity
  `cb8d923a51850ad769e0682de783c207b54a1021d814f15cf24a58414406c32f`,
  evaluated dirty source tree
  `f5186e4b63d08d2bce868e3ec0a8a098314fc6e2bc3fb677fcd954d0f021ca58`;
  `evaluated-r19.patch` retains tracked changes before final handoff edits.
  `agent-source-r19.json`: checkout/container both
  `1a59ecdb05fe8bbc9decac004e168f7f9e8f657c76b770942fb3eb910fc54894`.

### Runtime and cross-machine resume

Local RTX 4090 Laptop, Ollama 0.33.2 / Qwen3.5 4B, existing interactive
voice_mujoco profile. GI context/output 16384/512; GA 32768/2048;
Fast/Deep 49152/4096; SC 49152/1024, temperature 0, top_p 0.9, think false.
Configured priority does not establish Ollama preemption or a 2-second response.
Remote Gemma evidence remains unavailable here. No profile or training promotion.
Newly source-based waiting supports all selected Goals waiting; mixed new
waiting/ready Goals need further qualification. #24/#32 remain open.

After retained safe idle, the owned headless simulator/MCP launcher was terminated;
those containers stopped. Agent/ASR/LLM/TTS remain healthy, no Host Orchestrator.
No physical microphone, speaker or robot session occurred. TTS warm-up/harness audio
was discarded. Existing owner microphone/ASR acceptance is unchanged.

Reproduce using fresh evidence directories; preserve local work and fetch first:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir /tmp/chromie-intent-next-replay
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir /tmp/chromie-intent-next-level-a
```

For another automated aggregate, start `./scripts/start_soridormi_mujoco.sh
--no-viewer` from the paired repo, then `./scripts/start_chromie.sh --no-orchestrator
--keep-services` from Chromie. Verify `python scripts/capture_runtime_identity.py
--verify-agent-source chromie-agent`; rebuild through `./scripts/start_voice_mujoco.sh
--build` for a personal supervised voice session when source differs.
For headless automation, capture a fresh identity with `--orchestrator-env
.chromie/voice-runtime/orchestrator.env --capability-manifest capabilities/soridormi.json
--compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --allow-dirty
--output NEW/runtime-identity.json`. Source the generated Orchestrator environment,
then run `python scripts/general_ability_acceptance.py --mode live-text --stage
must_pass --execute --soridormi-repo /home/chromie/github/soridormi --runtime-identity
NEW/runtime-identity.json --evidence-dir NEW/live`. Keep one source/deployment for
all cases; collect exactly one debug bundle after completion or hard stop and review
every attempted case. Final native failure is retained, not converted to a pass.


## Cross-machine resume baseline — 2026-09-15 (historical)

Owner requested upstream update and continued development. Fetched both remotes;
Chromie `main` is already `6fca5be2b590a4b1ca83d49fb197cdd74b50b2d0`, Soridormi
`codex/turn-count` is `fa6331f1344ce26154b197ca7d7c49badea292ad`, both current.
No merge or stash was needed. Preserve Soridormi's local playground-submodule
content and uninitialized Mini Runtime submodule. No commit/push was performed.
Only this handoff, checkpoint and Status gain the new evidence state.

R = `.chromie/acceptance/resume-20260915-6fca5be2/` (local, ignored):

- `canonical.log`: 3,510 tests / 1,164 subtests, 145 benchmarks, 20 legacy tests;
  policy, ownership, static, configuration and documentation gates pass; two
  existing FastAPI warnings. `level-a/`: 45/45. `workflow/summary.json`: all
  6,000 expected outcomes, source unchanged, manifest
  `31ff225d1b84ab34946d135e420c48664ff23f369c07f4fb814ed9f563768083`.
- `agent-build.log`, `services-start.log`, `agent-source.json`: stale Agent rebuilt
  and recreated; host/container digest both
  `eb3839ab3ac4c6b283b6c569ff691d5be3a8867724d325324ba4a99a61ca3a7a`.
- `runtime-identity.json`: clean evaluated revision, identity
  `3a88193a0a59d954a0e869679e3ae0e9729fd0eff718aa5afcbd5a74d6a5aad5`;
  RTX 4090 Laptop, interactive voice_mujoco profile, Ollama 0.33.2 / Qwen3.5 4B.
  `ollama-models.json` retains installed model digests. This is not the remote
  Gemma profile. Subsequent documentation edits are outside that clean identity.
- `live-manifest.json`, `live/`, `live.log`: one discovered 51-case must-pass
  invocation with execution enabled and discarded audio; first case failed,
  50 unrun. `native-calls.json` and `adjudication.json` retain/review GI primary,
  source-based Deep, GA and late SC outputs. Fast advance was cancelled without
  a completed raw response. See checkpoint for actual module I/O and attribution.
- Exactly one aggregate bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20260915_232529.tar.gz`;
  `debug-bundle.log` records collection. Private evidence is not publishable raw.

The owned headless Soridormi launcher was stopped after retained safe idle.
Agent/ASR/LLM/TTS services remain available with refreshed local configuration;
no Host Orchestrator or physical microphone/speaker session was started. Startup
TTS synthesis discarded PCM. Previous manual microphone/ASR acceptance is unchanged.
The native GI/GA failures remain unresolved; no experimental prompt was restored,
model replaced, validator weakened, or training reference promoted.

Resume by fetching/checking both branches, preserving local work, and inspecting
R/`adjudication.json`. Reproduce source checks using new evidence directories.
For personal voice testing use `./scripts/start_voice_mujoco.sh`; packaged Agent
source matches the current executable checkout. For another automated baseline,
start Soridormi headless, use `./scripts/start_chromie.sh --no-orchestrator
--keep-services`, verify packaged source and capture a fresh runtime identity.
Run `scripts/general_ability_acceptance.py --mode live-text --stage must_pass
--execute` with the current generated Orchestrator environment, explicit identity,
paired repository and a new evidence directory. Keep one source/runtime throughout,
collect exactly one bundle at completion/hard stop, and judge every attempted case.
GI remains the earliest semantic failure; a downstream GA quantity-format repair
alone cannot establish whole-transaction correctness. No new qualification claim.

## Source-backed lightweight handoff delivery — 2026-09-15 (historical)

Owner authorized commit/push and asked to finish quickly. Deliver the validated
interface changes and earlier completed engineering work; do not continue tuning.
Repo `/home/chromie/github/chromie`, branch `main`, pre-delivery base
`a1ed4b4b22ee82ee846321b67df2d088d5226599`; resume at the latest commit carrying
both handoff files. Paired Soridormi remains
`fa6331f1344ce26154b197ca7d7c49badea292ad`. Upstream was fetched, divergence 0/0
before editing; fetch/verify again immediately before push. No force push.

Implemented workflow and boundary diagnosis are in the current checkpoint:
Host immutable source + accepted GI → concurrent GA / Fast; GA inherits complete
query without mandatory duplicate query_scope; Planner realizes literal source
arguments with ownership/contradiction checks. Counts, measured values, activation
and trusted target evidence keep their guards. SC still owns ordinary wording.
GI default prompt simplification **was not promoted**: two frozen candidates
regressed. Original GI prompt/interpreter are byte-identical to the before files.
This delivery supports sparse GI results but does not establish a lighter default
model output, latency gain or completed Qualification.

J = `.chromie/acceptance/gi-source-handoff-20260915/`:

- `canonical.log`: 3,510 tests / 1,164 subtests and 145 benchmark tests; legacy
  completion recorded at the end. Policy, test ownership, Ruff, mypy, configuration
  and docs gates are part of that command. Two existing FastAPI warnings.
- `workflow-summary.json`: 6,000 expected outcomes; `workflow-full.tar.gz` fully
  read-verified, SHA256 `b34f298f1d83363481bdb0d8123f3f241c690699d1c15f5d2c510477120690df`,
  16,602 members. Owned `/dev/shm` replay directory removed after verification.
- `level-a/summary.json`: 45/45. `focused-final.log`: 900 tests / 712 subtests before
  five final canonical provenance tests; all are covered by the canonical run.
- `request-refreeze-review.json`, `pre-request-refreeze.tar.gz`: 5,205 changed
  request-only scenarios / 10,513 requests. No expected response/oracle changes.
- `semantic-review.json`, `candidate/`, `final/`: 46 rejected GI responses; neither
  candidate directory contains the delivered GI prompt. Baseline reused from I
  after exact source/prompt byte verification. All training_eligible=false.
- `native-downstream/`, `native-downstream-review.json`: controlled GI references
  with no query bindings pass real GI Schema/Host; native GA 4/4 and pre-GA Fast
  4/4 retain correct queries/arguments. Canonical Fast/Deep 0/8 semantic acceptance:
  evidence absence mistaken for clarification, contradictory dispositions/steps.
  No provider execution, SC, microphone, speaker or robot claim. Separate failed
  URL preflight retained; no model inference in that preflight.
- `runtime-source.json`: host source differs from running Agent; deployment was
  not updated. The original mic/ASR owner acceptance stays closed.

Commands to reproduce after checkout:

```bash
./scripts/run_tests.sh
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir /tmp/chromie-source-handoff-level-a
python scripts/run_workflow_replay.py --workers 8 --evidence-dir /dev/shm/chromie-source-handoff-next
./scripts/start_voice_mujoco.sh --build
```

The last command is the owner's personal test entry point, with a rebuild needed
for this checkout. The retained prior 51-case live cohort is incomplete and its
GI/Planner/SC failures remain open. No further model/prompt/architecture optimization
or training is authorized by this handoff alone. Native evidence archives are local
retained artifacts; committed fixtures reproduce deterministic checks on another
machine without those archives.

## GI intent handoff experiment — 2026-09-15 (previous experiment)

**Runtime simplification was not safely completed.** All trial prompt/Schema/DTO
changes were rejected and rolled back. Current production behavior is the preceding
Schema-deduplicated revision; no deployment or fixture rewrite occurred. The owner
has already authorized the lighter intent-preserving direction, so do not ask for
that same approval again. It still requires a non-regressing implementation.

Read the current checkpoint for module I/O, precise failure classes and scope.
Evidence: `.chromie/acceptance/gi-intent-handoff-20260915/`:

- `frozen-manifest.json`, `corpus/`: 18 cases / 23 primary/Deep transactions.
- `baseline/`: immutable native baseline; 21/23 mechanical acceptances.
- `candidate*/`, `probe.log`, `semantic-review.json`: all 106 retained native
  responses, including rejected/incomplete experiments. No candidate was promoted;
  wrong atomic decomposition and invented constraints cannot be averaged away.
- `focused-final.log`: 102 tests / 136 subtests. Controlled sparse-query path passes
  GI Host → GA → Planner; explicit numeric omissions still reject.
- `level-a/summary.json`: 45/45 Level A; no native robot claim.
- `canonical-final.log`: 3,481 tests / 1,164 subtests, 145 benchmarks and 20 legacy
  tests pass; two existing FastAPI deprecation warnings. Policy, ownership, static
  analysis and docs checks pass.
- `runtime-final.json`: restored host/deployed Agent both
  `3e17a056a40e81dc199a5df3490ec102e47ba36e2917ce17577eed132699dd06`.
- `prompt.before.txt`, `model_interpreter.before.py`: byte-identical to final
  runtime source. `prompt.candidate-*` are rejected evidence, not resume targets.
- `refreeze.py` was dry-run only; replay fixture responses/oracles are untouched.

Retained changes are two GI tests, two downstream test variants and correction of
one stale SC wording-owner sentence. No Git commit/push. Existing uncommitted work
and Schema deduplication are preserved. Mic/ASR stay owner-accepted; whole
Qualification stays open. No speedup or successful architecture migration is claimed.

Next: owner checks Chromie using `./scripts/start_voice_mujoco.sh`, then decides the
next data/training/architecture step. Do not keep broadening prompt rules without
clear evidence; do not add a semantic reviewer or case-specific runtime rule.

## GI Schema deduplication — 2026-09-15 (preceding)

Owner authorized the reviewed bounded experiment. **Schema deduplication is
implemented; model Qualification remains open.** Next work remains the owner's
personal Chromie check and decision. No prompt rewrite, candidate pruning, weights,
training promotion, commit or push. Microphone/ASR stay closed by owner-reported
acceptance. Earlier sections retain their evidence and are superseded here.

Base `a1ed4b4b22ee82ee846321b67df2d088d5226599`, uncommitted on `main`;
origin fetched and divergence 0/0 before editing. Previous dirty work is preserved.
Evidence root: `.chromie/acceptance/gi-schema-dedup-20260915/` (G below).

### Implemented boundary and measured result

GI primary and source-based Deep now reuse the existing
`SourceBackedBindingString` definition for location/duration/speed. Every original
character-slice value, applicability limit, context fallback, numeric alternative,
field description and semantic owner remains unchanged. No new semantic decision
or repair call is added. Tests preserve exact-source acceptance/rejection and
numeric alternatives, and assert one serialized enum in the native request.

| Boundary / evidence | Actual result and limit |
| --- | --- |
| Immutable example → GI Schema | The 39-character weather question previously copied one 748-value list three times. It now references one identical definition. Earliest redundant boundary repaired: request serialization, not human meaning. |
| Frozen 12-case / 16-variant comparison | All 16 expanded schemas match exactly; messages/model/options unchanged. Baseline and candidate each pass Schema/DTO/Host 16/16, with byte-identical paired raw outputs. Four independent source-based Deep variant screens are not automatic repair calls. |
| All 40 native calls | 32 full-cohort calls plus 8 interleaved warm calls pass mechanical checks. Model semantic failures remain identical. Partial rubric 8/16 is not complete acceptance: full review passes 1/16 under source-span, sparse-binding and uncertainty requirements. Cross-clause `parcel` vs `A parcel` preserves the same exact referent and is accepted. |
| Actual weather request | 78,500 → 52,973 transmitted bytes (32.5% lower); compact Schema 58,409 → 32,882 bytes. Model input tokens remain 3,836. |
| Measured execution cost | Request JSON serialization median 0.490 → 0.323 ms across 20 alternating blocks per arm. Four warm calls per arm: 4.3256 → 4.3312 s median; no end-to-end speedup established. First-observed latency is not proven cold compilation; no shared cache flush or model restart. |
| Downstream scope | No GA/Planner/SC/Work/robot invocation in the role experiment. This is native GI evidence, not a whole-robot qualification or microphone proof. |

Retain this small equivalent reduction in transmitted data/serialization cost; do
not claim model-token, response-speed or accuracy gains, and stop before broader
optimization. Full per-case review: G/`semantic-review.json`; comparison and source
proof: `comparison.json`, `equivalence-proof.json`, `authority-audit.md`.
The frozen corpus and requests contain no target labels during inference and
remain training-ineligible. Review is not independent model qualification.

### Validation and retained snapshots

- Focused: **115 tests / 173 subtests** pass. Level A **45/45**.
- Complete final workflow replay: **6,000/6,000 expected outcomes**, unchanged source;
  `workflow-final-summary.json`. It does not measure model ability.
- Final canonical gate: **3,477 tests / 1,161 subtests**, **145 benchmarks**,
  **20 legacy tests** pass, including pinned static/policy/ownership/config checks;
  two existing FastAPI warnings. G/`canonical-final.log` retains the result.
  The earlier pre-refreeze gate was intentionally interrupted, not passed.
- Final replay archive read-verified: **16,602 members**; owned temporary directory
  removed. G/`workflow-archive-verification.json` retains this check.
- First replay produced 4,585 exact GI request-snapshot mismatches, retained in
  `workflow-before-refreeze-summary.json` and `workflow-before-refreeze.tar.gz`.
  Only request Schema snapshots were then refrozen in **4,587 cases / 4,802
  transactions**, with 505 artifact replacements. Expanded schemas match; all
  messages, model outputs, expected outcomes, splits and training eligibility are
  unchanged. `pre-schema-refreeze.tar.gz` retains originals;
  `schema-refreeze-review.json` records proof. This extends the prior retained
  request-only refreezes and never rewrites semantic answers to pass.

### Runtime and resume

Local Agent was rebuilt; host/container digest matches
`3e17a056a40e81dc199a5df3490ec102e47ba36e2917ce17577eed132699dd06`
in G/`agent-source-final.json`. Existing Agent/LLM/ASR/TTS remain healthy;
no microphone or simulator was started in this pass. Paired Soridormi remains
`fa6331f1344ce26154b197ca7d7c49badea292ad`. Native model stays
`chromie-gemma4-12b`; GI prompts/budgets unchanged. The old exported GI example is
an immutable pre-change snapshot; the new request is retained in
G/`candidate/weather_en_today-primary.json`.

For the owner's personal check, from the repository root:

```bash
./scripts/start_voice_mujoco.sh
```

Full Qualification is still blocked by the earlier native GI/Planner/SC failures
and incomplete 51-case live coverage. This pass additionally retains exact GI
source-span, time-field, capability-question-context and unresolved-referent
failures; no semantic repair is claimed. Further prompt/data/training direction
awaits the owner's decision. New current documents, environment variables and
runtime flags: zero; no authority or architecture amendment.

## Necessary engineering repair — 2026-09-15 (previous pass)

**Bounded engineering repair is complete; full Qualification remains open.**
The owner will personally check Chromie and decide subsequent work. Do not start
another broad engineering/prompt optimization or training pass without that next
instruction. Microphone/ASR remain **closed by owner-reported manual acceptance**.
Earlier sections retain history and are superseded by this resume point.

Uncommitted on `main`, base `a1ed4b4b22ee82ee846321b67df2d088d5226599`;
origin fetched and upstream divergence 0/0 before editing. Paired Soridormi remains
`fa6331f1344ce26154b197ca7d7c49badea292ad`. Prior dirty work, including the earlier
request-only fixture refreezes, is preserved. Evidence root:
`.chromie/acceptance/necessary-engineering-20260915/` (N below).

### Implemented scope and evidence

- Existing Fast native Schema now preserves GI-authored provider-required vocal
  mode: only the qualified vocal provider with that exact supported mode may bind
  that source. Missing/empty catalogs cannot substitute a body provider or invent
  one. Independent body sources and valid same-mode composition remain available.
- Existing Fast execution/delegation invariants are exposed as native state
  alternatives. This Fast result cannot both commit new Capability Work and request
  Deep for its unresolved decision. Complete execution and source-based delegation
  remain different results; full Schema/DTO/Host checks remain independent.
  This adds no semantic decision, retry, or authority. Already-committed other Work
  is unaffected. It does not make Deep an execution-failure-only path: consequential
  uncertainty may justify Deep before commitment; new execution Evidence can later
  reactivate Planner. Invalid Fast output is not automatically repaired by Deep.
- Seventeen mode/provider and nine execution/delegation regression cases were added.
  Final focused checks: **347 tests / 68 subtests**. Final canonical
  `canonical-decision.log`: **3,475 tests / 1,143 subtests**, **145 benchmarks**,
  **20 legacy tests**, including pinned static/policy/ownership/config gates; two
  existing FastAPI warnings. `workflow-decision-summary.json`: **6,000/6,000
  expected outcomes**, unchanged source; archive read-verified (16,602 members).
  `level-a-decision`: **45/45**. These do not establish model ability.
- Final frozen native five-packet screen: **3/5** contract and semantic passes.
  Reproduced provider substitution and execution/delegation contradictions disappear;
  two cases still fail on upstream decomposition/Planner grounding or invalid input
  questions. No prompts, model weights/profile/budget, corpus/oracles, current
  documents, environment variables or runtime flags were added/changed in this pass
  except the owned status documentation and Schema/tests described here.

### Final real workflow and known failures

Agent host/container source digest matches
`3bf6b5fe26ca3b3218fcceecf3dc76f7ba8bdaa30c17fef6226d440919fa8a73`;
`agent-source-decision.json` and `runtime-identity-decision.json` retain provenance.
One complete directory-discovered 51-case cohort was attempted on that fixed image:
**1/4 mechanical and 1/4 reviewed semantic passes; 47 unrun** after a contract failure.
`decision-live-review.json` reviews all four cases, including the mechanical pass.
All executed Work reached safe idle. All **10 SC calls** stopped normally (maximum
**678 tokens**), with no repeated-output truncation or changed-words identity collision.
This is injected-text/MuJoCo evidence with discarded playback, not physical proof.

| Actual module / handoff | Input → actual output; expected output and verdict |
| --- | --- |
| Compound GI → GA → Fast, `a235ce54` | GI correctly preserves three ordered outcomes and left direction; GA preserves three Goals. Fast selects negative yaw `-0.12` for left, despite the provider direction contract. First wrong boundary: Planner realization. Expected positive-left command. |
| Compound Runtime → Evidence → Planner/SC | Three selected commands complete, safe idle. Later cognition reports left complete; this is a downstream false outcome claim, not proof that the requested direction occurred. Ingress SC separately promised before planning. |
| Gaze/blink GI → GA → Fast → Runtime → SC, `5d426735` | Two independent parallel outcomes → gaze 3 seconds and blink count 2 with correct bindings → both complete → supported final Chinese completion. Reviewed pass. |
| Milk GI → GA → Fast, `2f4dc3ca` | Correct bring-milk outcome and available acquisition/delivery contract → Fast selects only walking at 0.15 m/s for 15 seconds as complete. Expected full resource outcome, or a grounded unresolved result. First wrong boundary: Fast selection/coverage. |
| Milk Runtime → Evidence → Fast re-entry → SC | Only walking completes; acquisition/delivery provider never runs. Fast explicitly equates that Evidence with bringing milk; SC says it has the milk. Wrong semantic satisfaction and downstream false completion, plus an independent premature ingress promise. |
| Singing GI → GA → Fast, `624a907a` | GI merges walking into one singing Responsibility; GA retains one Goal. Expected two independent outcomes. Fast invents a song-content gap tied to resource acquisition and omits required schema-inspection evidence. Full validation rejects before Work; no Deep call repairs it. |
| Concurrent singing SC → playback | Without an established Plan/input Need, SC promises both actions and asks which song. Separate semantic overreach. Harness `cognitive_text_check_failure` text is not actual speech. |

Exactly one final-aggregate debug bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260915_142752.tar.gz`.
N/`root-cause-review.md`, `decision-native-review.json`, `decision-live-review.json`
and `decision-native-llmcall_*.json` retain actual I/O and comparisons. The first
mode-only aggregate stopped at 0/2 with bundle `chromie_debug_bundle_20260915_141612.tar.gz`;
it diagnosed the native execution/delegation gap before the second repair.

The previous R aggregate was 3/4 mechanical and 2/4 semantic; this final aggregate
is worse. The frozen native milk control still passes, but stable aggregate semantic
benefit/non-regression is **not established**. These are bounded existing-contract
repairs, not evidence of general ability improvement or qualification closure.
GI decomposition, Planner direction/whole-outcome satisfaction, SC promises and
47 unrun cases remain open. Training/reference/hidden-family and #24/#32 closure
are not inferred. No examples were promoted to training, and no commit/push occurred.
Current-document/environment-variable/runtime-flag counts have no net growth.

### Exact resume point: owner checks Chromie

The owned headless simulator launcher was stopped only after retained safe-idle
observations and the final bundle. Preexisting Agent/LLM/ASR/TTS remain healthy;
Agent is rebuilt from the tested source. From the Chromie repository root, the
normal personal test entrypoint starts the viewer and voice workflow:

```bash
./scripts/start_voice_mujoco.sh
```

No further microphone qualification is requested. Wait for the owner's experience
and chosen next direction. Before any later source development, preserve this dirty
work and fetch/check upstream again. Read N's reviews before choosing a repair;
do not add phrase rules, automatic semantic repair calls or retry cases into a pass.
Documentation updates after the aggregate only record results; its earlier captured
source-tree hash does not represent those subsequent documentation edits.

## Qualification repair — 2026-09-15 (previous pass)

**Qualification remains open.** The general engineering changes pass the local
checks, but the fixed Gemma model still fails semantic requirements in the native
workflow. Microphone/ASR remain **closed by owner-reported manual acceptance**;
they are not a blocker for this work. No fine-tuning, training-data promotion,
commit or push occurred. Earlier sections are historical and superseded here.

Uncommitted on `main`, base `a1ed4b4b22ee82ee846321b67df2d088d5226599`;
upstream fetched/current before editing. Paired Soridormi remains
`fa6331f1344ce26154b197ca7d7c49badea292ad`. Existing dirty work was preserved.
Evidence root: `.chromie/acceptance/qualification-closure-20260915/` (R below).

### Implemented and verified

- SC generates reason and exact Need accounting before its Activity array, with
  compact native JSON. Required questions use native ask branches consistent with
  Host. The complete raw JSON Schema is validated before DTO/Host, including unions
  and references skipped by the former argument-only validator.
- The unchanged authoritative delivery ledger is presented before larger context.
  With prior acts present, the native Schema offers eight fresh request-scoped IDs
  and allows an old ID only with its original words. This preserves explicit
  multi-act repetition and existing playback reuse; it does not select meaning.
- Fast's aggregate disposition procedure uses distinct current per-Goal decisions.
  Native timing branches preserve GI relations and provider compatibility. Bounds
  common to every valid Work assignment are exposed before generation, preventing
  completed response-only re-entry from reissuing Work.
- Fast's selection procedure compares the whole requested terminal outcome with
  Capability scope/effects; a prerequisite alone is not complete fulfillment.
  Three stale GI/DTO descriptions now correctly name SC as the sole wording owner.
- No case/phrase rules, second semantic judge/repair call, weights, budget, new
  environment variable, runtime flag or current document were added. SC's semantic
  system prompt is unchanged. Previous context/budget/order repairs are retained.

### Current evidence and actual failure path

- `canonical-final.log`: **3,449 tests / 1,143 subtests**, **145 benchmarks** and
  **20 legacy tests** pass; pinned static, policy, ownership and config checks pass.
  Two existing FastAPI warnings remain. SC focused: 157 tests / 40 subtests.
- `workflow-final-summary.json`: **6,000/6,000 expected outcomes**, source unchanged.
  `workflow-final.tar.gz` read-verified (16,602 members); Level A **45/45**.
- SC native `sc-state-screen/identity-pool`: **10/10** structural and semantic passes;
  `sc-owner-screen/identity-pool`: **12/12**, including actual EN/ZH conversation,
  Work/Situation and direct-deep variants. These are bounded native screens.
- Rebuilt Agent source matches host digest
  `60a90b61f8067d39638f680f7e24acdcccdaf280bfd732422a5dd0299f86b935`.
  `final-runtime-identity.json` binds exact source/corpus/services. Final full
  51-case injected-text/MuJoCo aggregate: **3/4 mechanical passes**, **2/4 reviewed
  semantic passes**, **47 unrun** after a hard failure. All completed Work reached
  safe idle. No physical evidence is claimed; delivery uses a scripted provider mock.
- All **10 SC calls** in that final aggregate stop normally (maximum **654 tokens**);
  no repeated-output truncation or immutable-ID collision. Compound completion,
  parallel gaze/blink and delivery all reach their final speech. Milk's initial
  promise still exceeds its then-established planning facts.

| Actual module / handoff | Input → actual output; expected boundary and verdict |
| --- | --- |
| Original SC primary → transport | Completed Work/Evidence + fresh Needs → repeated act until 1,024-token truncation. First wrong generation; transport correctly rejects partial JSON. Native decision order/compact format repairs the reproduced mechanism. |
| Delivery SC → Host | Old acknowledgement in ledger + new terminal Evidence → reused old ID with new words, HTTP 422. Request-local ID/text branches repair this earliest mechanical gap; final delivery uses fresh ID and completes. |
| Final GI, case `580989ad` | Exact walking-plus-singing source → one singing Responsibility, walking hidden in `comparison`; expected two independent outcomes and coordination. First semantic divergence. |
| Final GA → Fast | One defective GI Responsibility → one Goal; GA preserves its authority and cannot invent the missing outcome. Fast selects walking for singing; existing typed-mode Host rejects before Work. |
| Concurrent SC ingress → playback | No established Plan or input Need → promises both actions and asks which song. Separate semantic overreach; no repair call or literal phrase guard added. |
| Final Runtime / Soridormi | Rejected Fast decision → no Work dispatch; aggregate stops incomplete. Retained source and failure evidence are not converted into a pass. |

`root-cause-review.md` and `final-live-semantic-review.json` retain the complete
module I/O review and prior iterations. Original/parallel/fetch final SIDs:
`3e520d36`, `b583d3e7`, `3a1c7129`. Exactly one final-aggregate debug bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260915_134723.tar.gz`.

### Review corrections and remaining blockers

The previous SC completion screen's **5/10** semantic score is corrected to **7/10**:
its two pending cases reused the exact existing identity/words; actual Host replay
produced zero new syntheses. The three fresh-Need failures remain historical failures.
The broad SC screen's initial **9/12** review is corrected to **12/12** because its
frozen oracle permits useful conversation/question with Need pending. Host has no
reverse covered-if-spoken invariant and pending metadata alone schedules no retry.
Neither correction changes output, corpus or runtime state. See `pending-playback-proof.json`,
`pending-review-correction.json` and `sc-owner-identity-review.json`.

Native model qualification is still blocked by combined-outcome decomposition,
exact modality/Capability preservation, premature promises/unestablished questions,
and retained directional variation in earlier full iterations. Explicit existing
contracts and complete source packets do not reliably produce the right semantics.
The last 47 cases are unqualified. Fine-tuning/reference/hidden-family and #24/#32
closure are not inferred from local passes. All retained cases remain training-ineligible.
Do not add phrase patches or weaken these gates to obtain closure.

Request-only fixture refreezes: aggregate prompt (4,605 cases), shared Work bounds
(2,805), retired wording-owner descriptions (6,005). Responses, expected outcomes,
scenario intent and training eligibility remain unchanged; originals are retained
in `pre-prompt-refreeze.tar.gz`, `pre-bounds-refreeze.tar.gz` and
`pre-owner-refreeze.tar.gz`, with per-change reviews. The large fixture diff is
intentional. Failed identity/Need prompt trials, regex constraints and expanded
Fast assignment schemas were not promoted.

### Exact resume point

Owned headless simulator launcher was stopped after retained safe-idle observations
and the final bundle; preexisting LLM/Agent/ASR/TTS services remain. Agent is rebuilt
from the tested source above. Documentation edits after the aggregate only record
its results; they are not represented as part of the earlier captured tree hash.

1. Read R/`root-cause-review.md`, `final-live-semantic-review.json` and the final
   native packets before selecting another repair. The first unresolved boundary
   is GI atomic decomposition; SC wording and Fast modality remain distinct owners.
2. Preserve dirty work and fetch/check upstream before further source development.
   Do not use a post-hoc model judge, literal utterance rules or automatic training
   promotion. Model comparison/fine-tuning is not represented as a completed repair.
3. For source changes, rerun the matching frozen native contrast cohort and the
   complete live cohort on one rebuilt identity; do not retry isolated cases into
   a revision pass. Retain one bundle at the aggregate stop and review every case.

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_test_ownership.py
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir /dev/shm/chromie-workflow-next
python scripts/general_ability_acceptance.py --mode level-a --execute --evidence-dir .chromie/acceptance/level-a-next
```

Use new, unused evidence directories. To reproduce the broader native SC screen,
run `python .chromie/acceptance/qualification-closure-20260915/sc_owner_screen.py
next .chromie/acceptance/qualification-closure-20260915/sc-owner-screen/identity-pool/corpus`
from repository root, with Gemma/SGLang at loopback 30000. Its original rubrics stay
outside model packets. The ten-case script hardcodes its old output name; copy it
with a new output name before re-execution so retained evidence is not overwritten.

For full live evidence, start the paired Soridormi headless launcher from its repo,
verify/rebuild Agent using `.env.runtime`, `docker-compose.yml`,
`docker-compose.sglang.yml` and `.chromie/voice-runtime/compose.voice-mujoco.yaml`,
then capture a fresh runtime identity. Retained Host input profile:
`.chromie/acceptance/sc-completion-20260915/orchestrator.env` (text injection and
ordered discarded playback). Run `scripts/general_ability_acceptance.py --mode
live-text --stage must_pass --execute --runtime-identity <new-identity.json>
--evidence-dir <new-directory>` with that profile; collect exactly one debug bundle
after the aggregate. Do not rerun microphone/ASR as a prerequisite.

## SC completion repair — 2026-09-15

Microphone/ASR remain **closed by owner-reported manual acceptance**. This work
uses native model calls and injected text/MuJoCo; it makes no physical claim.
Uncommitted on `main`, base `a1ed4b4b22ee82ee846321b67df2d088d5226599`,
upstream fetched/current before editing. Earlier sections retain prior iterations.

Root cause of the retained failure: SC's primary result repeated an already
complete communicative act, exhausting the 1,024-token output budget before JSON
closure. Truncation was downstream containment. The original decoder permits a
complete single-act response; an unchanged replay finished in 751 tokens. Thus
neither insufficient budget nor mandatory act cardinality explains this case.

The existing native Schema now presents disposition, reason and Need accounting
before the variable-length Activity array. This changes generation order, not
semantic authority, field meanings or allowed act count. The exact originating
request reproduced duplicate-ID truncation before the repair, then completed with
one unique act in 747 tokens in both ordered and final cohorts. This supports the
field-order repair empirically; it does not prove universal model reliability.
A separate native Schema gap exposed by the contrast run is closed: Memory arrays
must be empty outside Situation ingress, matching existing Host validation.

No semantic prompt, weights, output budget, retry/judge, case rule or single-act
cap changed. Prompt-only and formatting-only trials did not qualify and were
reverted. Explicit repetition with 2 or 8 distinct act IDs remains valid; duplicate
IDs fail closed without a second model call. Situation Memory remains supported.

| Module / actual handoff | Input → output and expected boundary |
| --- | --- |
| Origin GI/GA/Fast → Runtime | Three source Responsibilities and sequential actions → three completed simulator results with safe idle; observed correct |
| Origin Fast → SC primary | Accepted return Plan, three fresh answer Needs and completion evidence → one complete act followed by identical ID/text/ref copies; first wrong boundary |
| Origin transport → Host | 1,024 tokens of unfinished JSON → `output_truncated`, no partial resolution or playback; correct containment |
| Repaired SC primary → Schema/DTO/Host | Same original packet with decision/coverage-first Schema → one act/747 tokens; valid multi-phase two-act controls retained |
| Current live Fast evidence reentry | Three completed results → top-level `mixed` but every Goal `respond`; DTO rejects the contradiction before post-completion SC is invoked |
| Current live Host → output | Retains completion evidence and safe idle; no TTS. The scenario fails; this is not evidence against or proof of post-completion SC behavior |

Final evidence, rooted at `.chromie/acceptance/sc-completion-20260915/`:

- `canonical-final.log`: **3,414 tests / 1,141 subtests**, 145 benchmarks and
  20 legacy tests pass, including pinned static, policy, ownership and config gates.
  Two existing FastAPI warnings remain. Focused SC: 120 pass.
- `workflow-final-summary.json`: **6,000/6,000** expected outcomes, unchanged
  source; `workflow-final.tar.gz` read-verified (10,601 members). Level A: **45/45**.
- Frozen native `final/`: **10/10 mechanical Schema/DTO/Host passes**, versus
  baseline 9/10. Semantic review is only **5/10**: fresh-Need silence and repetition
  of already-queued speech remain failures. Language-selector contrasts do not
  establish bilingual fidelity. No cases are training-eligible yet.
- Rebuilt Agent's exact original request returns HTTP 200 with silence/pending:
  no truncation, but required communication remains unqualified. Its packet matches
  the direct call, demonstrating residual semantic variation.
- Full 51-case native aggregate: **0/1 passed, 50 unrun**, stopped on the Fast
  contradiction above (SID `246ded32`). All three simulator actions completed,
  safe idle retained. Initial SC calls completed; post-completion SC was not called.
  `live-semantic-review.json` judges the executed case. Exactly one debug bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20260915_105607.tar.gz`.

Agent source digest (host/container match):
`cf147a18deb623c6b11fad69f91a7cc81b5b06313cb63924dbc4fd885bb8de22`.
Paired Soridormi remains `fa6331f1344ce26154b197ca7d7c49badea292ad`.
`runtime-identity.json`, `root-cause-review.json`, `semantic-review.json`, complete
native packets and `tested-implementation.patch` retain the exact evidence.
Owned simulator stopped after safe idle/bundle; preexisting services retained.
No commit or push. No new current document, environment variable or runtime flag.

Next: reproduce `live-fast-failed-native-call.json` at the Planner result boundary;
repair the general top-level/per-Goal contract without rewriting model semantics.
SC silence/queued-duplicate cases remain separate model-role qualification work.
Use `PYTHONPATH=. python .chromie/acceptance/sc-completion-20260915/probe.py NAME`
to rerun the frozen 10-case screen against the running native endpoint; review
all outputs, not just mechanical passes. After another implementation change,
rerun canonical gates and the complete live cohort with a fresh runtime identity.
Fine-tuning/release readiness is not promoted by this targeted completion repair.

## Engineering qualification — 2026-09-15

Owner acceptance update (2026-09-15): microphone and ASR validation are closed
for the current work based on the owner's report of personal testing and explicit
acceptance. Do not schedule repeat microphone/ASR qualification as a prerequisite
to continuing the engineering/fine-tuning preparation unless a new regression is
reproduced. This is owner-reported manual acceptance, not an automated test artifact.
The failed automated run below used injected text and bypassed microphone/ASR;
its remaining SC generation and model/Runtime coverage failures are separate.

Owner direction: move toward model fine-tuning by using cases to repair general
engineering boundaries, without case-specific semantic rules. This is an
uncommitted engineering pass on Chromie `main` at base
`a1ed4b4b22ee82ee846321b67df2d088d5226599`; no commit or push was made. Upstream was
fetched and current before development. Paired Soridormi was fast-forwarded to
`fa6331f1344ce26154b197ca7d7c49badea292ad` on `codex/turn-count`, preserving its
untracked submodule content. The earlier integration section is historical.

Implemented at existing owners:

- Planner required Goal, source, interaction and Evidence projections are lossless;
  the existing transport admits the whole request, including output reserve.
- Canonical Fast uses the existing request-local compact JSON format, preventing
  the reproduced syntactic whitespace tail without changing shared model settings.
- SC request construction reuses Context Assembly's current leaf projections,
  removing the duplicate Conversation aggregate and retained Host task history.
  Situation-selected relational memory is added after projection and retained.
- Planner materialization can discharge an AFTER edge to completed source Work
  only with exact source Plan/fingerprint, Goal/step and matching terminal Evidence.
  The authored relation and proof remain in Need facts. Unknown, BEFORE and current
  Work dependencies retain their checks; completion is not inferred Goal success.
- SC native Schema now realizes its existing communicate/silence/deliberate states:
  silence keeps needs pending; unresolved cognition commits no coverage or Memory.
  SC still owns whether to speak and every word. No semantic retry/judge was added.

No model weights, semantic prompt wording, global profile, case expectations,
product switch or first-class architecture owner changed. No new current document
or environment variable was introduced. A broader Fast native-assignment Schema
experiment was reverted after the actual production schema failed compilation;
its small decoder probe did not establish production validity.

Observed workflow and responsible boundaries (same three-action probe, separate
frozen revisions/iterations; all retained private artifacts under the path below):

| Owner / handoff | Material input and observed output | Expected contract / disposition |
| --- | --- | --- |
| GI → GA and Fast; SC runs independently | Ordered walk at 0.2 for 10 seconds, two nods, left turn → three Responsibilities, canonical Goals and sequential Work; initial SC silent | Source bindings conserved and requested Work executed in the observed case; no speech delivery inferred |
| Runtime / Soridormi → reentry | Three completed results, exact Plan/Goal/Evidence correlations and safe idle | Correct simulator completion; physical behavior unproven |
| Planner projection | Baseline SID `fcc265bf`: 12,803-character Interaction context rejected by a 7,000-character section quota before inference | Fixed: complete request admission at transport; frozen 30-case contrast is lossless, including 20 formerly rejected cases |
| CanonicalPlan materialization | SID `e17a70e4`: response-only Work referred to the exact completed `act_r1/r2/r3`; validation called them unknown new Work | Fixed mechanically from retained completion proof; bilingual Fast/Deep regressions also use a conditional information-acquisition episode |
| Host → SC context | SID `97aa4cff`: repeated aggregate/leaf state produced 181,655 input characters and budget rejection before generation | Fixed at Context Assembly ingress; frozen request serialization 172,556 → 99,745 characters, retaining current owners and Evidence |
| SC Schema → Host | SID `882fce75`: silence and three covered needs accepted by Schema, rejected by Host for absent verbal acts | Fixed existing decision-state invariant; 14 native contrasts pass in decoder field order. Exact frozen primary call now returns valid silence/pending, which still leaves the user update undelivered |
| SC primary generation → transport | Final SID `a17ee0ea`: Fast return accepted; SC used 39,124 prompt tokens, repeated one Activity ID three times and reached the 1,024-token output cap | Remaining failure: incomplete primary result, correctly blocked as `output_truncated`; no post-result speech. Repetition is observed; its deeper cause remains unproven |

Final automated evidence: `canonical-sc-final.log` passes 3,402 tests / 1,141
subtests, 145 benchmarks and 20 legacy tests, including policy, test ownership,
pinned static analysis, configuration and docs gates. Two existing FastAPI
warnings remain. `workflow-sc-final-summary.json` passes all 6,000 expected outcomes
with source unchanged (1,400 workflows, 1,800 states, 2,580 rejections, 220 expected
nonexecution outcomes); archive contents were read back and verified.
`level-a-sc-final/` passes 45/45. Focused SC tests pass 108; earlier context/order
focused tests pass 169. These are not physical or model-ability qualification.

Final native aggregate selected all 51 must-pass cases in one invocation and
stopped on its first hard integrity failure: 0/1 passed, 50 unrun. The three
simulator actions completed and safe idle was retained. Bundle collected exactly
once at aggregate end:
`/home/chromie/Downloads/chromie_debug_bundle_20260915_100642.tar.gz`.
Earlier failed iterations and one disk-interrupted run are retained as failures;
none were converted into passes. Bulk replay now uses temporary RAM storage and
verified compressed retention to avoid repeating that disk interruption.

Evidence root: `.chromie/acceptance/engineering-readiness-20260915/`.
`engineering-review.json`, `manual-semantic-review.json`, frozen packets/corpora,
`sc-final-truncated-native.json`, all logs and verified replay archives retain the
case workflow and limits. Final live identity is `runtime-identity-sc-final.json`,
SHA `db56da9f055ddb23af3a58a15115396142ca4050f5ad128c446600d29ad57303`, captured
before these documentation updates. Agent packaged source matched host digest
`9e777b256986bc982350ad38ef84275c8832b52bad97801b2903c681549b0c93`.
`tested-implementation.patch` SHA is
`62d293f059ede320c1ecbfb4b8dff7f3caf9fde5fb315fc780a5a2641fba2509`.
The Agent remains rebuilt with these changes; the task-owned headless simulator/MCP
launcher was gracefully stopped after observed safe idle. No operator Host was
replaced. These are local observations, not portable process identities.

Next: investigate SC primary Activity repetition and output-budget coverage from
the retained complete request and partial response, preserving multi-act
composability and independent wording authority. Do not force one act, rewrite
semantic output, add case rules, or tune frozen expected results. A broader native
cohort, independent reference review, hidden-family evaluation and #24/#32 closure
remain open; fine-tuning/release readiness is not promoted. No training was run.

Resume with fresh upstream verification and CHROMIE_RUNBOOK.md's machine-local
profile/rebuild procedure. Recheck packaged Agent source and capture a fresh
runtime identity. After any repair run `./scripts/run_tests.sh`,
`python scripts/general_ability_acceptance.py --mode level-a --evidence-dir <new-path>`,
and `python scripts/run_workflow_replay.py --workers 4 --evidence-dir <new-path>`
(use sufficient temporary storage, then verify the retained archive). Follow focused
proof with one complete `general_ability_acceptance.py --mode live-text --stage
must_pass --execute --runtime-identity <new-identity> --evidence-dir <new-path>`
invocation; keep source/services fixed through it, collect one debug bundle at its
end, and judge every executed case. Private evidence does not accompany a clone.

## Integration delivery — 2026-09-15

Owner authorization: integrate the newest remote SC design, resolve conflicts,
rerun validation, commit and push both repositories. Chromie was fast-forwarded
from `d5a7985e` to `2e18f86a` on `main`; Soridormi from `284273b` to `0af3d09`
on `codex/turn-count`. The paired provider integration is now committed and
pushed as `fa6331f1344ce26154b197ca7d7c49badea292ad`. Resume at the latest
Chromie delivery commit containing both handoffs. Original local changes remain
in recovery stashes; do not reapply them over this integration. Both repositories now require fetching/checking upstream
before development and again before push, preserving dirty work during integration.

The upstream SC design is authoritative: SC alone authors ordinary communication;
Planner authors Work and planning facts. Preserve SC > GI > GA > Fast scheduling,
separate Vocal/Activity waiting queues, prepared-start alignment and all remote
weather/evidence/catalog/argument-validation repairs. The old Planner wording
prompts were not restored. Complete catalog projection now uses the existing
transport budget at the new common Work prompt owner and layered projections.
Applicable local Schema/DTO, technical re-entry containment, typed diagnostics,
preflight/integrity collection and post-failure status regressions are integrated.
Soridormi keeps its new manifest validator and existing resource mappings,
adding only route-to-source realization and structured-input regression coverage.
Unrelated submodule content remains untouched.

Combined canonical passes 3,382 tests / 1,139 subtests, 145 benchmarks and 20
legacy tests, including policy, ownership, pinned static/configuration/docs gates.
Two existing FastAPI warnings remain. Full 6,000 SC-aware workflow replay passes
with source unchanged: 1,400 workflows, 1,800 expected states, 2,580 expected
rejections and 220 expected nonexecution outcomes. Level A passes 45/45.
Focused SC/Planner/acceptance: 785 tests / 364 subtests; rebound workflow: 104/104;
final re-entry: 15 tests / three subtests. Provider: 798 tests / two skips, body
165, task 147, governance, compile and manifest pass. The initial 68 failures were
exact Schema mismatches; only input-format snapshots and hashes were rebound on
the remote SC-aware corpus. The provider automatic merge also hid upstream mapping
keys; the existing regression caught it and all upstream declarations were restored.
Large corpus manifest: `3ba46381bf230f7a930982b05f8cebd9cb672ccd4efbfbdee14d0c4994084f04`.

Evidence: `.chromie/acceptance/sc-integration-20260915/` retains source recovery,
focused/failing/final logs, Schema rebind accounting and the aggregate replay.
The prior `.chromie/acceptance/engineering-18-20260914/` twelve-iteration Qwen
proof is historical pre-SC evidence only: 3,296 tests / 1,071 subtests and 6,000
replays passed there, but its native cohorts were incomplete. It cannot qualify
this SC integration. See the audit for original root causes and changed ownership.
No model weights, production model profile or decoding defaults are changed in
this integration; retain upstream's single-Gemma configuration. Local services
still package the pre-integration revision and are not fresh SC target evidence.
The earlier simulator/MCP were safely stopped; no new physical proof is claimed.
Fine-tuning/release readiness remains false; #24/#32, independent reference review,
hidden semantic-family evaluation and current target closure remain open.

Cross-machine resume: fetch and fast-forward both named branches, initialize
Soridormi submodules and follow CHROMIE_RUNBOOK.md for that machine's generated
profile and rebuild. Never copy another machine's PIDs or edit `.env.runtime`.
Run `./scripts/run_tests.sh`, `python scripts/general_ability_acceptance.py --mode
level-a --evidence-dir <new-path>`, and `python scripts/run_workflow_replay.py
--workers 4 --evidence-dir <new-path>`. Before native evaluation verify packaged
Agent source and capture a fresh runtime identity using the current CLI. Run a
complete discovered cohort with one revision and retain one bundle at its end;
judge every case and leave unrun coverage explicit. Private traces/scripts and
recovery archives are ignored/local and do not accompany a fresh clone.

## Delivery — 2026-09-14

Owner authorization: commit all accumulated project changes and push both paired
repositories. Chromie base is `ec4a5c268a557ac0f4281c668b1404edb96c57cc` on `main`,
remote `origin/main`; resume at the latest commit containing this checkpoint and
handoff. Paired Soridormi commit is `0af3d09` on `codex/turn-count`, containing
provider argument-realization contracts, manifest validation and tests.

This delivery includes single-Gemma priority scheduling (SC > GI > GA > Fast),
SC verbal/nonverbal Runtime handoff, separate Vocal/Activity waiting queues and
prepared-start alignment, token-budget verification and existing Schema invariants,
plus the reproduced catalog, weather, terminal-evidence and argument-serialization
repairs. The detailed module I/O and failure workflows below remain authoritative.
No case-specific semantic rules, extra model reviewer or Qwen promotion is included.

Latest unchanged-code gate: `.chromie/acceptance/qwen9b-comparison-20260914/canonical.log`
records 145 benchmarks, 3,303 tests / 886 subtests and 20 legacy tests passing,
including policy/ownership/static checks; two existing FastAPI warnings remain.
Documentation checks passed after comparison updates and are rerun for this delivery.
Earlier same-source evidence: 6,000 workflows and 45 Level A cases pass; paired
Soridormi full suite 790 passed / 2 skipped, governance and body concurrency pass.
Both executable patches were compared to their retained tested snapshots before
commit; full tests are not rerun solely for this delivery-document update.

Release readiness remains blocked: the 51-case native cohort stopped on wrong-sign
turning during its first case; focused right-turn/weather pass 2/2 does not replace
it. GI/GA/Planner semantic failures and #24/#32 remain open. The 44-request-per-model
Qwen comparison found lower latency but no qualified replacement; SC/Deep/physical
proof was not obtained. The failed and passing evidence below retains those limits.

Runtime stays on the restored single Gemma and existing operator Host (PID 854858,
launcher 852382, preserved text client 400841); details below are a local snapshot,
not a portable process identity. Commit metadata changes do not rebuild running
images. Before live validation, verify packaged source and capture a fresh identity.

Cross-machine resume: fast-forward Chromie `main` and Soridormi `codex/turn-count`,
initialize Soridormi submodules, read this delivery and the current comparison,
then follow `CHROMIE_RUNBOOK.md` to generate the machine profile and rebuild services.
Use `python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent`
and `python scripts/capture_runtime_identity.py --allow-dirty --output <path>`
as separate checks before an authorized full native cohort. Preserve single Gemma,
non-thinking, Soridormi safety ownership and supervised physical-evidence limits.

Raw traces, model weights, `.env.runtime`, `.chromie/acceptance/` and debug bundles
are local/generated or ignored artifacts, not included in Git. Their exact paths and
summaries are retained below; a new clone does not itself contain raw proof. Generated
social-eyes XML inside Soridormi's Open_Duck_Playground submodule also stays local;
no third-party submodule revision is changed. No tracked project edits are excluded.

## Qwen3.5-9B comparison — retained 2026-09-14

The owner authorized model comparison after the failed-case repair. Both frozen
44-request cohorts completed: GI 30, GA 6, Fast 8. Messages, dynamic Schema,
sampling, stream mode and non-thinking were identical except served model ID.
Official Qwen3.5-9B and Gemma-4-12B-it both used online FP8 in the same pinned
SGLang image, context 65,536; architecture-specific templates/parsers/cache differ.
The comparison made no production model replacement, semantic code/prompt change
or retry/judge call. Its preceding implementation is included in the delivery above.

Evidence: `.chromie/acceptance/qwen9b-comparison-20260914/`.
`report.md` owns this experiment's readable comparison; `adjudication.json` retains
all 88 reviewed outputs, module input/output evidence, earliest divergence and
containment. `manifest.json` freezes 44 case hashes; paired request equality was
verified with only model ID excluded. `source-before.patch`, exact raw requests,
responses, engine/model identities and offline validation are retained.

Both models pass 44/44 Schema checks. Corrected DTO/Host results: Gemma GI 30/30,
GA 6/6, Fast 5/8; Qwen GI 28/30, GA 6/6, Fast 6/8. A missing GI validator constructor
argument was a harness error, corrected offline for both complete raw cohorts;
there was no repeat inference or changed criterion. Reviewed Fast plans acceptable:
Gemma 3/8, Qwen 1/8. GA stage results: 4/6 versus 5/6, including required conservation
of invalid upstream WHAT, not successful originating episodes. GI strict oracle
5/24 versus 2/24 includes lexical/span false positives; no GI semantic accuracy
claim is derived from it. Uncertain manual GI judgments remain explicitly review.

Sequential request latency medians (Gemma/Qwen): GI 4.54/2.80 s, GA 6.81/4.01 s,
Fast 5.57/3.42 s. Qwen improves latency and one acquisition/handover classification,
but retains wrong turn direction, incomplete work claimed complete, misbound values
and invented semantic uncertainty. Both candidates remain unqualified. No SC, Deep,
whole-runtime, physical voice/robot or real-time scheduling proof was obtained.
Do not promote Qwen or infer a role split from this failure-focused sample.

Production restored to single `chromie-gemma4-12b`; temporary Qwen container is
stopped. Launcher PID 852382, text Host PID 854858, PTY 39865; existing client
PID 400841 preserved. Host evidence: `.chromie/acceptance/psm-live-text/20260914T120750Z/`.
Soridormi and configured speaker remain enabled; startup synthesis discarded PCM,
and no audible or embodied test was submitted. `restored-source-verification.json`
confirms packaged Agent matches source; `restored-models.json` confirms Gemma.

Current comparison follow-up gates pass: `canonical.log` records 145 benchmarks,
3,303 tests / 886 subtests and 20 legacy tests, with two existing FastAPI warnings.
Repository policy, test ownership, documentation and incremental static gates pass.
The comparison changed only retained evidence and existing status/handoff documents;
the preceding 6,000-workflow/45-Level-A and Soridormi results were not rerun here.

Next: retain the engineering patch and compare the remaining semantic failure clusters
at their earliest owner under the frozen-cohort method. No case rules, downstream WHAT
repair, or extra semantic-review call. #24/#32 and physical evidence gaps remain open.
Before another live cohort, gracefully stop the current Host, verify/capture fresh
runtime identity, run the whole discovered cohort, adjudicate every case and retain
one debug bundle per aggregate stop; restore the operator afterward.

## Failed-case repair — preceding 2026-09-14

Current source includes weather entity validation, early-read language and terminal
result handoff, SC structural evidence retention, aligned Fast argument serialization,
provider direction/duration realization metadata, and atomic catalog refresh visibility.
The checkpoint's current section owns the per-module failure/repaired workflow table;
`final-native/adjudication.json` retains the final actual episode and I/O. No case rules,
extra model reviewer, model substitution, commit or push were made. Preserve all prior
dirty work in both Chromie and `/home/chromie/github/soridormi`.

Chromie base is `ec4a5c268a557ac0f4281c668b1404edb96c57cc`, branch main, dirty.
Evidence root: `.chromie/acceptance/failed-case-repair-20260914/`.
`baseline.patch` and `soridormi-baseline.patch` preserve pre-repair state.
`final-canonical.log`: 3,303 tests / 886 subtests, 145 benchmarks, 20 legacy tests,
policy/ownership/static/docs checks pass (two existing FastAPI warnings).
`final-workflow/`: 6,000/6,000, unchanged source; `final-level-a/`: 45/45.
Paired Soridormi: 790 passed / 2 skipped in `soridormi-final-canonical.log`;
body concurrency/governance pass. Failed environment-only test attempts remain retained.

Final deployed identity: `cb2a9d0db2b062372758bc9be97d93c009f02b58cf9041233df4b882d0d092ff`.
Agent host/container source: `2b0283a4087a081d143a7d0d8bac655808555f7b0c9c0150b60f48bbd996e593`.
Full 51-case native aggregate stopped during first case after wrong-sign turn executed
and simulator returned safe idle: 0 completed summaries, 1 interrupted, 50 unrun.
Bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260914_194741.tar.gz`.
This is a hard semantic/provenance failure, not a passing revision. Final cold request
proves full provider catalog and complete numeric output but still plans right for left.
Other retained blockers: GI effect merging, GA dropping acquisition/handover resource
shape, Fast substituting partial locomotion or an unsupported vocal provider. Six-packet
Fast variant reviews and the unchanged 24-case GI screen are retained with separate
mechanical/oracle/semantic verdicts; neither qualifies the whole model role. No physical
microphone/speaker/robot proof or whole-runtime release readiness is claimed.

Post-aggregate focused regressions on the same runtime source pass 2/2:
`final-native/focused-live/` (right turn SID `6878f992`, weather SID `28a14ee0`).
Manual review confirms walk 3 s then negative-yaw right turn; weather uses 重庆/night,
returns matching provider data and SC reports grounded values through discarded PCM.
`final-native/focused-adjudication.json` records both. These focused passes do not
replace the failed complete-cohort attempt or establish prompt nonregression.

Operator restored: launcher PID 838087, Host PID 840376, PTY 28859;
`./scripts/start_chromie.sh --text-console --keep-services`. Existing text client
PID 400841 remains. Host evidence:
`.chromie/acceptance/psm-live-text/20260914T115053Z/`.
Capabilities and configured speaker are enabled; no automatic audible test was sent.
`restored-source-verification.json` confirms packaged Agent matches the checkout.
Documentation updates after runtime capture do not alter the tested executable source.

Next: retain the current engineering patch and review residual semantic failures before
any release claim. The subsequently authorized Qwen comparison is recorded above;
it did not qualify a production replacement. Keep Gemma 12B fixed and preserve the
global non-thinking boundary. The active #24/#32
line remains open; no scoped semantic acceptance or release acceptance is inferred.
Before any live rerun, inspect/stop the operator Host gracefully, verify packaged source
with `python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent`,
then separately capture a fresh identity with `--allow-dirty --output <path>`.
Reuse directory-discovered frozen scenarios, adjudicate every result, retain one debug
bundle per aggregate stop, and restore the operator afterward. Do not use phrase rules,
new semantic judge calls, or Host reinterpretation to repair GI/GA/Planner meaning.

## Scheduler alignment — preceding 2026-09-14

The owner-authorized lane scheduling and prepared-start change is implemented.
Preserve the earlier dirty work below; no commit or push was made. Evidence root:
`.chromie/acceptance/lane-coordination-20260914/`. The preceding SC handoff section
retains baseline/history; this section owns the current validation and operator state.

The reproduced defect was execution starting as soon as each provider returned
from its own preparation: parallel submission alone left an 80 ms start gap
(`baseline.log`). Runtime now maintains separate eligible-FIFO Vocal/Activity
waiting queues under one capacity/resource arbiter. Total capacity is unchanged;
with capacity > 1, one slot is reserved for Vocal and the remainder supports
compatible Activity concurrency. Required prepared members reserve resources
atomically and await one release; optional SC decoration cannot hold ready speech.
Each member releases resources independently after completion/cancellation.

SC's exact anchored verbal/nonverbal result is materialized once before Runtime
submission, including Situation and wordless entry points. Host waits for first
PCM/output readiness, Soridormi waits for plan/monitor/confirmation or existing
trusted SC preflight, and terminal results return to the social ledger. A reproduced
old Planner-only outcome guard now recognizes SC's source/owner without granting
Goal-completion authority. Optional provider loss is retained without suppressing
speech. No new prompt/model call, service, environment key or document was added;
existing `LaneCoordinationGroup.start_policy` adds/defaults to `prepared_start`.

| Actual controlled workflow | Input → observed output | Verdict |
|---|---|---|
| SC / semantic owner | One controlled informative utterance plus one exact anchored blink → unchanged act/anchor IDs | Controlled decision; not native inference |
| Adapter / materialization | Complete SC result → one packet, one coordination ID, no Goal ownership for blink | Correct; no independent expression dispatch |
| Runtime / scheduling | Two accepted members with distinct resources → one common release at monotonic 35952.817652954 | Correct shared Host release |
| Host PCM and Soridormi preparation | Blink ready 719 ms before PCM → neither advances before release; both complete | Correct preparation/transport, no physical-onset claim |
| Ledger / evidence | Real terminal results → speech completed and social decoration completed; simulator safe idle | Correct; admission is not completion |

Validation: `final-canonical.log` passes policy, ownership, static analysis, docs,
145 benchmarks, 3,295 tests / 876 subtests and 20 legacy tests (two existing FastAPI
warnings). `final-workflow/` passes all 6,000 cases with source unchanged;
`final-level-a/` passes 45/45. Focused scheduling/playback/SC matrix passes 107 tests /
32 subtests; broader Runtime checks pass 71 tests / 15 subtests. Negative cases cover
required preparation failure/timeout, optional lateness/resource conflict/provider
loss, unsupported compound preparation, cancellation, lane fairness and resource drain.

`queue-sim-bound/` proves real Host/TTS (discarded PCM) plus deployed Soridormi
simulator execution for controlled speech+blink. Identity SHA-256:
`e5462d3261e19898aa18f2f4153e63ff409c2ca093db368adce0f8360fa13f93`.
Agent packaged-source host/container digest both:
`5c335cd307cce67c8047b11721378b857a9c39a272caf0421f8321bbb7ee4ef0`.
The full directory-discovered native cohort was invoked once on this bound source,
without edits/restarts between cases, then manually stopped for confirmed hard
Goal-coverage/provenance failures: 0/6 completed cases pass, seventh interrupted,
44 unrun. `final-live-adjudication.json` records every completed module workflow,
actual inputs/outputs, expected contract, first wrong boundary and containment.
All 33 native call records are retained in `final-live-transactions/`; separated
Docker stderr avoids two interleaved records in the combined monitoring log.
One bundle for this aggregate:
`/home/chromie/Downloads/chromie_debug_bundle_20260914_190044.tar.gz`.

Remaining native failures are outside this scheduler repair: Fast output truncation;
GI merging independent gaze/blink or walk/sing responsibilities; Fast claiming full
milk acquisition/delivery from one 10-second walk; right-turn intent lost to an
omitted direction parameter; and weather resolving 重庆 to Zhongqing, Guizhou then
SC reporting those values as Chongqing weather. Case 6's separate missing-SC check
is an evidence-projection gap: SC actually returned an utterance and three PCM
segments completed. These failures are not averaged into a passing revision.

Evidence limits: initial adapters cover Host speech and a single Soridormi plan per
prepared group. Unsupported compound body preparation fails closed (optional
members may be omitted); ordinary same-provider batches retain embodied compilation.
There is no guarantee of identical physical onset, word/gesture alignment, atomic
cross-provider rollback or physical microphone/speaker/robot behavior. Physical
WorkDAG nodes remain sequential. Current release readiness remains development-only.

Retained harness failures are not production passes: initial build raced old Host
shutdown; the first identity command verified source but did not write an identity.
`queue-sim/` and `unbound-harness-run/` therefore do not establish bound evidence.
That incomplete native attempt was stopped and has one bundle,
`/home/chromie/Downloads/chromie_debug_bundle_20260914_185559.tar.gz`.
The corrected bound proof/cohort above replaces those claims. Early full-test runs
exposed fixtures assuming two Activity slots at total capacity two; those fixtures
now request capacity three while preserving their original concurrency assertions.

Operator restored: launcher PID 719138, Host PID 721389, PTY 27611;
`./scripts/start_chromie.sh --text-console --keep-services`. Existing user client
PID 400841 remains. New Host evidence:
`.chromie/acceptance/psm-live-text/20260914T110210Z/`. Source verification passed;
one resident Gemma 12B, capabilities and configured speaker remain enabled.
No automated physical playback was performed. Final documentation edits follow
runtime evidence capture and do not alter tested runtime source.

Next resume: inspect the retained native workflows and continue the existing
canonical/target-evidence delivery line (#24/#32), repairing earliest semantic or
provider evidence boundaries under the frozen qualification method. Recheck the
running Agent with `python scripts/capture_runtime_identity.py --verify-agent-source
chromie-agent`; inspect operator state before any further acceptance run. Stop the
Host before immutable live testing; preserve its separate dialogue client and
restore `./scripts/start_chromie.sh --text-console --keep-services` afterward.
Configuration keys 381 → 381; maintained Markdown documents 102 → 102; reading-path
entries 15 → 15. Existing execution-lane prose was consolidated rather than adding
a design document; one existing start-policy enum gained a value, no new architecture
layer or semantic authority.

## SC Runtime handoff — current 2026-09-14

The owner's SC speaking/social-attention queue requirement is implemented through
existing owners. One resident Gemma 12B remains; no prompt, model, semantic DTO,
service, environment key, architecture term or current document was added. Existing
dirty work is preserved; this continuation did not commit or push.
Evidence root: `.chromie/acceptance/sc-runtime-handoff-20260914/`.

Confirmed and repaired boundaries:
- The common independent SC response discarded its resolution, so GI-triggered
  optional expressions never reached Runtime admission. It now carries the exact
  request/snapshot and complete SC result, including wordless and mixed acts.
- SC invocation identity replaced the admitted user-turn ID, hiding early completed
  speech from later Goal-scoped context. Delivery now retains the source turn;
  inference/snapshot identity stays separate. Both weather live packets confirm
  that the later SC request sees the initial completed speech.
- Independent expression execution omitted terminal ledger feedback. The adapter
  now records actual completed/failed/cancelled results through the existing owner;
  admission alone never becomes completion or Goal satisfaction.
- Deployed Soridormi preflight still recognized the retired Planner auxiliary
  source; SC's queued blink therefore failed before execution. The same old source
  check also marked grouped SC decoration mandatory. Both now recognize SC source
  and semantic owner. Low-risk/non-motion restrictions, request/definition/body
  confirmation requirements and safety monitoring remain; no consent is fabricated.
  Situation's redundant resolution assignment was removed, preserving its dedicated
  freshness/concurrent-delivery path.

Actual repaired workflow (controlled decision; native GI/model choice is not
claimed by the queue probe):

| Owner / boundary | Authoritative input and expected output | Observed before repair → after repair | Handoff / evidence |
|---|---|---|---|
| GI → independent SC | Existing greeting Responsibility r1, original turn; SC may propose wordless blink. | Controlled request and complete SC result valid; real GI not invoked in this probe. | Exact request/snapshot retained in `queue-sim-final/`. |
| Common Host response | Complete SC result must survive transport. | Dropped expression result → exact request/result retained. | `baseline-boundary-replay.log`; mixed/wordless regressions. |
| SC adapter → Runtime | Validate source, anchor, live Capability, arguments, freshness, resources; enqueue optional request without Goal authority. | Missing result yielded no request → blink committed under original turn. | `social_decoration_committed`, real Runtime queue. |
| Soridormi provider | Fresh body plan says no confirmation required; low-risk blink and monitor accepted. | Old Planner-source check rejected SC → SC-owned preflight accepted; actual blink completed. | `queue-sim/` failure vs `queue-sim-final/` completion. |
| Completion → ledger | Record actual terminal provider result, never infer success from admission. | Missing independent terminal event → completed/failed/cancelled retained. | Live completed blink; controlled failure/cancellation regressions. |
| Playback → later SC | Completed early speech remains visible after GA Goal identity binding. | SC request ID hid user-turn speech → later native weather context has `already_spoken=1`. | Playback regression and both weather packets; duplicate new greeting remains a separate failure. |

Validation: `final-canonical.log` passes repository policy, ownership, documentation,
pinned static analysis, 145 benchmarks, 3,284 tests / 868 subtests and 20 legacy tests
(two existing FastAPI warnings). `final-workflow/` passes 6,000 cases with source
unchanged; `final-level-a/` passes 45/45. Earlier focused transport proof is 136 tests /
16 subtests; final provider/SC proof is 100 tests / 12 subtests. Negative preflight
cases cover retired/missing ownership, physical effects/class and all confirmation
sources. These local gates do not establish native-model ability.

`queue-sim/` retains the real queued-but-rejected blink; `provider-baseline.log`
reproduces two source-owner failures. `queue-sim-final/` binds the final runtime
identity and proves the same controlled SC nonverbal decision reaches the real
Runtime queue and deployed Soridormi simulator, then records
`social_decoration_committed` → `social_decoration_completed`, with safe idle.
The SC output is controlled, not a native semantic inference or physical proof.
`queue-sim-provider-focused/` retains the earlier successful focused replay.
Retained harness errors are not production failures: initial empty Responsibility
fixtures, first queue probe's wrong ledger accessor, and a final-cohort CLI typo
that started no case. Corrected failures/proofs have separate artifacts.

Final native/live identity SHA-256:
`b7ceb2c4973bf76e6716a04b4a256fb0021321597075222181c2a222a8ab1043`.
The complete directory-discovered cohort was invoked on each evaluated source,
without changes between cases. Each stopped incomplete at the fourth case's GI
HTTP503; three completed cases failed and 47 were unrun. One bundle per aggregate:
- Before provider-source repair: `live/`, `live-adjudication.json`, bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20260914_173851.tar.gz`.
- Final source: `final-live/`, `final-live-adjudication.json`, 15 retained native
  transactions in `final-live-transactions/`, bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20260914_174407.tar.gz`.

The final failures remain substantive: Fast Planner truncates the compound motion
output; another plan has a singleton parallel member; the milk request falsely
claims complete coverage with only a 10-second walk. Host admits that incomplete
milk Plan and the simulator executes the walk, without acquisition/delivery.
Fast/Deep evidence reentry then rejects required catalog projections (22,097 >
9,000 / 28,410 > 12,000 chars), while SC silence relies on an overbroad completed-task
projection. GI's singing/walking Responsibilities reuse overlapping source spans;
its HTTP503 is validation containment, not an engine outage. The supported
`coordination` wire field is not the defect. SC/GA/Planner were not invoked in that
interrupted fourth case. Do not report overall SC/Planner/robot qualification.

Both original weather probes complete native lookup and final grounded result
speech with discarded audio: 83.89 s / 83.05 s total, first simulated playback ends
at 15.93 s / 14.85 s. `weather-adjudication.json` and `weather-transactions/` retain
all results. Later SC context now contains initial speech, but both cases still
repeat the greeting under a newly created Planner communication Need. Current
Need coverage requires a new explicit verbal act; interpretation-triggered unbound
acts cannot respond/ask. Qualify that early-act/Need linkage as a complete semantic
transaction before changing it. Do not substitute a wording filter, invent Goal
completion, or let acknowledgement discharge an unresolved answer/action Need.
Repetition, latency, prior SC model truncation and #24/#32 release closure remain open.

Operator state restored: text Host PID 654715, launcher PID 652481, PTY session
2104, Host evidence `.chromie/acceptance/psm-live-text/20260914T094729Z/`.
Existing interaction client PID 400841 remains. Startup verified packaged Agent
source digest `62d104f162af5d3bd29046160e46098b60f19d3a4889f46c30cfb02e5fbdbd68`
and the single Gemma profile; capabilities and normal operator speaker are enabled.
Automated dialogue used discarded audio only; no physical microphone/speaker/robot
claim. The app terminal-open request is queued, not confirmed visibly opened.

Resume from `weather-adjudication.json`, the original weather packets and the
active SC exception: audit complete Need/early-act authority with the semantic
qualification skill, freeze the contrast cohort before semantic edits, then run
focused and full qualification. Preserve the current failed aggregate and prior
single-engine evidence below. For operator interaction use
`python scripts/chromie_psm_live_text_console.py`; logs stay with
`./scripts/start_chromie.sh --text-console --keep-services`.
Surface inventory remains 381 configuration keys, 102 Markdown files and a
15-document core reading path; no new current document/configuration surface.

## Single resident Gemma 12B — preceding evidence 2026-09-14

The owner explicitly superseded the dual-instance request with one resident
Gemma 12B SGLang engine. SC/GI/GA/Planner keep independent context and authority:
SC=500 > GI=400 > GA=300 > Fast Planner=200; Deep Work=100, background=0.
Both SC and GI preserve their priority in their permitted deeper pass. No new
model/service/environment key/current document or semantic authority. Existing
uncommitted startup, SC/GA and terminal-dispatch repairs remain intact. Dual
configuration and Qwen prompt experiments were withdrawn. No new commit/push.

Evidence root: `.chromie/acceptance/dual-inference-20260914/`; the historical root
name does not imply the selected topology. Dual Qwen AWQ/Gemma FP8 probes failed
at 18 GiB CPU offload (lazy NCCL CUDA allocation) and at 24 GiB (Deep exceeded its
unchanged 120 s deadline). Probe containers are stopped. The selected engine is
the original pinned Gemma FP8 profile without CPU offload; ASR/TTS and Soridormi
remain enabled. Generated `.env.runtime` is single Gemma again.

`priority-single-gemma/` proves both running priority-200 requests retracted once
for SC/GI and then resumed/completed. Foreground first tokens arrived 77–78 ms
after submission. This is synthetic native scheduling evidence, not whole-turn
response latency or semantic qualification. `single-budget-proof-margin2048/`
replays the complete original SC packet with the production 2,048-token margin:
50,060 input + 1,024 output + 2,048 margin = 53,132 < 65,536; native primary output
passes Schema/DTO/Host in 15.18 s. The provider now confirms estimated overflow
using its own tokenizer, retains full failure packets and returns typed failure.
No content pruning, second semantic call or increased timeout is involved.

Whole-turn evidence remains mixed. The original baseline completed 12/51 cases,
then stopped incomplete on an SC false budget rejection; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20260914_162109.tar.gz`.
The rebuilt single-engine aggregate completed three cases, all failed, and stopped
at case four's GI source-provenance rejection; 47 not run. Its one bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260914_165712.tar.gz`.
Every completed/interrupted result is adjudicated in `single-live-adjudication.json`.
Independent Planner numeric/coverage/schema failures and GI overlapping source
spans remain unqualified; the GI 503 is validation containment, not engine outage.

The two reported weather episodes were retained separately: `weather-today/`
completed lookup and result speech in 75.93 s headlessly; `weather-rain/` failed
an SC pre-action ordering invariant. Native frozen SC comparisons retain every
iteration, including failed output binding, missing expression and one truncated
output. The bounded decoder repair preserves upstream delivery-phase choices,
authors Need bindings before timing/wording, and requires a real expression for
wordless acts. Prompt, model, Host authority and generation budget are unchanged.
A focused native retry with recording passes, but does not erase the truncation.

Current-source canonical gate `expression-canonical.log` passes 3,274 tests /
860 subtests, 145 benchmarks and 20 legacy tests (two existing FastAPI warnings).
`expression-workflow/` passes all 6,000 cases with source unchanged;
`expression-level-a/` passes 45/45 cases. The earlier interrupted
`final-canonical.log` is not a passing gate. Native `sc-order-expression/` retains
12/13 passes; the weather case repeats acts until truncation. The original phase
and empty-expression shapes are now excluded, but the transaction remains
unqualified. Agent rebuild/source verification completed (digest
`62d104f162af5d3bd29046160e46098b60f19d3a4889f46c30cfb02e5fbdbd68`).
Current diagnostic runtime identity is
`7ac0718629eed501840a27d4f68564f7fb1049dd23af3fa6493cedf85411f79a`
(`expression-runtime-identity.json`, dirty/non-release evidence).
Native/physical stability, rapid interaction and #24/#32 release closure remain open.

The current-source live aggregate (`expression-live/`) again completed three of
51 cases, zero passes, then stopped at case four's GI validation failure (whole
admitted turn copied into `comparison`, not the prior run's overlapping spans).
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260914_171846.tar.gz`.
All 15 native calls and all completed/interrupted cases were inspected; see
`expression-live-adjudication.json`. In the milk case, unlike the prior rejection,
Fast claimed complete coverage with only a 10-second walk. Host admitted it and
the simulator completed locomotion, without acquisition/delivery. Later Fast/Deep
reentry hit required Capability-catalog projection limits (22,097>9,000 and
28,410>12,000 chars). Safe idle was observed afterward; the user goal was not met.
This is a real Goal-coverage failure and cannot be averaged into a pass.

Both original weather episodes subsequently completed lookup and grounded final
SC replies on the same revision: `weather-rain-expression/` 83.08 s and
`weather-today-expression/` 77.83 s; first virtual playback 14.79 / 14.04 s.
Both repeated the initial greeting in the later required response. Thus their
mechanical passes do not establish natural interaction or rapid response.
`weather-expression-adjudication.json` binds replies to provider data and retains
the duplication. The old packet has completed early SC speech in
`conversation.history` but no `interaction_context.already_spoken`; projection
and request/user-turn correlation remain an unresolved provenance audit, not a
claimed repair. No semantic same-stage repair call or latency budget increase.

Text Host is restored with `./scripts/start_chromie.sh --text-console --keep-services`;
ASR is bypassed, Soridormi remains enabled, and launcher logs stay separate from
the interaction client. Host PID 584502; retained Host evidence directory
`.chromie/acceptance/psm-live-text/20260914T092337Z`; launcher terminal session 49319.
The original client PID 400841 was left intact. The app terminal open request was
queued. Earlier pause/no-restart statements below are historical. Physical
microphone/speaker proof remains unclaimed; the restored operator Host uses the
normal speaker, while all automated scenarios above used no speaker.

Next resume: audit early SC delivery identity/projection and duplicate need
fulfillment at the existing authority; qualify complete Planner Goal coverage and
required Capability catalog projection, and the GI atomic-binding failure. Keep
one immutable aggregate per deployed revision, retain one bundle per stopped/full
cohort, and never promote focused passes over these failed whole-turn results.
To interact from repository root: `python scripts/chromie_psm_live_text_console.py`.
Do not start a second Host. No new commit or push; branch/base remains
`main` / `ec4a5c268a557ac0f4281c668b1404edb96c57cc` plus the preserved dirty patch.

### Current failure workflow and repair ownership

| Boundary / owner | Material input → actual result → expected result; verdict |
|---|---|
| Host admission → GI | Exact weather text admitted without ASR; GI accepted greeting r1 and weather r2. Correct transport; broader GI quality not inferred. |
| GI → concurrent SC/GA/Fast | Separate requests share the engine at their role priorities. SC has no dependency on Fast completion; independent Work still needs its canonical GA join. |
| Planner Need → SC | Greeting Need binds r1/Goal and requires `pre_action`. SC originally authored `final`; conditional Schema admitted it to native generation, strict validation rejected. Earliest defect: decoder did not enforce existing phase dependency. |
| SC decoder → DTO/Host | Explicit phase alternatives stop wrong-phase Need binding; binding-first generation fixes the retained omission. A further native output proposed an empty nonverbal act without expression: now explicit verbal/nonverbal alternatives enforce the existing DTO requirement. Host still rejects incomplete or unsupported output. |
| Work/Evidence → later SC | A complete 50,060-token input was falsely rejected by character estimate before inference. Same-model tokenizer now verifies it fits; exact native replay succeeds without removing context. |
| Failed cognition → Host/CLI | Prior acknowledgement must not hide later failure or skip terminal dispatch. Preserved earlier repair sends the bounded operational failure through ordered delivery and session completion, respecting explicit silence. |

Flow: text → GI → **concurrent {SC, GA, Fast Work}** → canonical join →
required SC pre-action delivery → provider Work → Evidence → SC result → terminal
completion. At a failed boundary, no fabricated communication or executable Work
is supplied. The native role repair remains one primary invocation; qualification
replays are offline evidence, never runtime semantic retries.

## GA source status and terminal failure repair — 2026-09-14

Baseline remains `ec4a5c268a557ac0f4281c668b1404edb96c57cc` plus local startup and
SC/GA repairs below. The user independently loaded the preceding patch; before
this new repair, checkout and Agent digest both equaled
`56a44ed330ee66db91efec01808622abdf61ebdb3a122689064ca04009c6f636`.
Current additional source changes remain local/uncommitted and undeployed.

User SID `f1c26dc9`, 15:45:11 Asia/Shanghai, explicit text:
`hello, what's the weather today in chongqing?`.

| Owner / handoff | Material input → actual output; boundary verdict |
|---|---|
| Host admission → GI | Empty history/Goals, explicit text → admitted envelope. ASR bypassed; correct transport. |
| GI WHAT → fan-out | r1 greeting/speech, r2 weather/information with entity=weather, location=chongqing, time=today; accepted at 8.910 s. Fine-grained segmentation not independently qualified. |
| SC interaction → TTS | GI/snapshot → pre_evidence acknowledgement with acknowledge_work, 8.31 s SC call. First playback 17.704 s, final early playback 21.134 s; valid DTO and observed playback logs. |
| Fast Work → held join | Greeting obligation plus weather lookup proposal, 14.30 s call. Resolved terminal is not execution authority; GA join unavailable. |
| GA continuity → DTO | Information source status unknown but source_name literal none. Conditional decoder constraint not enforced; primary output invalid. DTO correctly rejects at 28.969 s into turn. No Goal or weather provider dispatch. |
| Host containment → session | Existing early SC speech caused failure notice and final dispatch to be suppressed. This was incorrect: no notice of later failure and no llm_done transition. |
| Session → CLI | Idle abandonment at 152.274 s, then CLI timeout 180 s after handler completion. Downstream symptom of omitted terminal dispatch. |

Flow: text → GI → **concurrent {SC → TTS, GA → reject, Fast → held Work}** →
Host skips terminal dispatch → session abandonment / CLI timeout. Source repair
changes only the GA decoder dependency and Host's failed-resolution branch.
Explicit source alternatives preserve the existing DTO and supplied referent IDs;
Host does not infer a missing source. The operational fallback always traverses
normal terminal dispatch, retains earlier playback order, honors silence and
authorizes no effects. No prompt/model/new semantic invocation or authority change.

Evidence root `.chromie/acceptance/sc-ga-terminal-failure-20260914/` is local/Git-ignored:

- `originating-turn.log`, `originating-workflow.json`, `agent-before.log`, four
  `*-transaction.json` files and `diagnosis.md` retain the episode and owner audit.
- One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260914_155414.tar.gz`.
  No independent live aggregate was started: the operator holds the Host lock.
- Four frozen `corpus/*.json` packets: previous two repaired-role requests and
  this episode's SC/GA. `native-before/` repeats the new GA source failure; the
  other three pass. `native-after/` all pass; `adjudication.json` applies real SC
  DTO/source validation and GA materialization. Full rendered GA schemas equal
  replay packets; one primary call per role, no targets or repair calls.
- GA after-results retain both Responsibilities, location and time, with absent
  or empty source names under unknown status. SC acknowledges without claiming
  a weather result. `semantic-review.json` retains limits: the prior weather
  probe still invites unnecessary reconfirmation, and both SC acknowledgements
  mention lookup while citing only the greeting Responsibility. Finer semantic
  source coverage and communication quality remain unqualified. This is bounded
  implementer review, not independent general language, complete turn,
  contention latency or physical evidence.
- `fail-first-corrected.log`: 10 failures at the predicted schema/dispatch
  boundaries. Initial `fail-first.log` also contained test setup mistakes and is
  excluded from that count. `focused-after.log`: 122 tests / 155 subtests pass,
  including six controlled-delivery cases using real dispatch, session completion
  and CLI wait. `workflow-focused.log`: all 104 strict tests pass, no fixture edits.
- `canonical.log` exits 0: 3,262 tests / 849 subtests, 145 benchmarks and 20 legacy
  tests; pinned static/policy/ownership/config/docs checks pass, two existing
  FastAPI deprecation warnings. `workflow-final/summary.json`: all 6,000 cases
  pass their declared verdicts, source unchanged, no fixture edits. All 45 Level A
  cases pass in `general-ability/summary.json`. These are bounded automated gates.

No services stopped/rebuilt and no commit/push. Pending pause authorization from
the prior turn still applies. After approval, stop the operator Host gracefully,
use the saved operator overrides and selective Agent rebuild commands below,
verify source/profile identity, then run the directory-discovered safe live cohort
under one immutable identity. Retain exactly one debug bundle at completion or a
hard-failure stop and review every output. Exact follow-up probes are the two
weather utterances above/below; use `--no-speaker` and keep capabilities enabled
(do not use the earlier greeting's `--expect-no-capabilities`). Restore the
operator text Host after validation. #24/#32 and rapid-response latency remain open.

Subsequent scheduling discussion is not a deployment amendment: user proposes
two resident Fast/Deep inference instances and priority SC > GI > GA > Fast.
Read-only inspection (`scheduling-inspection.json`) confirms one deployed SGLang
0.5.19 instance, `max-running-requests=2`, priority enabled, preemption threshold 10;
current purpose ranks are SC=400, GI/Fast=300, GA=200. One RTX 5090 was observed,
32,607 MiB total and 26,893 MiB used (about 26.3 GiB at first check).
Use exact raw measurements in the retained artifact for capacity decisions.
Host's GI fan-out starts all three independent requests; serial arrows in the
summary do not establish GPU start order or observed preemption. Two independent
engines have separate queues and do not automatically coordinate cross-engine
GPU preemption. No model, priority or topology changes were made for this discussion;
the existing foreground/deep-load measurement gate still applies.

## SC / GA decoder and workflow repair — 2026-09-14

Source baseline `ec4a5c268a557ac0f4281c668b1404edb96c57cc` plus the preceding
uncommitted startup-identity patch. Current additional changes are also local.
No model, prompt, semantic authority or runtime permission was changed.

User episode: SID `1d3e19dc`, `hi, will it rain today in Chongqing?`, 14:43:34
Asia/Shanghai. SC owns interaction, GA owns canonical Goal continuity, Fast owns
Work, and Host owns admission/delivery. Actual workflow:

| Boundary | Actual input/output and result |
|---|---|
| Gateway → GI | Explicit text admitted; GI accepted r1 greeting and r2 rain query with Chongqing/today bindings in 9.204 s. |
| Host fan-out | GA, Fast and SC inference began at 14:43:44.308/.329/.372 after GI completed .081. SC was invoked. |
| SC → DTO | Model authored a pre_evidence acknowledgement without progress_kind. Schema allowed it; DTO rejected it; HTTP 500. No SC speech delivered. |
| Fast → join | Returned greeting communication obligation plus weather Work after 10.016 s. A terminal frame is not an accepted complete Goal/Plan join. |
| GA → materializer | Preserved Chongqing but query_scope.location.entity_type=string. Schema accepted; existing location validator rejected after 16.458 s. |
| Host → TTS | No valid Goal/Plan join or weather/body execution. Generic failure fallback, 2/2 recorded playback completions, 30.734 s session. |
| Workflow observation | SC was recorded only after success, so the failure vanished from session_flow; an old log incorrectly named Fast as communication owner. |

Earliest failing owners: model-facing schemas did not expose invariants already
required downstream. Conditional-only tightening was insufficient for SGLang.
Final source fix uses explicit SC truth-stage alternatives and direct location
vocabulary on GA's GI-bound query-scope row. The vocabulary has one contract
owner shared with the Host validator. SC invalid output returns a 422 contract
error; initial SC start/failure/cancellation/stale outcomes are observable. Host
never supplies missing semantic fields, adds a reviewer, or executes a failed Plan.

Evidence root: `.chromie/acceptance/sc-ga-live-failure-20260914/` (local/Git-ignored).
`diagnosis.md` retains full I/O, earliest-boundary reasoning and distinctions among
trigger, root cause, symptom and remaining gaps. Original files:
`originating-turn.log`, `originating-workflow.json`, `agent-before.log`, and four
`*-transaction.json` files. One stdout/stderr-interleaved SC evidence record was
reconstructed by removing the exact HTTP access-log fragment; untouched raw logs
are retained. One baseline debug bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260914_144922.tar.gz`.

- `fail-first.log`: original code fails the new schema, SC observation and HTTP
  error assertions (8 failures, including three location-type subtests).
- `native-before/`: complete frozen two-request failure cluster; both reproduce
  the original Schema/DTO/Host mismatch with chromie-gemma4-12b on SGLang.
- `native-after/`: invalid harness attempt omitted the production wire-schema
  transform; excluded from production-regression claims.
- `native-after-wire/`: conditional-only repair still fails native constraints.
- `native-after-branches/`, `adjudication.json`: both primary outputs pass; SC
  validates against the authoritative request and GA resolves through its real
  materializer with one call. Prompts/model unchanged; production schemas changed.
- `broad-sc-before/`, `broad-sc-after/`: same frozen 12-case SC corpus, both 12/12
  contract passes. Old SC source is loaded in isolation from retained ec4a5c26;
  the before manifest identifies it separately from workspace source hashes.
  `broad-semantic-review.json` is implementing-agent, non-independent review.
  Controlled source facts/empty expression catalog do not prove full live behavior;
  formal wording remains a limitation, and no latency improvement is claimed.
- `focused-after.log`: 234 tests / 156 subtests passed; `general-ability/`: all
  45 Level A scenarios passed. `native-final/` repeats both original packets with
  the final production wire schemas and passes both DTO/Host checks.
- `canonical.log` retains an intermediate 74-failure request-snapshot run caused
  by a decoder-ineffective global conditional. Removing that unnecessary clause
  preserved the direct location-row fix and restored all 104 workflow tests.
  No fixture or expected outcome was rewritten. Final canonical results are
  retained separately in `canonical-final.log`: exit 0, 3,255 tests / 835 subtests,
  145 benchmarks and 20 legacy tests; two existing FastAPI deprecation warnings.
  Pinned static, policy, ownership, configuration and docs checks passed.
- `workflow-final/`: unchanged full 6,000-case offline aggregate passed;
  source_unchanged=true, 1,400 passes / 1,800 expected state outcomes / 2,580 expected
  rejections / 220 expected nonexecuting rejections. No native/physical claim.

Deployment remains pending. The active operator Host holds the exclusive lock;
permission to pause it, rebuild Agent and run headless replay was requested
asynchronously and has not arrived. No deployment or Host interruption was done.
The earlier runbook/source-identity commands below remain applicable after the
Host is stopped. Replay this turn with the existing interaction runner using
`'hi, will it rain today in Chongqing?' --no-speaker`; then run the complete safe
live cohort under one fixed deployment and retain/adjudicate one post-run bundle.
Do not edit/restart between aggregate cases, bypass the lock, or claim physical
microphone/speaker/robot evidence. The #24/#32 and rapid-response targets stay open.

## Agent source verification repair — 2026-09-14

Current source baseline: `ec4a5c268a557ac0f4281c668b1404edb96c57cc` on `main`,
already pushed by the preceding delivery. This follow-up is local/uncommitted.
The user reported SID `037d1216`, `hi, how are you?`: GI was accepted, but SC
returned 404 and the Agent emitted retired `presentation_commit` frames. Direct
container-file inspection confirmed old Agent source attached to the current
Host. The earliest failure was startup accepting configuration/health without
checking packaged source; the generic TTS fallback was downstream containment.

Implemented: startup profile verification now shares the existing closed-loop
Agent content digest through `scripts/capture_runtime_identity.py`. It checks
Agent app, Agent Skills, shared contracts and shared runtime, fails closed for
mismatch/unavailability, and gives rebuild/recreate instructions. No semantic
prompt, runtime behavior contract, dependency lock, or compatibility path changed.
No new document, environment variable, service or architectural term was added;
the source-identity implementation has one owner.

Evidence: `.chromie/acceptance/agent-source-startup-20260914/` (local/Git-ignored).
`diagnosis.md` reconstructs the actual module I/O, provenance, root cause and
repair mechanism; `originating-turn.log` retains the user's report. One debug
bundle was retained at
`/home/chromie/Downloads/chromie_debug_bundle_20260914_142622.tar.gz`.
The later `before-source.json` probe found the old container already stopped
during the user's independent rebuild; it is unavailable-evidence rejection,
not an old full-tree digest. Pre-rebuild main-file hashes and missing-route
inspection are recorded in the diagnosis.

The user independently restarted with `--build` during diagnosis. Afterward,
`after-source.json` records equal Host/container digest
`a02e65fd1f453deb413a6b578540695f02425f7d40a16cb6b195e0dc84b443ce`;
`after-profile.log` passes; `deployed-api.json` contains `/social-cognition` and
no `PresentationCommit` schema. The agent did not restart services or interrupt
the user's active Host.

Observed user-initiated follow-up `hello`, SID `0fec435f`: GA/Fast and SC accepted;
“Hello! How can I help you today?”; 2/2 playback completions recorded, no Work
steps or runtime fallback. See `after-hello-workflow.json` and
`after-hello-events.json`. First playback 32.04 s, completion 34.84 s: quick
response remains unqualified. This different greeting is not an automated exact
replay, full live cohort pass, warm latency proof or physical audio qualification.
The active Host lock prevented an independent headless run; it was not bypassed.

Focused tests: `focused.log`, 24 passed / 12 subtests; `general-ability/`, all
45 Level A cases passed. Canonical `canonical-final.log` exits 0: 3,248 tests / 832 subtests, 145 benchmarks,
20 legacy tests; two existing FastAPI deprecation warnings. Policy, static,
ownership, configuration and documentation gates passed. Target #24/#32 closure and
response-latency diagnosis remain open.

Next: use the existing runbook startup instructions; once the operator Host is
stopped, verify the Agent digest, retain a current runtime identity, reproduce
`hi, how are you?` headlessly, then run and adjudicate the directory-discovered
safe live cohort before any semantic/latency repair. Do not rebuild or edit
source between aggregate cases. The existing `scripts/general_ability_acceptance.py`
`--mode live-text --stage must_pass --execute` uses the simulator with speaker
disabled by default; verify the runtime identity and simulator provenance first.
Physical microphone/speaker/robot evidence still requires supervision.
After stopping the operator Host, resume with the existing generated profile:

```bash
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output .chromie/acceptance/agent-source-startup-20260914/runtime-identity.json
flock -n /tmp/chromie-orchestrator.lock python scripts/interaction_text_mujoco_check.py 'hi, how are you?' --no-speaker --expect-no-capabilities --language en-US --runtime-identity .chromie/acceptance/agent-source-startup-20260914/runtime-identity.json --evidence-dir .chromie/acceptance/agent-source-startup-20260914/exact-replay
python scripts/general_ability_acceptance.py --mode live-text --stage must_pass --execute --runtime-identity .chromie/acceptance/agent-source-startup-20260914/runtime-identity.json --evidence-dir .chromie/acceptance/agent-source-startup-20260914/live-must-pass
```

`--allow-dirty` records the local source identity for development diagnostics;
it does not qualify a dirty revision for target release. Do not omit a required
identity/service or override the Host lock to make a run pass.

## Social Cognition implementation handoff — 2026-09-14

Repository `/home/chromie/github/chromie`, `main`, base
`d5a7985ec74b02cd01c11b0d538fca7ae13a3498` is the pre-delivery baseline.
The owner requested commit and push to `origin/main`; a fetch found local HEAD
and remote main equal before this delivery. Expected resume revision: the latest
commit containing this handoff and checkpoint. No rebuild, restart or runtime
profile change was performed. Earlier quiet-console edits are included.
The [checkpoint](DEVELOPMENT_CHECKPOINT.md) and
[status](docs/STATUS.md#social-cognition-migration) own implementation/resume claims.

SC is the interaction planner and the sole maintained wording/expression owner.
It reads shared GI, Goals, Work/task state, history, Memory/Mind, Situation and
actual delivery. It can act on a trusted Situation without synthetic GI or Work.
Work Planner emits complete Work and scoped communication needs. Host joins them
without rewriting semantics, preserves exact confirmation/causal order, rejects
stale results and records heard dialogue only from correlated completed playback.
SC expression uses the existing qualified runtime/Soridormi boundary; it never
completes task Goals. No optional communication blocks independent Work.

The earlier combined writer, `PresentationCommit` DTO/schema/transport and its
scheduler were removed, as was the Goal-free Situation-only model endpoint.
The existing common SC endpoint is `/social-cognition`. Its foreground SGLang
priority is 400; ordinary Planner is 300 and deliberative cognition 100. Before
services stopped, read-only inspection observed SGLang 0.5.19,
`chromie-gemma4-12b` / `google/gemma-4-12B-it`, context 65,536, higher-first
priority enabled, max running requests 2 and preemption threshold 10. These
settings establish no measured speedup or starvation guarantee.

Evidence root: `.chromie/acceptance/social-cognition-mainline-20260914/`.
Raw artifacts are local/Git-ignored and are not included in this push. Another
machine must obtain reviewed evidence separately or rerun the commands below;
it must not assume those local paths exist after cloning. The delivery check
matched every changed file to `final-worktree-identity.json` before refreshing
delivery documentation, so the full code tests did not need a redundant rerun.
The subsequent generalization discussion changed no code and supplies no new
ability evidence. Test counts retain their stated contract/fixture scope.

| Retained evidence | What actually passed / limitation |
|---|---|
| `canonical-sc-closed.log` | Exit 0: 3,245 tests / 820 subtests, 145 benchmarks, 20 legacy tests; pinned static, policy, ownership, configuration and docs green. Two existing FastAPI deprecation warnings. |
| `retired-writers-final.log`, `acceptance-sc-checked.log`, `acceptance-sc-timing.log` | Exact SC/Work joins, current source-only writer paths, expression safety, native schema contracts and migrated acceptance assertions. |
| `workflow-sc-closed/` | Final strict aggregate: all 6,000 declared outcomes pass with unchanged source after explicit fixture migration. Earlier `workflow-sc-final/` also passes all 6,000. |
| `general-ability-sc-complete/` | 45/45 distinct Level A scenarios; controlled runtime/provider fixtures, not live speech. |
| `native-final-sc/` | 12/12 native Schema/DTO/Host and reviewed semantic cases, one call per case. Empty expression catalog. |
| `native-work-roles-complete-order/` | 8/8 native Work transactions; controlled GI/GA/catalog. Deep raw evidence is the client's parsed JSON, not a literal wire-token audit. |
| `recorded-sc-final/`, `recorded-work-final/` | All 20 current production packets equal retained native packets exactly; current resolver replay passes. No fresh native inference. |
| `native-sc-retired/` | Failed availability attempt: 12 connection errors, zero native outputs. Subsequent `docker ps` showed no running containers; no stop cause inferred or restart attempted. |
| `workflow-adjudication-current.json` | Ordered owner/input/output/correlation audit and root-cause/repair evidence, including original-user-trace gaps. |

The 6,000 cases remain 60 authored contrast families expanded over action/value/
language combinations, with separately scripted SC interaction. Expectations,
fault/rejection oracles and splits were preserved; all rendered requests were
explicitly recaptured outside acceptance, then frozen and strictly replayed.
No acceptance hook auto-records requests or substitutes an expected answer.
They are not 6,000 independent model inferences and remain training-ineligible.
`workflow-generator-sc.json` checks all 60 generator families' current Work form.
Earlier failed iterations remain retained, including the native ordering failure
that passed structure but failed semantics. Final explicit `precedes_step_ids` /
`follows_step_ids` and source-relation validation close that role-case defect.

The original user's timing report has no retained source-turn timing trace, so
no measured original latency cause is claimed. This was an authorized ownership
change with reproduced model-contract and fixture boundaries. Source complete
is separate from current deployed behavior, whole-chain native cognition,
paired contention/latency and physical microphone/speaker/robot qualification.
Those target evidence gaps and existing #24/#32 remain open.

Current source verification:

```bash
./scripts/run_tests.sh
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir .chromie/acceptance/sc-level-a-next
python scripts/run_workflow_replay.py --workers 8 --evidence-dir .chromie/acceptance/sc-workflow-next
python scripts/check_docs.py
python scripts/check_test_ownership.py
git diff --check
```

Use new evidence directories. Before future native/live testing, verify service
availability and the intended deployed source/profile; do not use host-default
Agent model settings as a substitute for the recorded SGLang profile. Complete
the directory-discovered safe live cohort and retain/adjudicate its debug bundle;
physical microphone/speaker or robot runs remain supervised.

Quiet interaction retains the existing launch contract:

```bash
./scripts/start_chromie.sh --text-console
python scripts/chromie_psm_live_text_console.py
```

The first terminal owns runtime logs; the second connects to
`.chromie/text-console/dialogue.sock` for dialogue, bypassing ASR while retaining
Soridormi and normal runtime capability checks. No service is currently claimed
running or rebuilt with SC.

Surface accounting: 102 current Markdown files / 15 core reading-path documents,
unchanged; no new environment variable or service. The owner-approved SC term
replaces the old interaction responsibility. Most changed files are the 6,000
frozen generated workflow cases, not new production modules. This delivery
includes both handoff owners with these evidence limits.

## Previous documentation-stage handoff — Social Cognition, 2026-09-14

Repository `/home/chromie/github/chromie`, branch `main`, base
`d5a7985ec74b02cd01c11b0d538fca7ae13a3498`. This change records the owner's
accepted communication/Work authority split in the existing documentation owners.
No Social Cognition source, endpoint, schema, runtime setting, service restart,
deployment, commit or push was performed for this amendment. The
[checkpoint](DEVELOPMENT_CHECKPOINT.md) and
[target lifecycle/source inventory](docs/COGNITIVE_TURN_LOOP.md#social-cognition-target-lifecycle)
own resume scope and the current-to-target workflow respectively.

The pre-existing text-console patch remains in
`scripts/chromie_psm_live_text_console.py`, `scripts/start_chromie.sh`,
`scripts/start_orchestrator.sh`, `tests/test_psm_live_text_console.py`,
`config/runtime_configuration_inventory.json`, `docs/USER_MANUAL.md`,
`docs/API_REFERENCE.md` and `orchestrator/README.md`. The last two also gain
target/current-source notices here; their local text-transport documentation
is preserved. Do not attribute those earlier runtime changes to Social Cognition.

Validation artifacts for this documentation change are retained under
`.chromie/acceptance/social-cognition-docs-20260914/`:

- `canonical-final.log`: exit 0; 3,223 tests / 818 subtests, 145 benchmark tests
  and 20 legacy Agent tests pass. Two existing FastAPI deprecation warnings.
  Pinned policy, ownership, Ruff/Mypy, configuration, runtime and docs gates pass.
- `policy.log` and `ownership.log`: standalone checks exit 0. `docs-final.log`
  records the corrected documentation check; `docs-after-handoff.log` retains
  the final documentation recheck after recording these results.
- `docs.log` and the first `canonical.log` retain the initial duplicate
  architecture-ID reference failure. The references were corrected without
  changing the checker; that first canonical attempt stopped before pytest.
- `preserved-source.json`, `source-identity.json` and `validation.json` retain
  unchanged earlier runtime-file digests, dirty-tree identity and check results.
  `git diff --check` passes. No files or reading-path entries were added.

No native model, latency, simulator, audio or physical proof is collected here.
Historical deployment/model identities below have not been reverified by this
documentation task. In particular, intended SGLang use is not evidence that a
deployed version has priority/preemption correctly enabled.

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
git diff --check
```

Surface impact: Social Cognition target role count `0 -> 1`, replacing Planner's
communication responsibility. Current Markdown documents `102 -> 102`, core
reading-path entries `15 -> 15`; environment-variable/service count delta `0` for
this amendment. Consolidation
must remove the old writable Planner reply/stream coupling when source migrates.
Current source assertions and APIs remain documented as migration baseline, not
as permission to preserve competing speech authors. #24/#32 stay open; the
canonical gate → narrow supervised voice → default target-evidence closure
sequence remains the delivery requirement.

## Previous delivery — native continuation and #67, 2026-09-14

Repository `/home/chromie/github/chromie`, `main`; pre-delivery base
`d7c7f27767d8e137edbf2aa165a11b81d6282527`. Python
`/home/chromie/miniconda3/bin/python`. Resume from the latest commit containing this
file and [DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md). Owner authorization
covers continued implementation, bounded fixes, project decisions, reports, normal
commit/push and solved-Issue closure. #67 closes with delivery; #24/#32 stay open.
No new runtime flag/profile/semantic owner or document: 102 Markdown / 15 core-path.

## Changed workflow and evidence boundary

GI owns WHAT; GA Goal continuity; Planner HOW/speech; Runtime execution/Evidence.
Native input `把那个拿给我。`, empty context, returned prompt-example `distance="twenty
meters"`, `direction="behind you"`, `entity="A parcel"` and no unresolved meaning.
The original Host accepted. The existing duration validator now checks distance
strings/scalar shape too. Unsupported distance rejects before GA/Planner; it is not
removed, replaced or sent to another semantic call. Primary failure uses one call;
failure after genuine unresolved primary uses two total. Numeric normalization and
other semantic correctness remain unqualified. The [audit](ARCHITECTURE_AUDIT.md#native-gi-continuation-and-distance-containment--243267)
contains actual module I/O, first wrong native boundary, Host containment and live
case correlations; it must not be reduced to a claim that GI understanding improved.

R = `.chromie/acceptance/issue24-source-order-20260914/` (private, ignored):

- `design.json`, `source-only-design.json`, `corpus/`, per-cohort frozen packets,
  raw replies and semantic reviews: three pre-fix 44-case cohorts / 242 calls.
  Baseline 3 full passes, 2 meaning-correct/provenance-unqualified, 39 failures;
  source-first 0 passes and source-only 1. Both candidates rejected; production
  prompts and Schema order unchanged. The first candidate also moved confidence;
  the second isolates only source_evidence property position.
- `retained-host-before-after.json`: all 242 original replies were old-Host valid;
  exactly six now reject unsupported distance strings. Other 236 results unchanged.
  `distance-red.log`: nine reproduced failing negative subcases; positive controls
  pass. `distance-green.log`: 91 GI tests / 115 subtests pass after repair.
- `host-fixed/`: final 44-case / 71-call production-order native rerun, source/model
  stable; every raw JSON equals reviewed baseline. One primary distance rejection,
  43 final decisions; native meaning remains unqualified. Four cohorts total:
  176 cases / 313 calls, all normal stops and think:false, no separate thinking field.
- `canonical-1.log`: exit 0; 3,217 tests / 818 subtests, 145 benchmarks, 20 legacy;
  pinned policy/static/config/docs/ownership pass. Two existing FastAPI warnings.
  `level-a/`: 45/45, 15 classes. `workflow-6000/summary.json`: all 6,000 expected
  outcomes, unchanged source/manifest; 1,400 workflows, 1,800 state/fault/permission,
  2,580 contract rejections, 220 safe nonexecuting replies. This is engineering
  replay, not native model/physical qualification or training approval.
- One debug bundle per direct cohort, plus exactly one live aggregate bundle;
  `debug-bundles/` retains all five. `validation-ledger.json`, `source-snapshot/`
  and `evidence-index.json` bind the observed evidence. Final delivery docs and
  publication/CI records are post-archive and retained separately in Git/R.

Transfer archive: `/home/chromie/Downloads/chromie_issue67_native_continuation_20260914.tar.gz` (265,500,309 bytes), SHA256 `22eab7ac1445fbb9f0df183586a9df82d77f0f7ca852f4139e8b74237b027f53`; 11,249 indexed members verified.

## Deployment, live failure and safe shutdown

Seven initially stale container files match historical `6f726ce3`/`8aa3f499`, with no
unique container-only edits. They were retained before Agent rebuild. All 113
Agent/shared source files now match the tested patch. Current Agent image:
`sha256:252febc02cb55260ef28747b0a6c9695905a83ca7ae2cdcdefd95a1e09478637`.
Agent/TTS/LLM remain healthy; ASR absent. No host Orchestrator remains running.
Soridormi `/home/chromie/github/soridormi`, `codex/turn-count`, revision
`284273bc344cc94012347c75ab270a9f4ac8ffdb`; preserve untracked
`workspace/Open_Duck_Playground`. Owned headless MuJoCo/MCP were stopped after
safe idle; launcher exit 1 follows requested shutdown, not failed startup.

Native direct GI used Ollama 0.33.2 / qwen3.5:4b, model digest
`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`,
context 16,384, output 512, timeout 120,000 ms, fixed options and residency traces.

The current generated runtime profile is **interactive**. The old
`.chromie/acceptance/laptop-iterations-20260910/orchestrator.env` is now stale for its
budgets; initial identity capture rejected that mismatch before any case. New
`R/orchestrator.env` uses the prior automated transport settings with current
`.env.runtime` budgets through `scripts/sync_orchestrator_profile_env.py`.
`R/prepare-live-env.py` retains generation; do not hand-edit `.env.runtime` or reuse
an old acceptance env after changing the active profile. The live harness explicitly
uses stdin/discard, despite the snapshot's synthetic input setting. No microphone,
ASR, audible speaker or physical body evidence was collected.

`R/iteration-01/runtime-identity.json`:
`b078a0b56709653f160d5c6bb805281cb4cac59a4ab0cddd11db17ea76d9c190`;
dirty source-tree hash
`52061f7822f0e113dcb8c273c8843b3ade50046af3f92b7dcd3287107ddc3d31`.
This is diagnostic-only patch evidence, not a clean-revision qualification. Both
Chromie and Soridormi source identities were unchanged during the live invocation.

One discovered 51-case must-pass invocation used `--execute` against headless
MuJoCo. Result: **2 failures / 1 interrupted / 48 unrun**. Compound sid `cbe8a87b`:
primary GI merged three effects and invented actor uncertainty; deeper split them;
GA conserved values; Fast emitted walking speed 0.02 instead of 0.2, correctly
rejected before execution. Gaze/blink sid `8a11295e`: GI fused two effects; Fast
made blink decoration with a communicative anchor pointing to a Capability, correctly
rejected. Milk sid `5b7a0a66` interrupted: two late GI replies bury distance in
direction; no completed Host/GA/Planner result. Nine native Agent calls retained.

The old private watcher missed model_contract. Reviewer stopped the cohort on the
first retained hard failure after the next case completed and third started. Original
`run-cohort-iteration01-frozen.py` is retained; `run-cohort.py` includes that domain
for future stops. Aggregate exit -15; one bundle exit 0:
`/home/chromie/Downloads/chromie_debug_bundle_20260914_005335.tar.gz`.
`post-stop-provider-status.json`: sim, safe_idle=true, active_task=null,
active_lanes={}, fallen=false, emergency_stop=false. Per-case status_after is absent;
the separate post-stop query supplies only the post-stop safe-idle claim.

## Resume commands and claims

From repository root, use fresh evidence output directories:

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q tests/test_goal_interpreter_llm_prompt.py
python scripts/run_workflow_replay.py --workers 4 --evidence-dir .chromie/acceptance/workflow-next
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir .chromie/acceptance/ability-next
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

For a justified next live cohort, verify current profile budgets and source before
starting. Do not mix old acceptance envs with regenerated profiles. Existing Compose:

```bash
./scripts/check_orchestrator_idle.sh
docker compose --env-file .env.runtime -f docker-compose.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml build chromie-agent
docker compose --env-file .env.runtime -f docker-compose.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml up -d --no-deps chromie-agent
```

Start Soridormi from its repository using `./scripts/start_soridormi_mujoco.sh
--no-viewer`; supervise only simulator mode and stop its owned services afterward.
Create a fresh iteration directory; `R/verify-deployed.py 2` writes iteration-02
source proof. Capture a matching identity with `scripts/capture_runtime_identity.py`
using explicit Agent/LLM/TTS services, current generated text env and Compose override;
use `--allow-dirty` only for an explicitly diagnostic patch, never a target claim.
`R/run-cohort.py 02` runs the same discovered cohort against that identity. No source
edits/rebuilds between cases; stop all hard integrity/provenance/model_contract faults,
collect one bundle and review every retained case. Do not repeat rejected native
ordering controls. Restore prior native evidence if replaying the original historical
runner; its old-corpus paths are retained verbatim, with the same 44 inputs also in
`R/corpus/` for designing a fresh frozen run.

Keep #24/#32 open. Preserve canonical gate → supervised narrow live voice → default
target-evidence closure order. Before LoRA, independently review positive references
and hidden semantic-family holdouts; injected faults are not training targets. No
follow-up is scheduled.

## Previous immutable transfer evidence

- 6,000 replay: `/home/chromie/Downloads/chromie_workflow_6000_20260913.tar.gz`,
  1,855,642,868 bytes; SHA256
  `18295607616d0bef24c484726f4f0b75cf957ca9181e1384cf49f9de26f21e1a`.
  Manifest `1d9f5d3d35cf8b993ea2fe6703ac30adac2838514d8e7a27a9bd5431775a0773`.
- Prior native GI: `/home/chromie/Downloads/chromie_issue24_gi_boundary_20260912.tar.gz`,
  SHA256 `14e2b27523f92e4438a93f273f78cade42008a048530a414fd792945da7a4dc2`.
- Prior full repair/live: `/home/chromie/Downloads/chromie_remaining_issues_evidence_20260912.tar.gz`,
  SHA256 `604b801d6331c0356c0541d47bc0fb37eca91793454bda7d75e58e724c3ecd78`.
- The [preceding handoff](https://github.com/TimeTreker/chromie/blob/d7c7f27767d8e137edbf2aa165a11b81d6282527/HANDOFF.md)
  retains the original five-case/1,500 archives, older identities and known #51
  cross-machine artifact gap. None of these older results qualify the current model.
