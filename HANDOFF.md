# Chromie Latest Handoff

## Current continuation — maintained numeric guards; GA candidate retained

The Goal-driven single-authority architecture remains the target. Active Issue #35 on
main. Pre-delivery base: `08890f844d21eb75e939f36dbed03188e6abd2df`; expected resume
revision is the latest main commit containing both checkpoint and handoff. This main
milestone updates evidence/resume notes only. Runtime/source remain the maintained GA/Fast
numeric-guard implementation. Full main preview remains 0/51 reviewed passes; prior main
canonical gate passed 2306 tests / 283 subtests. Fixed SGLang/shared Gemma4-12B on RTX 5090;
ASR/TTS retain their own models.

Candidate `4dd7685d` is committed and pushed on `codex/ga-request-format`, not promoted.
It merges main's Fast guard into `ea2ae1a0` and adds the recursive GA object-schema repair
summarized below. Candidate results do not describe main behavior. The next candidate
resume point is that pushed branch; retained evidence is local to this machine.

Confirmed initiating defect: the installed XGrammar parser prioritizes intersections
before ordinary object fields. Candidate-aware GA schemas could admit abbreviated root
objects while rejecting complete valid ones. `goal_association_schema.py` now exposes
already-required object constraints as a single redundant `anyOf` alternative, recursively
including nested association/binding/source objects. Original `allOf` conditions remain.
This preserves full JSON Schema meaning and existing semantic authority; it does not
implement all unsupported cross-field conditions in the decoder.

| Actual ordered owner / handoff | Before -> after evidence | Contract / verdict |
|---|---|---|
| Frozen GA input | “Continue the previous walk.”; same r1 continue and retained goal-walk | Constructed role input; GI not invoked |
| GA prompt/Schema -> SGLang | Same messages/model/options; only response_format changes | GA owns continuity, not WHAT or HOW |
| Gemma primary | Only associations/new_goals, wrong local_ref field -> complete object with source_responsibility_refs=[r1], continue goal-walk | First proven wrong boundary is decoder representation; after output is correct |
| GA DTO/Host | Before repair still fails closed; after resolves in one call | No semantic rewriting or extra judge |
| Downstream | Role probe returns resolution only | Planner, persistent Goal store and physical dispatch not invoked |

Eight frozen English/Chinese role cases cover continue, modify, independent new blink and
mixed continue+joke. Before: 0/8 resolved, 16 raw Schema failures. After: 8/8 correct
continuity/ownership outcomes; 7 primary passes, 1 bounded mechanical repair. English
modify's primary already chooses modify/r1/goal-walk and five-second change in rationale;
repair adds missing updated_description. Do not call it a clean primary pass. Exact packets,
raw outputs and review are retained; expectations never enter candidate requests. Corpus
digest: `18a4403d8cbf3a2dc4773c8e39556c2cb93926af5390f6c774955e3be9b4632c`.

Frozen installed-grammar proof: 2427 separate cases, zero changed full-Schema verdicts.
Valid acceptance improves 183/229 -> 229/229. Invalid acceptance changes 169/2198 ->
175/2198 (9 newly reachable, 3 newly rejected). Of those 9, four fail DTO checks, three
fail existing Host ownership checks, and two repeated-identical-ID cases normalize but
still fail strict raw Schema. This is not full decoder soundness. The outer-only prototype
was rejected because it admitted malformed nested fields. Final helper matches all 11
unique frozen schemas; fresh fixture comparison has 45 comparisons / 44 unique, no verdict
changes. No new current document, environment variable or semantic authority is introduced.

Full immutable before/after 51-case live-text previews: 16 mechanical passes each;
reviewed passes improve 9 -> 12, with all nine earlier positive cases retained. Added preview
passes: tired social response, capability inventory, Chongqing-afternoon initial lookup.
A lookup preview does not prove a weather-provider result or completed evidence re-entry.
GA primary raw Schema passes improve 20/47 -> 38/48; after still has 10 primary plus 10
repair Schema failures. All 51 cases were reviewed from raw calls, including mechanical
passes. After retains 164 calls, 163 linked to the cohort, with no log JSON decode errors.

**Promotion is withheld:** an earlier GA Schema failure contained “去那边等我。”; now a
valid GA object lets Fast's ungrounded two-second walk reach preview. GI had failed to mark
the unknown destination unresolved; Fast substitutes walk_forward; Host admits the wrong
semantic result. No physical dispatch occurs. “调大一点。” similarly reaches unrelated
movement (before nod, after walk_velocity). These hard failures cannot be offset by more
passes. Reminder promises, milk resource classification, GI framing/prohibition/multi-turn
provenance, multi-Goal arrays, Fast DTO/latency and Deep capability inventions remain open.
Main's previous full preview remains 0/51 qualified; neither branch is behavior-qualified.

Validation on candidate `4dd7685d` (tested pre-commit source): focused GA/Fast 202 tests / 45 subtests; canonical gate 2311
tests / 318 subtests, 140 benchmark checks and 20 legacy tests passed. Policies, docs,
test ownership and pinned static gates passed. Level A continuity 4/4 and robust intent
8/8 (11 distinct). All 70 deployed Agent source files matched tested source. Evidence is
Level A plus live model/Level C-preview, not physical microphone/speaker/robot, target
closure, release readiness or a controlled backend performance comparison.

Evidence root (local, not uploaded): `.chromie/acceptance/ga-root-fields-20260909/`.
Start with `repair-report.md`, `role-review.json`, `role-comparison.json`,
`nested-grammar-summary.json`, and both `baseline/behavior-review.json` and
`after/behavior-review.json`; all raw transactions are in their `reviewed-cases/`.
Exactly one bundle followed each full cohort:
- Before: `/home/chromie/Downloads/chromie_debug_bundle_20260909_210540.tar.gz`.
- After: `/home/chromie/Downloads/chromie_debug_bundle_20260909_212140.tar.gz`.
Both preview exits are 1; both bundle exits are 0. No source edits/restarts occurred within
cohorts. Candidate Agent image:
`sha256:422b446a3a2be6279cdab7f969c598b824505db3c875c6a8a9b8a112fbe8f0c4`,
retained as `chromie-agent:ga-object-shapes-20260909`.

