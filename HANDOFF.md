# Chromie Latest Handoff

## Current delivery — 6,000-case workflow audit, 2026-09-13

Repository `/home/chromie/github/chromie`, branch `main`; pre-delivery base
`6bf16ccfbe816c068e0b51048331cbec15938c4e`. Python `/home/chromie/miniconda3/bin/python`.
Resume from the latest commit containing this file and [DEVELOPMENT_CHECKPOINT](DEVELOPMENT_CHECKPOINT.md).
The owner authorized expansion, bounded repairs, principle decisions, GitHub delivery
and solved-Issue closure. #60/#65/#66 close with delivery; #24/#32 remain open.
No native inference or LoRA training. No new current document, environment variable,
model profile or architectural owner (102 Markdown / 15 core-path counts unchanged).

## Actual workflow and changed boundaries

| Owner | Material input → output / previous defect | Final mechanism and observed result |
| --- | --- | --- |
| GI primary WHAT | New request with `2099-09-04T19:00:00+08:00`; simulator returned `ready_at`, but Schema/Host rejected it | Primary Schema/prompt admit requested temporal WHAT. ISO/timezone and source/receipt checks reject mechanical/provenance violations. Relative five minutes anchors to receipt `2026-09-04T00:00:00+00:00`; ambiguous calendar/timezone remains unresolved |
| GA continuity | Admitted Responsibility → new canonical Goal | Existing conservation passes exact `ready_at` and action parameters. Test asserts no pre-seeded Goal and equality at both boundaries |
| Planner / Host waiting | New Goal → waiting Plan → persisted condition → scoped due re-entry | No provider call before due; restart retains open Goal and exact due time; one due wake executes the requested parameter and closes only with controlled result evidence. Semantic cancellation prevents later wake |
| Planner model validation | One Goal; execute reply with absent/empty/foreign outcome map previously passed via single-Goal exceptions | Exact map key coverage is now required for every count and both tiers before adaptation. Eight direct shape contrasts and all 100 omission cases pass; zero provider calls on rejection |
| Replay/driver evidence | Earlier resource test stopped too early; mixed speech result correlation was incomplete | Real production auxiliary speech correlation and catalog resource metadata are retained. Two-Goal resource tests require `parallel_resource_claim_conflict`; a generic rejection cannot pass. Twenty-eight static DTO references in 27 older tests preserve their intended semantic assertions under the stronger contract |

