# Chromie Handoff

Updated 2026-09-22. Audience: the owner and next development session. This file owns
volatile machine identity, evidence locations and resume commands. Read the current
[Checkpoint](DEVELOPMENT_CHECKPOINT.md) for priorities and [Status](docs/STATUS.md) for
claim boundaries. Historical delivery snapshots remain in Git; they are not commands
to rerun old cohorts. The owner has authorized this development commit and push.

## Checkout and runtime

- Chromie: `/home/chromie/github/chromie`, `main`, remote
  `https://github.com/TimeTreker/chromie.git`. HEAD/fetched origin before editing:
  `4a1606fd0fc546601b38e664a5428c6a79ad489b`, 0 ahead/behind after the delivery fetch.
  Expected resume revision: latest `main` commit containing this handoff and checkpoint.
  Current delivery adds receipt-interval overlap assertions and strengthens the existing
  simultaneous gaze/blink scenario; prior production repairs remain unchanged.
  Raw private evidence remains local; no passing semantic qualification is claimed.
- Python: `/home/chromie/miniconda3/envs/Chromie/bin/python`.
- RTX4090 Laptop, SGLang `chromie-qwen35-4b`; host inference endpoint
  `http://127.0.0.1:30000/v1`. Keep the configured model fixed for these contrasts.
  This is not the previous RTX5090/Gemma qualification profile.
- Generated profile: `.chromie/voice-runtime/orchestrator.env`; use the maintained
  voice_mujoco Compose wrapper. Never edit `.env.runtime` directly. Containers use
  service names, host tools use loopback endpoints.
- Soridormi: `/home/chromie/github/soridormi`, branch `codex/turn-count`, revision
  `013f46d19ec5101c4392532ab848e0b0819c2a50`. Its pre-existing dirty
  Open_Duck_Playground submodule was preserved. No Soridormi source edit in this work.
- Final rebuilt Agent digest matches checkout:
  `856fd9bf2caaee2fc64684bd27031adef00950a711a06718993886aa5b59163a`.
  Source patches/identities are retained before handoff-only edits.
- SGLang image `chromie-sglang:qwen35-4b-awq` rebuilt with bounded compiler grammar
  retention (512 MiB) and no duplicate backend retention. Model/profile unchanged.
- The owner restarted services during source-first UMI diagnostics, causing SIGTERM,
  then authorized stopping those instances. User-started simulator and LLM instance
  were stopped; LLM restarted in the same configuration and is healthy after controlled
  diagnostics. No service interruption occurred during the completed new screens.
  Agent remains running. TTS/ASR and simulator/MCP are not currently started by this task.
  Verify health and capture a new identity before any future live invocation.

Previous four-case runtime identity (not the restarted service identity):
`ad2f6e7868d249845e795f805535b8e6b2abcc49facd672386886754ccf706db`.
Earlier purpose-only identity:
`c2933ecd0c31c4967cfa7859391fcf8578c959efeb8abdcc9774f7c89684d7a2`.
Neither closes complete semantic qualification.

## Available private evidence

Newest root: `.chromie/acceptance/temporal-observation-20260922/` contains REVIEW.md,
red/green tests, `final-tests.log` (90 passed /20 subtests), `retained-cohort-regrade.json`,
Level A and policy/static checks. `scenarios/` is a new frozen four-case snapshot with
only the simultaneous oracle strengthened. Original live artifacts are unmodified;
regrade is mechanical 1/4, not a new live run or semantic repair.

