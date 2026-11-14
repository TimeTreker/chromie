# Chromie Handoff

This file owns the volatile operational snapshot. [STATUS](docs/STATUS.md) owns the
four-axis state and ordered open work; [Checkpoint](DEVELOPMENT_CHECKPOINT.md) owns
the stable resume boundary. Replace current facts rather than append history.

## Current snapshot

- Checkout `/home/chromie/github/chromie`; branch `codex/sc-context-budget-failure-notice`.
  Pre-delivery HEAD `cd038af616b7d8de3ed28526ba156d776cffb414`; expected resume revision is
  the latest commit containing these three delivery owners. Upstream was fetched before
  source development and delivery preparation; check again before push. Branch-only
  diagnostic push is owner-authorized; no main merge without approval.
- Owner-authorized WHAT-only UMI; GA identity/continuity, Planner HOW/Skills, SC expression.
  Same Gemma4 12B, context/output/deadline/provider permissions. No Planner relaxation,
  semantic critic, phrase routing, candidate prompt adoption or new production flag.
- Agent `78f7c3f01221442bb9f1e5dd65fae78a33f96ab52807bc9a5fd28f932df0abf0`,
  image `sha256:25f89b77bea3b77568ec5968434652a7e8157a04a354b803506f30044d203c04`;
  Host/container Agent+shared source `9ee2082fa27da5b2c9a025103c4d4ef27e20e9e1871ac488d566a0f4e6a1c728`.
  This is evaluated dirty behavior source; later current-state Markdown updates change
  the full-tree hash, not the evaluated behavior. Do not relabel it clean-commit proof.
- Model `1e5d4ace2318970946739cb6da71037041be395fb958e18fd9194da004ea6857`,
  image `sha256:ab5368ff1306a55fa694d8b88173ddb23dad56c2e615d41d7068675f65c524dd`;
  Gemma revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, SGLang0.5.19,
  pinned/backported XGrammar0.2.1, RTX5090. Model lifetime starts2026-11-13T07:29:46Z.
  Model/ASR/TTS containers remained unchanged during before/original/final runs.
- Context65,536; UMI/GA output2,048 and60s; Planner output4,096, Agent60s/Host65s,
  cognitive300s; SC output1,024 plus2,048 margin; TTS start6s/local speech30s;
  compiler cache512MiB. Effective model and cognitive-budget comparisons pass.
  Do not claim equality of every unrelated environment value from hashes alone.
- Paired Soridormi `/home/chromie/github/soridormi`, clean main
  `a49a87f68bb923800c6819b0ea81ab9f4c92c71d`, unedited; `open_duck_forward`, scene
  `configs/simulation_scenarios/thirst_water_delivery.json`, SHA256
  `44454edb6a5ed5bce7f441316acf8c71655ca230cc945e52d37de8fc4afdbfca`.
  Same-scene resets only between cohorts. Final MCP status safe_idle=true,active_task=null,active_lanes={},standing=true; all jobs ended.
- Evidence ceiling: fixed native model/services, text, discarded TTS and MuJoCo/mock handover.
  No physical microphone/speaker/robot evidence, owner-human acceptance or release claim.

## Retained evidence and blockers

Private artifacts remain ignored/local; do not push raw prompts/logs or old snapshots.

```bash
cd /home/chromie/github/chromie
review_root=.chromie/acceptance/semantic-full-review-20261114
work_root=.chromie/acceptance/meaning-coverage-repair-20261112
```

- `source-before-repair.patch`/status preserve pre-existing dirty work;
  `this-turn-repair.diff` and `this-turn-repair-paths.json` isolate16 paths.
  `json-patch-audit.json` reviews all3,333 changed JSON blobs; most fixture changes are
  explicit WHAT-only frozen-corpus migration. Never blindly restore historical source.
- Local required checks:176 benchmarks /4,361 main /1,042 subtests /20 legacy pass;
  5 host xgrammar skips supplemented by30 original byte-tokenizer native controls.
  Ruff/Mypy/policy/docs pass,98 Markdown/15 core readings. `final-local-checks.json`
  retains exits; `strict6000-current/` passes6,000 and `local-general-ability/`45/45 Level A.
  Restricted socket-environment failures are preserved separately, not model failures.
- `baseline-full/`:126 cases, automatic105/126; Codex semantic50 pass/6 partial/70 fail,
  including26 hard failures (124 severity corrected from the provisional draft). Old episode loop attempted156/163 main turns plus1 extra
  stop;7 later turns were skipped. Case41 timed out in teardown; pre-timeout evidence
  retained separately. One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261114_133456.tar.gz`.
- `native-original/`:10/10 inputs and terminal notifications,57 accepted role calls,
  about20m59s, but no semantic pass. Original09 delivers milk, not water; original10
  UMI preserves other-food inquiry and Planner explicitly substitutes water. GA06
  references unrelated old delivery Goal; SC duplicates/outdated commitments remain.
  One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261114_161530.tar.gz`.
