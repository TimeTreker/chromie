# Chromie Latest Handoff

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