`.chromie/acceptance/meaning-first-20260922/` retains nine-case baseline and rejected
meaning-first output-order candidate; source-first is incomplete because the owner
stopped the inference service during that batch. Bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260922_223021.tar.gz`.
Service logs show SIGTERM, Docker stop then SIGKILL; no OOM evidence. This interruption
must not be counted as a cache-repair regression. `.chromie/acceptance/activity-timing-20260922/`
retains unchanged four-packet baseline, rejected local wording candidate and Host
adjudication (simultaneous becomes invalid singleton parallel timing). Subsequent complete
screens also reject UMI `demonstration` (nine cases; wrong addressee frame/added HOW/language)
and Fast `timing_first` (four cases; still sequential/sidestep, invalid acquisition walk).
Each root retains raw packets, results and separate adjudication; no production change.

Oracle workflow: retained UMI while meaning → Fast sequential activities → sequential
provider receipts → observation projection formerly dropped intervals → case falsely
passed. Only the last two evidence boundaries change: preserve correlated timestamps
and require actual overlap. Fast semantic authorship/scheduling remain unchanged.

Paths below are local ignored evidence, absent from a fresh Git clone.
`R=.chromie/acceptance/planner-purpose-root-cause-20260922` is the previous production-repair root.

| Artifact under R | What it establishes |
| --- | --- |
| `REVIEW.md`, `adjudication.json`, `repair.patch`, `cumulative-source.patch` | Actual module I/O, before/after mechanics, every attempted live case's semantic verdict, remaining UMI/Fast/SC gaps and exact evaluated changes. |
| `purpose-red.log`, `span-red.log`, `shared-span-tests.log` | Failing-before provider-purpose and reversed-span regressions; final 376 tests +143 subtests pass. |
| `span-decoder-probe.json`, `span-decoder-verdict.log` | Actual installed XGrammar rejects original reversed output and accepts ordered structural probe. Preparation-error files retain an initial null-output harness mistake. |
| `cases/`, `baseline/`, `candidate/`, `contract/`, `final_cases/`, `final/`, `host-adjudication.json` | Four frozen exact native packets, isolated prompt/schema changes, final real inference, Schema/DTO/purpose checks and full Host admission. Final Host 3/4; semantic requested Work 1/4. |
| `unconstrained/`, `activity_order/`, `catalog_order/` | Rejected diagnostic variants: malformed unconstrained output; ID order ineffective; catalog order fixes compound but breaks acquisition. Not production candidates. |
| `live/`, `native-calls.json`, `runtime-identity.json`, `memory-pressure.json` | Purpose-only four-case cohort, mechanical 2/4; last milk times out at 23.44 GiB. All safe idle; no source edits between cases. |
| `llm-build-final.log`, `llm-up.log` | Successful pinned-image build and real backend 64-schema self-test. Earlier `llm-build.log` contains rejected tokenizer fixture, not a successful build. |
| `final-live/`, `final-native-calls.json`, `final-runtime-identity.json`, `final-agent-source.json` | All four attempted, mechanical 2/4, requested Work semantic 1/4. Compound wrong effect, sequential pass, simultaneous false completeness, milk source rejection. All safe idle. |
| `final-memory-before.json`, `final-memory-after.json` | 12.31 →12.05 GiB across final bounded live cohort; no service timeout/disconnect. Not a memory soak or total-memory bound. |
| `level-a/`, `final-policy.log`, `final-ownership.log`, `final-ruff.log`, `final-mypy.log`, `final-docs.log` | Composable Level A 5/5 and final narrow mechanical checks. Full suite remains deferred. |

One bundle per invocation under `/home/chromie/Downloads/`:

- Purpose-only: `chromie_debug_bundle_20260922_220312.tar.gz`.
- Final source/image: `chromie_debug_bundle_20260922_221519.tar.gz`.

Current final case correlations: compound `8cec7b59`, sequential `28429ba9`, simultaneous
`708b6dc7`, milk `f19f15c7`. Exact calls include SC using its own request identity; filter
by SID anywhere in the raw packet, not only top-level correlation fields.

Previous roots remain retained:

- `.chromie/acceptance/planner-gap-schema-20260922/`: clarification/lookup-wrapper
  repairs; bundles 211846, 212306 (OOM), 212439 (reverse span), 212641 (purpose).
  Its REVIEW, native calls and pre-consolidation snapshots remain historical evidence.
- `.chromie/acceptance/sc-context-refresh-20260922/`: Host continuity repair and the
  exact four frozen scenarios reused here. SC tests 158 pass; broader 248 pass/1
  pre-existing failure/17 subtests; truthful speech Level A 6/6. Bundle 205334.
- `.chromie/acceptance/umi-source-wording-20260922/`: new six-case UMI experiment,
  baseline/candidate, complete raw calls and per-case adjudication. Rejected: only
  2/6 full semantic/source passes despite 6/6 mechanical. Production prompt unchanged.
- `.chromie/acceptance/umi-perspective-20260922/`, `planner-order-20260922/` and
  `resume-bounded-20260922/`: preceding rejected wording/order candidates and audit.

Earlier Gemma private evidence and original broad replay raw audit remain absent here.
Historical counts do not qualify this source/model. Private prompts may contain user
content; review before publication.

## Resume commands and stopping rules

Owner scope remains a few common cases; no full tests/replay/cohort or latency work.
The existing SC/Runtime unit failure remains explicitly open. Focused deterministic checks:

```bash
cd /home/chromie/github/chromie
export PATH=/home/chromie/miniconda3/envs/Chromie/bin:$PATH
python -m pytest -q tests/test_outcome_observations.py tests/test_general_ability_acceptance.py
# Previous production repairs: tests/test_fast_planner_streaming_commit.py,
# tests/test_fast_planner_pr3.py, tests/test_sglang_runtime_integration.py,
# tests/test_user_meaning_interpreter_llm_prompt.py, tests/test_intent_only_handoff.py
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/run_ruff.py
python scripts/run_mypy.py
python scripts/check_docs.py
```

For a justified new live candidate, first fetch/verify upstream, inspect dirty work,
and rebuild Agent if its source changed. Start the maintained Soridormi launcher
`./scripts/start_soridormi_mujoco.sh --no-viewer` from its repository in a separate
terminal; wait for service health before admission. In Chromie's root:

```bash
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
run_dir=$(mktemp -d "$PWD/.chromie/acceptance/bounded-resume.XXXXXX")
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty --output "$run_dir/runtime-identity.json"
python scripts/general_ability_acceptance.py --mode live-text \
  --scenario-root .chromie/acceptance/temporal-observation-20260922/scenarios \
  --runtime-identity "$run_dir/runtime-identity.json" --evidence-dir "$run_dir/live" \
  --soridormi-repo /home/chromie/github/soridormi --execute
./scripts/collect_debug_bundle.sh
```

Keep source/service identity fixed within each aggregate. Stop on hard integrity or
safe-idle failure; collect exactly one bundle after that stopped/complete invocation,
judge every attempted case including mechanical passes, and retain unrun cases as gaps.
A focused case after aggregate diagnosis does not close the aggregate. Do not reuse an
old runtime identity after changes. Preserve safe-idle evidence before stopping the
owned simulator. Physical microphone/speaker/robot proof remains supervised and open.

Before any later authorized commit/push, refresh upstream and update both handoff files
in that same commit. Keep #24/#32 open; no release/default-target closure is claimed.
