# Chromie Latest Handoff

Audience: a coding agent or operator resuming the current semantic-authority closure.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; source, tests, retained evidence, and the
checkpoint remain authoritative.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch at start: `main`
- Base commit: `e13a30405bf9b7d58976d2de8121038aa2ae5955`
- Base subject: `feat: frame fast planner presentation and terminal plan`
- Scope: tighten GI/GA/Planner prompt and schema grounding, preserve exact admitted
  source wording through the lifecycle as read-only provenance, and retain the one-stream
  Fast Planner/Planner-owned auxiliary architecture
- Expected resume revision: the latest commit containing this handoff

Bootstrap on another machine:

```bash
git clone https://github.com/TimeTreker/chromie.git
cd chromie
git switch main
git pull --ff-only origin main
git status --short --branch
```

## What changed

The exact admitted user wording now has one lifecycle owner and one downstream rule.
`UserTurnEnvelope.original_input.text` is the sole stored source. GI receives that exact
wording once in an explicit source block. `CognitiveWorkRequest` computes a digest-bound
read-only projection for GA and Planner, and rejects an invalid/spoofed projection. Runtime
retains the full envelope as metadata without interpreting it.

Planner result/state re-entry now prefers the exact original input over its whitespace-
normalized transport copy. The Host projects the exact text plus SHA-256 into re-entry
context, but keeps `request.text` and all Responsibility/Goal/Plan/Evidence projections
restricted to the affected Goal subset. The full turn is therefore visible for fidelity
and correlation but cannot revive or narrate an excluded sibling. Prompt labels now state
the authority boundary directly: GI owns current-turn WHAT, GA owns continuity, and
Planner owns HOW from accepted Responsibilities/Goals.

Project Charter principle 44, `AGENTS.md`, and `CONTRIBUTING.md` now require every future
delivery commit/push to update this handoff and `DEVELOPMENT_CHECKPOINT.md` in the same
commit with truthful evidence, blockers, revision context, and next commands.

GI no longer calls a second coverage model or performs certificate-driven source
resegmentation. The primary result now carries each Responsibility's inclusive source
token span together with its mode, bindings, Goal relationship, and sibling relations.
Trusted code checks only closed mechanics and provenance.

Logical call budgets are:

- resolved valid primary meaning: one `goal_interpretation` call;
- mechanically malformed primary DTO: one optional
  `goal_interpretation_contract_repair` call;
- genuinely unresolved meaning: one optional `goal_interpretation_deep` call;
- semantic or authority contradiction: fail closed without a reviewer;
- one mechanically malformed Deep location citation may use the one constrained
  `goal_interpretation_deep_contract_repair` allowed at that stage.

Repository policy now rejects the retired GI coverage stage/certificate/payload and
acceptance-wrapper names. Scenario fixtures contain explicit primary source evidence
and no longer expect semantic repair of noncanonical pace bindings.

GA now uses one `goal_association.primary` call for a valid result. Only a
Pydantic-invalid primary DTO may receive one `goal_association.contract_repair`; that
prompt receives the malformed object and exact validation errors, but no user turn,
candidate Goal projection, or identity context, and may not change semantics. The old
responsibility-coverage certificate, fresh interpretation, and final-audit model calls
and their DTO/schema/prompt/validation surfaces are removed. Grounding, Responsibility
conservation, binding, and continuity validation run deterministically after parsing and
fail closed without another model call.

The streaming Fast result, canonical Fast Plan, and Deep Plan now each require their
complete Goal/Evidence truth, exact wording, provenance, step ownership, and satisfaction
decision in the primary result. The separate truth qualifier, retained
response review, and coordinated Goal-coverage review calls are removed together with
their DTO/schema/prompt surfaces, `planner_audit.py`, dedicated truth-model client,
runtime health field, environment key, and warm-model role. Trusted validation remains
mechanical; one existing semantics-preserving DTO repair or a distinct Fast-to-Deep
escalation is not a second same-owner semantic review.

The DBOS misunderstanding is removed rather than preserved as a dormant compatibility
path. `CapabilityRuntime` directly tracks in-process `asyncio.Task` submissions; the
optional DBOS dependency, runtime-backend interface, DBOS adapter, model-facing
durability flag, and their tests are deleted. A future inter-process event transport
must start from a proven domain message contract instead of reviving this speculative
backend surface.

General-ability live acceptance no longer uses a central index. The former
`scenarios/general_ability_acceptance.json` is deleted and every scenario now owns its
metadata in one file beneath `scenarios/general_ability/`. Directory discovery currently
finds 50 must-pass, 15 core, and 8 challenge cases. The runner completes every selected
must-pass case and reports all failures before the stage gate can block core/challenge.
This layout is directly shardable and can later be imported into a database without
changing scenario identity or maintaining a second registry.