The primary end-to-end path is fresh source/receipt → GI → GA → Planner → canonical
adapter → state/Runtime → correlated outcome. Conditional weather completion and due
wake use real Host re-entry methods and real role clients. One genuine GI uncertainty
may invoke its designated deeper cognition once; no same-authority semantic repair
or additional reviewer is added. Clock/UUIDs, initial admission and scheduling,
provider results, successful speech receipts and one terminal-Goal fixture remain
explicitly controlled. Runtime authorization is supplied/withheld by a trusted test
fixture; this is not confirmation dialogue or physical proof. Full I/O and limitations
are in the [audit](ARCHITECTURE_AUDIT.md#broader-workflow-audit--606566).

`benchmarks/integration/workflow_corpus.py` is authoring-only. GPT-6 Astra authored
60 contrasts; 4 actions × 5 values × 5 language forms produce 6,000 separate cases,
not 6,000 independent inferences. All outputs are training-ineligible and review
non-independent. 3,600/1,200/1,200 splits hold out action/value groups, not semantic
families. Corpus: 6,000 JSONs, one manifest, 898 shared packet parts, 382,137,005 bytes.
Original five semantic answers are unchanged; their GI requests were explicitly
refrozen for #60. Independent worker processes accelerate offline episodes; candidate
mode requires one worker and preserves actual requests, raw responses and uncovered
branches without substitute answers.

## Observed checks and retained evidence

R = `.chromie/acceptance/workflow-6000-20260913/` (ignored/private):

- `baseline-identity.json`: exact clean pre-change source matches the retained 1,500
  result at `6bf16ccf`: 1,450 expected successes / 50 known #60 failures.
- `authored-v1/` through `authored-v3/`, three representative captures and `capture-v3/`
  retain reference/wiring failures and all original answers. `frozen-v4/` explicitly
  corrects only 60 terminal dry-condition responses after review. Resource captures
  retain the initial shallow pass, two failed refinements, and final specific conflict.
- `baseline/summary.json`: immutable strict full run, 5,900 expected successes and
  100 empty-map failures. First repair `issue66-focused/` rejects all 100. The later
  absent-map contrast `missing-map-red/` retains 60 rejections / 40 unexpected failures;
  `missing-map-green/` correctly rejects all 100 after the complete fix.
- `final/` passes the preceding empty-map cohort; **`final-2/summary.json` is current**:
  6,000/6,000, unchanged source, aggregate exit 0, no native calls. Counts: 1,400 complete
  workflows; 1,800 state/fault/permission outcomes; 2,580 rejections; 220 safe nonexecuting
  replies. Manifest SHA256 `1d9f5d3d35cf8b993ea2fe6703ac30adac2838514d8e7a27a9bd5431775a0773`.
- `gi-focused-2.log`: 88 tests/101 subtests. `planner-broader-3.log`: 295 tests/173
  subtests. `remaining-focused-2.log`: 36 tests/4 subtests. The broader final gate
  includes all current replay/role checks and changed static references.
- `canonical-3.log`: `./scripts/run_tests.sh` exit 0, **3,214 tests/804 subtests,
  145 benchmark tests and 20 legacy tests**; pinned static/configuration/policy/
  ownership checks pass. Two existing FastAPI deprecation warnings. Previous
  `canonical-1.log` and `canonical-2.log` fail 7 and 4 old reference tests respectively;
  intermediate focused failures and their corrections are retained, not called passes.
- `level-a-2/`: 45/45 distinct cases across 15 classes. `validation-ledger.json` and
  `delivery-source-identity.json` bind results; `source-snapshot/` retains 192 source/
  authority files, including exact final production, replay and primary prompt hashes.
- Reference review files retain all changed DTOs and original copies. Missing/empty/
  foreign negative examples stay malformed, with explicit rejection assertions.
  No runtime mock or normalizer automatically fills their missing outcomes.

Archive: `/home/chromie/Downloads/chromie_workflow_6000_20260913.tar.gz` (1,855,642,868 bytes), SHA256
`18295607616d0bef24c484726f4f0b75cf957ca9181e1384cf49f9de26f21e1a`; 79,430 indexed payload files verified.
It includes all indexed private evidence, source snapshots, completed validation
logs and the index. Post-archive documentation, commit/push and CI records are separate
in R/Git and are not claimed inside the immutable archive.

Prior 1,500 archive `/home/chromie/Downloads/chromie_workflow_1500_20260913.tar.gz`:
433,808,729 bytes, SHA256 `4bb09dafc01ba865da43ac811001c4cf620a54c09ebb314aa878a6b2d83c5430`,
21,428 verified payloads. Prior five-case archive
`/home/chromie/Downloads/chromie_workflow_replay_20260913.tar.gz`: 2,883,802 bytes,
SHA256 `a31606849c791af7cf66ecc18c57a42984e6edc2e546d8ead8c9a52348cf3ba1`.

## Reproduce and resume

From repository root, using fresh evidence directories:

```bash
python -m pip install -r requirements-test.txt
python scripts/run_workflow_replay.py --workers 4 --evidence-dir .chromie/acceptance/workflow-6000-new-run
python -m pytest -q tests/test_workflow_replay.py
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir .chromie/acceptance/workflow-ability-new-run
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```

The full cohort must exit 0 without exclusions. `--family` is focused diagnosis;
`--case-root benchmarks/integration/scenarios` selects the original five episodes.
Candidate substitution follows [benchmarks](benchmarks/README.md#offline-workflow-replay)
with an explicit role/URL/model and one worker. Do not auto-capture changed packets,
feed expected answers to a candidate, or treat a new continuation as model failure.
Before LoRA, independently review positive references and hidden semantic families,
then qualify isolated real roles and the combined real-model workflow. Keep #24/#32
open; offline fixture success cannot replace their native/target evidence.

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
