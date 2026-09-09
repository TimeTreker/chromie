# Chromie Development Checkpoint

## Current continuation — decoder candidate withheld; numeric guard retained

Active Issue #35, main, migration `9df526095494a89c83a421ca22aadb267037c34f` is pushed.
SGLang/shared Gemma4-12B remains selected for RTX 5090; ASR/TTS remain specialized.
This delivery includes the numeric-conservation guard as the maintained change. It rejects
GA outputs that drop typed numeric/boolean GI values, including after mechanical repair;
its two exact retained-output replays changed accepted incomplete Goals to fail_closed.
This is containment, not successful action. Its full preview remains 0/51 qualified.

Delivery base: `9df526095494a89c83a421ca22aadb267037c34f`; expected resume revision
is the latest main commit containing this checkpoint and handoff. Rejected prompt/decoder
candidates are not included in implementation. Evidence under `.chromie/acceptance/`
and Downloads is local to this RTX 5090 machine, not uploaded by this commit.

Actual repaired workflow: GI authoritatively supplies nod count 2 or blink count 1;
GA primary or its permitted mechanical repair emits a Goal without that binding;
the old Host conservation collector skipped numeric values and accepted the incomplete
Goal. The guard includes typed scalars in the same deterministic validation before
Goal commitment, so those exact retained outputs now fail closed with zero Goals.
GA remains the semantic author; Planner is not invoked to repair missing GA meaning.
The focused regression covers missing values with/without repair and wrong/right counts.
See `.chromie/acceptance/ga-numeric-conservation-20260909/root-cause-report.md`.

The next decoder repair was implemented and evaluated, then withheld. Removing only
provably redundant GA Schema intersections preserved 2,377 distinct mutation verdicts;
pinned XGrammar changed from accepting all 8 malformed count variants to rejecting all 8
while accepting the valid reference. Independent multi-ref/candidate/resource constraints
were retained. A live primary then exhausted 2048 tokens on whitespace, so the existing
SGLang compact-output option was tested with that schema candidate. Six retained direct
GA packets completed: 3 Schema passes, but only nod/blink were semantically correct;
physical delivery still chose an ordinary Goal without a resource responsibility.

Focused full preview: blink 1 passed without repair; mixed-language nod failed at GI.
The immutable 51-case cohort finished: 4 mechanical / 3 reviewed preview passes (filler blink 2,
English nod 2, Chinese shake 2). B. merely echoed B. and was rejected. Remaining failures:
23 GI overlaps, 10 GI truncations, 1 GI DTO failure, 7 GA, 3 Fast, 2 preview limitations, 1 latency.
GI-terminal failures increased from 1 in the guarded cohort to 34. The combined candidate
is not promoted; the global whitespace change affected GI as well as GA. These are
observed transaction differences, not a controlled model/backend performance claim.

Both candidate Schema and compose changes, and their new tests, were removed from the
working tree after the complete cohort. The earlier numeric guard/tests are preserved.
Candidate source, all 51 reviews, 100 raw Agent calls, mutation corpus, exact runtime identity
and report are retained under `.chromie/acceptance/ga-decoder-redundancy-20260909/`;
start with `candidate-report.md`. Complete raw text for 10 truncated GI calls is unavailable;
the recorded generation errors are retained. One post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260909_154052.tar.gz`.
Candidate source hash: 432aeaa2c14e19b4d75fbba60edcaf750e26b83cdc7f75f161c8416bcca28f67.

Candidate gates passed 2307 tests/286 subtests, 140 benchmark checks, 20 legacy tests;
focused 90/18, robust-intent Level A 8/8. Restored gates pass 2305 tests/276 subtests,
140 benchmark checks and 20 legacy tests; policies/docs/test ownership also pass.
The first restored run caught a missing status-focus declaration, corrected before rerun.
Restored image is sha256:9c2a2d206a19ae3a6158737bba5aa7ecc628e910c65f5524df7d963f2eb85bdf;
all 122 packaged files match the retained numeric guard. Four services are healthy;
restored focused nod/blink again fail closed at GA. See `restored-file-verification.json`,
`restored-focused-review.json` and `restored-final-runtime-identity.json` in the evidence root.
No physical voice/effects, target closure, or release readiness is claimed.

Earlier primary-layout candidate is also withheld: 22 mechanical/13 reviewed preview passes
but newly released unsupported reminder promises and ungrounded action previews.
Its prompt stays restored; `.chromie/acceptance/ga-primary-layout-20260909/candidate-report.md`
retains the evidence. Do not promote it based on count-only focused proofs.

Next: isolate structured decoding at the existing request/provider boundary, preserving
GI behavior. Before live changes, prove ordinary, multi-ref, candidate and resource schema
coverage. Do not remove independent conditions or add another semantic model decision.
Installed llguidance 1.8.0 is not yet a solution: actual offline grammar validation rejects
the original if/then conditions; serialization alone was not a valid grammar proof.
Separately diagnose general GI responsibility segmentation (framing/punctuation promoted
to Goals), preserving Gemma and upstream/downstream authority.

Resume commands (after reading retained report and identities):
```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```
Use generated `.env.runtime`. If restarting the LLM, stop speech services during transient
model-load memory use, then restore them. Cached TTS restart required the existing
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` environment overrides because its configured
proxy was unavailable. No new environment variable or runtime flag remains in source.