Next: use the completed cohort as the baseline for the multi-responsibility new-Goal array
cluster, where malformed items and omitted Goals remain reachable. Prove exact installed
grammar item/cardinality behavior with frozen valid/invalid contrasts before editing.
Keep the ambiguous-destination case as a hard promotion blocker; separately diagnose GI
unresolved meaning without a semantic reviewer or Host intent rules. Do not repeat the
already-closed root-object diagnosis or promote this candidate from focused results alone.

Operational runtime: main Agent backup `chromie-agent:fast-numeric-guard-20260909`
(image `sha256:63cabb1e5e863b204aa97e86acbb2f11eb2568dcaa18db2e9fffef4382d4cac7`)
and maintained SGLang `chromie-sglang:guard-baseline-20260909`
(image `sha256:2f425788c02f2502fd5541455f4917819759352b68e8b8b987bee750204c11ac`)
were restored after the cohort. All four services are healthy, and all 70 packaged Agent
files match main 08890f84; see `restoration-verification.json`. Candidate code remains
isolated. `restored-runtime-identity.json` records the main images and metadata-only
dirty checkout. This main documentation delivery passes docs, policy and test-ownership
checks; the full source suite was run on the candidate as recorded above. Generated
`.env.runtime` was not edited; no physical Orchestrator started; preserve unrelated
Soridormi working-tree changes.

Resume commands from the repository root:
```bash
git show origin/codex/ga-request-format:HANDOFF.md
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```
Live invocation after capturing a fresh identity and using a new evidence directory:
```bash
python scripts/general_ability_acceptance.py --mode live-text --stage must_pass \
  --runtime-identity PATH_TO_FRESH_IDENTITY \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo /home/chromie/github/soridormi --evidence-dir NEW_EVIDENCE_DIRECTORY
```
Do not reuse old identity files after switching images. Stop ASR/TTS before restarting
SGLang because transient model-load memory can exceed capacity. Restore cached speech
using existing `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` overrides if needed. Compose uses
`.env.runtime`, `docker-compose.yml`, `docker-compose.sglang.yml` and
`.chromie/voice-runtime/compose.voice-mujoco.yaml` in that order.


## Delivered migration baseline — SGLang/Gemma, before numeric guard

Active Issue #35; pre-delivery base `67d2b2f867064d59c21c075a8ad0108abc3250da` on `main`.
Expected resume revision: the latest delivery commit containing this checkpoint and handoff.
RTX 5090 auto-detection now selects shared Google Gemma4-12B online FP8 on SGLang,
served as `chromie-gemma4-12b`: 65536 context/shared cache tokens, two request slots,
priority preemption, 0.125 sliding/full cache ratio, and Host speech leases.
ASR SenseVoice int8 and TTS CosyVoice3 0.5B remain specialized. Laptop unchanged.
Normal launcher startup passed, including unplayed zh/en/mixed TTS warmups. All four
services remain healthy; no host Orchestrator/microphone or physical effects were run.

Build owner `llm/sglang/Dockerfile` pins the upstream image and repairs the reproduced
missing `lm_head_is_tied` constructor field. `docker-compose.sglang.yml` overrides the
existing `chromie-llm` owner; the obsolete Qwen validation overlay was removed. SGLang
rejects colons in served aliases, so the profile uses the new alias for the same weights.
Provider-aware startup, health, diagnostics and provenance validation are implemented.
No prompt/Schema/semantic-authority changes. Inventory remains 381 environment keys.

Evidence root `.chromie/acceptance/sglang-gemma12b-migration-20260909/`.
Read `migration-report.md`, then `behavior-review.json` and `reviewed-cases/`.
The real 23,919,549,408-byte checkpoint SHA256 was verified (`model-verified.json`).
Real weights occupy 13.68 GiB; KV allocation is 3.50 GiB. No dummy-weight timing claim.
Provider protocol passed. Saturated two-slot preemption passed 3/3 (foreground first
output 74.69–77.90 ms). Speech pause/resume/revocation/recovery passed 3/3 with generated,
unplayed audio. Actual GI median was 4.35 s; short canaries are not full-workflow latency.

The immutable 51-case preview completed: four mechanical passes, zero fully qualified
transactions. Terminal buckets: 37 GA Schema/DTO, seven Fast contract, one GI duration,
two preview-reflex limitations, four mechanical passes rejected by review. Nod2/blink1
planned correct actions but GA lost count bindings; B. merely echoed; capability inventory
was not answered. No Fast input-budget failures. Earlier shared-Gemma 0/51 was Ollama Q4,
not SGLang; FP8/64K versus Q4/32K is not a controlled backend-only comparison.
All 49 raw GI results passed Schema; all 96 raw GA results violated submitted Schema.
Offline proof: pinned XGrammar permits the exact invalid GA output through unsupported
multi-option allOf; installed LLGuidance rejects contains constraints. These are retained
integration gaps, not proof of intrinsic Gemma incapacity. Host binding conservation after
GA repair also remains open. Preserve SGLang selection; do not silently weaken contracts.

Canonical gate passed 2303 tests/268 subtests, 140 benchmark and 20 legacy tests; Level A
45/45. Later final logs bind diagnostic/documentation consistency checks separately.
Runtime identity: `runtime-identity.json`; complete raw calls: `raw-calls.jsonl` (194).
Exactly one post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_141505.tar.gz`.
Owner authorized commit/push of this migration, followed by GA root-cause repair.
Physical voice and default target closure remain open.

### Exact runtime and resume

Google revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`; source weight SHA256
`5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`.
Deployed image ID `sha256:2f425788c02f2502fd5541455f4917819759352b68e8b8b987bee750204c11ac`.
Normal startup log `startup-alias-fixed.log`; rejected-name log `served-name-failure.log`.
The complete model is cached in `hf_cache/hub/models--google--gemma-4-12B-it/`.
Use the existing cache; no background downloader remains. Historical paused partial
Ollama/BF16 download files are not active and are not the deployed artifact.

