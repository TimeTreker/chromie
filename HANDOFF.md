# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns current
four-axis state/open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns stable decisions.
Replace current facts; history remains in Git and [CHANGELOG](CHANGELOG.md).

## Current snapshot

- Checkout `/home/chromie/github/chromie`, branch `codex/sc-context-budget-failure-notice`.
  Pre-delivery HEAD `a0e7524c69d6d555e26bb19ccf390922cd14fdb3`; expected resume revision is
  the latest commit containing the three delivery owners. Remote was fetched before
  development and delivery preparation; check again before push. Branch-only diagnostic
  push is authorized; no main merge without explicit owner approval.
- Six rounds complete, all final tests ended. WHAT-only UMI, GA identity, Planner
  HOW/Skills and SC expression remain. Same Gemma4 12B, all budgets/permissions and
  Planner rules. No prompt candidate, semantic critic or new production flag adopted.
- Agent `4dbf37d8f3de4709f3487ed6961f3432a60c3b740453cd4b05e30c469f8fd180`,
  image `sha256:f9138d8641f02a686a57fe1e8ad81f8bfa500db22dbe261c9bd461cd14b5cd4a`;
  host/container Agent+shared digest
  `85ac490b3722d8f95efdfdb3ba3d2fee72db0dcf313882d5b1e904608aa79332` matches.
  Evaluated behavior was dirty HEAD plus12-path patch; later delivery Markdown changes
  full-tree hash, not behavior. Do not relabel the run clean-delivery-commit proof.
- LLM `1e5d4ace2318970946739cb6da71037041be395fb958e18fd9194da004ea6857`,
  image `sha256:ab5368ff1306a55fa694d8b88173ddb23dad56c2e615d41d7068675f65c524dd`;
  Gemma revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, SGLang0.5.19,
  pinned/backported XGrammar0.2.1, RTX5090. LLM/ASR/TTS stayed unchanged; Agent was
  rebuilt for round6 before its proofs. Start/end same-cohort container/model/budget
  comparisons all pass. Services are left running; acceptance Hosts have ended.
- Context65,536; UMI/GA output2,048/60s; Planner output4,096/Agent60s/Host65s;
  cognitive300s; SC output1,024 plus2,048 margin; TTS start6s/local speech30s;
  compiler cache512MiB. Effective identity JSON owns exact values. Never edit generated
  `.env.runtime`; use `.chromie/voice-runtime/orchestrator.env` as retained.
- Soridormi `/home/chromie/github/soridormi`, clean main
  `a49a87f68bb923800c6819b0ea81ab9f4c92c71d`, unedited; `open_duck_forward`, scene
  `configs/simulation_scenarios/thirst_water_delivery.json`, SHA256
  `44454edb6a5ed5bce7f441316acf8c71655ca230cc945e52d37de8fc4afdbfca`.
  Final safe_idle=true,active_task=null,active_lanes={},standing=true,fallen=false,
  emergency_stop=false. No source/rebuild/restart/model probes between final cohort cases.
- Evidence ceiling: fixed real model/services, injected text, discarded TTS,
  MuJoCo/mock handover. No physical microphone/speaker/robot, owner-human acceptance,
  target-evidence closure or release. No new model-capacity limit proved; LoRA deferred.
- Repository surfaces:98 current Markdown files unchanged; no new current document,
  environment variable, compatibility path or first-class architectural term. New proof
  lives in ignored evidence, not in Git. Existing exception registry records the new
  closure fallback handler. Remaining failures are not waived by branch delivery.

## Retained evidence

Private artifacts stay local/ignored; never push raw prompts/logs or restore old snapshots.

```bash
cd /home/chromie/github/chromie
review_root=.chromie/acceptance/engineering-first-6turns-20261114
```

- `comprehensive-review.md`: all128 final verdicts, six rounds, original10, actual failure
  reasons and engineering/inference/ability distinction. `round6-workflow-index.md/json`
  gives source-bound module I/O and raw call refs; reflection/global associations remain
  explicitly unknown where they cannot bind a case.
- `round6-qualified-source.patch`, `round6-end-freeze-check.json` and
  `live-corpus-manifest.json`: evaluated12 paths and128 identical scenario hashes.
  `round6-full-identity.json` / `round6-final-identity.json`, start/end invariant files and
  `round6-final-agent-source.json`: exact services, model/budgets and source equality.
- `round6-full-live/`:128/128;167 admitted main inputs plus1 during-motion stop,
  automatic112 pass /16 fail; final contract+interaction43 pass /2 partial /83 fail;
  8 runner integrity records retained. Initial56/2/70 was revised after13 raw body-only
  Plans added forbidden answer obligations.0 skips; all cases reviewed. Bundle once:
  `/home/chromie/Downloads/chromie_debug_bundle_20261115_090031.tar.gz`.
- `round6-full-llm-calls.jsonl`:1016 records,0 log parse loss;1004 complete plus12
  intentional need-first prefix exits with same-turn final inference. Not12 model
  failures; raw acceptance is not DTO/Host/semantic acceptance. Streaming parsed_output
  can be null by design. No current observed grammar compilation timeout.
  `round6-wire-conformance-audit.json` validates all1,004 complete raw outputs against
  captured request Schema with0 unknowns; it is not full DTO/Host or native qualification.
