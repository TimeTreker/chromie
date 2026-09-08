# Chromie Development Checkpoint

## 2026-09-09 active checkpoint — GI contract repairs and SGLang comparison

Repository `TimeTreker/chromie`, branch `main`; pre-delivery baseline
`759b5e062cd43ac2cb919e4ca587a682ca673eee`. Expected resume revision is the delivery
commit containing this checkpoint and `HANDOFF.md`. Active Issue:
[#35](https://github.com/TimeTreker/chromie/issues/35).

### Owner direction and architecture

The owner prioritizes non-model engineering correctness; remaining model inference errors
are separate future model/LoRA work. Lower latency means responsive Fast work, first audio,
and interruption recovery while Deep is busy, not every module finishing sooner. A runtime
replacement must avoid additional degradation relative to the maintained deployment.

The Goal-driven single-authority architecture is unchanged: GI owns WHAT, Planner owns HOW,
GA owns continuity, and runtime owns effects. No prompt tuning, semantic repair, model swap,
or maintained provider-default change is included. Existing model imperfection is not itself
a requirement to block engineering delivery.

### Implemented scope

- Align GI binding-schema order with the existing lexicographic prompt contract, including
  optional context fields in both Fast and Deep. A compiled SGLang grammar reproduced the
  old rejection of direction-then-duration and accepts the corrected serialization.
- Replace the default primary-screen oracle with version 2: 24 separate scenario files,
  canonical Schema/Host-validated references, unit/pronoun preservation, unfamiliar-name
  versus material ambiguity, source-span scoring, and deterministic corpus digest.
- Retain passing raw outputs, reject truncated completions, and leave unalignable semantic
  dimensions unscored. Historical v1 and its raw-potential probe remain explicitly historical.
- Add qualification-only `SGLANG_MAX_TOTAL_TOKENS=32768` to the maintained Compose service,
  retaining two request slots and bounded shared-GPU speech headroom. This replaces reliance
  on private cache overrides; it does not guarantee every model/GPU fits.
- Consolidate the oversized checkpoint that had blocked the existing documentation gate.
  No new current document or architecture term; qualification SGLANG inputs 14→15,
  maintained inventory unchanged at 381 keys/four modes/one public boolean/zero aliases.

### Evidence and decision

- Full gate: **2302 tests, 268 subtests, 20 legacy Agent tests**, two warnings; the benchmark
  test group also passed 140 tests. Focused pre-final-test set: 115 tests/18 subtests.
- General abilities: **13/13 Level A** (robust intent 8, composable action planning 5).
- Existing daily-life GI reference audit: **1496 references** remain Schema/Host compatible.
- Same-source complete GI comparison, including only actual unresolved-triggered Deep:
  **SGLang 2/24 vs Ollama 4/24 mechanical passes**. All raw results reviewed; these are
  not complete correctness scores. Model-output differences include both improvements
  and regressions; nod-then-hello loses speech mode/sequence on the current AWQ candidate.
- Three responsiveness trials each: Fast GI first-delta median **91.294 ms SGLang vs
  27473.888 ms Ollama**; foreground window median **279.363 vs 27686.594 ms**.
  SGLang retained and resumed Deep around both speech leases in 3/3 trials.
- These are synthetic real-service/GPU results with generated, unplayed audio. No
  microphone-to-speaker, physical robot, all-role Agent, or release-percentile claim.

Keep Ollama selected for now: the current whole-deployment AWQ candidate is not a
no-degradation replacement. This does not undo the demonstrated scheduling benefit or
require all existing LLM defects to be solved first. Backend-versus-quantization numerical
causality is not isolated; do not classify all remaining differences as SGLang bugs.

### Retention and resume

New artifacts: `.chromie/acceptance/sglang-contract-comparison-20260909/`.
Earlier sizing evidence: `.chromie/acceptance/sglang-laptop-quantized-20260909/`.
See [HANDOFF.md](HANDOFF.md) for exact identities/commands and
[accelerator evidence](docs/ACCELERATOR_LATENCY_EVIDENCE.md#2026-09-09-contract-repair-and-responsiveness-comparison)
for module I/O, failures, corpus versions, latency limits and bundles.
Ollama and TTS are running; the isolated SGLang container is stopped and retained.

Next: preserve these engineering repairs while the owner selects/optimizes model artifacts.
Before a maintained provider switch, compare the chosen artifact's per-case changes and run
actual Agent/Host foreground/voice continuity with retained source/runtime identities.
Do not add prompt patches to mask model differences, or claim physical evidence from these
synthetic runs. Canonical current-revision and target evidence closure remain open.

```bash
python3 scripts/check_repository_policies.py
./scripts/run_tests.sh
python3 scripts/check_docs.py
python3 scripts/check_test_ownership.py
python3 scripts/runtime_configuration_inventory.py --check
git diff --check
```