```bash
./scripts/start_chromie.sh --build --no-orchestrator --keep-services
./scripts/verify_runtime_profile.sh
```

`cohort-command.json`, `protocol-command.json`, `contention-command.json`, and
`preemption_probe.py` retain exact probes. Use new evidence directories for a rerun;
never overwrite this frozen baseline. Capture a new runtime identity after implementation
changes. The existing 51-case run was bound to `runtime-identity.json`; subsequent changes
only correct launcher diagnostic text and documentation. No service rebuild was needed.

Historical sections below describe earlier deployments, not the current selection.

## Latest 2026-09-09 — shared Gemma RTX 5090 worktree

No new commit. Source remains `67d2b2f867064d59c21c075a8ad0108abc3250da` with owner-requested
profile/test/configuration/status edits. Every RTX 5090 reasoning role now uses `gemma4:12b`;
one resident runner, 32768 context. ASR SenseVoice and TTS CosyVoice3 models are unchanged.
This topology is implemented, not behavior-qualified: all 51 preview cases failed (see report).
Canonical gate passed 2302 tests/268 subtests + 140 benchmark + 20 legacy; Level A 45/45.

Evidence root `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/`.
Read `comparison-report.md` first, then `shared-gemma-review.json` and `reviewed-cases/`.
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260909_121448.tar.gz`.
`ollama-q4-runtime-identity.json` binds the frozen baseline worktree before later docs edits.
`recovered-llm-calls.jsonl` has 62 calls; one interleaved Uvicorn fragment removed; original
bundle unchanged. `tests-final.log` is the successful canonical gate (earlier attempts failed).

Fair timing is blocked in the tested setup: native SGLang GGUF loader has no
`gemma4_unified` mapping; BF16 placeholder-weight allocation with ASR/TTS resident failed
at fraction 0.80 and yielded only 2017/32768 cache tokens at 0.99. These are allocation
preflights, never model quality or throughput tests. No matched BF16 inference was run.
Both probes stopped; Ollama shared Q4 model is warmed and all four normal services healthy.
Downloads paused; partial cache files retained. Google artifact revision is
`707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`; expected safetensors SHA256
`5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`.
Ollama BF16 blob is `a01bdd1527e5daebb520cbb570d32e4074bb94df263743ae733a8ef75bc4778d`.
Only one full norm tensor has been compared (3840 exact matches), not all weights.

Resume downloads only after choosing a viable matched configuration:
`docker exec chromie-llm ollama pull gemma4:12b-it-bf16`.
HF: use cached image `59e11312666e` with `/home/chromie/github/chromie/hf_cache` mounted
to `/root/.cache/huggingface`, and `huggingface_hub.snapshot_download` for the exact Google
revision above (allow JSON/Jinja/model/safetensors/README files). The prior ephemeral
`chromie-gemma-download` container was stopped and removed.
`replay_gi.py` and `gi-freeze.json` retain 24 identical primary GI packets; invoke with
`--provider ollama|sglang --model <verified-id> --url <loopback-base> --output <fresh-dir>`.
Do not claim complete GI qualification from that primary-only probe; permitted depth
delegation/repair and downstream all-role behavior require their own complete transactions.
No performance claim while downloads or unrelated GPU workloads run. Rebind source/runtime
identity after final docs edits and before any new aggregate. Keep one bundle per aggregate.

## 2026-09-09 active handoff — RTX 5090 provider comparison

Owner asked whether to switch to SGLang. Recommendation: pursue its demonstrated scheduling
benefit, but do not promote the current all-role 9B profile. Maintained Ollama is restored;
SGLang is stopped/cached. No source/prompt/model-file changes, commit or push. Source main
`67d2b2f867064d59c21c075a8ad0108abc3250da` with existing documentation-only changes;
comparison timing worktree hash `d95d8948f347f83f3b73fa9b46d62706311846669cd1133a403c0bf70dcb22be`.

Evidence root: `/home/chromie/github/chromie/.chromie/acceptance/sglang-switch-rtx5090-20260909/`.
Read `switch-decision.md` and `comparison-review.json` for all 51 case decisions, exact
module I/O and the rejected mechanical pass. Three trials/provider: median GI first output
19403 ms Ollama vs 37 ms SGLang; foreground window 19882 vs 209 ms; speech first audio
3504 vs 2180 ms. SGLang finished foreground before Deep and resumed after both speech
leases in 3/3 trials. Maximum observed VRAM 25314 vs 31403 MiB (32607 MiB device).
These are synthetic canaries/unplayed TTS, not physical voice or release percentiles.

Frozen 51-case planning preview: runner 1/51 SGLang vs 0/51 earlier Ollama. Review accepts
zero complete transactions. Candidate terminal buckets: GI duration provenance ten,
Fast input budget eight, output truncation eleven, contract six, GA contract thirteen,
preview-only reflex restrictions two, mechanical pass one rejected on review. Correct
validation rejection is not successful behavior. Original runner summaries remain unchanged.
All scenario files match the Ollama baseline; `cohort-match.json` records each hash check.

Critical case: `shake_head_twice_plain_request`, turn c70cf61a. GI primary and source-only
Deep invent actor ambiguity; Deep also confuses robot self-identity with the human. GA
primary emits malformed count/entity bindings; its repair drops them to bindings=[] and
Host accepts the Goal. Concurrent Fast emits execute/complete shake_no with unresolved=[].
Host constructs an executable interaction despite retained upstream unresolved meaning.
Preview prevents dispatch; the mechanical oracle checks capability/count and misses this
conservation/authority failure. This is a reproduced gap to fix before execution, not a pass.
Look-then-blink also loses duration on SGLang where Ollama retained it (with other errors).
Common model errors and new downstream reachability must remain separate from regressions.

Exact candidate: SGLang 0.5.19/CUDA 12.9.2; Qwen/Qwen3.5-9B BF16 safetensors revision
c202236235762e1c871ad0ccb60c8ee5ba337b9a, served chromie-qwen35-9b-sglang. 32768 context/
shared cache, two requests, ten Mamba slots, .80 memory fraction, breakable prefill graphs.
Candidate fingerprint 5298cb5d35f866eeb5f7ff1a3d52696ee16b3fe4f4d2d384ee232d6fbe28e545.
Ollama 0.32.14 used maintained Gemma4-12B GI/GA/Deep and Qwen3.5-9B Fast, Q4_K_M weights,
32768 context, q8_0 KV. Different artifacts/topologies prevent scheduler-only attribution.
See `*-series-command.json`, `*-contention-summary.json`, `sglang.env`,
`sglang-runtime-command.json`, `sglang-runtime-identity.json`, `ollama-models.json` and
`ollama-cuda-maps.txt`. CUDA was initially unknown in Ollama commands; maps supplement it.

Initial identity capture rejected dirty documentation; the shell nevertheless started a
cohort. It was interrupted/excluded and bundled once:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_114037.tar.gz`.
Then capture used --allow-dirty and explicit candidate services/Compose files. The unchanged
replacement completed and was bundled once:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_115034.tar.gz`.
`sglang-must-pass-preview-bound/` is the complete run; `sglang-must-pass-preview/` is excluded.
`recovered-sglang-calls.jsonl` reconstructs interleaved records from that retained Agent log.
GA/Fast raw content lives in provider_response.choices[0].message.content, despite the generic
raw_model_output field being null. Truncated Fast calls lack a complete retained raw result.

The unchanged source passed the earlier full gate (2302 tests/268 subtests, 140 benchmark,
20 legacy Agent) and 45 Level A cases. This comparison passed 14 focused SGLang tests.
Soridormi remains running headless at port 8000/mcp on pre-existing dirty revision
 d03c7e3b7da73b777b1e923044340fa9c8d66fa7; do not overwrite its skill/config/test edits.
Earlier same-host Ollama baseline: `.chromie/acceptance/resume-67d2b2f8-rtx5090-20260909/`.
Prior laptop comparison directories below are absent on this host.

Next: reproduce c70cf61a conservation/unresolved admission, then shared full Fast payload
preflight. Validate a role-compatible model/profile and actual Host voice continuity before
promotion. No semantic host rewriting or global-authority change is proposed here.
Reproduction commands are retained as structured arrays in `*-series-command.json`;
use fresh output paths. Start candidate from the recorded SGLang Compose env only after
unloading Ollama. Generate the opt-in validation profile, warm services, capture with the
actual service list and --allow-dirty only when truthful, then run general abilities with
--mode live-text --stage must_pass and that identity. Collect once after each full cohort.
Do not reuse old identities or run physical effects from this preview evidence.

## Earlier 2026-09-09 handoff — engineering repairs and paired runtime evidence

Repository `TimeTreker/chromie`, `main`; pre-delivery baseline
`759b5e062cd43ac2cb919e4ca587a682ca673eee`. Resume from the delivery commit containing
this handoff and checkpoint. The owner authorized commit/push to remote main. No runtime
promotion is included: the current candidate shows additional behavior differences, while
existing common LLM deficiencies remain separate future model/LoRA work.

### Delivered changes and causal boundary

GI schema order contradicted its prompt: an ordered decoder could not emit duration after
direction. Sorting the existing property set after context additions fixes that mechanical
contract without changing authority, meaning or model. The v2 primary screen fixes oracle
unit/ambiguity rules, source-span coverage, reference validation, raw retention and completion
integrity. The 32K shared-cache limit is now a supported qualification Compose input instead
of an ignored private override. Earlier checkpoint history was consolidated to restore its
reviewed documentation limit. Detailed actual module I/O, root causes, containment and
remaining inference differences are in
[accelerator evidence](docs/ACCELERATOR_LATENCY_EVIDENCE.md#2026-09-09-contract-repair-and-responsiveness-comparison).

Full gate passed **2302 tests, 268 subtests, 20 legacy Agent tests**, two warnings, plus
140 benchmark tests. Focused set before the final completion-integrity test: 115 tests and
18 subtests. General-ability Level A: robust intent 8/8, composable actions 5/5. All 1496
existing daily-life references still validate. Final documentation/policy/diff checks follow
these documentation updates; no live voice or release closure is implied by local tests.

### Paired evidence

Root: `/home/chromie/github/chromie/.chromie/acceptance/sglang-contract-comparison-20260909/`.
Both complete 24-case GI runs and both three-trial contention series used one source digest:
`fc0d5a0b425f759af72c34fa2bfda0eb1555dbc38e5e1992940331eb63227cb9`.
Later changes add the already-tested cache cap to Compose, defensive grader checks/tests,
and documented post-batch accepted-variation review; original inference reports are intact.
The primary message, ordered schema, temperature and budget match per case. Production
`interpret_goal` made 24 SGLang and 32 Ollama calls: eight Ollama cases invoked source-only
Deep because unresolved was present. Confidence alone never triggers Deep.

Key artifacts:

- `decoder-order-proof.json`, `order-fixed/`: compiled grammar proof and full old-screen rerun.
- `complete-sglang/`, `complete-ollama/`: frozen manifest, raw requests/responses, Schema/Host
  outcomes, per-case decisions, latency, runtime identity and stable-source summaries.
- `paired-packet-audit.json`, `post-batch-rubric-review.json`: matching inputs and explicit
  post-batch review. Mechanical counts remain 2/24 SGLang and 4/24 Ollama; nominal passes
  still require semantic review. No candidate response was repaired.
- `fast-sglang/`, `fast-ollama/`, their `*-summary.json` and `*-command.json`: three trials
  each. Fast GI median 91.294 ms vs 27473.888 ms; complete foreground window 279.363 ms vs
  27686.594 ms. These are synthetic workload timings, not full voice-turn measurements.
- `ollama-identity.json`, `ollama-loaded-cuda.txt`: exact Ollama identity; its command recorded
  CUDA unknown, and supplemental process maps prove loaded runtime 13.0.96.
- `maintained-compose-command.json`, `full-gate.log`, `focused.log`, `abilities.log`,
  `daily-life-reference-validation.log`: rendered resource command and source validation.

The current checked-in v2 scenario tree is
`7b233a6647f20c7c453e6606f70cfeae47f6a592067e8c5c93735d17f2b156b5`;
the inference snapshot tree was
`b434ce62a0b7a55eb08c1a7b1af0d9da1090c6691cccc2d29af31bc264c80c67`.
The difference accepts valid transfer wording/direction translation and is explicitly reviewed
without rewriting or silently rescoring old reports. Historical v1 is unchanged.

```text
SGLang: 0.5.19 / CUDA 12.9.2
image digest: sha256:59e11312666e1c5c155210ea335589b91daa0d70848521b390b93b1b1e8fb0ef
model: cyankiwi/Qwen3.5-4B-AWQ-4bit
revision: ef85d23bebaba87b3c4672ba11c449c79dbdb23e
upstream Qwen revision: unpublished/unknown
weights SHA256: 902477edf53bc6768bd1f212dd1866856fd5a0627def06887780c95900ffb013
format: compressed-tensors AWQ W4A16 group32, BF16 activation/KV
served name: chromie-qwen35-4b-awq-sglang
context/shared cache: 32768/32768; requests: 2; Mamba: 10; fraction: .80
prefill graphs: disabled; decode graphs retained
Ollama: 0.33.2; qwen3.5:4b; GGUF Q4_K_M; one request; q8_0 KV
image digest: sha256:020e4134285e2ef4d8fd801234176de3b4faadc992a3eb06c8e66a2f9d4c4ba2
model digest: 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
TTS: ws://127.0.0.1:5000, chromie_mixed, generated audio not played
```

### Operational state and resume

Ollama and TTS are healthy/running; SGLang is stopped to avoid concurrent model residency.
Agent was not started/promoted. SGLang's stopped container/cache and all private raw evidence
remain local. Different quantized artifacts mean this is a deployment comparison, not isolated
scheduler-versus-model causality. Do not hide concrete modality/sequence regressions, and do
not require all common model errors to disappear before further engineering work.

For resource reproduction, use the existing `docker-compose.sglang-qualification.yml` with
the pinned image/model/revision above, warmed resident TTS, prefill disabled, .80 fraction,
32K context, two requests, ten Mamba slots and `SGLANG_MAX_TOTAL_TOKENS=32768`.
Stop/unload Ollama first; do not run both full model pools on this laptop. The rendered
`maintained-compose-command.json` records the exact argument set. No `.env.runtime` edit
was made. `AGENT_LLM_PROVIDER` remains Ollama; the existing validation bridge is opt-in.

The local `compare_gi.py` and `run_series.py` reproduce the retained comparison; they are
private instrumentation, not new maintained APIs. Use fresh output directories and capture
new runtime identities; do not overwrite this run. The maintained primary screen is
`scripts/qualify_inference_provider.py --goal-interpreter-probe`, defaulting to the v2 manifest.
It is primary-only; the full comparison used the production GI entrypoint separately.

Bundles (local, not uploaded by Git):
`/home/chromie/Downloads/chromie_debug_bundle_20260909_060924.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_061242.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_061915.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_062218.tar.gz`.
Earlier resource/OOM artifacts remain under
`.chromie/acceptance/sglang-laptop-quantized-20260909/`; its bundle paths are retained in
accelerator evidence. Copy private artifacts explicitly when changing machines.

Next is owner-directed model/artifact work, followed by matched no-degradation checks and
actual Agent/Host foreground, speech and interruption continuity before changing defaults.
Keep all canonical validation and supervised physical-evidence boundaries intact.

## Historical 2026-09-09 BF16 laptop resource boundary

This historical section is superseded by the active quantized handoff above. Its original base was
repository `TimeTreker/chromie`, branch `main`, base
`7f9d1c019b5be97c664a3a26d88ae00f1376b459` plus the checkpoint patch that contains this text.

### What is already settled

- Keep the Goal-driven single-authority architecture. GI owns WHAT; Planner owns HOW; GA owns Goal
  continuity; runtime/provider owns effect truth; provider scheduling owns only operational compute.
- Keep Ollama as the maintained production/control path. SGLang is still a candidate provider.
- RTX 5090 provider evidence already proved priority/preemption, presentation lease, interruption
  revocation, reacquisition for replacement TTS, and Deep continuity with protocol 5.
- The RTX 5090 SGLang Qwen3.5-9B production-shaped GI semantic cohort passed only 1/16. Treat that
  model-role promotion as rejected; the correct Host fail-closed validators must not be weakened.
- Do not infer semantic quality from the RTX 4090 Laptop Qwen3.5-4B run described below. It is a
  resource canary only.

### RTX 4090 Laptop measured state

The operator switched to the 16 GB RTX 4090 Laptop and kept CosyVoice on the same GPU. The first
TTS restart loop was a container-network proxy error, not CUDA: the host shell exported
`127.0.0.1:7897`, which addresses the container itself. Using
`host.docker.internal:7897` made CosyVoice healthy with zero restarts. The qualification compose in
this patch now exposes the same proxy/offline contract permanently.

With TTS resident, exact SGLang canary identity:

```text
image: lmsysorg/sglang:v0.5.19-cu129
model: Qwen/Qwen3.5-4B
revision: 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
served name: chromie-qwen35-4b-sglang
weights: HF safetensors, BF16, unquantized
context_length: 32768
max_running_requests: 2
max_mamba_cache_size: 10
```

Measured sequence:

```text
mem_fraction_static=.70
  weight load: 8.62 GB
  result: fail before KV pool; SGLang minimum viable fraction > .826

