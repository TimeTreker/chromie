# Chromie Handoff

## Current resume point — 2026-10-05

Pre-delivery checkout `main` / `489bd63968e791d90c4855401f38d70f6bd547e6`
contains fetched `origin/main`; the previous non-model delivery is already pushed.
The owner requested more non-model repair and previously authorized conditional
commit/push for that scope. Expected resume revision: latest `main` commit containing
this Handoff and [checkpoint](DEVELOPMENT_CHECKPOINT.md). Canonical local gate now
passes; current-revision voice proof and default target closure remain open.
Charter, production prompts/Schema/DTO/Host, model and module authority are unchanged.

## Current workflow corpus repair

Root `/home/chromie/github/chromie/.chromie/acceptance/workflow-contract-audit-20261005/`.
The6000-case fixed baseline failed before UMI output: exact-request HTTP409,
zero external inference/provider calls. Earliest wrong owner: stale frozen corpus,
not production interpretation or model capability. Request-only captures showed
missing required live UMI body classification and retired GA wire fields.

Repair: author existing body classification from the original scenario action;
remove only retired `decision=create_goals` and empty `non_goal_responsibility_refs`;
recapture exact current production requests. `invariant-review.final.json` compares
all6000 cases plus5 prototypes: original inputs/context, historical Goals, full meaning,
Goal relationship choices, Planner outputs/parameters, provider contracts/observations,
fault payloads, rejection/terminal assertions and splits remain. No runtime semantic
conversion, weaker matching, candidate-fitted targets or new inference is introduced.

- `baseline/summary.json`:6000 UMI mismatches, fixed source, zero candidate calls.
- `capture-summary.json`:request-only recapture still fails61/65 representatives;
  `capture-full-summary.json`:6000 authored workflows pass. Authoring is separate
  from strict replay and remains non-independent, `training_eligible=false`.
- `focused.log`:first strict run5 fail/115 pass. Extra nonrequired prior-Goal metadata
  did not match the original seed used for capture; removed, with original Goals
  retained exactly. `timer-harness-diff.json` and earlier captures remain.
- `focused.final.log`:120 pass. `strict-full/summary.json`:6000/6000 pass, fixed source,
  zero candidate calls;1400 complete workflows,1800 state handling,2500 expected
  rejections,300 safe nonexecuting rejections. `adjudication.json` covers all60 families.
- `canonical.log`, exit0:benchmarks164 pass, main3968 pass/5 environment skips/
  1023 passing subtests,20 legacy Agent tests pass. Policies, ownership, pinned
  Ruff/mypy, configuration/runtime and docs pass. All former83 workflow failures close.
- `cold-baseline.json`:the original Git source now restores all6076 files in this
  checkout. Earlier isolated-export incomplete-source evidence remains historical.
  `cold-final.json`:new source restores6050 exact files; verified cache restores0.

The complete reviewed source is retained as
`benchmarks/integration/workflow_scenarios/frozen.tar.xz` (1,244,372 bytes;
SHA256 `fd9a07d3004a4643d04b54ffc570796080b6d13501459334e21c2ab6b191be7c`).
The manifest binds all6000 case and50 shared-packet hashes plus the source archive
and its inner manifest; current shallow checkout needs no historical fetch.
Historical Git-source support keeps the original freeze retrievable. The restoration
owner verifies the complete archive before publication and never overwrites changed
cache or regenerates answers. One maintained corpus asset is added; no new document,
environment variable, runtime flag, production module or architecture term.

Fresh-checkout resume:

```bash
cd /home/chromie/github/chromie
python -m benchmarks.regression restore-fixtures
./scripts/run_tests.sh
```

On a populated older checkout, preserve the previous ignored case/packet cache before
removing it and restoring the new freeze. Do not remove the tracked manifest/archive;
do not blindly overwrite mismatched files. The current checkout already has the new
verified cache. `corpus-before/`, `seeds-before/`, previous manifest and failed captures
retain earlier bytes locally. Do not stage private evidence.