- `final-full/`:automatic108/126; Codex53 pass/9 partial/64 fail, including26 hard failures. All17 smoke/98 core/11 challenge complete;
  all163 main inputs plus1 extra stop attempted. One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261114_200858.tar.gz`.
  Source immutable during the cohort. `final-semantic-review.json`/`final-coverage.json`
  and raw calls are authoritative for observed counts. Review is by Codex, not human approval.
- Four GA complete68-case batches:20/60,20/60,39/60,28/60 current-valid strict references;
  each has8 reference/current-contract gaps, not8 model defects.39/60 still fails all12
  unrelated-new probes; tagged variant has35 ReadTimeouts. No candidate adopted.
  An invalid16-case harness attempt and all failed outputs remain retained.
- Planner20-case baseline/candidate scores5/20 and3/20; candidate rejected.
  `planner-projection-ab/`:current_1=7/20 strict,20/20 contract; before_fix=7/20 strict,19/20 contract; current_2=7/20 strict,19/20 contract.60 complete interleaved transactions,
  unchanged inputs/messages/options and ordered expanded-schema equality. These60
  transactions each used1 model call; no need-first continuation was triggered.
  Not Runtime/Skill or physical qualification.
- Projection stability: old16 requests yield2 wire hashes, repaired16 yield1;
  ordered expanded schema identical. Actual262,144-token vocabulary compiler accepts
  4 full positives and rejects9 negatives. Historical4MB source-Schema compiler proof
  is11.400s compressed vs31.751s original; this is preprocessing, not all Planner latency.
- Current51 quiet+nod2 completes with zero TTS/playback. Current41 exits normally but
  independent clock is215.4386s old at actual playback. Defensive cancellation proof
  does not identify the exact old native blocked await. Story106 still times out30s;
  shorter story117 fits this run, not a qualified generic delivery repair.
- SC77/80 first-turn fact proposal is missing before new-conversation recall failure;
  `current-memory-workflow-proof.json` accepts correct alternatives at Schema/DTO/Host.
  UMI104 misses deceptive-request value review. GA/Planner grounding, Need readiness,
  duplicate/later-future speech, time contracts, Skill disclosure and provider scopes
  remain open. Four post-cohort weather probes resolve cities and TCP but time out during forecast TLS; the deeper network cause and historical low-level phases remain unknown.
- `native-boundary-proof.json`:9 exact-case real-tokenizer controls,8 match expectation and1
  fails: the captured invalid terminal-supersede Goal is admitted with EOS despite wire
  enum rejection. Host remains fail-closed. Both stated=true memory proposals are native-valid.
- `parked-model-diagnostics-ready/`:2 additional historically parked cases,4/4 admitted
  turns,22 accepted calls,automatic0/2 and semantic0/2. Shopping-note first turn never
  commits Memory; later recall fails. Its old memory.keep automatic expectation is absent
  from current catalog, an independent reference gap. First failed setup stays in
  `parked-model-diagnostics/` with0 admissions/model calls: MCP startup reset ZMQ timeout.
  The full2-case batch was rerun only after verified readiness and identical source/model/budgets.
  Ready bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261114_203736.tar.gz`;
  failed-setup bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261114_202719.tar.gz`.
- Current83 correctly retains Chinese preference; raw next SC input contains it, yet English
  ingress is spoken. Do not attribute that case to missing preference storage. The controlled
  Planner repeat has identical payloads and2/20 declared Plan signature differences; its
  18/20 raw-output differences include rationale/IDs and are not18 semantic regressions.
- `comprehensive-review.md` gives the126-case current table, both aggregate summaries, original10,
  role experiments and evidence limits; `workflow-audit.md` gives actual module I/O,
  concurrency, earliest boundaries, unknowns and concrete general repair/validation work.
  This branch is a truthful diagnostic handoff, not semantic qualification.

## Resume and verify

Read the core path, current owners, retained workflow audit and actual failed transactions.
Repair one earliest owner inside the existing architecture; preserve complete WHAT,
model/budgets and Planner rules. Freeze a new target-blind full-role corpus for each
source transaction change, retaining old source-bound cohorts and failed candidates.
Do not use native prefix-only calls, known reference gaps or accepted transport as passes.

For a behavior repair, run the focused regression and relevant general-ability class,
then the required gates and broad offline evidence using unused paths:

```bash
set -e
cd /home/chromie/github/chromie
next_root=.chromie/acceptance/semantic-full-review-20261114/resume-next
test ! -e "$next_root"
mkdir "$next_root"
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir "$next_root/strict6000"
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir "$next_root/level-a"
```

When Agent source changed, stop the Host, rebuild/recreate only that service, verify
safe idle, and reset the same scene BETWEEN cohorts. Keep generated runtime configuration:

```bash
./scripts/compose.sh build chromie-agent
./scripts/compose.sh up -d --no-deps --force-recreate chromie-agent
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
```

One complete native invocation; do not edit source, rebuild, restart or insert model probes
between its cases. Owner-authorized diagnostic continuation retains failed gates as failed:

```bash
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
export ORCH_ACTION_DRY_RUN=false CHROMIE_OPERATOR_MODE=voice_mujoco
export PYTHONPATH=/home/chromie/github/chromie
python scripts/capture_runtime_identity.py --allow-dirty \
  --orchestrator-env .chromie/voice-runtime/orchestrator.env \
  --output "$next_root/native-full-identity.json"
set +e
python scripts/general_ability_acceptance.py --mode live-text --keep-going \
  --scenario-root .chromie/acceptance/repair-retest-20261111/corpus-final-live \
  --execute --runtime-identity "$next_root/native-full-identity.json" \
  --soridormi-repo /home/chromie/github/soridormi \
  --evidence-dir "$next_root/native-full" > "$next_root/native-full.log" 2>&1
native_result=$?
./scripts/collect_debug_bundle.sh > "$next_root/native-full-bundle.log" 2>&1
bundle_result=$?
# Retain both exits, inspect every case and verify final safe idle; a hard failure stays failed.
```

The separate original10 replay uses `review_root/replay_console_overlap.py`: copy it into
an unused next_root, capture `original-identity.json` there, then run the copied helper
and collect exactly one bundle after it exits. Its original TEXTS source is preserved at
`.chromie/acceptance/sc-context-budget-20261102/baseline/original-dialogue.json`.
Keep03/04 overlap; exact historical intervals are unknown. Never overwrite completed runs.
All requested current tests are complete; rerun behavior gates after a new repair, not
merely to disguise current native failures. Main merge still requires owner approval.
