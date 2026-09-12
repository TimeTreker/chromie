# Chromie Latest Handoff

## Current delivery — audit continuation, 2026-09-12

Repository `/home/chromie/github/chromie`, branch `main`, pre-delivery base/fetched
origin `f5522f874671ff1b8bd42553a22793eaad0b1f51`, initially clean. Python used:
`/home/chromie/miniconda3/bin/python`. Resume from the latest main commit containing
both this file and [DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md). The owner
requested GitHub publication, actionable Issues and handoff. This delivery updates
those records and consolidates historical narrative; no runtime, prompt, Schema,
configuration, model or principle was changed. Normal commit/push is authorized.
Do not close #52 or qualification Issues: this is diagnosis, not implementation.

The [audit report](ARCHITECTURE_AUDIT.md) contains the current Issue map, external
review assessment, exact workflow tables, boundaries and acceptance criteria.
#49–#51 are verified delivered/closed. #52–#55 and #24/#32/#35 remain open.
New #56 owns package-wide typing; #57 owns review of one real lifecycle seam.
Maintain evidence-closure priority; do not revive the numeric size ceilings removed
by owner-approved #45 or add architecture simply to reduce class sizes.

## Evidence and unchanged workflow

R = `.chromie/acceptance/issue52-cancellation-scope-20260912/`, ignored and requiring
separate transfer. This machine does **not** contain the private other-machine
`.chromie/acceptance/issue51-staged-progress-20260912/` artifacts. Their prior results
remain historical, not fresh evidence. Earlier original audit probes are available
at `.chromie/acceptance/project-wide-audit-20260912/audit_probes.py` and reproducible
from the [published original appendix](https://github.com/TimeTreker/chromie/blob/3e1c50414b6709a2b7222269cadce203e5e6661a/ARCHITECTURE_AUDIT.md#reproduction-appendix).

| Actual owner / episode | Input → output and verdict |
| --- | --- |
| Cancellation context/catalog | Retained stateful reminder Goal + scoped cancelled/released-confirmation Evidence + available reminder fixture → response-only, empty catalog, false direct-speech description. First wrong projection, reproduced for four cases × two provider states × Fast/Deep. |
| Fast Schema/Host | Correct scripted `respond`, satisfaction 0 with original reminder unmet, no Work → two Schema-branch errors and `goal_satisfaction_not_exact`; speech retained as undelivered advisory. Incorrect admission constraint. |
| Deep Schema/Host | Same scripted raw result → accepted `respond`, zero Work, original Goal unsatisfied. No output rewriting or semantic repair. |
| Fresh Deep model | Cancelled EN/ZH pass; released-confirmation EN/ZH incorrectly claim reminder capability absence. Projection remains a contributing cause; no isolated model-root-cause claim. |
| Runtime/token/delivery | Not exercised by these Planner probes. Remain required #52 proof; no real reminder capability was added. |
| Host Reflection closure | Actual closure method with controlled pending Reflection → result Planner waits; Reflection receives no Mind; retained advisory absent in Fast/Deep prompt. #53/#54 remain reproduced. Scripted closure ends `planner_reentry_unavailable`, not a successful response. |

No fix changes this workflow in this delivery. Proposed #52 work preserves WHAT and
catalog truth separately from execution permission, admits truthful scoped reporting
without false satisfaction, and verifies revocation/sibling/delivery behavior at the
real Runtime boundary. Changes to canonical meaning require owner authorization;
no blanket threshold relaxation, second semantic reviewer, new flag or phrase rule.

Fresh verification:

- `canonical-audit.log` and `publication/canonical-delivery-final.log`: full gates passed, 2,988 tests/794 subtests, 145 benchmarks,
  20 legacy tests; policy/static/config/docs/ownership pass; two existing FastAPI
  warnings. `tests/test_planner_staged_progress.py`: 32 passed independently.
- `contracts-mypy-diagnostic.log`: all 30 contract package files pass strict Mypy;
  enforced `config/mypy_scope.txt` still contains only five files. This is diagnostic
  proof for #56, not a ratchet change.
- `fast-before`: 204/204 complete one-call outputs, Schema/Host; 201 frozen hard
  passes. Three admitted #51 staged reads remain failures against old escalation
  regions. Semantic review additionally flags an invented dewdrop topic in
  `direct_communicative_planning_06_supported_en`; two English future-read cases
  (`temporal_readiness_planning_34/35_supported_en`) mark acquisition/delivery exact
  and need #35 adjudication. No full semantic or Runtime-adapter qualification.
- `deep-before`: 40/40 complete one-call outputs, Schema/Host; 36 frozen hard passes.
  Two valid staged reads miss composite-only regions; two released-confirmation
  cases falsely claim provider absence. Cancelled EN/ZH pass with original Goal unmet.
- `semantic-review.json` in each cohort records every case, raw digest, review and
  rationale. Review used all 244 scenario/raw-semantic-content projections plus
  exact mechanical checks and focused full-output inspection; non-independent
  post-hoc agent review, no repairs or Runtime feedback.
- `cancellation-projection-and-contract-probe.json`: 16 captures and two scripted
  Host replays. `remaining-reflection-probes.json`: current #53/#54 reproduction.
  `cancellation_probe.py` and `scripted-control-response.json` retain reproduction.
- Initial diagnostic harness mistakes remain explicitly separate:
  `scripted-control-response-probe-harness-error.json` supplied a dict to a raw-string
  replay helper; `cancellation-probe-schema-key-error.log` used the wrong capture
  Schema key. Corrected harness outputs are separate. Neither made candidate calls,
  changed production source or counts as a failed/passed model result.
- The first documentation consolidation omitted the explicit Goal-driven focus
  declaration required by the existing checker. It failed before tests; the current
  checkpoint restores that architectural statement. Initial logs remain in
  `publication/`; the checker and its requirements are unchanged.

Candidate identity: fixed `gpt-5.6-sol/high`, Codex CLI, one target-blind primary call,
600-second timeout, no retries/repair; Fast concurrency 8, Deep 4. Source/harness
and prompt/Schema hashes are retained in `batch-identity.json`, `packets/`, `schemas/`
and `source-stability.json`. Fast corpus SHA256:
`2650948b9027071c948bb75481d203104923b4aff2bfc33750288d350679c2d8`;
Deep corpus: `a0c79e38cf4055b7021a4dcc1cbd0a2caec915872174d41e9c2bf153a4a7406a`.
Source stayed unchanged through both cohorts; only audit documents changed afterward.
Sequence limit: Deep inference started after Fast inference/mechanical adjudication;
Fast post-hoc semantic review finished while Deep was running. This is retained as
an audit baseline, not a completed ordered Optimize qualification. Before a repair,
finish and diagnose the full Fast phase before beginning the Deep phase.

## Live baseline and cleanup

Agent source initially differed from the checkout. Rebuilt/recreated only Agent at
unchanged `f5522f87` using `.env.runtime` and existing
`.chromie/voice-runtime/compose.voice-mujoco.yaml`. All 112 Agent/shared Python files
then matched byte-for-byte (`live-before/source-verification.json`). No generated
configuration was edited. Initial identity capture rejected stale
`.chromie/voice-runtime/orchestrator.env`; the already existing
`.chromie/acceptance/laptop-iterations-20260910/orchestrator.env` matched the qualification
32k profile and was used instead. Both failed and successful identity logs remain.

Successful identity: `e6456782c8ca523585ec2bdb7b6b3da55309a038e0b45208d21bfecea06631f4`.
Agent/TTS/LLM were healthy and bound explicitly. ASR was not running or included.
Deployed role models remain configured Qwen3.5:4b/Ollama; this live evidence is
separate from the fixed Codex offline surrogate, not a substituted candidate model.
Soridormi repo `/home/chromie/github/soridormi`, branch `codex/turn-count`, retains
pre-existing untracked content under `workspace/Open_Duck_Playground`; do not clean it.

`R/run-live-before.py before` invoked the complete directory-discovered 51-case
must-pass text-preview cohort once, without source/provider edits between cases.
The script loads the existing matching environment and stops on hard integrity
failure, then collects one bundle. It must not be rerun into its existing directory.

| Live boundary | Material evidence → actual result / verdict |
| --- | --- |
| Input | `compound_walk_nod_turn`: “walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left”; session `67cc5d79`. |
| Primary GI | Call `llmcall_goal_interpreter_c97d9d89b6f74c55`: one body-action responsibility, confidence 0.5, direction/duration/speed plus whole-turn `subtype`. First observed wrong output boundary; exact prompt/provider/model causal attribution remains unresolved. |
| GI validator/HTTP | Whole-turn subtype rejected as `invalid_primary_goal_interpretation_semantics`; `goal_interpreter_unavailable`, HTTP 503. Correct fail-closed containment. |
| GA / Planner / Runtime | Not invoked for failed case. #52 was not reached. |
| Cohort stop | One completed failure, second case `look_while_blinking_twice` interrupted during startup, 49 unrun; all 51 slots reviewed. Incomplete and failed. |

The one retained raw response has verified SHA256
`dd300bc80a67ea0064a99d3b0b685134d0ad86c0f1513c46f63503451d63bf91`.
Transport `accepted` does not mean semantic admission. Exactly one bundle for this run:
`/home/chromie/Downloads/chromie_debug_bundle_20260912_171920.tar.gz` (collection exit 0).
Do not collect another bundle to relabel this same cohort. `live-before` holds original
Agent logs, parsed call, source/provider before/after identity, commands, review,
integrity stop, runtime identity and readiness/idle checks.

Final simulator MCP status: sim, safe_idle=true, no active task/emergency/fall.
Owned simulator container `soridormi-sim-run-6c9f610628b8` and MCP were stopped; owned
preview exited and Host idle was checked. Agent/TTS/LLM remain healthy development
services. No audible speaker, microphone, simulator execution or physical robot
proof. #24/#32/#35 and default target/voice closure remain open.

## Resume commands and transfer

Use `git status` before updating; preserve other work. On another machine, fast-forward
main, read the checkpoint and selected Issue, install the pinned test environment
from CONTRIBUTING, and transfer R/live corpus/debug bundle separately for exact replay.
Generated runtime environments must be recreated through their existing profile
owner; do not edit `.env.runtime` or reuse a stale identity on another machine.

A private transfer package is retained at
`/home/chromie/Downloads/chromie_issue52_audit_evidence_20260912.tar.gz`, with a
companion `.sha256` file. It includes R (excluding publication drafts) and the
existing single debug bundle; packaging does not collect another live bundle.
`retained-live-scenarios/` preserves the exact discovered corpus. No generated runtime
environment file was added separately; recreate environments through the profile owner.

```bash
git status --short --branch
git pull --ff-only origin main
gh issue view 52
python -m pytest -q tests/test_planner_staged_progress.py
./scripts/run_tests.sh
python -m mypy --config-file mypy.ini shared/chromie_contracts
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

For a new fixed-source offline iteration, choose unused output directories. Run and
review the full Fast cohort before Deep; preserve the original target identities:

```bash
python -m benchmarks.datasets.fast_planner_daily_life.qualification prepare --label issue52-next --output-dir .chromie/acceptance/issue52-next-fast
python -m benchmarks.datasets.fast_planner_daily_life.qualification run --output-dir .chromie/acceptance/issue52-next-fast --concurrency 8 --timeout-s 600
python -m benchmarks.datasets.fast_planner_daily_life.qualification adjudicate --output-dir .chromie/acceptance/issue52-next-fast
python -m benchmarks.datasets.fast_planner_daily_life.deep_qualification prepare --label issue52-next --output-dir .chromie/acceptance/issue52-next-deep
python -m benchmarks.datasets.fast_planner_daily_life.deep_qualification run --output-dir .chromie/acceptance/issue52-next-deep --concurrency 4 --timeout-s 600
python -m benchmarks.datasets.fast_planner_daily_life.deep_qualification adjudicate --output-dir .chromie/acceptance/issue52-next-deep
```

Future live work starts from the retained GI diagnosis. Restart the existing
Soridormi launcher with `--backend mujoco --profile open_duck_forward --no-viewer`
and its existing MCP service, verify exclusive Host idle, rebuild/verify changed
Agent source and capture a fresh identity before one complete cohort. Use
`live-before/cohort-command.json` and `run-live-before.py` as reviewed references
with a **new** evidence directory; inspect their private path dependencies first.
Never mutate/rebuild between cases or substitute an isolated case for aggregate
qualification. Collect exactly one debug bundle at completion/hard stop and review
all cases, including mechanical passes. Physical voice proof remains supervised.

## Prior delivery and historical evidence

The [complete previous handoff at f5522f87](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md)
retains every preceding #49–#51 workflow, all earlier provider iterations and exact
historical evidence/commands. The [previous checkpoint](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/DEVELOPMENT_CHECKPOINT.md)
retains their stable resume decisions. #51's complete delivery starts at that
handoff's first section; historical provider diagnostics start at line 4000.
Those records remain in Git history under existing documentation governance; they
are not current deployment instructions. No new history document, numeric cap,
configuration switch or architecture owner is introduced by this consolidation.
