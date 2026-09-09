# Chromie Development Checkpoint

## Current continuation — Fast numeric argument guard; GA candidate isolated

Active Issue #35 on main. Delivery base: `8e2ad455ebcdbd4890a8da695099c16c04b3fbc1`
(the GA typed-binding conservation guard, already pushed). Expected resume revision is
this latest main commit containing both checkpoint and handoff. SGLang/shared Gemma4-12B
remains selected for RTX 5090; ASR/TTS remain specialized. This milestone changes only
Fast Planner deterministic validation and its regression coverage, not prompts or models.

Originating case: `blink_once_plain_request`, session `d161936c`, input “眨一下眼睛。”
The completed request-format candidate preserved GI count 1 and GA Goal count "1", but
Fast emitted blink count 2 with intensity 1.0. The old Host numeric collector accepted
that unrelated 1.0 as conservation evidence; its later direct-input check excluded
optional/defaulted arguments. This was a wrong model decision plus a confirmed Host
containment hole, not a successful action or evidence that Gemma cannot serve the role.

| Actual owner / handoff | Material input and output | Verdict / repair effect |
|---|---|---|
| GI WHAT | Exact turn -> r1 body_action, count 1, source t0..t5 | Correct in originating case; immutable r1 feeds GA and Fast concurrently |
| GA Goal continuity | r1 count 1 -> exact-Schema Goal count "1" | Correct in originating candidate case; does not repair Planner |
| Fast HOW stream | Same r1 and blink catalog -> silent presentation, terminal count 2/intensity 1.0 | Wrong terminal decision; expected count 1 |
| Fast Host validation | GI binding plus unchanged Capability args -> previously execute | Now checks each same-named numeric input per source ref, including optional/defaulted fields; rejects contradiction before executable work |
| Host join / preview | GA result plus validated Fast result -> previously wrong two-blink preview | Repaired replay returns unavailable and zero Activities; no physical provider dispatch was invoked |

No new semantic authority, model call, prompt, current document or runtime switch is
introduced. The guard never rewrites args or invents cross-name/unit mappings. Existing
other realization checks remain. Exact retained-stream replay changes execute(count 2)
to unavailable with zero Activities and one model call. Seven regression contrasts
reject four wrong/omitted numeric arguments with decoy values and preserve three valid
cases, including an unbound default. A narrow audit of all 46 readable Fast terminals
from the candidate finds only the originating blink conflict with this added invariant.

Focused current-main live session `8f6c0484` independently emitted count 2 for GI count 1;
the new guard rejected it, with no action preview. This is containment, not a successful
blink (0/1 behavior). The subsequent immutable 51-case main preview finished: 1 mechanical,
0 reviewed transaction passes. B. merely echoed B.; both its GA outputs also fail exact
Schema. All 49 GI raw outputs pass Schema but one fails duration provenance; all 96 GA
outputs (48 primary / 48 mechanical repair) fail exact Schema. 48 Fast streams and one
failed Deep output are retained. Full-run blink has Fast count 1 but fails at GA; do not
claim that full case proves the new count guard or successful behavior. Main remains
0/51 qualified, as before. No physical voice/effects, target closure or release claim.

Validation: focused Fast/binding tests 146 passed / 7 subtests; canonical gate 2306 tests /
283 subtests, 140 benchmark checks and 20 legacy tests passed. Policies, docs and test
ownership pass. Level A robust intent 8/8; capability grounding 7/7 and composable planning
5/5 (10 distinct scenarios across those last two overlapping classes). These are offline
proofs. Source remained unchanged throughout the full live cohort; one bundle followed it.

Evidence root: `.chromie/acceptance/fast-numeric-argument-20260909/` (local, not uploaded).
Start with `root-cause-report.md`, `replay-results.json`, `behavior-review.json`, all 51
`reviewed-cases/`, and `runtime-identity.json`. 199 retained raw calls include the focused
run; 194 are linked to the full cohort. One post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_202626.tar.gz`.
Deployed Agent image: `sha256:63cabb1e5e863b204aa97e86acbb2f11eb2568dcaa18db2e9fffef4382d4cac7`;
all 70 `agent/app` files match source. SGLang remains the maintained image
`sha256:2f425788c02f2502fd5541455f4917819759352b68e8b8b987bee750204c11ac`.
All four services were healthy after deployment; no physical Orchestrator was started.
Generated `.env.runtime` remains authoritative and was not edited directly.

Separate candidate `ea2ae1a080d18062fb75c8c7bf46fd5bf8a6c68c` is pushed on
`codex/ga-request-format`, not promoted to main. It removes proven redundant GA Schema
intersections and requests compact whitespace only for GA via the existing request
boundary/pinned provider patch. 2377 distinct mutation verdicts are unchanged; provider
proof rejects eight malformed single-count variants. Full candidate cohort: 15 mechanical /
8 reviewed preview passes, with unsupported reminder promises, resource/provenance and
other failures still open. The original wrong blink was found in that full review.
Candidate gates: 2308 tests / 291 subtests. See its branch checkpoint/handoff and
`.chromie/acceptance/ga-request-format-20260909/candidate-report.md`; its bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260909_200451.tar.gz`.
The current main deployment does not contain that candidate. Prior global-format and
primary-layout candidates also remain withheld; their evidence is retained under
`.chromie/acceptance/ga-decoder-redundancy-20260909/` and
`.chromie/acceptance/ga-primary-layout-20260909/`.

Next: bring the current main guard onto the candidate branch before further qualification.
Repair the reproduced XGrammar candidate-aware root-allOf/required-sibling mismatch:
two exact valid fixtures (49acd63b… and ffaca21f…) are rejected while an abbreviated
object missing required siblings is accepted. Preserve independent conditions; prove
valid and malformed variants with actual grammar acceptance before another immutable
live cohort. Separately retain GI framing, prohibition, unresolved-reference and future
reminder classification failures. Do not introduce another semantic repair call or switch
Gemma. Speed/backend superiority and physical acceptance remain unproven.

Resume commands:
```bash
git show origin/codex/ga-request-format:HANDOFF.md
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/check_test_ownership.py
```
Use `.chromie/acceptance/fast-numeric-argument-20260909/preview.log` and the retained
identity for exact live invocation context. Stop speech services before any LLM restart
because transient model-load memory can exceed capacity; restore cached speech with the
existing `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` overrides if its proxy is unavailable.
Preserve unrelated Soridormi working-tree changes.

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
