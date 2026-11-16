# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).

## Current snapshot

- Checkout `/home/chromie/github/chromie`, branch `codex/sc-context-budget-failure-notice`.
  Pre-delivery HEAD `0729b3634971194cf7de5f3c63d4f5832050fd86`; expected resume revision
  is the latest commit containing all three delivery owners. Origin was fetched before
  source work and delivery preparation; branch upstream0/0. Fetch again before push.
  Branch-only diagnostic push authorized; no Main merge without explicit owner approval.
- All requested comparison tests are finished. Main `55f5587d4ca8034fdefb24e53d632df5790b7dba`
  vs branch `0729b3634971194cf7de5f3c63d4f5832050fd86`:128 cases each plus exact original10
  each. No application edits during this delivery or cohorts. Source test edits are opaque
  IDs, purpose/stage preservation and frozen oracle/precondition corrections; no model,
  budget, permission or Planner-rule changes. Six optimization rounds preceded this
  frozen comparison; do not silently start another broad optimization round.
- Detached app checkouts `/tmp/chromie-ab-main-20261116` and
  `/tmp/chromie-ab-branch-20261116` stay pinned. The same declared observer overlays were
  applied to both; app directories have no diff. Common128 manifest/source/runtime
  identities remain under the evidence root. Sequential weather/time is externally
  confounded; shared compiler backend excludes the historical backport benefit.
- Original Agent restored as container
  `3d80fedb83534a60ca8ab670dc8a9febaf0cf5f601034d6e4301600b9419074a`, image
  `sha256:f9138d8641f02a686a57fe1e8ad81f8bfa500db22dbe261c9bd461cd14b5cd4a`;
  Agent/shared digest
  `85ac490b3722d8f95efdfdb3ba3d2fee72db0dcf313882d5b1e904608aa79332` matches.
  Final delivery documentation/harness changes are not a clean-commit app qualification.