mem_fraction_static=.90, default prefill graph
  Mamba ~= .53 GB
  KV = 5,091 tokens
  result: fail during prefill CUDA-graph capture OOM

mem_fraction_static=.90, prefill graph disabled
  decode graphs remain for bs=1,2
  SGLang healthy + TTS healthy
  KV = 5,091 tokens
  total GPU ~= 15.9 / 16.4 GiB

same run + --language-only
  multimodal loading still initialized
  0.10 GB multimodal sizing reservation remained
  weights stayed 8.62 GB
  KV stayed exactly 5,091 tokens
  result: no useful memory gain; do not retain this flag
```

The Numba `inkling` warning (`Numba needs NumPy 2.4 or less; got 2.5`) is an ignored optional
multimodal-processor import warning, not the current blocker. Do not downgrade NumPy merely to
silence it.

### Current decision / do-not-do list

The laptop proves **physical co-residency, not a deployable cognitive topology**. 5,091 tokens is
below the maintained GI 16K request and far below other 32K roles.

Do not:

- run protocol-5 and call it product evidence with this 5K pool;
- reduce `max_running_requests` to 1 and thereby remove the foreground-vs-Deep objective;
- shrink semantic contracts, source provenance, or Host validators to fit VRAM;
- add model-specific semantic repair;
- promote Qwen3.5-4B or Qwen3.5-9B in model lock / Agent profiles from these results;
- keep `--language-only` as a supposed memory optimization;
- copy `.90` or disabled prefill graphs blindly to a future quantized model—the new artifact must
  be resized from its own measured pre-load/weight/pool facts.

### Exact next work

The next comparison target is a **quantized SGLang-served model/artifact** appropriate to the
16 GB shared-GPU laptop. Hold these requirements fixed:

```text
CosyVoice resident and healthy
two simultaneous model requests
priority/preemption enabled
32K target context topology (GI must at least clear 16K)
typed non-thinking / structured-output transport
exact source model + revision + quantization + runtime identity retained
```

First prove resource fit only. Do not run or optimize semantic prompts while the engine cannot
retain the required context. Once a quantized candidate retains a production-sized pool:

1. run one foreground-under-Deep provider canary;
2. run one protocol-5 presentation lease/revocation round-trip with TTS;
3. run the frozen production-shaped 16-case GI semantic cohort with the prompt/Schema/Host
   transaction unchanged;
4. only if semantic failures cluster narrowly at an evidenced prompt/profile boundary, optimize
   that owner and rerun focused + full cohorts;
5. only after GI qualification proceed to Fast/Deep Planner and real Agent/Host end-to-end work.

### Patch/application gate

This patch intentionally does **not** add a laptop SGLang Agent overlay. It only makes
qualification infrastructure reproducible and records the checkpoint.

After apply:

```bash
python3 scripts/runtime_configuration_inventory.py
python3 scripts/runtime_configuration_inventory.py --check

