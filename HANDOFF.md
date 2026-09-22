# Chromie Handoff

Updated 2026-09-23. Audience: the owner and next development session. This file owns
volatile identities, evidence paths and resume commands. [Checkpoint](DEVELOPMENT_CHECKPOINT.md)
owns priorities; [Status](docs/STATUS.md) owns claim limits. This is the owner-requested
delivery handoff; resume from the latest `main` commit containing this file.

## Checkout and runtime

- Chromie `/home/chromie/github/chromie`, `main`, remote
  `https://github.com/TimeTreker/chromie.git`; HEAD/fetched origin before editing
  `542aefd08d4ca017e5ae11815dbf39ee8e2bae36`, 0 ahead/behind. This delivery includes all repairs/tests/request-artifact
  migrations and the all-case diagnostic runner. No remote Issue was created.
  The new delivery hash is intentionally not self-embedded; use the latest commit
  containing both handoff owners.
- Live launcher Python: `/home/chromie/miniconda3/envs/Chromie/bin/python` (3.12).
  Final canonical/replay/Level A commands used `/home/chromie/miniconda3/bin/python`
  (3.13.13); both are local test runtimes, not model changes.
- Fixed RTX4090 Laptop / SGLang `chromie-qwen35-4b`, host
  `http://127.0.0.1:30000/v1`. This does not requalify RTX5090/Gemma.
- Generated profile `.chromie/voice-runtime/orchestrator.env`, maintained
  `scripts/start_voice_mujoco.sh`. Never edit `.env.runtime` directly. Containers
  use service names; host tools use loopback.
- Soridormi `/home/chromie/github/soridormi`, branch `codex/turn-count`, revision
  `013f46d19ec5101c4392532ab848e0b0819c2a50`. Existing untracked
  Open_Duck_Playground preserved; no source changes.
- Agent package and host both hash
  `a88ffaeb7781a3753d134cc9534d73a1fc61ac653d30d1511c3594ac6eff9487`.
  Rebuilt after each retained production fix with resolved service configuration
  preserved. LLM/model/profile configuration unchanged throughout live cohorts. The latest
  all75 run caused one automatic LLM restart; stable-service qualification fails.
- Final Agent/LLM/TTS healthy; ASR off. Existing TTS cached model and supported
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` options remain from earlier startup.
  No audible playback claim. Task-owned simulator/MCP stopped after standing,
  safe-idle, empty active tasks/lanes proof. Launcher “stopped unexpectedly” text
  followed our explicit shutdown signal, not a cohort crash.

Latest all75 live identity: `b15ae287f34f78201ac51380d985290b06f1eecae801cd5a1c10eaf367c29d1c`.
Later fixture/doc changes alter repository identity, but not deployed Agent source.
Capture a new identity for future runs; never reuse it after source/service changes.

## Latest all75 diagnostic and six-loop resume

`R=.chromie/acceptance/all75-20260923/`. Raw evidence is private/ignored and is
**not in Git or available automatically on another machine**. The committed facts
below are sufficient to reproduce the originating scenarios; transfer raw evidence
separately only with an appropriate private channel. No raw logs/payloads are pushed.

- `live/summary.json`: all75 attempted, 1 passed/74 failed, **1.33%**; zero skipped
  independent cases. Case 5 `walk_then_turn_right` passes. Dependent turns blocked by
  failed prerequisites remain unrun; `cohort_complete` and qualification are false.
- Cases 1–22: meaning/action/concurrency, contract and oracle failures. Case 23
  `contextless_turn_it_up` (SID `c16f6814`, input “调大一点。”) crashes the model
  service during Fast grammar compilation. Cases 24–75 (52) fail availability,
  not measured semantic inference. No source edits/manual restarts between cases.
- Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260923_063530.tar.gz`.
  `native-calls.json` retains 120 call records, including failed requests;
  `llm-crash.log` retains SIGSEGV and `docker inspect` reports no OOM, restart count 1.
- `harness-red.log` → `harness-green.log`: six failing-before regressions, **80 passed**
  after. `canonical.log`: **145 benchmark; 3,795 main/1,092 subtests; 20 legacy pass**,
  plus repository policy, test ownership, Ruff/mypy, configuration/docs; two warnings.
- `crashing-schema.json` / `llmcall_agent_14a9d86fc5a2433b.json`: exact Fast wire
  request, valid 143,403-byte schema without empty enums. UMI call
  `llmcall_user_meaning_interpreter_fe37ff50a467406f`, GA call
  `llmcall_agent_b952fc2b12824b76` precede it.

Actual failure workflow:

| Owner/boundary | Material input → observed output; expected output | Verdict/handoff |
| --- | --- | --- |
| Text Host → UMI | Contextless adjustment admitted under fresh simulator preflight; UMI returns meaning DTO | Admission correct; semantic adequacy still reviewed separately; SID above |
| GA → Fast | Accepted interpretation/Goal context produces the retained Fast schema/request | Request reaches provider; no invented Host repair |
| SGLang/XGrammar | Exact schema + actual Qwen BPE vocabulary → native lookahead compilation SIGSEGV | First confirmed service boundary failure; expected compiled grammar or handled error, not process death |
| Agent → Host | Disconnected model HTTP stream → closed failure/no authorized Work | Containment correct; no model output to adjudicate |
| Diagnostic runner | Failed independent case → next case's fresh preflight/admission | Continues all75; subsequent unavailable-service failures retained rather than skipped/pass |

The user authorized **up to six new repair loops**, then requested immediate
commit/push for relocation. **Zero new repair loops completed.** Compiler diagnosis
is loop 1 in progress; no compiler upgrade, prompt change or oracle repair promoted.
Runtime remains SGLang **0.5.19 / XGrammar 0.2.1**, fixed Qwen3.5-4B AWQ.

Resume at these exact boundaries:

1. Reproduce `contextless_turn_it_up` after a fresh identity/healthy service. Native
   CPU subprocess reproducer `reproduce_grammar.py` compiles the retained schema
   with the actual cached Qwen tokenizer, threads 1 or 8 and 512 MiB cache; both
   segfault. A byte-only vocabulary passes. This excludes GPU/OOM/concurrency as
   necessary triggers, not every possible contributing condition.
2. Normalized EBNF roundtrip passes the original request but aborts another retained
   grammar; `rejected-roundtrip.Dockerfile` is private/reverted. Versions 0.2.2,
   0.2.3 and 0.2.4 still crash; 0.2.6/0.2.7 pass the original. SGLang pins 0.2.1,
   so upgrading requires explicit compatibility proof, not an unqualified install.
   0.2.6 rejects 24 GA wire schemas containing empty enums (99 occurrences).
   Private equivalent-false-schema diagnostic compiles all120 retained requests
   (`grammar-wire026-false-enums.log`), but no equivalence/decoding/live qualification
   or production change exists. Installed candidate packages live only in isolated
   `/tmp/chromie_xgrammar*` container directories, never on the serving import path.
3. Then repair the confirmed oracle bug in `scripts/interaction_text_mujoco_check.py`
   `validate_contract`: cases 15 `thanks_after_completed_blink`, 18
   `multi_goal_look_then_blink`, 20 `nod_then_shake_head` omit optional count in model
   args, but matching retained Capability contracts declare default 2. The precheck
   reads `None`, blocks execution and scores failure. Reuse version/request-bound
   default realization already in `scripts/outcome_observations.py`; preserve explicit
   values and reject missing/mismatched contracts or required-field omissions. No
   outcome was retroactively changed to pass.
4. Each accepted minimal repair needs focused proof and an immutable all75 rerun,
   one debug bundle afterward and review of every case. Do not repeat rejected
   prompt candidates from the prior18 batch or substitute another model. Keep
   the six-loop limit and distinguish diagnosis from completed repair/rerun loops.

## Earlier retained private evidence

`R=.chromie/acceptance/iterate18-20260922/` (date remains the batch start date).
Raw payloads and service snapshots are private ignored evidence, absent in a fresh
clone. Review privacy before publication. The owner's 18-iteration batch is complete.