- LLM container `1e5d4ace2318970946739cb6da71037041be395fb958e18fd9194da004ea6857`,
  image `sha256:ab5368ff1306a55fa694d8b88173ddb23dad56c2e615d41d7068675f65c524dd`;
  Gemma HF `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, SGLang0.5.19,
  pinned/backported XGrammar0.2.1, RTX5090. TTS image
  `sha256:50871c1b589c36616b8940dab1ec5ca067ebb76e76600781ac6b0b130e347f64`.
  Services are left running; acceptance Hosts have ended. The controller reset the same
  scene/services only between cohorts, never between cases.
- Context65,536; UMI/GA output2,048, Planner4,096, SC1,024; Agent60s/Host65s,
  deep120s/125s, cognitive300s, local speech30s, first TTS6s, weather7s/two attempts,
  context margin2,048; compiler cache512MiB. Effective identity JSON owns exact settings.
  Never edit generated `.env.runtime`; retained Host env is
  `.chromie/voice-runtime/orchestrator.env`.
- Soridormi `/home/chromie/github/soridormi`, Main
  `a49a87f68bb923800c6819b0ea81ab9f4c92c71d`, untouched;
  MCP image `sha256:389cedb814f93c14d28394a2ff0f421de89e66806d07f7984c5cfa37581d924b`.
  `open_duck_forward`, `configs/simulation_scenarios/thirst_water_delivery.json`, SHA256
  `44454edb6a5ed5bce7f441316acf8c71655ca230cc945e52d37de8fc4afdbfca`.
  Final safe_idle=true, active_task=null, active_lanes={}, standing=true, fallen=false,
  emergency_stop=false. No physical microphone/speaker/robot or release proof.
- Source libraries207: general99/everyday106/parked2; all205 old IDs retained, plus2
  retained order contrasts.128 online comparison cases comprise108 daily/10 functional
  Smoke/10 functional Core; the original79 functional cases are reviewed/retained but
  not all replayed by128. No new current document, env variable, compatibility path or
  first-class architecture term;98 current Markdown files remain. Raw private evidence
  stays ignored, not pushed. No intrinsic weight-capacity limit is established.

## Retained evidence

```bash
cd /home/chromie/github/chromie
review_root=.chromie/acceptance/fair-main-branch-20261116/qualified-v2
```

- `comprehensive-review.zh.md`: complete scope, results, original episode, failure
  classification and proposed general repairs. `paired-review.zh.md/json`: all128 paired
  manual verdicts/reasons. `workflow-index.zh.md/private.json`: actual stage I/O, intervals,
  model call references and source paths for256 case-arms; global unbound calls stay unknown.
- `confirmed-boundaries.zh.md`: earliest error tables, actual module handoffs, containment,
  general repair/verification. `branch-original/original-workflow.zh.md`: the actual09 food
  WHAT→Planner water substitution→mock handover→SC/console sequence, plus all10 inputs.
- `main-full/`, `branch-full/`:128/128 each, automatic117/109 pass; functional Main94 pass/
  12 partial/21 fail/1 insufficient, branch84/11/32/1; interaction complete33/12. Stage22/96/10.
  Functional Smoke10/10 both; functional Core7/10 vs5/10. No qualified revision.
- `main-original/`, `branch-original/`:10/10 terminal notices each,47/57 calls; both episode
  fail. Main09 UMI misgrounds food as water despite supplied food context; Main final TTS
  exists but history/console omits it. Branch09 UMI/GA preserve food but Planner delivers
  water;10 gives visible food limitation.03 interrupted by04 in branch; raw meaning and
  subsequent GA preserve thirst. Exact historical intervals unknown; completion is not pass.
- Each arm retains `identity.json`, `invariants.json`, source checks, `exits.json`,
  `post-status.log`, model-input/raw-contract/context audits. Main16 and branch18 identity
  checks pass;2104 retained model requests have0 reviewer markers/missing/parse losses.
  `observer-overlay-v2.json`, `common128-manifest.json`, `comparison-protocol.json` bind
  the frozen test conditions. Earlier parent Main124 is contaminated diagnostic evidence,
  excluded from this qualified-v2 comparison. Never overwrite completed results.
- Full raw Schema counts:Main968 valid/1 invalid/17 unadjudicated; branch1005/0/9.
  Original Main39/4/4; branch56/0/1. Branch9+1 cancellations each have one same-turn final
  need-first continuation. `cancelled-call-adjudication.private.json` uses turn_id, correcting
  an initial report-helper null-sid join; that helper error is not an app defect.
- `native-backend-results.private.json`: post-cohort CPU grammar matching,0 inference/actions,
  5 actual Schema/16 controls.11 legal accepted/4 illegal rejected/1 JSON-valid property
  order rejected. Correct tomorrow meaning accepts another ordering; not semantic exclusion.
- SC full peak51,494 Main/33,009 branch tokens; inline contract101,250/62,692 characters
  dominates the peak messages. Native format is separate, not extra prompt tokens.
  No current grammar timeout or SC overflow observed; historical trace gaps remain.
- `branch-playback-key-collision-proof.json` is a zero-model reproduction in both source
  revisions. Each full arm's `playback-receipt-audit.json` flags22/50 non-reused early
  receipts; event counts are not semantic failure counts or physical speaker evidence.
- `local-validation.json` and parent `repository-gates-v2.json/log`:176 benchmark,
  4,415 main,1,042 subtests,20 legacy,5 skips/3 warnings; policy/docs pass.160 focused
  harness is a subset. Initial socket EPERM attempt retained as environmental restriction.
  Source-purpose review: parent `scenario-curation-review.json/md`,
  `existing-functional79-review.json`, `curation-source-proof.json`.
- Earlier six-round evidence remains in
  `.chromie/acceptance/engineering-first-6turns-20261114/`; its strict6,000/45 Level A,
  native GA41/811 and typed-proof52/208 controls retain that earlier revision scope.

One bundle was collected after each completed cohort:

```text
/home/chromie/Downloads/chromie_debug_bundle_20261116_175411.tar.gz  Main128
/home/chromie/Downloads/chromie_debug_bundle_20261116_180601.tar.gz  Main original10
/home/chromie/Downloads/chromie_debug_bundle_20261116_221156.tar.gz  Branch128
/home/chromie/Downloads/chromie_debug_bundle_20261116_223229.tar.gz  Branch original10
```

## Resume and verify

Read the report/workflow first, then STATUS's ordered blockers. Do not reinterpret all
failures as intrinsic LLM inability. Primary semantic errors, overconstraints, lost input,
provider/timeouts and Runtime failures have different owners. No output-mode restoration,
phrase routing, second semantic critic, budget increase or relaxed Planner rules.
All current jobs have finished. These commands inspect retained evidence without inference:

```bash
set -e
cd /home/chromie/github/chromie
review_root=.chromie/acceptance/fair-main-branch-20261116/qualified-v2
cat "$review_root/progress.json" "$review_root/restored-agent-source.json"
cat "$review_root/main-full/exits.json" "$review_root/branch-full/exits.json"
cat "$review_root/main-original/original/episode-summary.json"
cat "$review_root/branch-original/original/episode-summary.json"
python "$review_root/build_paired_report.py"
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