python3 -m pytest -q   tests/test_sglang_qualification_compose.py   tests/test_sglang_runtime_integration.py   tests/test_runtime_configuration_inventory.py

python3 scripts/check_repository_policies.py
python3 scripts/check_docs.py
git diff --check
```

Commit the regenerated `config/runtime_configuration_inventory.json` together with the patch
changes if the inventory generator modifies it.

## Historical handoff retained for provenance

Audience: the project owner or coding agent resuming the current Goal-driven
single-authority focus, deployed Planner qualification, and current-revision
evidence closure for Issue #35.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and working state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Pre-delivery base: `46b6fe90a36179e63da36f086ac2b04ed8e7b3c1`
  (`main == origin/main` before this continuation).
- Expected resume revision: the latest normal `main` commit containing this
  handoff and `DEVELOPMENT_CHECKPOINT.md` after the authorized fast-forward push.
- Delivery target: fast-forward `main` to `origin/main`, then verify the remote ref.
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35).
- 2026-09-06 transaction-fidelity continuation: A01–A06 are source-closed in the current worktree. The next evidence gate is a clean checkout with pinned dependencies running `./scripts/run_tests.sh` and recording the full pytest collection/pass counts before any model/profile promotion.
- Scope: deliver the transport, warm-up, scenario, test, status, checkpoint,
  and handoff changes listed below in one revision.

Changed paths:

```text
agent/app/clients/ollama_client.py
config/runtime_exception_boundaries.json
docs/CONFIGURATION.md
docs/STATUS.md
scripts/warm_ollama.sh
scenarios/general_ability/must_pass/speech_identity_latency/standalone_greeting_one_natural_reply.json
tests/test_general_ability_acceptance.py
tests/test_ollama_client.py
tests/test_runtime_reliability_stage4.py
DEVELOPMENT_CHECKPOINT.md
HANDOFF.md
```

## 2026-09-06 transaction-fidelity continuation

The archive audit found six implementation mismatches without changing the target authority architecture. The current worktree removes live GA semantic repair, makes terminal Fast limitations/refusals final unless canonical state materially changes, validates request-specific early speech before release, switches the main test tree to pytest collection and migrates stale hidden tests/scenarios, makes authoritative GI Responsibility projection lossless in both GA prompt paths, and reconciles completed GA commit truth into downstream error results.

Focused evidence retained in this work session: PR7 71 passed plus 2 subtests; A05/A06 focused 153 passed plus 2 subtests; migrated hidden-test focused set 94 passed plus 2 subtests; Level-A `multi_goal_daily_life` 10/10; one broad pytest partition 475 passed plus 50 subtests. Another broad partition exceeded this execution environment's command timeout, so this handoff does **not** claim a complete canonical gate. Run the pinned full gate on the destination checkout before delivery/promotion.

Next commands after applying the patch:

```bash
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
python scripts/general_ability_acceptance.py --mode level-a --ability-class multi_goal_daily_life --no-write
git diff --check
```

## What was reproduced

The exact live greeting did not fail because Goal Interpretation misunderstood
it. On the current RTX 4090 all-Qwen profile, the observed workflow changed as
successive earlier boundaries were repaired:

1. Exact microphone session `fe7a5819`: ASR produced `你好。`; GI returned a
   correct greeting speech Responsibility in about 1.94 s; GA and Fast both
   timed out near 60 s with no output. The session ended before playback.
2. Direct probes showed current Ollama 0.33.2 `/api/generate` with
   `think:false` emitted no bytes before timeout, even for a tiny request.
   `/api/chat` completed immediately, including structured JSON and streaming,
   with no thinking field. GI already used `/api/chat`; generic Agent semantic
   roles used `/api/generate`.
3. After the Agent `/api/chat` repair, a focused greeting still timed out because
   the resident Qwen runner was 16K while GA/Fast requested 32K. An identical
   direct 16K chat completed immediately. The old warm-up had used the broken
   endpoint and had not established production context residency.
4. After restarting Ollama and running the repaired `/api/chat` warm-up, the
   runner reported context length 32768 and direct 32K chat completed. The exact
   greeting then reached GI, GA, and Fast, exposing a repeatable Fast semantic
   failure.

```text
`你好。` -> GI: correct speech Responsibility (~5.50 s)
        -> GA: correct speech Goal (~6.08 s)          [concurrent]
        -> Fast: empty commit (~8.246 s), then        [concurrent]
                 clock Capability + `现在的时间是。`
        -> Host rejects invalid speech-to-clock Plan
        -> no natural greeting response
