# Chromie Latest Handoff

## Current delivery — 1,500-case workflow audit, 2026-09-13

Repository `/home/chromie/github/chromie`, branch `main`; pre-delivery base
`0457db8dfba677363bf99b7ab4f17027e70d4740`. Python `/home/chromie/miniconda3/bin/python`.
Resume from the latest commit containing this file and [DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md).
The owner authorized corpus expansion, bounded repairs, GitHub publication and solved
Issue closure. #61–#64 close with this delivery; #24/#32/#60 remain open. Future LoRA
was discussed, not started. No new semantic owner, model profile, environment variable
or current document (102 Markdown / 15 core-path counts unchanged).

## Implemented boundary and actual workflow

The existing `benchmarks/integration/model_replay.py` serves exact frozen `/api/chat`
responses to real GI/GA/Fast/Deep clients. Parsers/validators, canonical Goal state,
Capability Runtime, result re-entry and due wake remain real. The driver supplies
initial admission/role scheduling, controlled wall time/UUIDs, providers and successful
local speech receipts. This is Level A architecture evidence, not a full Gateway,
autonomous scheduler, native-stream, audio or robot pipeline.

`benchmarks/integration/workflow_corpus.py` is authoring-only; the runtime runner
never executes it. Current-task GPT-6 Astra authored 30 contrasts and response rules;
2 actions × 5 values × 5 language forms produce 1,500 cases. Review is non-independent,
not 1,500 independent inferences. The new frozen `workflow_scenarios/` holds 1,500 case
JSONs, one manifest and 255 hash-addressed shared prompt/Schema parts (88,054,200 bytes).
The original five `scenarios/` remain available. All responses are training-ineligible;
intentional model faults and unrepresentable results are separately labeled. Whole
parameter contrast groups stay in one 900/300/300 split; this is not unseen-family
semantic qualification.

#62: an intentionally unknown GI `binding_items` field failed the raw Schema but
passed normalized Host admission. GI now checks authored wire/canonical key names
against the actual primary/Deep request Schema. Existing relation-reference validation
is preserved. Direct parser callers now include prior-speech context when constructing
the fallback Schema; otherwise 34 legitimate prior-speech references were rejected by
the first patch. There is no extra semantic call or new compatibility alias.

#63: two modest canonical Goal snapshots (3,431 characters in the retained English
blink/walk probe) exceeded Deep's 3,200-character whole-list fragment limit before a
model call. The existing allowance now scales with authoritative Goal count; complete
association/snapshot JSON, all other fragment limits and whole-request preflight remain.
After repair, valid two-Goal plans execute both effects sequentially; omission plans
reach and fail the intended Host guard before any provider call. An explicit extension
captured only 72 previously unrenderable Deep packets, proving every old packet and
semantic answer/oracle unchanged. Original failed cases and manifest identities remain.