- `round6-original/`, `round6-original-workflow.md`, source-map JSON:10/10 inputs and
  terminal notifications /54 calls, but duplicates/lifecycle remain.09 food intent kept
  and milk delivered;10 explicitly cannot check further food. Final10 stored Goal state
  unknown.03/04 overlap preserved; exact historical interval unknown. Original bundle:
  `/home/chromie/Downloads/chromie_debug_bundle_20261115_055808.tar.gz`.
- `round6-focused-live/`:3 auto passes,2 visible passes/1 stale-time-repeat failure;
  4 bounded results respond, but Goal closure remains unqualified.
- `round6-local-checks.json`:176 benchmarks /4,414 main /1,042 subtests /20 legacy;
  5 skips /3 warnings. Policy/docs/45 Level A/strict6,000 pass. Strict first restricted
  PermissionError attempt and post-run report-helper field error are preserved separately.
- `native-links-proof.json`:GA41 Schema/811 controls per arm,335→0 mismatches;
  `incremental-proof-v2-backend-proof.json`:52 Schema/208 controls per arm0 mismatches;
  `round6-candidate-isolated-proof.json`:96/96 controls;147 isolated and274 focused pass.
  No claim beyond captured scopes; invalid v1/serializer/prefix attempts remain retained.
- `round6-bounded-native-audit.json`:25 calls, no completed incremental missing respond;
 17 completed calls:15 respond,2 same-clock reminder executions rejected.8 failed-result
  calls separate. Case124 failed incremental decision was repeated at aggregate closure;
  fix this consumption gap before target qualification.
- `round6-input-fact-audit.json` and `round6-memory-pipeline-audit.json`:given birthday,
  Max/blue/piano and bottle observations differ from missing cross-conversation facts.
 85 has an accepted preference proposal on an unplayed ingress ack, lost before spoken
  Work reply; request.language en-US then conflicts with the requested preference.
- `round6-extra-response-raw-proof.json`, `round6-case40-42-workflow.md`:source authority,
  premature result and mixed-stage contract failures; `round6-full-marker-surface-audit.json`
  records22 redundant SC proof objects (max3,094 JSON chars, no low-level keys observed).
- `round6-sc-context-breakdown.json`:peak32,849 prompt tokens /35,921 with reserves,
  below65,536; inline output Schema60,235 chars dominates, native wire90,086 chars is
  decoder surface, not another prompt-text token copy. Context still needs engineering.
- `goal-delivery-registration-proof.json` and `verified-memory-age-proof.json` are zero-LLM
  mechanical controls, not adopted production fixes. Do not blindly set binding=True or
  treat storage time as observation time. Earlier invalid control versions are retained.
- `round1-review.md` and `round5-review.md` retain separate complete128 revisions/rubrics.
  Round5 bundle `/home/chromie/Downloads/chromie_debug_bundle_20261115_052453.tar.gz`;
  round1 `/home/chromie/Downloads/chromie_debug_bundle_20261115_005739.tar.gz`.
  GA/SC/Planner candidates and reference gaps remain; no candidate prompt was adopted.

## Resume and verify

Read core owners and the current comprehensive workflow first. The next change follows
STATUS's ordered blockers; do not silently add another optimization round to this finished
six-round request. Preserve model/budgets/permissions and complete WHAT. No semantic
critic, phrase routing, UMI output-mode restoration or Planner rule relaxation.

Use unused evidence paths for an authorized next behavior repair:

```bash
set -e
cd /home/chromie/github/chromie
next_root=.chromie/acceptance/engineering-first-6turns-20261114/resume-next
test ! -e "$next_root"
mkdir "$next_root"
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir "$next_root/strict6000"
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir "$next_root/level-a"
```

When Agent behavior changes, stop the acceptance Host and rebuild only that service;
verify safe idle and reset the same scene BETWEEN cohorts, never between cases:

```bash
./scripts/compose.sh build chromie-agent
./scripts/compose.sh up -d --no-deps --force-recreate chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

One frozen directory-discovered aggregate, with diagnostic keep-going retaining all
failures. Verify effective models/budgets/identities before admission:

```bash
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
  --scenario-root .chromie/acceptance/engineering-first-6turns-20261114/live-corpus \
  --execute --runtime-identity "$next_root/full-identity.json" \
  --soridormi-repo /home/chromie/github/soridormi \
  --evidence-dir "$next_root/full-live" > "$next_root/full-live.log" 2>&1
cohort_result=$?
./scripts/collect_debug_bundle.sh > "$next_root/full-bundle.log" 2>&1
bundle_result=$?
# Retain both exits, inspect every case, verify final safe idle. A failure stays failed.
```

After safe-idle verification and a same-scene reset between aggregates, copy the retained
original10 helper to the unused resume root. It preserves03–04 overlap and writes only
its own new `round6-original` child:

```bash
cp "$review_root/replay_round6_console.py" "$next_root/replay_console.py"
python scripts/capture_runtime_identity.py --allow-dirty \
  --orchestrator-env .chromie/voice-runtime/orchestrator.env \
  --output "$next_root/round6-original-identity.json"
set +e
python "$next_root/replay_console.py" > "$next_root/original-replay.log" 2>&1
original_result=$?
./scripts/collect_debug_bundle.sh > "$next_root/original-bundle.log" 2>&1
original_bundle_result=$?
# Retain both exits, inspect all ten source-bound results and final safe idle.
```

The original source transcript remains under
`.chromie/acceptance/sc-context-budget-20261102/baseline/original-dialogue.json`.
Collect one bundle after each complete separate replay. Never overwrite completed runs.
All requested current tests have finished; source behavior changes require new qualification.
Documentation-only delivery updates do not create clean-commit live evidence.