```

| Module/boundary | Authoritative input and actual output | Expected output | Judgment |
|---|---|---|---|
| Gateway | Exact explicit text; admitted | Admit usable addressed turn | Correct |
| GI | `你好。`; one greeting speech Responsibility | WHAT-only greeting meaning | Correct, slow |
| GA | Immutable GI result; one speech Goal | Exact Goal coverage | Correct, slow |
| Fast commit | Same GI/context; empty commit at ~8.246 s | Natural immediate greeting within 2 s | Late/incomplete |
| Fast terminal | Speech ref `r1`; clock Capability and time-preface text | Speech-only `complete_response`, no Capability | **Earliest remaining wrong semantic boundary** |
| Host validator | Invalid Plan rejected before execution | Validate without semantic rewrite | Correct containment |
| Capability/playback | Not launched as successful work | Launch only from a valid canonical Plan | Correctly absent |

The Fast transaction's printed schema already forbids Capability mapping for a
speech-only source Responsibility. This isolated case therefore does not show a
missing prompt rule and does not justify a greeting-specific patch.

## Unchanged deployed aggregate

The complete directory-discovered must-pass stage then ran once without source,
service, model, or warm-state changes:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
Result: 5/51 hard-passed; 46 hard-failed
Evidence: Level C-preview, dirty source, incomplete runtime identity
Semantic review: pending
```