#64: the older behavior scenario oracle ignored expected `output_mode`. Its focused
baseline demonstrated body-action vs speech mismatches incorrectly passing. The
existing evaluator now checks this field. Eleven older fixtures were migrated from
undeclared binding aliases; the compound reference additionally corrects swapped
modality/source spans and removes invented blink concurrency while retaining the
explicit joke-while-walking relation. Source turns and requested obligations remain.
These are oracle/reference defects, distinct from product/model behavior. Originals
and exact before/after hashes are retained. The [audit](ARCHITECTURE_AUDIT.md#expanded-workflow-audit--61626364)
provides the full coverage matrix, module I/O, first wrong boundaries and limits.

The replay server can explicitly forward one GI/GA/Fast/Deep role to an Ollama-compatible
candidate service; it sends only the actual role packet with the chosen model name.
Other roles remain frozen. Raw candidate transport and termination survive unchanged;
HTTP failure gets no reference fallback. An accepted variation without a frozen next
packet stops as `uncovered_replay_branch`, not a semantic failure/pass. Candidate
Schema violations take precedence. Model-fault/gap cases and cases without the role
are excluded explicitly. Local fixture services prove all four routing paths, altered
continuations and raw failure retention; the 50-case CLI proof used a second local
fixture service, not a native model. No LoRA jobs, candidate training exports or native
model-ability qualification are delivered.

## Observed checks and evidence

R = `.chromie/acceptance/workflow-1500-20260913/` (ignored/private):

- `authored-v1/`: semantic responses/oracles frozen before the 1,500-case capture;
  `capture-v1/` retains every case and actual available packet on production `0457db8d`.
- `baseline/summary.json`: 1,328 expected successes, 122 unexpected failures, 50 known
  #60 gaps. Manifest SHA256 `97c8d1ed36b51b64d5a6eb4dae9bd59ef4ae02a948e681884c87e68b277e9dbe`.
- `after-gi/summary.json`: 1,378 expected successes, 72 failures, 50 gaps. No changes
  between cohort cases. `after-deep/`, `final/`, `final-2/`: each 1,450 expected
  successes, zero unexpected failures, 50 gaps. Final source identity unchanged
  through the run; no native calls. Each aggregate intentionally exits 1 for #60.
- Final successful outcomes: 350 completed workflows, 400 expected state/fault
  outcomes, 675 explicit rejections, 25 nonexecuting clarify/refuse results. A safe
  unknown-Capability clarification is correct containment, not a bug.
- `packet-extension-2/`: successful 72-packet extension with original identities;
  `legacy-reference-review.json` and `legacy-references/`: all 11 reference originals.
- `candidate-focused-final.log`: 66/66; `candidate-cli/`: 50/50 normal Fast cases with
  only GI forwarded, 50 external fixture calls. `candidate-provider.json` declares the
  provider as local fixture/no inference. The summary's unknown native-call count must
  not be relabeled as real native evidence. `oracle-fixed.log`: 10 tests/4 subtests.
- `canonical-2.log`: `./scripts/run_tests.sh` exit 0, 3,175 tests/798 subtests,
  145 benchmark tests, 20 legacy tests, pinned static/config/policy/ownership pass;
  two existing FastAPI deprecation warnings. Production/replay source did not change
  after this gate. Final documentation checks are retained separately.
- `level-a-2/`: 45/45 cases across 15 classes after fixture vocabulary migration.
  `level-a-final/` repeats after the oracle fix and also passes 45/45 across 15 classes.
- Initial `canonical-1.log` failed 34 direct-parser benchmark references; initial
  `level-a/` was 36/45 due to stale fixture keys. `general-ability/` is library-only
  validation, not execution. `broader-2.log` retained three additional fixture/oracle
  failures, now repaired. Preparation, editing and focused-test failed attempts
  remain in their original logs; none is presented as a pass.

Transfer archive: `/home/chromie/Downloads/chromie_workflow_1500_20260913.tar.gz`, 433,808,729 bytes,
SHA256 `4bb09dafc01ba865da43ac811001c4cf620a54c09ebb314aa878a6b2d83c5430`; all 21,428 indexed payload files verified.
It contains original and intermediate failures, final replay/source snapshots and
completed validation logs. Post-archive documentation/publication checks are retained
separately in R and Git; they are not claimed to be inside this immutable archive.
Prior five-case archive remains `/home/chromie/Downloads/chromie_workflow_replay_20260913.tar.gz`
(2,883,802 bytes; SHA256 `a31606849c791af7cf66ecc18c57a42984e6edc2e546d8ead8c9a52348cf3ba1`).

## Reproduce and resume

Use the repository root, test requirements and a fresh evidence directory:

```bash
python -m pip install -r requirements-test.txt
python scripts/run_workflow_replay.py --evidence-dir .chromie/acceptance/workflow-1500-new-run
python -m pytest -q tests/test_workflow_replay.py
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir .chromie/acceptance/workflow-ability-new-run
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

The full workflow command exits 1 while #60's 50 gaps remain; inspect `summary.json`.
For the original five passing prototypes, add `--case-root
benchmarks/integration/scenarios` to that command on one shell line. For candidate
substitution, use the explicit role/URL/model instructions in
[benchmarks](benchmarks/README.md#offline-workflow-replay). Never silently capture new
packets, feed expected answers to a candidate, hide failed branches or promote faults
into training data. Before LoRA, independently review references and freeze a hidden
semantic-family cohort; then qualify isolated roles and the combined real-model system.
Keep native #24, stream/target #32 and new-request readiness #60 open as described in
the checkpoint. No new inference/training or deployed-service proof occurred here.

## Retained deployment context (historical, unrefreshed)

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