This patch affects benchmark evidence only. No services were rebuilt/restarted,
no model/prompt/profile/Charter/module authority changed, and no native cohort,
physical microphone/speaker/robot or independent qualification was performed.
Native residual failures and source-bound runtime evidence below remain open.

## Previous non-model delivery — 489bd639…

Root `/home/chromie/github/chromie/.chromie/acceptance/non-model-delivery-20261005/`.
`pending.before.patch`, `before.json` and `before/` preserve all31 reviewed pending
paths and the handoff/status/audit originals against pre-delivery `b693467ca…`.
They are already-applied local changes, not a patch to apply again.

- UMI wire formatting:16-character structural whitespace bound forwarded by
  SGLang/XGrammar; strings, Schema meaning and model unchanged.
- SC model view:one exact copy of current mirrored snapshots; unique/divergent
  Memory and trusted request/digest unchanged. Historical native budget proof is
  42,428→37,077 against40,960; source/context issue before inference.
- Weather provider:geocoding locale follows admitted geographic names/qualifiers;
  reply-language preference, canonical location and strict identity checks unchanged.
- Test evidence:forward existing interrupt controls and require provider-start then
  cancelled walking receipt; strengthen clarification/draft acts; geographic identity
  remains blocking semantic review. Include required ambiguous-movement body metadata,
  previously withdrawn Tianxin case deletion and79-case inventory/documentation.
- Current focused suite347 pass/5 environment skips/57 subtests; Level A19/19 unique
  cases across3 relevant classes. `native-grammar.log`:bounded0/8/16 accepted,17/128
  rejected; unbounded reference accepts all5;128 semantic string spaces retained.
- `agent-source.json` still matches host/package93b58310…; Agent image124a02f6… and
  LLM image2330d155… remain running/restart0. No model/profile/prompt, Charter or
  module-authority change, no service rebuild/restart, no additional LLM decision.
- Current full gate `.chromie/acceptance/non-model-delivery-20261005.canonical.log`,
  exit1:benchmarks160 pass, main83 fail/3885 pass/5 skips/1023 passing subtests.
  Policy/ownership/pinned Ruff/mypy/configuration/docs/scenario stages pass;
  legacy not reached. `canonical-comparison.json`:same83 ordinary failure IDs as
  latest full local-tree source-Schema run, no new IDs/subtest failures. Former
  first-delivery fixture failure now passes. All6000 targets and strict replay remain.
  Final status/Handoff/audit/checkpoint edits are documentation-only after that gate.

This follow-up commits the local source already used by the latest retained79-case
native iteration below. It does not create a new native cohort, reuse its runtime
identity for a new run, or qualify this new Git revision. Native residual failures,
physical/independent evidence gaps and the red canonical gate remain open.

## Latest retained native proof and first-delivery history

Root `/home/chromie/github/chromie/.chromie/acceptance/planner-compound-contract-20261004T140758Z/`;
latest source/target iteration is `count-scope/source-schema/`.

- First-delivery entry backup retains3113 dirty paths; exact corpus/input/foreign preservation and
  `combined-*-patch-paths.txt` inventories remain at the root.28 excluded paths are
  unchanged in `source-schema/foreign-preservation.json`. First-delivery staging excluded
  hunks in Agent README, Acceptance and general-ability tests now included above. The
  already-dispatched SC presentation handling and its regression are included as
  prerequisites for the admitted-user chronology repair. Do not blanket-add
  ignored evidence or other work.
- Frozen compound12 references9/12→12/12; count11 references6/11→11/11;
  exact source/enum13 references10/13→13/13. Frozen targets and existing provider
  formats/bounds/defaults remain; source IDs alone are not semantic proof.
  All are scripted primary Schema/DTO/Host checks, no native/independent training proof.