| Under R | Evidence and limit |
| --- | --- |
| `REPORT.md`, `iterations.json` | Eighteen iteration outcomes; actual module I/O, confirmed fixes, open semantics, authority/evidence limits. |
| `starting.patch` | Prior dirty work preserved before this batch; hash in iteration ledger. |
| `design.json`, `cases/`, `01_*` through `08_*`, `10_ordered_source_schema/` | Frozen nine-case bilingual/reference/quotation/timing UMI screens. Best 7/9; no prompt promoted. |
| `fast-design.json`, `fast_extended/`, `11_*` through `18_*` | Seven valid Fast meaning controls plus one upstream-defect control; exact requests/raw streams. All candidate cohorts fail. |
| `screen-reviews.json` | Per-case post-hoc review, request/schema/output hashes, timing/options and primary-only evidence limits. Iteration 15 lookup continuation is unproven; private Work DTO errors are not production errors. |
| `09-token-projection-red.log`, `09-token-projection-green.log` | Four failing-before bilingual primary/deep omissions; 45 tests/28 subtests after, including fail-before-HTTP budget proof. |
| `10-schema-red.log`, `10-schema-green.log`, `10-native-decoder.log` | Fifteen backward-pair failures before; 192 tests/118 subtests after; installed XGrammar ordered/reversed proof. |
| `schema-migration.json`, `replay-capture/`, `replay-focused.log` | Only UMI source schema changed in five seeds/23 shared artifacts/6,000 refs; zero response/oracle changes; 104 focused tests pass. |
| `replay6000/summary.json`, `replay6000.log` | 6,000 expected outcomes, immutable source, zero native calls. |
| `canonical.log`, `docs-final.log`, `level-a/` | 145 benchmark +3,789 main/1,092 subtests +20 legacy pass; policy/static/docs pass; 45 Level A pass. |
| `baseline/`, `09-live/`, `10-live/` | Full75 discovered each: 0/4 then 0/3 then 0/3; hard stops, 71/72/72 unrun. Identities, review, native calls and bundle paths. |
| `final-provider-status.json`, `final-agent-source.json`, `final-services.txt` | Final safe idle, source equality and remaining services. |

One debug bundle per live invocation under `/home/chromie/Downloads/`:

- `chromie_debug_bundle_20260922_234939.tar.gz`: baseline, stops on walking+singing.
- `chromie_debug_bundle_20260923_000503.tar.gz`: complete-token projection fix.
- `chromie_debug_bundle_20260923_001052.tar.gz`: ordered-source decoder/current production.

Latest SIDs: compound `5e9ad597`, simultaneous `286d246d`, milk `e6a7dc3d`.
Fast calls respectively `llmcall_agent_60708faba089408e`,
`llmcall_agent_8479d7b564b94449`, `llmcall_agent_2a8788c797d84a50`;
milk UMI `llmcall_user_meaning_interpreter_52b7fda1cf334eed`.
Native call retention counts: baseline16, after-fix9 11, after-fix10 11.

Prior repairs and their evidence remain at
`.chromie/acceptance/full-repair-20260922/REPORT.md`: required-SC freshness,
Activation scope/social context, prior UMI system-paragraph replay migration and test
oracle corrections. Earlier rejected experiments remain under `meaning-first-20260922`,
`activity-timing-20260922`, `umi-source-wording-20260922` and related acceptance roots.
Do not reclassify historical/isolated improvements as qualification.

## Resume commands and stopping rules

No semantic candidate was promoted. Resume the authorized six-loop batch above,
starting with service integrity and the confirmed oracle boundary. Current native
qualification and supervised voice/default target closure remain open. On another
machine, fetch/pull `main`, read Checkpoint/Handoff, regenerate the owned runtime
profile for that machine and verify the declared model is available; do not copy
`.env.runtime` blindly or claim laptop evidence for a different target.

For focused changes and canonical validation, preserve work and verify fresh upstream:

```bash
cd /home/chromie/github/chromie
export PATH=/home/chromie/miniconda3/bin:$PATH
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir NEW_EVIDENCE_DIRECTORY
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir NEW_LEVEL_A_DIRECTORY
```

For a new live aggregate, rebuild/verify Agent after product changes, start
`./scripts/start_soridormi_mujoco.sh --no-viewer` from Soridormi in a separate terminal,
and wait for health/safe idle. Then from Chromie's root:

```bash
set -e
export PATH=/home/chromie/miniconda3/envs/Chromie/bin:$PATH
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
run_dir=$(mktemp -d "$PWD/.chromie/acceptance/full-resume.XXXXXX")
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty \
  --service chromie-agent --service chromie-llm --service chromie-tts \
  --output "$run_dir/runtime-identity.json"
live_rc=0
python scripts/general_ability_acceptance.py --mode live-text --keep-going --assertion-scope full \
  --runtime-identity "$run_dir/runtime-identity.json" --evidence-dir "$run_dir/live" \
  --soridormi-repo /home/chromie/github/soridormi --execute || live_rc=$?
./scripts/collect_debug_bundle.sh
printf 'Live runner exit: %s\n' "$live_rc"
```

Discover all75, no source/scenario/service edits between cases. The owner-requested
`--keep-going` diagnostic retains every failure and attempts every independent case
under its existing safety guards. It never authorizes unsafe dispatch or emergency
reset. Retain one bundle afterward; judge every attempted case, mark blocked dependent
turns and unavailable inference unknown. Focused screens cannot close the aggregate.
Preserve safe idle before stopping owned services. Text/simulator/PCM is not physical
voice/robot proof. For later delivery, refresh upstream and update both handoff owners.
