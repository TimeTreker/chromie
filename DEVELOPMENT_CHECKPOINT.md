# Chromie Development Checkpoint

## Current continuation — GA object-shape candidate; promotion withheld

The Goal-driven single-authority architecture remains the target. Active Issue #35. Candidate branch `codex/ga-request-format`; pre-delivery parents are
`ea2ae1a080d18062fb75c8c7bf46fd5bf8a6c68c` and maintained main
`08890f844d21eb75e939f36dbed03188e6abd2df`. Expected candidate resume revision is the
latest commit containing both checkpoint and handoff. This merge brings the existing
Fast numeric guard onto the candidate and adds one GA decoder-representation repair.
Main remains the maintained deployment line. Fixed SGLang/shared Gemma4-12B on RTX 5090;
ASR/TTS retain their own models. No prompt or model changes in this repair.

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

Validation on the candidate: focused GA/Fast 202 tests / 45 subtests; canonical gate 2311
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
isolated. Generated
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


## Retained baseline and claim boundary

Migration baseline `9df52609` selected shared Gemma4-12B on SGLang; laptop configuration
is unchanged. The previous Ollama Gemma Q4 full preview also had 0/51 qualified cases.
Earlier Qwen/SGLang versus Ollama latency trials used different model/precision/topology
and are not a controlled backend comparison. See HANDOFF.md and retained comparison
reports under `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/` and
`.chromie/acceptance/sglang-switch-rtx5090-20260909/` for exact inputs and results.

GI binding-schema ordering, frozen primary-screen corpus, raw-output/termination retention
and the 1496-reference audit remain preserved. The current candidate milestone is defined
above; rejected field-layout/global-format experiments remain evidence only. Keep source
and deployed identity distinct. Never count containment as successful behavior or reuse an
old cohort as proof for a changed revision. Current-revision physical voice and default
target-evidence closure remain open. The one-authority architecture remains binding.