- Count focused1090 passed/451 subtests; source stream179 passed; each relevant
  Level A3 classes18/18. Latest canonical benchmarks160 pass, main83 fail/3885 pass/
  5 skipped/1023 subtests. `source-schema/canonical-comparison.json`:same83 failure
  IDs, no new ones; strict stale workflow HTTP409 precedes candidate inference;
  legacy stage not reached. Do not rewrite6000 targets or weaken strict comparisons.
- Full native79 automatic20 pass/59 fail; all79 reviewed by same coding agent:
  6 bounded pass/12 partial/59 fail/2 insufficient. All79 attempted/zero skipped;
  blocked dependent turns keep cohort/qualification incomplete. Exact module I/O,
  delivered speech, completed/planned results and limits are in
  `source-schema/live-adjudication.final.json`. No independent/physical/audible qualification.
- Native SID923cce48 has count2 binding and completed sim walk10/.2→nod2→left-turn1;
  SID0b0cdc27 has direction source t11:t12 and completed sim walk3→right-turn1,
  with English wording for Chinese input. Current direct-stop case has unrequested
  idle and planned-only records, no stop execution. Weather lookup/Evidence in
  SID7b14073a is real provider evidence, with English wording. Automatic safe idle,
  acknowledgement and an empty execution do not establish task completion.
- `source-schema/live-iteration-integrity.json`:source/service unchanged throughout;
  source tree `00212ba188af4eec80049e5751dbcdbea4a2b44e05fb6cc9c263b8b8aa8f055b`. One bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20261005_003209.tar.gz`.293 full calls,285 SID-correlated,
  all82 GA primary cognition requests empty; background Evidence activation is
  retained separately. No GA/Host addition of initial Planner requests.
- Root `repair-only.patch` and per-phase repair-only patches are already applied,
  not files to apply again. Source-schema reverse-check is successful. Later four
  status/audit/Handoff/checkpoint edits are documentation-only delta from that
  frozen tree; full local Agent source remains matched. First-delivery staging
  excluded source/context/oracle changes now included in this follow-up. Historical
  full-tree identities remain bound to their original runs and documentation deltas.

## Historical immutable native iterations

| Iteration | Automatic | Same-agent review: pass/partial/fail/insufficient | One bundle |
| --- | --- | --- | --- |
| GA relationships | 19/60 | 3/7/66/3 | `chromie_debug_bundle_20261004_195926.tar.gz` |
| GA + Planner media | 18/61 | 6/5/65/3 | `chromie_debug_bundle_20261004_203439.tar.gz` |
| Planner body compound | 21/58 | 5/8/64/2 | `chromie_debug_bundle_20261004_223730.tar.gz` |
| Planner count | 18/61 | 5/12/61/1 | `chromie_debug_bundle_20261004_235201.tar.gz` |
| Count + source-Schema, current | 20/59 | 6/12/59/2 | `chromie_debug_bundle_20261005_003209.tar.gz` |

All bundle basenames above are under `/home/chromie/Downloads/`; each cohort tried
79 cases but blocked later turns remain unknown. Earlier GA/media source identities
and full records remain in `.chromie/acceptance/ga-relationship-contract-20261004T111406Z/`;
compound/count records in the current root. Only the first GA run overlapped
canonical CPU work; do not infer latency improvement or model ranking from scores.
SC language trials remain in `.chromie/acceptance/sc-language-policy-20261004T125029Z/`:
eight native packets,4/8 baseline,4/8 system-policy,3/8 footer; both rejected and
exact SC bytes restored including foreign changes. Original blink UMI omission is
real, but intrinsic capacity and prompt/context soundness are unproved; no downstream
repair or model substitution. Current native failures remain at their own owners.

## Tested services and evidence limits

Current Agent tag `chromie-agent:audit-planner-source-schema-20261005`, image
`sha256:124a02f6aaae067e98c2b5e56ec4d95a7d85772c562a74d15a8c76fe3202f935`, container
`db950343b37b7db2fd660a094486f70c93d28fd851e91b3d22d8b920f7ab18e6`, started `2026-10-04T16:17:39.47574139Z`.
`source-schema/agent-deployment.json`:healthy/restart0/zero environment changes.
`agent-source.pre-live.json` and `agent-source.after.json`:host/package digest
`93b58310173575dd106a108cd680d5d26ff524d6d4b16efe3e4b13bda81e8284` matches. Build used official Agent Dockerfile,
original generated build args and host networking; exact original environment is
retained in ignored `source-schema/agent-proof.private.json`. Historical count
image9600b13a…/sourcec03788ff… and compound image2e6656e9…/sourcecaedb275… are not current.

Default `chromie-qwen35-4b` / Qwen3.5-4B AWQ is unchanged, LLM image2330d155…,
UMI context/output32768/4096, Fast40960/4096. ASR unchanged. TTS tag
`chromie-tts:audit-resource-fix-20261004`, image
`sha256:a56b24862af4acf7d26cb87376db9ff3013ae6204674d2ee5b33bb5ec21f0ed0`,
provider source `df06d27d86a634c5f7f6b2c870d2408c1e02309dea6474b48923b60d5f28eded`.
TTS is a source-only proof image over saved dependencies; official dependency
rebuild remains unqualified. Its original61 env entries/mounts are retained in
ignored `root-cause-audit-20261004T061558Z/tts-source-proof.private.yaml`.
`.env.runtime` is generated and unchanged; default Compose alone does not identify
these tested source images. Do not restart LLM/ASR/TTS to resume an Agent proof.

Soridormi `/home/chromie/github/soridormi` remains HEAD
`2af3034a91842ecb9964a45ce24e9bdc18fcde58`, headless MuJoCo5555/MCP8000;
acquisition/handover mocked. Preserve its foreign README/script/test/workspace changes.
Actual milk object/pose and mixed-place lookup qualification remain open. TTS PCM
is generated with discarded playback. No physical microphone/audible speaker/camera,
real grasp or physical robot proof. Supervised-only hardware/audio flags must not
be used to claim automated evidence.

## Resume commands

Verify saved proof images/private overrides first. If Agent source differs, rebuild
through its official Dockerfile and verify the package before fresh identity capture.
Stop interactive Host before a cohort. Never edit/rebuild/restart during the full
cohort; after it ends collect once and judge every case. The local gate is red:

```bash
cd /home/chromie/github/chromie
set -euo pipefail
git fetch origin
git merge-base --is-ancestor origin/main HEAD
git status --short --branch
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

