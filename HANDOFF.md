# Chromie Latest Handoff

## Current delivery — native GI boundary investigation, 2026-09-12

Repository `/home/chromie/github/chromie`, branch `main`, investigation/pre-delivery
base `2b9910e7659b2bf3a0df9f7251db6dec62e7ec2f`. Production behavior remains implementation
`8aa3f499151e4d25e8aed3fec74dec486f12b9cd`. Python: `/home/chromie/miniconda3/bin/python`.
Resume from the latest main commit containing this file and
[DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md). The owner authorized repairs,
principle decisions, commit/push and closure of solved Issues, then agreed to the
focused GI investigation. #35 and #49–#58 remain closed; only #24/#32 are open.

This delivery records evidence only. No production prompt, Schema, source code,
configuration or model profile changed. No principle was amended. There are still
102 tracked Markdown documents and a 15-document core path; no new document owner,
runtime flag, compatibility path or semantic authority. The
[audit report](ARCHITECTURE_AUDIT.md#native-goal-interpretation-boundary-investigation--24)
owns the full episode/module I/O and experiment comparison.

## Actual workflow and conclusion

Complete admitted walk/nod/turn text and tokens `t0`–`t19` reach the GI packet.
The current primary prompt requires independent WHATs, exact binding ownership and
sequence; a correct three-effect reference passes its dynamic Schema and Host.
Native primary output nevertheless merges effects into one responsibility. In the
original live episode, copying the entire turn into `subtype` triggers Host rejection
and HTTP 503, with no GA/Planner/Runtime invocation. In the fresh unchanged direct-role
baseline, copying only the later nod/turn clauses passes the mechanical guard. Missing
count and sequence remain incorrect. No diagnostic output reaches downstream modules.

The first observed wrong boundary is the raw primary GI meaning. Parser/normalization
cannot restore omitted effects; Host acceptance does not prove semantic completeness.
The compound result declares no material uncertainty, so designated deep cognition is
not invoked. Other cases use the existing source-based deep branch once when required.
Confidence alone is not that branch's authority. Do not add a semantic splitter,
second reviewer, phrase router or confidence-threshold workaround.

No tested candidate qualifies. Attribution among remaining prompt/context
representation, model and native provider behavior is unresolved; no model intelligence
ceiling is established. The controls narrow the next investigation, not the acceptance
contract. #24 remains open; #32 still requires native typed-stream, terminal consistency,
cancellation, accepted-presentation/TTS latency and shared-resource proof.

## Frozen native evidence

R = `.chromie/acceptance/issue24-gi-boundary-20260912/`, private and ignored. Every batch
freezes packets/corpus/source/model identity before inference. All original 44 reference
outputs pass Schema/Host; all 88 original primary/deep packets match historical Qwen4b
packets. Source and model tags remain stable in each batch. Inference calls the real
`OllamaGoalInterpreter.interpret_goal` through native HTTP, completion checks, parser,
normalization, DTO and Host. Predeclared packet deltas are applied at the actual call
boundary. One primary plus at most one source-based deep call; no retries or critics.
All raw outputs were reviewed after inference; review is non-independent.

| Directory / isolated control | Cases / calls | Final Host decisions | Strict dimensions |
| --- | --- | --- | --- |
| `baseline/`: unchanged production transaction | 44 / 66 | 43 | 5 |
| `schema-shape/`: append derived Schema structure; actual full Schema unchanged | 44 / 44 | 44 | 2 |
| `presence-zero/`: baseline except presence penalty 0 | 44 / 47 | 43 | 5 |
| `json-control/`: schema-shape messages, plain-JSON decoding, original full adjudication | 44 / 44 | 0 | 0 |
| `instruct-control/`: presence-zero except installed Qwen3 Instruct model | 44 / 44 | 43 | 0 |
| `cold-control/`: six baseline cases, absent model before each call, keep-alive 0 | 6 / 9 | 6 | 0 |

Total: 226 case executions/254 calls over 44 unique scenarios. Every response finishes
normally with top-level `think:false`; no separate thinking field. Original Schema:
210 call passes, 44 plain-JSON failures (missing per-responsibility confidence). Strict
counts are not semantic pass rates: wording/span limitations and extra-binding gaps
in the old oracle are separately reviewed. Every candidate retains concrete hard
meaning failures. Instruct separates the three actions but loses sequence and labels
speed as distance; cold loading still merges effects and confuses query mode.

`comparison-summary.json`, per-mode `semantic-review.json`, `frozen.json`, `summary.json`,
`packets/`, case JSONs and `residency.jsonl` retain actual results. Executed driver copies
are `run-<mode>-frozen.py`. Every raw response is kept separately from accepted DTOs.
Full continuity/lifecycle, other semantic roles, native streaming and concurrent TTS
are outside this diagnostic cohort. There is no fresh live aggregate or audio proof.

Actual baseline: Ollama **0.33.2**, Qwen3.5:4b digest
`2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.
Instruct tag `qwen3:4b-instruct-2507-q4_K_M`, digest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
Request: `stream:false`, `think:false`, temperature 0, top-p 0.9, **num_ctx16384**,
num_predict 512, keep_alive 24h except cold control. Inherited baseline presence
penalty 1.5/top-k 20 are retained in `provider-show.json`; the neutral control explicitly
sends presence 0. Native sampler logs show repeat penalty 1/frequency penalty 0. The
historical environment's 32k label is not the actual GI request context. Original live
failure stops normally at 212 output tokens, not truncation.

Sampled peak GPU 9,029 MiB, minimum free 6,917 MiB, at most one resident model. Sampling
may miss brief peaks; TTS was healthy but not concurrently exercised. Endpoint timing
is not streaming TTFT or proven cache benefit. All nine cold calls verify target model
absence before inference, with 2.55–4.60s load durations. The original Qwen3.5:4b was
preloaded again with 24h keep-alive; that empty preload uses provider-default 32k context,
not a new GI setting. `final-development-state.json` records the restored resident.

Retain these diagnostic limitations and corrections:

- Full Schema append was rejected by preflight before inference. The initial 4
  chars/token exploratory estimate was corrected to the actual 2; all 88 such projected
  packets exceed that conservative bound. Only the derived structural outline ran.
- Inherited `frozen.json` model/hypothesis labels are stale for later controls; actual
  request/response model fields and the pre-inference named design files are authority.
  Cold's inherited 88-packet label means 12 actually compared packets. No raw manifest
  is rewritten; `metadata-corrections.json` explicitly records each discrepancy.
- Original summaries' Pending labels predate the completed per-mode semantic reviews.
  Empty since-filter provider logs are retained; only `provider-runner-tail.log`
  supports sampling-setting inspection. Its older calls are not cohort call counts.
- Plain-JSON control preserves the structure experiment's exact messages, including
  its decoder-description text, to isolate format. It is deliberately diagnostic and
  never a production proposal to weaken constraints. No reference answer is exposed.

Fresh canonical `canonical.log`: 3,105 tests/794 subtests, 145 benchmarks, 20 legacy tests;
pinned static/config/policy/ownership gates pass, two existing FastAPI warnings.
`canonical-completion.json` records the final gated log marker and hash; the separate
shell exit status was not retained after tool-context truncation. Post-documentation
checks/publication records live in `R/publication/`, outside the immutable archive.
Prior Level A 45/15 and 294 offline Planner cases are unchanged historical evidence.

## Last live identity and development services

No deployment rebuild/restart, new live cohort, extra debug bundle or physical action
occurred during this investigation. Last 113-file deployed source match and failed
51-case live cohort remain bound to:

- runtime `ccb85b7e47fd86467f143fa6c7cbc4f2cd596494724659c779ccf4ba985c9470`;
- dirty source SHA256 `b0af916d102ddcd5fa14383bb0ccc7a252132b2376a5eaf8e3ae71105da1a6ea`;
- call `llmcall_goal_interpreter_d2278e1d3bfa4a1b`, session `6df0558e`;
- raw response SHA256 `dd300bc80a67ea0064a99d3b0b685134d0ad86c0f1513c46f63503451d63bf91`;
- result: 1 failed, 1 next startup interrupted, 49 unrun; all 51 slots reviewed;
- exactly one bundle `/home/chromie/Downloads/chromie_debug_bundle_20260912_193424.tar.gz`.

This precedes final documentation/commit and is not a clean-revision release claim.
Agent/TTS/LLM remain healthy development services; ASR absent. Owned simulator/MCP stay
stopped after the previous safe_idle=true,standing=true/no active task/fall/emergency
check. Soridormi `/home/chromie/github/soridormi`, branch `codex/turn-count`, revision
`284273bc`; preserve pre-existing untracked `workspace/Open_Duck_Playground`.
No physical microphone, audible speaker, simulator capability execution or robot proof.

## Transfer and next commands

New private archive `/home/chromie/Downloads/chromie_issue24_gi_boundary_20260912.tar.gz`:
10,322,848 bytes, SHA256
`14e2b27523f92e4438a93f273f78cade42008a048530a414fd792945da7a4dc2`.
The archive has 603 files; all 602 payload files were verified against retained hashes
(the manifest excludes itself from self-hashing). Contains R before publication metadata, the original 44-case
complete-Mind corpus, original Qwen4b packet directory and copies of the last live
GI call/source verification at their original repository-relative paths. Restore the
`.chromie/` tree in a matching checkout; adapt machine-local paths. Never publish raw
Mind, complete prompts or unrestricted provider payloads to GitHub.

Previous full repair/live archive remains
`/home/chromie/Downloads/chromie_remaining_issues_evidence_20260912.tar.gz`, 48,344,022 bytes,
SHA256 `604b801d6331c0356c0541d47bc0fb37eca91793454bda7d75e58e724c3ecd78`.
It contains the complete live driver/scenarios and debug bundles. New archive adds the
native investigation and is not a substitute for that full live package. Private #51
artifacts from the other machine remain absent here.

On another machine inspect local changes before fast-forwarding. Do not overwrite
retained outputs; copy a frozen driver into an unused evidence directory and correct
its experiment metadata before freezing a new hypothesis. `run.py` compares rendered
packets to the retained historical baseline and fails on drift; a source repair needs
a new reviewed freeze, not deletion of that check. It is a private diagnostic driver,
not a maintained qualification CLI. Keep the 44 regressions and add independent cases
for the chosen hypothesis and missing continuity/lifecycle scope before qualification.

```bash
git status --short --branch
git pull --ff-only origin main
gh issue view 24
gh issue view 32
sha256sum /home/chromie/Downloads/chromie_issue24_gi_boundary_20260912.tar.gz
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

Before new live claims rebuild/verify source and capture a new identity. Use the
existing generated `.chromie/acceptance/laptop-iterations-20260910/orchestrator.env`
and `.chromie/voice-runtime/compose.voice-mujoco.yaml`; do not reuse stale
`.chromie/voice-runtime/orchestrator.env` or edit generated `.env.runtime`. Launch
Soridormi with `--backend mujoco --profile open_duck_forward --no-viewer` and the existing
MCP service, verify idle, and use the previous archive's `live-final/cohort-command.json`
and `run-live-final.py` as references with a new output directory. Run the full discovered
cohort without between-case edits/restarts/substitution; exactly one bundle at completion
or hard stop, then review every case. Supervised voice/default target closure and native
streaming qualification remain mandatory. No follow-up is scheduled.

The [preceding handoff](https://github.com/TimeTreker/chromie/blob/2b9910e7659b2bf3a0df9f7251db6dec62e7ec2f/HANDOFF.md)
and [checkpoint](https://github.com/TimeTreker/chromie/blob/2b9910e7659b2bf3a0df9f7251db6dec62e7ec2f/DEVELOPMENT_CHECKPOINT.md)
retain all prior implemented workflows, failed attempts, exact offline evidence,
CI and Issue closure. Historical narrative stays in Git rather than a new document.