| Non-overlapping primary result bucket | Cases | Representative evidence |
|---|---:|---|
| Passed | 5 | Three simple body requests, one filler request, one social response |
| Goal Interpretation | 5 | Binding/provenance or relationship/unresolved contract rejection |
| Goal Association | 2 | Structured-output validation failure |
| Fast Planner | 35 | Invalid JSON/DTO, invented fields/Capabilities, timing/resource conflicts, truncation, or missing communication |
| Deep Planner | 1 | Invalid Goal-outcome coverage |
| Preview evidence limitation | 3 | Deterministic reflex requires non-preview execution evidence |

This classification assigns each case once by its primary user-visible failure;
some concurrently running roles also failed. Of 39 retained Fast timings, zero
met the two-second GI-handoff-to-commit target: minimum 9.795 seconds, median
12.228 seconds, maximum 14.586 seconds. The aggregate greeting repeated the
clock-Capability error with GI at 2.676 seconds and Fast commit at 10.685
seconds. This broad distribution rejects the hypothesis that only the greeting
wording is defective.

## Latest supervised voice diagnosis

After that aggregate, the operator ran the dirty source through device
microphone and speaker mode. The latest bundle retains two current-session
turns and their raw model transactions:

```text
SID 97957fa9: `你好。`
  ASR 126.5 ms -> Gateway greeting/admit 2.416 s
  -> GI accepted one greeting speech Responsibility 8.552 s total
  -> GA created one greeting Goal 7.308 s [concurrent with Fast]
  -> Fast empty commit at 9.547 s; terminal result at 10.645 s
  -> raw Plan invented chromie.clock.local + `现在的时间是。`
  -> Host rejection -> fixed failure speech; session total 27.33 s

SID 17c7c47a: Chongqing rain request
  ASR 199.3 ms -> Gateway request/admit 626.1 ms
  -> raw GI output translated exact source `重庆` to `Chongqing`
  -> provenance rejection at 11.572 s; GA/Planner/weather not invoked
  -> same fixed failure speech; session total 18.16 s
```

Both model calls completed with `done_reason=stop`; neither was a timeout,
truncation, HTTP failure, or TTS failure. The GI prompt explicitly requires the
source-language location surface, and the Fast contract requires ordinary
speech to use `complete_response`; the raw Qwen outputs violated those existing
rules. The earliest wrong boundaries are therefore deployed-model inference in
GI and Fast. Deterministic Host validation correctly contained each invalid
result. Its shared failure utterance makes distinct upstream faults sound
identical but is not their cause.

The same model slot alternated 16K GI and 32K Fast requests. Provider records
showed load durations of 3.80 s for greeting GI, 3.87 s for greeting Fast, and
7.81 s for weather GI. This is a measured latency contributor; the exact
internal Ollama eviction/reload mechanism was not independently proven. The
failed greeting Goal also remained active when the weather turn began; whether
failed planning should retain that Goal is an open recovery-state question,
not an authorized change in this delivery.

## Implemented repair

- `OllamaClient.generate_complete()` and `generate_stream()` use `/api/chat`,
  send system/user messages separately, consume `message.content`, and enforce
  non-thinking output. Existing test-fixture response shapes remain accepted at
  the decoder boundary.
- `scripts/warm_ollama.sh` uses the same `/api/chat` path as production.
- `docs/CONFIGURATION.md` owns the updated transport/warm-up statement.
- A discovered must-pass `speech_identity_latency` case now covers exact
  `你好。`, no Capability, one speech Goal/outcome, a Fast communicative act, no
  Fast contract failure, and the existing warm latency budgets.
- The runtime-exception-boundary body hash changed; its reviewed classification
  remains `narrow_reraise`.