A separate bounded diagnostic does not waive the gate. Use a new evidence directory
and freshly captured identity, never the previous tree snapshot:

```bash
cd /home/chromie/github/chromie
set -euo pipefail
task_proof=.chromie/acceptance/planner-compound-contract-20261004T140758Z/count-scope/source-schema
task_resume="$task_proof/resume-native-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$task_resume"
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty \
  --runtime-profile .chromie/runtime_profile.json --orchestrator-env .env.runtime \
  --capability-manifest capabilities/soridormi.json \
  --compose-override docker-compose.sglang-rtx4090-laptop.yml \
  --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml \
  --compose-override .chromie/acceptance/root-cause-audit-20261004T061558Z/tts-source-proof.private.yaml \
  --compose-override "$task_proof/agent-proof.private.json" \
  --output "$task_resume/runtime.before.json"
task_live_rc=0
python scripts/general_ability_acceptance.py --mode live-text --keep-going \
  --assertion-scope full --execute --runtime-identity "$task_resume/runtime.before.json" \
  --evidence-dir "$task_resume/live" --soridormi-repo /home/chromie/github/soridormi \
  || task_live_rc=$?
./scripts/collect_debug_bundle.sh
test "$task_live_rc" -eq 0
```

## Historical evidence and first-delivery patch preservation

Earlier roots, retained for causality and original bytes:

- `.chromie/acceptance/project-audit-20261004T011454Z/`:initial design/document
  audit, dirty36-path backup, Attention two-call and SC-silence probes.
- `.chromie/acceptance/audit-repair-20261004T014950Z/`:text admission chronology,
  actual State/Runtime regressions and Level A fixture repairs; dirty55-path backup.
