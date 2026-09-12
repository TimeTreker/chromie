# Chromie Latest Handoff

## Current delivery — offline workflow replay, 2026-09-13

Repository `/home/chromie/github/chromie`, `main`, pre-delivery base
`6f726ce32f2d69d6fd167ad600cfb7f9eb599536`. Python `/home/chromie/miniconda3/bin/python`.
Resume from the latest main commit containing this file and
[DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md). The owner authorized this first
small integration replay, explicitly excluding LLM ability, and retains authorization
for repairs, commit/push and solved-Issue closure. #59 is delivered; #24/#32/#60 remain
open. No new current Markdown owner, runtime flag or model profile (102 documents,
15-document core path unchanged).

## Actual change and workflow

`benchmarks/integration/model_replay.py` serves frozen replies at an ephemeral loopback
`/api/chat`. Every actual request must match the next frozen message/context/Schema/
options packet exactly. Only explicitly registered runtime Goal IDs may vary. Unknown,
changed, reordered, extra or unused calls fail closed; there is no model, keyword
router, online fallback or automatic capture in the maintained service.

`tests/workflow_replay_support.py` uses production GI, GA, Fast/Deep clients and their
parsers/validators; actual state, Capability Runtime and result/due re-entry paths run.
Initial admission and role scheduling are supplied explicitly; time/UUIDs, providers
and successful speech receipts are controlled. This is Level A evidence, not a full
Gateway/native-stream/audio/robot pipeline. The standalone runner is
`scripts/run_workflow_replay.py`; five frozen JSON episodes plus manifest live in
`benchmarks/integration/scenarios/`. Current-task author identity was verified as
GPT-6 Astra/xhigh; reference authoring/review is non-independent, not independently
sampled target-model inference or model-ability evaluation.