For a next authorized repair, choose an unused root. Source changes require new focused
proof and full qualification; documentation alone does not require redoing model inference:

```bash
set -e
cd /home/chromie/github/chromie
review_root=.chromie/acceptance/fair-main-branch-20261116/qualified-v2
next_root="$review_root/next-authorized"
test ! -e "$next_root"
mkdir "$next_root"
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir "$next_root/strict6000"
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir "$next_root/level-a"
```

When application behavior changes, end the acceptance Host, rebuild only the changed
service and verify source/idle. Use the existing `run_comparison.py` reset/status helpers
as read-only operational references; do not rerun that completed controller or reset during
an aggregate. After the same scene reset BETWEEN cohorts, run one frozen complete batch:

```bash
./scripts/compose.sh build chromie-agent
./scripts/compose.sh up -d --no-deps --force-recreate chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
export ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco
export PYTHONPATH=/home/chromie/github/chromie
python scripts/capture_runtime_identity.py --allow-dirty \
  --orchestrator-env .chromie/voice-runtime/orchestrator.env \
  --output "$next_root/full-identity.json"
set +e
python scripts/general_ability_acceptance.py --mode live-text --keep-going \
  --assertion-scope user-outcome --scenario-root "$review_root/common128" \
  --execute --runtime-identity "$next_root/full-identity.json" \
  --soridormi-repo /home/chromie/github/soridormi \
  --evidence-dir "$next_root/full-live" > "$next_root/full-live.log" 2>&1
cohort_result=$?
./scripts/collect_debug_bundle.sh > "$next_root/full-bundle.log" 2>&1
bundle_result=$?
# Retain both exits, judge every case and verify final safe idle; any failure stays failed.
```

After another between-cohort safe-idle verification/reset, preserve the original10 input
bytes and03/04 overlap with the retained helper. It writes only a new `original/` child:

```bash
set -e
cp "$review_root/original-dialogue.json" "$next_root/original-dialogue.json"
mkdir "$next_root/original-episode"
python scripts/capture_runtime_identity.py --allow-dirty \
  --orchestrator-env .chromie/voice-runtime/orchestrator.env \
  --output "$next_root/original-episode/identity.json"
set +e
python "$review_root/run_original.py" "$next_root/original-episode" \
  > "$next_root/original-replay.log" 2>&1
original_result=$?
./scripts/collect_debug_bundle.sh > "$next_root/original-bundle.log" 2>&1
original_bundle_result=$?
# Keep exits, raw call windows and actual playback events; inspect all10 and final idle.
```

Do not copy live claims from planned responses, discarded audio, the simulator or an older
revision. Physical evidence remains supervised; Main merge remains owner-controlled.