The current worktree applies the owner-approved Social Attention amendment. A
`PresentationCommit`, terminal Fast result, or canonical Fast/Deep Planner primary result
now owns zero or more `auxiliary_activities[]` under exact primary anchors. The field is part
of Plan fingerprint/revision truth but structurally separate from Goal-owned `steps[]`
and cannot affect completion. The independent Planner/DTO/endpoint/client/model settings
and Host background opportunity queue/worker are deleted.

Runtime performs exact mechanical validation and then executes or suppresses the
Planner proposal. It cannot choose another gesture or target. Accepted requests use
`source=canonical_plan_auxiliary_activity`, `auxiliary_plan_activity=true`, and empty
`source_goal_ids`. Auxiliary-only failure, completion, or target drift cannot create a
`CognitiveOpportunity`; there is no legal Goal ID to attach. Explicit user-requested
gestures remain ordinary Goal-owned Plan steps.

Issue [#32](https://github.com/TimeTreker/chromie/issues/32), **Streaming Planner with
Early Typed Presentation Commit**, is implemented in source as the sole `/fast-advance`
path. The Agent makes one Ollama text-streaming invocation with ordered closed
`presentation_commit` and `terminal_plan` payload frames, then emits typed NDJSON:
one complete validated immutable `PresentationCommit`, then one terminal result or a
typed pre/post-commit failure. GA starts concurrently. Runtime may launch only the exact
committed communication and its anchored auxiliary proposal; all Goal Work waits for the
terminal result, GA binding, and canonical validation. The terminal frame, Fast advance,
and CanonicalPlan must reference the same commit. The separate endpoint, DTO, model/config
role, client method, and compatibility path are removed.

## Evidence ledger

Current automated evidence:

```text
python scripts/test_matrix.py goal-interpretation
Ran 38 tests ... OK

python scripts/scenario_runner.py \
  --suite goal_interpretation --suite cognitive_core_dialogue
Behavior scenarios: 31/31 passed

python scripts/check_repository_policies.py
Repository engineering policies passed (15 rule families, 0 reviewed exceptions)

pytest -q tests/test_goal_interpreter_llm_prompt.py \
  tests/test_goal_association_pr2.py tests/test_fast_planner_pr3.py \
  tests/test_planner_reentry_policy.py \
  tests/test_capability_result_evidence_reentry.py \
  tests/test_cognitive_runtime_pr7.py
331 passed, 10 subtests passed

./scripts/run_tests.sh
Ran 2012 tests; FAILED (4 failures)

python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class planner_goal_semantic_quality \
  --ability-class composable_action_planning \
  --ability-class multi_goal_daily_life --no-write
General ability acceptance: 18/18 distinct cases passed mode=level-a evidence=A

python scripts/check_docs.py
Documentation checks passed: 96 Markdown files

python scripts/check_test_ownership.py
Test ownership checks passed
```

The current full local gate is not closed. Its four failing test surfaces are:

- `test_behavior_truth_suite` and `test_cognitive_runtime_acceptance_pr7` retain
  related Level A multi-Goal/order behavior failures;
- `test_general_ability_acceptance` reports five failed `multi_goal_daily_life`
  cases from the same current scenario cluster;
- `test_semantic_task_continuity` expects the older literal phrase
  `Interpret this turn under the system WHAT-only contract`, while the current
  prompt says `Apply the system WHAT-only contract...`.

Treat the first three surfaces as one likely shared behavior cluster until workflow
evidence proves otherwise. Do not make them pass by changing expected ordering or
weakening validation. The literal prompt assertion should protect a semantic contract,
not freeze incidental wording.

The former local Ollama 0.32.14 / `qwen3.5:9b` structured-JSON probe emitted its ordered
members normally, but that wire protocol is now superseded. The current internal model
stream is text containing a closed `<presentation_commit>` payload followed by a closed
`<terminal_plan>` payload; it requires fresh protocol and behavior qualification.

Pre-fix live iteration 50 on RTX 4090/Qwen3 4B remains diagnostic evidence only:
32/36 cases were contract-valid, four legacy coverage-stage calls returned HTTP 503,
and approximately 25/36 passed strict semantic judgment. It does not exercise or
qualify the new source.

The post-Planner-change 50-case must-pass aggregate is retained at
`.chromie/acceptance/general-ability/20260828T101824Z-live-text`: 8/50 machine passes,
42 hard failures, and no core/challenge start. Runtime identity SHA-256 is
`c8b3fc0991b72d38dade6c7b38020353199c04cc3126eaae735bd42c5e53c9cc`; the source tree
was dirty, so this is diagnostic C-preview evidence only. The valid post-cohort debug
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20260828_183021.tar.gz`.
The retired Planner review families were absent; GA primary acceptance improved from
18/45 to 43/44 relative to the immediately preceding aggregate. Remaining clusters are
16 foreground-deadline failures, seven Runtime timeouts, four GA-stage failures, four
GI transport timeouts, and 26 fail-soft Social Attention timeouts. All 42 hard failures
were judged failed; manual semantic inspection of the eight mechanical passes also
rejects `capability_inventory_truthful` because it does not actually list a capability.
Independent multi-model semantic review, physical microphone/speaker evidence,
simulator execution, and physical robot evidence remain absent.

The current post-admission cohort is retained at
`.chromie/acceptance/general-ability/20260828T153643Z-live-text`: 0/50 hard-pass on dirty
RTX 4090 Laptop/Qwen3 4B C-preview identity
`86a04a8da490c02918545d2dfe01674800b516e5cf0b80e838b34a06c9906546`.
The mutually exclusive earliest clusters are 24 GI source-span overlap rejections, eight
GI `ReadTimeout`s, one GI whole-turn binding rejection, six GA timeouts, three foreground
deadlines, four other Runtime timeouts, two preview-only reflex cases, one canonical Fast
timeout, and one speech-only semantic miss. Its exactly one post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260828_234314.tar.gz`. Raw GI output proves
the dominant 4B failures duplicate effects, invent relation Responsibilities, cite
overlapping spans, and mislabel body actions as speech. Trusted validation is the correct
fail-closed boundary and must not be weakened or followed by semantic repair.

The GI-only model comparison is retained at
`.chromie/acceptance/general-ability/20260828T155554Z-live-text`: `qwen3.5:4b`
hard-passed 2/50 cases. Of 48 GI-invoked cases, 18 reached an accepted interpretation,
25 timed out, and five failed closed semantic/authority validation. Sixteen of the 18
accepted results still contained spurious unresolved meaning. The exactly one comparison
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20260829_000338.tar.gz`.

The current profile change keeps `qwen3.5:4b` in a bounded 16K/512 GI runner beside the
unchanged 32K `qwen3:4b-instruct-2507-q4_K_M` downstream runner and allows both models to
remain resident. A focused residency experiment proved that this removes the alternating
post-downstream GI eviction pattern. A two-request Ollama experiment was rejected: it
expanded the 32K Qwen3 runner to 65,536 tokens, exceeded the shared 16GB envelope, evicted
GI, and still could not admit the maintained Fast prompt at a smaller context. No
non-GI model identity changed. Prompt/schema attempts to suppress qwen3.5's false
ambiguity did not change its output and were removed rather than retained as tuning.

The complete post-change cohort is retained at
`.chromie/acceptance/general-ability/gi-qwen35-default-fixed`, bound to runtime identity
`78847784d3ff08df8b606fb921eb28010a0e87f34b146da41c4fabe1cc9341b8` and source-tree
SHA-256 `faa4f665b33d63ad2c45347f36dff85afd47b7623d65297bdd1f200d0733043d`.
It mechanically hard-passed 2/50, but both passes retained invented unresolved meaning;
strict manual semantic judgment is therefore 0/50. Compared with the pre-default cohort,
top-level retained GI results rose from 17 to 29 and explicit GI `ReadTimeout` cases fell
from 25 to six. Twenty-six of 29 retained results still carried false unresolved meaning.
The 48 mechanical failures cluster into 13 GI availability/outer-deadline cases, three GI
numeric-binding authority rejections, 30 downstream failures (including multi-turn
predecessor failures), and two preview-only reflex limitations. The exactly one
post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260829_063447.tar.gz`.

## Resume commands

Inspect and close the known local-gate failures first, then rerun local closure:

```bash
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

Do not rerun or append to `.chromie/acceptance/general-ability/gi-qwen35-default-fixed`;
the complete 50-case must-pass stage and its one debug bundle are retained. Start from the
two independently reproduced blockers: qwen3.5 emits false unresolved meaning that invokes
Deep GI and consumes the outer deadline, while the unchanged single Ollama request slot
serializes concurrent GA/Fast work. Do not repair either by weakening GI validation,
Host resegmentation, another same-authority model call, or changing a non-GI model role.

Typical deployment inspection commands remain:

```bash
docker compose build chromie-agent
docker compose up -d --no-deps chromie-agent
docker compose ps chromie-agent
ss -ltn '( sport = :8000 or sport = :5555 )'
```

The exact live profile/manifest commands are owned by `docs/ACCEPTANCE.md` and
`benchmarks/manifests/e2e_evidence_profiles.json`; do not copy a historical command if
those authorities have changed.

## Next evidence boundary

The auxiliary amendment's canonical source gates are complete. Issue #32 now uses one
model text stream with two closed tagged JSON-payload frames rather than one top-level
structured JSON object. It requires the full canonical source gates plus fresh
current-target qualification; the superseded structured-JSON probe is not evidence for
this wire path. After source gates, measure accepted-commit, TTS first
PCM, playback start, terminal Plan latency, commit/terminal consistency, and GPU
residency/contention before Fast-Planner Prompt/model promotion. Do not weaken validators,
add Host resegmentation or another semantic reviewer, or treat auxiliary decoration as
Goal completion.

## Claim boundary

This is development-only. Automated tests prove the local contract, not current-model
semantic quality or live robot behavior. Historical live evidence may diagnose the old
chain but cannot qualify the new one.