## Revision and retained baseline

Migration baseline: Active Issue #35, delivered as `9df52609` from base `67d2b2f8`.
This delivery contains the owner-selected shared Gemma4-12B reasoning profile;
The Goal-driven single-authority architecture remains: GI owns WHAT, GA continuity,
Planner HOW, and Host/runtime effects. No prompt or Schema
change is part of this migration. Laptop configuration remains unchanged.

Before migration, shared Gemma Q4 on **Ollama** completed all 51 preview cases with zero
passes: 30 GI overlaps, four duplicate refs, five duration provenance failures, eight
Fast request-budget failures, two invalid Fast plans and two preview-only limitations.
All 49 completed GI outputs passed JSON Schema; that is not semantic correctness.
Evidence: `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/comparison-report.md`,
`shared-gemma-review.json`, and `reviewed-cases/` retain inputs and raw calls.
One post-cohort bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260909_121448.tar.gz`.

Earlier SGLang Qwen versus maintained Ollama was a different-model comparison, not
matched Gemma evidence. Three synthetic trials showed GI median first output 37 ms
versus 19403 ms; model/precision/topology confound backend causality. Its only mechanical
preview pass was rejected: unresolved GI meaning and lost GA bindings reached executable
Fast work (head-shake case `c70cf61a`). Preview prevented actual dispatch.
Evidence: `.chromie/acceptance/sglang-switch-rtx5090-20260909/`, including
`comparison-review.json`, `test-utterances-and-results.md`, identities and trial summaries.
Neither preview supplies physical microphone, speaker or robot evidence.

## Preserved engineering work and open boundaries

HEAD already contains the GI binding-schema ordering repair, version-2 24-case frozen
primary-screen corpus and strict raw-output/termination retention. The 1496-reference
GI audit passed. Prior laptop comparison and module I/O details remain in
[HANDOFF.md](HANDOFF.md) and [accelerator evidence](docs/ACCELERATOR_LATENCY_EVIDENCE.md).
Historical instructions to restore Ollama are superseded by the owner's SGLang selection.

The former BF16 allocation failure is addressed by the current online-FP8 deployment
configuration, verified with the real-weight checks above. A single matched norm
tensor did not establish full Ollama/Hugging Face weight equivalence; current FP8 versus
previous Q4 timings must not be presented as a controlled backend-only benchmark.

GI conservation, unresolved-meaning commitment, GA binding preservation and Planner
contract failures remain separate semantic work. Current-revision physical voice proof
and default target-evidence closure remain open. Do not repair semantics with host
rewriting, a second judging model call, or reinterpret validation errors as success.

## Resume checks

The migration is pushed; the numeric guard is the current uncommitted implementation.
The rejected field-layout candidate is retained only as an evidence patch. Do not restore it
without closing the newly reachable grounding/truthfulness failures documented above.
Start with both retained reports and restored runtime identity. For a new change, capture
fresh identity and use a new evidence directory; never overwrite either frozen cohort.
Run the focused regression and complete cohort, then canonical policies/tests/docs checks.
Retain actual voice proof separately; current evidence is headless text/provider work.