- `.chromie/acceptance/root-cause-audit-20261004T061558Z/`:TTS OOM/encoder proof,
  original blink primary, native17/79 and one bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20261004_161413.tar.gz`.
  Focused sadness/no-advice produces PCM877ms after SC commitment; no physical proof.
- `.chromie/acceptance/contract-fixture-repair-20261004T084054Z/`:original UMI/GA
  bytes, reversible reference/adaptor/oracle repair, dirty68-path preservation.
- `.chromie/acceptance/text-model-comparison-20260930/`:historical three-model
  final matrix9B30/79, Gemma17/79, default4B18/79; incorrect then-user chronology
  invalidates intrinsic ranking. All237 same-agent reviews and one bundle/cohort
  are retained. These are superseded source/model runs, not current qualification.

Latest combined review manifest in the Planner compound root: `combined-patch-paths.json`,
`combined-corpus-patch-paths.txt`, `combined-text-patch-paths.txt`,
`combined-asset-patch-paths.txt`, `patch-manifest-summary.json`.
That historical inventory includes3093 paths (3012 corpus,76 text,5 retired assets), excluding28
other changed paths. Reviewed selective staging preserves unrelated hunks in shared
files. `repair-only.patch` is the already-applied continuation delta against entry
backups; do not apply again, stage private evidence or blanket-add the workspace.
Preservation proof and source/corpus hashes remain beside the manifest. Keep all
ignored artifacts before cross-machine resume; sanitize private payloads before
external transfer. This owner-authorized delivery updates both Handoff/checkpoint;
all red gates and target-evidence limits remain open.

The compound root's final `delivery/scope.json` and `delivery/owned-paths.txt`
record3094 intended paths (3012 corpus,77 text,5 retired assets) and selective
staging. The parent inventory omitted the owned count-scope regression in
`tests/test_planner_binding_representation.py`; final staging recovers it.
`selective-index.patch` removes only unrelated shared hunks from
the index; it is not a worktree rollback. `owned-delivery.patch` retains the staged
review artifact. `delivery/snapshot/` is an isolated export of the candidate tree;
its offline workflow fixtures were copied from local retained files only after
checking every pinned manifest digest. Direct Git archive restoration initially
failed with `frozen archive is incomplete`; `snapshot-bootstrap.json` retains that
failure and the6076 unchanged files copied. This was a failure of that isolated export. The current cold-restore audit above
passes against the same historical pin; retain both observations rather than claiming
a current blocker or regenerating expected output.

The full local native proof above includes client/SC/oracle changes formerly excluded. Use
its exact identities and retained evidence when reproducing it; do not treat a
checkout of a delivery commit alone as the tested runtime identity. The former
28 whole-file changes and3 shared-file differences are included in this follow-up;
verify final status and preserve any subsequently added work before integration.

Delivery snapshot gate: `delivery/canonical.staged.ready.log`, exit1;
benchmarks160 pass, main84 fail/3843 pass/5 skipped/1018 passing subtests.
Those totals precede recovery of the count-scope test. Its final isolated rerun
passes1 test covering9 contrasts (`delivery/count-regression.final.log`);
production code and fixture inputs did not change after the full gate.
The83 workflow failure IDs matched the full local-tree run exactly. The additional
UMI behavior-truth subtest reads the unchanged committed
`scenarios/user_meaning_interpretation/ambiguous_move_there.json`, which lacks
required `body_effect_family`; primary DTO failed closed before expected deep
delegation. The local metadata-only correction is included in this follow-up and
its focused behavior-truth regression passes. No production failure was established.
`delivery/canonical-comparison.json` records both ordinary failures and that subtest.
Policies, test ownership, pinned Ruff/mypy, configuration, docs and benchmarks pass;
legacy stage is not reached. Final handoff edits are documentation-only and checked
again after this full gate. Both the delivery and full local native revision remain
unqualified; do not report either failed gate as passed.