“Blink twice if rain is forecast in Hangzhou” maps through real GI/GA to a count-2
body Goal. Deep correctly proposes only weather acquisition with both deferred
obligations retained. Before repair, Schema excludes weather for lacking count and
Host count/numeric validation rejects the same prerequisite. After repair, Schema
retains declared acquisition and both guards use the existing complete-acquisition
scope; supplied argument/provenance checks and eventual exact count remain enforced.
Weather result keeps Goal open, then trusted Plan/Evidence re-entry drives Fast to
blink twice on rain or deliver a no-effect reply when dry. Execution/delivery closes
the Goal. Wrong Evidence fails replay matching; wrong/missing effect count fails
before dispatch. Cross-domain composition remains Deep-owned. See the
[audit table](ARCHITECTURE_AUDIT.md#offline-workflow-replay--59) for module I/O and limits.

The timer case starts from an explicit prior scheduled Goal, checks zero early Work,
persistence/restart and once-only due wake through result closure. GI's Schema cannot
emit `ready_at`, while Planner requires that exact Goal binding: new-request scheduling
is separately open #60. Operational stop cancels execution and leaves the original
unmet Goal open. Harness corrections (imports/DTO wiring, preserving absent async
session ID, source-Plan location, cancellation oracle, unique UUID prefixes) are not
product bugs. Final reference review expands the conditional source span t0–t1 to
t0–t7; the full condition/place is now cited. No reference answer is treated as truth
solely because Astra authored it.

## Observed checks and evidence

R = `.chromie/acceptance/workflow-replay-20260913/` (ignored/private):

- `canonical-1.log`: `./scripts/run_tests.sh` exit 0; 3,131 tests/794 subtests,
  145 benchmarks, 20 legacy, pinned static/config/policy/ownership pass; two existing
  FastAPI deprecation warnings. This predates only the final fixture span review.
- `final-run/summary.json`: final freeze 3, 5/5 episodes, 18 local model-shaped replies,
  zero native inference; per-call request/reply/Schema and state, source/corpus hashes.
- `focused-final.log`: 26/26 after final span review. `focused-2.log`: preceding
  143 tests/8 subtests including staged, numeric-binding and readiness regressions.
- `general-ability/`, `general-ability.log`: fresh 45/45 Level A cases across 15 classes.
- `prepare-*.log`, failed JSON captures, `preparation-review.json`: retained original
  failures and distinctions between production defect, harness mistakes and oracle
  review. `driver/` and `delivered-fixtures/` copy the executed helpers/final corpus.
- Post-archive document/publication checks are in `R/publication/`; they do not mutate
  the transfer archive or convert earlier test evidence into new native proof.

Transfer archive `/home/chromie/Downloads/chromie_workflow_replay_20260913.tar.gz`:
2,883,802 bytes; SHA256
`a31606849c791af7cf66ecc18c57a42984e6edc2e546d8ead8c9a52348cf3ba1`.
All 92 payload hashes verified. Restore its repository-relative `.chromie/` tree in
an appropriate checkout. Maintained fixtures/runner need no private archive to run.
Synthetic reviewed case packets may be public; unrestricted native diagnostic payloads
remain private. This archive is additional to the prior native/live packages.

## Resume commands and unchanged live blockers

Inspect local changes before fast-forwarding; never overwrite retained evidence.
Run without Python `-O` and choose a new evidence directory:

```bash
git status --short --branch
git pull --ff-only origin main
gh issue view 24
gh issue view 32
gh issue view 60
python scripts/run_workflow_replay.py --evidence-dir .chromie/acceptance/workflow-replay-new-run
python -m pytest -q tests/test_workflow_replay.py
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

No new deployment/restart, native model call, aggregate live run, debug bundle, audio
or robot action occurred here. Last service state was healthy development Agent/TTS/
LLM, absent ASR and stopped owned simulator/MCP; it was not freshly requalified.
Prior native GI investigation (five 44-case cohorts plus six cold cases) qualified no
repair. The last 51-case live cohort remains 1 failure, 1 startup interrupted and 49
unrun, with exactly one bundle `/home/chromie/Downloads/chromie_debug_bundle_20260912_193424.tar.gz`.
Runtime identity `ccb85b7e47fd86467f143fa6c7cbc4f2cd596494724659c779ccf4ba985c9470`;
dirty-source hash `b0af916d102ddcd5fa14383bb0ccc7a252132b2376a5eaf8e3ae71105da1a6ea`.
This predates the new source repair and cannot qualify it.

Prior native archive `/home/chromie/Downloads/chromie_issue24_gi_boundary_20260912.tar.gz`:
10,322,848 bytes, SHA256 `14e2b27523f92e4438a93f273f78cade42008a048530a414fd792945da7a4dc2`.
Prior full repair/live archive `/home/chromie/Downloads/chromie_remaining_issues_evidence_20260912.tar.gz`:
48,344,022 bytes, SHA256 `604b801d6331c0356c0541d47bc0fb37eca91793454bda7d75e58e724c3ecd78`.
The [previous handoff](https://github.com/TimeTreker/chromie/blob/6f726ce32f2d69d6fd167ad600cfb7f9eb599536/HANDOFF.md)
retains model digests, actual native request budgets, controls, raw call identities,
residency and full source verification. Private #51 artifacts from the other machine
remain absent. Native artifacts are not training/reference data for this test corpus.

Before new live evidence, rebuild/verify and bind current source/profile identity.
Use generated `.chromie/acceptance/laptop-iterations-20260910/orchestrator.env` and
`.chromie/voice-runtime/compose.voice-mujoco.yaml`; never edit `.env.runtime` or reuse
stale `.chromie/voice-runtime/orchestrator.env`. Soridormi checkout
`/home/chromie/github/soridormi`, branch `codex/turn-count`, revision `284273bc`; preserve
untracked `workspace/Open_Duck_Playground`. Prior launch used `--backend mujoco
--profile open_duck_forward --no-viewer` with the existing MCP service and safe idle.
Run a whole discovered live cohort without between-case edits/restarts; collect one
bundle at completion/hard stop and review every case. Supervised live voice and default
target closure remain required; #32 also needs native stream/cancellation/latency proof.
No follow-up is scheduled.