- No prompt, Schema, DTO, model, profile, semantic authority, retry, execution
  policy, configuration key, architecture term, or current document was added.

## Why the previous optimization did not fix hello

The Fast v33 and Deep v15 work fixed Codex `gpt-5.6-sol` as the candidate and
measured the prompt + schema + decoder + Host transaction offline. It never used
the local/deployed Qwen model as a Planner proxy. Those strong mechanical and
non-independent same-model results are useful contract evidence, but they are
not evidence that the RTX 4090 `qwen3.5:4b` can follow the transaction.

The target profile uses one Qwen model for every semantic role and
`OLLAMA_NUM_PARALLEL=1`. That serializes the GA/Fast work the architecture starts
concurrently, while the new case proves this Qwen Fast result is also
semantically invalid. The new current run hard-passed only 5/51 must-pass cases;
prior all-Qwen evidence had retained 0/50. The root project gap is qualification of the real
deployable model/resource profile, not absence of a hardcoded greeting rule.

Verdict after the frozen aggregate: **NO PROMPT CHANGE RECOMMENDED**. The next
comparison target is the complete deployable model/resource transaction.

## Retained evidence

Pre-change voice workflow:

```text
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.json
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.md
```

Pre-change bundle:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_212025.tar.gz
SHA-256: 390186fa3f9ffd22d87b429b0454289bd4ebe9a88eeb2b2c0a1dc1edce40145b
```

Post-repair formal greeting:

```text
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/
Result: 0/1, score 40, hard failure
Evidence level: C-preview, private, live text
Workflow SID: 65f84c93
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/01-must_pass-speech_identity_latency-standalone_greeting_one_natural_reply/session-workflows/20260904T14094030079-65f84c93.json
```

Post-change bundle, collected once after the formal case:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_221033.tar.gz
SHA-256: 386c50d9bd1844dead9a2e12da71705535c8da74054ea12c5d37dc8841c2660b
```

Unchanged must-pass aggregate and its one post-run bundle:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
/home/chromie/Downloads/chromie_debug_bundle_20260904_230315.tar.gz
SHA-256: e26db4bbaee0bfa9de7374d7ec81564e78a72e77993963e59b5150fde4907f4a
```

Latest supervised device-mode diagnosis (supersedes the preliminary `231903`
collection for these two turns):

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_232045.tar.gz
SHA-256: 4c8644003dad8f013999f98133bd2493aca52ae5af3a28e6d7cb0515cef3e959
Workflow: session-workflows/20260904T15174264392-97957fa9.json
Workflow: session-workflows/20260904T15191722733-17c7c47a.json
Source: 46b6fe90a36179e63da36f086ac2b04ed8e7b3c1 plus the listed dirty patch
Runtime: Ollama 0.33.2; all roles qwen3.5:4b; GI num_ctx=16384;
Fast num_ctx=32768; think=false; chat/chat_stream transport
```

Do not treat two earlier invocation-error directories as model evidence:
`qwen-chat-transport-must-pass-aggregate-20260904` rejected an unsupported
runtime-identity schema before inference, and
`qwen-chat-transport-must-pass-aggregate-rerun-20260904` used the MCP server
root rather than `/mcp` and received HTTP 404 preflight failures. No debug
bundle was collected for either invalid attempt.

The formal run used a dirty source tree and recorded incomplete runtime identity.
The latest device-mode trace is supervised diagnostic microphone/speaker
evidence, not a formal acceptance run. Neither artifact is clean
committed-revision, simulator, robot, safety, or release evidence.

## Validation

- Focused transport/runtime/scenario suite: 65 passed.
- Repository policy: 15 rule families, zero exceptions.
- Test ownership: passed.
- Canonical `./scripts/run_tests.sh`: passed, including 140 pytest, 2058
  unittest, and 20 legacy Agent tests.
- Unchanged current deployed must-pass aggregate: 5/51 hard-passed; 46
  hard-failed; semantic review pending.
- Latest device-mode diagnosis: two admitted turns, two distinct model-semantic
  failures, both correctly contained and rendered as the same fixed failure
  speech. No post-diagnosis source repair or acceptance rerun was performed.

## Runtime state and exact resume commands

At delivery review, the Host launcher and `python -m orchestrator.orchestrator`
were still running. The four main Compose services (`chromie-agent`,
`chromie-llm`, ASR, and TTS) were healthy, but Ollama `/api/ps` reported no
resident model. The latest retained voice run had also reached
`soridormi-runtime-mcp` and MuJoCo startup checks. Do not infer warm model state
or other service health from the still-running Host process.

Inspect first:

```bash
git status --short --branch
git diff --check
docker compose ps
curl -fsS http://127.0.0.1:11434/api/ps
```

If the Agent image or Ollama process has changed, restore the tested transport
and context state before evidence collection:

```bash
docker compose build chromie-agent
docker compose up -d chromie-agent
docker compose restart chromie-llm
./scripts/warm_ollama.sh qwen3.5:4b
```

Start the Host in the repository root when supervised voice use is intended:

```bash
CHROMIE_OPERATOR_MODE=voice_mujoco ./scripts/start_orchestrator.sh
```

Do not tune the single greeting next. Use the retained 5/51 aggregate to compare
the smallest deployable model/resource-profile change while keeping the frozen
cases and one-authority contracts fixed. Reproduce the dominant Fast failures,
then check the GI, GA, and Deep buckets. Rerun the complete cohort after the
chosen change before broader claims.

Repository-only revalidation:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

## Claim boundary

This delivery repairs the observed Agent endpoint mismatch and the warm-up
context mismatch. Tests verify those source contracts. The formal and later
device-mode cases prove the greeting reaches GI, GA, and Fast and that Host
validation rejects the invalid Plan; the weather turn proves GI can separately
violate explicit source-language provenance. The aggregate proves the current
all-Qwen profile is broadly unqualified—5/51 hard passes, with no retained Fast
timing meeting target—but does not qualify a replacement or normal physical
voice behavior. Clean committed-revision provenance, semantic review,
robot/sim behavior, safety, and release readiness remain open.
