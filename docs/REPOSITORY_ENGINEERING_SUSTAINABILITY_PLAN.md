# Repository Engineering Sustainability Plan

Status: current repository-proof and simplification plan; active Issue is
**Close Current-Revision Target Evidence**

This document records engineering recommendations accepted after
repository-wide external reviews and decomposes them into independently
closable Issues. The first intake produced the completed safeguards retained
below. A 2026-07-31 current-tree re-audit opened a second, evidence-first set of
Issues because the remaining repository size and configuration surface were not
resolved by one greeting extraction, a four-file Mypy ratchet, or documentation
indexing. Validation during that re-audit also found and drove repair of a
non-reproducible canonical local gate. The current-revision live proof now
precedes broader target evidence and structural work.

The plan is intentionally not one broad refactor. Each Issue must preserve the
Goal-driven single semantic authority, deterministic Host safety boundaries,
Soridormi embodiment ownership, current evidence honesty, and existing runtime
behavior unless that Issue explicitly owns a reviewed behavior correction.

## Program objective

Turn Chromie's existing engineering principles into durable repository
mechanisms while reducing the maintenance risk of the oldest implementation
surfaces.

The governing principle is:

> Thinking belongs to the LLM. Engineering guardrails validate implementation;
> they must not implement intelligence.

This program therefore may validate source structure, types, configuration,
network exposure, failure handling, and tests. It must not add keyword-to-skill
rules, benchmark-conditioned cognition, Host-authored social behavior, or a
second semantic authority.

## Intake decisions

The external review is treated as evidence and advice, not as an authoritative
work order. Every recommendation was filtered against the current architecture,
qualification priorities, hardware profiles, and project principles.

### Accepted

The following recommendations identify real, general engineering risks and are
included in the Issue backlog:

- bind local development service publications to host loopback by default;
- make silent failure handling and production invariants explicit;
- enforce repository engineering policies mechanically rather than relying only
  on prose and reviewer memory;
- introduce high-signal linting without a repository-wide formatting rewrite;
- introduce type checking incrementally at clean contract and runtime boundaries;
- replace behavior tests that merely inspect implementation strings while
  retaining legitimate architecture and artifact-contract checks;
- parse service configuration once into typed service-owned settings while
  preserving generated hardware/profile authority;
- decompose the `VoiceAssistant` composition root through behavior-preserving,
  one-collaborator changes rather than a broad rewrite;
- reduce documentation duplication while retaining documentation validation and
  evidence distinctions.

### Accepted with constraints

These recommendations are useful only under explicit limits:

- source-reading tests are not all invalid: behavior expectations should become
  executable tests, forbidden architecture should become AST/static policy, and
  literal generated-artifact contracts may remain content tests;
- caught cleanup exceptions should not all become error logs: expected
  best-effort cleanup may use narrow suppression or debug evidence, while model,
  service, execution, and evidence failures must remain visible;
- Mypy should start with selected modules and ratchet outward; whole-tree strict
  mode is not an initial exit criterion;
- Ruff should begin with high-signal defect rules; this program does not authorize
  a broad style-only rewrite;
- resource limits may be introduced later in deployment-specific profiles only
  when measured workload evidence supports them.

### Deferred or rejected

The following recommendations are not part of the current program:

- a big-bang rewrite of `VoiceAssistant` or the Host Orchestrator;
- full-tree strict type checking in one change;
- mandatory Black formatting or broad style normalization of the existing tree;
- blanket deletion of every test that reads source or generated files;
- blanket error logging for expected cleanup failures;
- Git LFS for the current small reference-audio footprint;
- hard CPU or memory limits in the main hardware qualification profile without
  measured profile-specific evidence;
- authentication retrofitted casually into local internal APIs without a
  separate remote-deployment trust and identity design.

### Accepted from the 2026-07-31 review

- restore one hermetic, dependency-complete canonical local gate before making
  a fresh automatic-verification claim;
- retain one current-revision live microphone-to-audible-response proof before
  further structural work;
- continue decomposing `VoiceAssistant` at real lifecycle seams instead of
  treating the first greeting collaborator as closure;
- inventory and reduce the supported configuration surface around maintained
  deployment profiles;
- expand Mypy by owned package rather than isolated files;
- classify every broad runtime exception boundary and mechanically reject new
  unreviewed handlers;
- shorten the README and the core reading path, merge duplicated tracing
  documentation, and remove in-tree archives after their provenance value is
  confirmed to exist in Git history;
- require an explicit growth justification for new documents, flags,
  compatibility paths, and architectural terms.

### Accepted with constraints from the 2026-07-31 review

- `1,500` lines per file, `40` methods per class, fewer than `15` booleans, and
  `12–15` total documents are useful pressure tests, not immediate mechanical
  gates. The first patch for each Issue must establish an owned baseline and a
  behavior-preserving reduction target.
- Some top-level service boundaries and best-effort cleanup paths legitimately
  catch broadly. Each must still be explicit: narrow the exception, re-raise,
  map it to a typed failure, fail closed, or preserve the primary failure while
  recording an expected-cleanup diagnostic.
- Specialized safety, interface, and evidence contracts may remain separate
  when they have a real audience and owner. An index link alone is not enough
  to justify a document.
- The proof-first freeze does not block fixes required to obtain trustworthy
  source identity, fail-closed behavior, or the retained live proof itself.

## Delivery rules

- Work one Issue at a time. Only one Issue from this program may be active.
- Retain the current-revision live-proof implementation, close the default
  target-evidence profile, then close the queued grounded-response latency Issue
  before starting the structural Issues. If an evidence workflow exposes a
  defect, fix the earliest responsible boundary and rerun the same evidence
  before continuing.
- Use the semantic Issue names below; do not introduce numbered Step, Stage,
  Phase, or milestone identities.
- Re-audit the current tree at Issue start. Counts from the originating review
  are historical observations, not permanent requirements.
- Keep one independently reviewable patch and commit per coherent Issue
  activity. Do not combine feature behavior changes with structural cleanup.
- Add regression evidence before deleting an old implementation or test seam.
- Update this registry, `ROADMAP.md`, and `DEVELOPMENT_CHECKPOINT.md` whenever an
  Issue becomes active or closes.
- Use the four-axis status vocabulary in `docs/STATUS.md`. Tooling installation
  or a passing mocked test does not establish target validation or release
  readiness.
- Run the maintained full suite and documentation checks for every Issue. Add
  focused checks appropriate to the Issue.
- Do not close a reduction Issue from a prose audit alone. Record the
  before/after surface and preserve behavior at the public boundary.

## Current-tree re-audit — 2026-07-31

The originating review could not run the repository. The current-tree re-audit
therefore treats its counts as hypotheses and records reproducible local
measurements from `aedfebabe5d7f519c0a21863a75acb6918382764`:

| Surface | Current observation | Interpretation |
|---|---:|---|
| Maintained Python files | 496 | Size alone is not a defect, but changes need narrower ownership. |
| `orchestrator/orchestrator.py` | 8,886 lines | The Host composition root remains physically entangled. |
| `VoiceAssistant` | 167 methods; 615-line `__init__`; 160 distinct `self` attributes initialized | The greeting extraction did not close decomposition risk. |
| `orchestrator/runtime/conversation_state.py` | 4,424 lines | A second large state/lifecycle boundary needs ownership review. |
| Literal runtime environment keys | 295 across Orchestrator, Agent, ASR, TTS, and shared runtime | These include public, profile-owned, internal, and compatibility values; they must be classified before a reduction target is set. |
| Documented configuration keys | 321 | Documentation currently exposes more knobs than the four deployment-mode summary suggests. |
| Current Mypy ratchet | 4 files | The mechanism exists, but package coverage is not yet meaningful. |
| `except Exception` handlers | 141: 85 Orchestrator, 53 Agent, 3 shared; 57 in `orchestrator.py` | The existing gate rejects only trivially silent handlers; a complete classification is still open. |
| Markdown surface | 125 repository files, including 80 directly under `docs/`; 31,438 lines | The core reading path and specialized reference set are not clearly separated. |
| In-tree historical archives | 3 files; 237,276 bytes | They are indexed and marked historical, but Git history may be the better owner. |
| Canonical local gate | At Issue intake, `python -m unittest discover -s tests -q` ran 1,654 tests but ended with 5 failures and 8 errors; pinned Mypy reported 42 errors in 11 imported files while checking its 4-file scope | Historical reproduced baseline; the Issue and its current result are recorded below. |
| Current-revision retained live voice loop | none | This is now active and blocks broader target evidence and structural work. |

These are source observations, not automatic or target validation. Every later
Issue must refresh its own baseline because counts may change.

## Issue registry

### Current proof and simplification Issues

| Issue | State | Depends on | Purpose |
|---|---|---|---|
| Restore Canonical Local Gate Reproducibility | implemented and automatically verified | none | Make the declared dependency-light test entrypoint deterministic in a maintained working tree and environment. |
| Retain a Current-Revision Live Voice Loop | implementation verified; physical target validation deferred | canonical local gate, satisfied | Prove clean-source microphone → ASR → Gateway/Core → chat → TTS playback on a microphone-equipped host. |
| Close Current-Revision Target Evidence | **active** | canonical gate and live-voice verifier implementation, satisfied; physical voice is optional for this profile | Retain and review the complete default source-bound evidence profile before structural work. |
| Reduce Time to First Grounded Response | implementation slice landed; qualification and remaining scope open | target-evidence closure | Planless direct spoken-response composition now bypasses Fast/Deep Planner under a typed contract; retained latency/result-delivery evidence and the remaining scope are still open. |
| Classify Broad Runtime Exception Boundaries | implementation slice landed; classification review open | grounded-response latency Issue | A symbol-level checked inventory now rejects new, missing, or stale broad handlers; deeper narrowing and retained failure evidence remain open. |
| Establish Typed Host Configuration Snapshots | implementation slice landed; inventory completion open | broad-exception classification | Immutable typed startup groups now own the principal Host audio, cognition, playback, session, and evidence settings; remaining Host reads and generated documentation are open. |
| Extract Playback Delivery Lifecycle | structural ratchet slice landed; transport extraction open | typed Host settings | Playback order, generations, waiters, cancellation bookkeeping, and delivered-speech events have one collaborator; compatibility properties were collapsed and composition-root counts are now ratcheted. PCM/output transport remains open. |
| Extract Input Turn and Session Lifecycle | source extraction complete; live input evidence deferred | playback lifecycle | One collaborator owns microphone callbacks, VAD framing, ASR transport, routed-turn/reflex tasks, injected audio, pending utterances, and idle-session sweeping. Session registry storage and semantic conversation state remain separate documented boundaries; live microphone, hot-plug, and target evidence remain deferred. |
| Reduce Supported Configuration Combinations | source implementation complete; target qualification deferred | typed Host settings and live proof | Four source-controlled operator modes own complete maintained combinations. The generated inventory classifies 450 keys, public choices are ratcheted, and all compatibility aliases have been removed. |
| Expand Mypy by Owned Package | source scope expansion complete; canonical tool execution required in the normal dependency environment | stable extracted boundaries | `shared/chromie_contracts`, `orchestrator/runtime/cognitive_gateway_modules`, and `orchestrator/schemas` are package-scoped; extracted Host lifecycle modules are explicitly owned and new package modules enter automatically. |
| Reduce the Current Documentation Surface | source implementation complete | structural Issues complete | The core path is ratcheted, eight trace documents became two owned observability documents, three in-tree archives were removed, and every specialized document must now be reachable from a current owner entrypoint or a declared mechanical contract. |
| Requalify the Simplified Runtime | source qualification workflow implemented; clean dependency-complete execution and target requalification deferred | simplification Issues source-complete | Bind deterministic source gates to one revision and retain an explicit report without claiming target, audio, simulator, LAN, robot, or release evidence. |

### Completed first-intake Issues

| Issue | State | Depends on | Purpose |
|---|---|---|---|
| Secure Local Runtime Exposure | implemented and automatically verified; local target validation pending | none | Remove unintended LAN exposure from the default local Compose profile. |
| Make Runtime Failure Paths Explicit | implemented and automatically verified | none | Replace silent operational failures and production assertions with intentional, observable invariants. |
| Establish Repository Engineering Policy Checks | implemented and automatically verified | Runtime Failure Paths audit complete | Convert stable source and deployment principles into dependency-light AST/configuration checks. |
| Introduce High-Signal Ruff Gates | implemented and automatically verified | Engineering Policy Checks | Add defect-oriented lint enforcement without broad formatting churn. |
| Establish Incremental Type Checking | initial four-file mechanism implemented and automatically verified | Engineering Policy Checks | Type-check clean contracts and runtime boundaries, then ratchet coverage outward. |
| Modernize Behavioral and Architecture Tests | first intake implemented and automatically verified | Policy Checks and static gates | Replace implementation-string coupling with behavioral, AST-policy, or artifact-contract ownership. |
| Establish Typed Service Configuration Boundaries | implemented and automatically verified | static gates; tests modernized where touched | Preserve profile authority while removing repeated internal environment parsing. |
| Decompose the VoiceAssistant Composition Root | implemented and automatically verified | test modernization; typed settings where relevant | Extract independently testable collaborators without changing interaction behavior or authority. |
| Consolidate Current Documentation Authority | implemented and automatically verified | may proceed after policy checks; final consolidation follows structural work | Separate current normative truth, status, evidence, and history while keeping documentation validation. |

Closing one Issue does not automatically activate the next. The current tree,
product milestone, and retained evidence determine whether the next queued Issue
is still the correct priority.


## Program status

The first-intake implementation Issues and the canonical local-gate repair are
closed with automatic verification. The active Issue is the default
source-bound target-evidence closure. The user-visible grounded-response latency
Issue is queued immediately after that closure and before structural work. This
program does not imply release readiness or physical support; Gateway/Core,
Social Attention, provider, audio, simulator, LAN, and physical claims remain
owned by their qualification documents.

## Issue: Restore Canonical Local Gate Reproducibility

Status: implemented and automatically verified

### Problem

The documented setup says that installing `requirements-test.txt` and running
`./scripts/run_tests.sh` is the canonical dependency-light gate. On the
2026-07-31 Issue-start working tree, that contract was not reproducible:

- `requirements-test.txt` omits `pytest`, although
  `tests/test_weather_goal_scope_contract.py` imports it;
- ignored historical bytecode under `router/app/__pycache__/` makes the Router
  removal guard report that the deleted source tree still exists;
- importing the Orchestrator loads generated `.env.runtime` values into the
  process, so later unit tests inherit a deployment TTS provider and LLM
  budgets instead of their owned defaults or fixtures;
- the pinned Mypy 2.3.0 gate reports 42 errors in 11 imported files while
  checking the configured four-file ratchet.

After installing the declared test dependencies, direct unittest discovery ran
1,654 tests in 14.921 seconds and ended with 5 failures and 8 errors. This is
Level A diagnostic evidence, not a passing automatic-verification claim. Ruff,
documentation, test-ownership, and focused documentation-authority checks pass
independently; they do not override the failing policy, Mypy, and unittest
results.

### Implementation outcome

- `pytest==9.1.1` is part of the pinned test dependency boundary;
- the removed-Router guard ignores cache-only residue while focused regression
  coverage proves maintained Router source still fails;
- Orchestrator imports no longer load generated runtime configuration; the
  canonical module entrypoint invokes an explicit runtime-environment bootstrap;
- the existing four-file Mypy ratchet passes without ignores or scope removal;
- on 2026-07-31, `INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh` passed repository
  policy, test ownership, Ruff, Mypy, documentation, 1,656 primary tests, and
  20 legacy Agent tests.

### Scope

- make every dependency imported by the canonical test entrypoint explicit and
  pinned in the declared test dependency set;
- make the Router removal check reject maintained or source-bearing Router
  content without treating ignored bytecode/cache residue as deployed source;
- isolate unit tests from generated runtime configuration, or load deployment
  configuration only through an explicit runtime bootstrap that tests can
  control;
- repair the existing Mypy scope without suppressing errors, removing checked
  files, or broadening ignores, and retain a regression for each corrected
  contract boundary;
- add focused regression coverage for dependency completeness, ignored
  historical cache residue, and test-order/environment independence;
- keep the canonical entrypoint and documented setup aligned.

### Non-goals

- no weakening of the Router-removal architecture rule;
- no deletion of user caches as a substitute for a robust policy check;
- no replacement of generated runtime configuration or maintained deployment
  profiles;
- no product behavior, prompt, provider, or live-evidence change;
- no broad test-framework migration.

### Exit criteria

- a fresh environment using only the documented test setup can import and run
  every canonical test;
- ignored cache residue cannot fail the Router removal check, while any
  maintained Router source, import, service, or current contract still fails;
- relevant TTS and LLM tests pass regardless of whether `.env.runtime` exists
  or which canonical test order is used;
- the pinned Mypy ratchet passes its existing scope before any later package
  expansion;
- `INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh` passes from a maintained working
  tree;
- `docs/STATUS.md` records the fresh result before the live-proof Issue becomes
  active.

## Issue: Retain a Current-Revision Live Voice Loop

Status: implementation and automatic verification complete; physical target
validation deferred because the current host has no microphone

### Problem

Chromie has extensive Level A coverage and historical live evidence, but no
retained current-revision proof of the smallest complete user loop:

```text
physical microphone
→ final ASR transcript
→ Gateway admission
→ Goal-driven chat handling
→ validated speech
→ TTS scheduling and audible playback
```

The supervised voice runner could collect only the `speech-only` case, while
the canonical verifier required the complete seven-case voice/MuJoCo matrix and
both `chat` and `robot_action` apply lanes. The implemented named profile now
supports the smaller claim without changing the default matrix.

### Scope

- add a named narrow verification profile to the existing voice evidence tools;
- keep the complete voice/MuJoCo matrix and its release-oriented verifier
  unchanged;
- bind the run to a clean Chromie checkout, generated runtime profile, running
  service image IDs, effective models, and exact retained artifacts;
- require real microphone input, an `asr_final` event, admitted Gateway/Core
  processing, an applied `chat` lane, zero executable skills, correlated TTS
  schedule/playback completion, and an operator audible-output verdict;
- fail on critical LLM timeout, truncation, fallback after authority
  acquisition, stale playback, missing source identity, or dirty source;
- retain the exact command, logs, structured events, audio-device identity, and
  a machine-readable claim that is limited to the live speech-only loop.

### Implementation status

The `current-revision-live-voice` profile and runner integration are implemented
and automatically verified. The runner captures a digest-valid runtime identity,
binds Gateway/Core evidence to it, retains physical input/output recordings and
device selection, and hashes the exact collection artifacts. The verifier keeps
the full seven-case profile as its default and fails closed on every rejection
class in the exit criteria. Sixty-eight focused tests and the canonical 1,664-test
suite pass. Target validation remains open until one clean committed revision
produces and retains a passing supervised bundle with operator review.

Attempt `20260731T110834Z` used the supported Python 3.11.15 runtime and healthy
services but captured no input; the operator confirmed that the PC has no
microphone and directed that physical validation be skipped. No live claim is
made, and the unfulfilled physical exit criterion remains open.

### Non-goals

- no Soridormi, MuJoCo, robot-action, cancellation, or physical-robot claim;
- no weakening of the full supervised voice-device matrix;
- no new cognition, prompt tuning, deployment mode, or general evidence
  framework;
- no release qualification from one successful conversation.

### Exit criteria

- focused tests prove the narrow verifier rejects synthetic input, partial
  events, dirty or mismatched source, missing runtime identity, skills, stale
  playback, and absent operator review;
- the maintained full matrix verifier retains its existing requirements;
- a clean committed current revision produces one retained passing supervised
  `speech-only` bundle;
- `docs/STATUS.md` records the exact target-validation claim without promoting
  simulator, physical-robot, or release status;
- the canonical repository gates pass.

## Issue: Close Current-Revision Target Evidence

Status: **active**; the default profile does not require physical voice evidence

### Scope

- retain the default `source_bound_development` closure from one clean Chromie
  revision and one exact Soridormi revision;
- include live Gateway/Core text behavior, active cancellation, positive Agent
  Skill/weather execution, reviewed Social Attention, paired MuJoCo safe-idle,
  and second-machine LAN evidence;
- keep physical voice and robot claims scoped to their supervised evidence;
- fix only blockers reproduced by the maintained evidence workflow.

### Exit criteria

- every required report belongs to the initialized clean revisions;
- exact request, provider, execution receipt, response, and human-review
  fingerprints agree;
- the default closure is eligible while still reporting
  `release_qualified=false`;
- Status, Roadmap, Checkpoint, and Handoff point to the retained bundle;
- every blocker fix is regression-tested and the closure restarts from the
  fixed revision.

## Issue: Reduce Time to First Grounded Response

Status: source implementation complete; latency qualification and shared-load evidence remain open; depends on **Close Current-Revision Target Evidence**

Implementation note (2026-08-02): a typed direct-response composition branch now
lets a validated, non-effectful `spoken_response` Goal proceed from Goal
Association to Response Composer without invoking Fast or Deep Planner. The LLM
still authors the response and the Host validates goal correlation, coverage,
commitment, and completion claims. Downstream Response Composer and Tool Result
Interpreter stages reuse the exact planner-authored Agent Skill selection after
validating immutable Plan provenance. Completed earlier safe-read results now
distinguish ordinary overlap from explicit output invalidation: they wait for
the newer foreground turn and output queue to become idle, re-check
cancellation/supersession, and then deliver once through the normal
evidence-bound response path. Generation-only invalidation and cancelled
execution remain suppressive. Retained warm/cold latency and shared-load
qualification remain open.

### Problem

Chromie can acknowledge slow work early, but meaningful conversational,
proposal, and confirmation speech still often waits for a serial chain of
complete model generations. A reviewed 2026-08-01 diagnostic compound turn
reached Core-authored `fast_speech` at 3.58 seconds and audible playback at 7.19
seconds, while the terminal cognitive response was not ready until 50.32
seconds. Goal Association, Fast/Deep planning, model contract repairs/review,
and Response Composition accounted for almost all of that delay; final Host
preparation and TTS scheduling took milliseconds. Ordinary chat diagnostics
also reached first audio only after roughly 35–40 seconds, with TTS synthesis
accounting for about 1.6–2.5 seconds.

Those logs predate the latest natural-confirmation wording correction and are
diagnostic evidence only, not clean current-revision target validation. They
nonetheless reproduce the architectural problem: the important delay is late
semantic commitment after avoidable serial model work, not the deterministic
validator itself. The validator correctly caught invalid structured output and
must not be bypassed.

Source review also found a related result-delivery defect: ordinary overlapping
turns retain their work, but the current final-response staleness check compares
an earlier outcome with global playback-generation and session identity. A
newer ordinary turn can therefore make a valid earlier result response
ineligible even though its Goal completed and its evidence remains. The current
overlap scenario proves task completion but not eventual delivery of both
results; the stale-final scenario models broad generation suppression rather
than distinguishing explicit cancellation or supersession from ordinary
overlap.

### Scope

- retain and score representative direct-conversation, bounded capability,
  ambiguous, compound, and safety-relevant scenarios before implementation;
- record admitted input, first complete valid speech commitment,
  `tts_request_start`, first PCM, first audible playback, plan readiness,
  execution start, terminal evidence, final playback, model queue/evaluation,
  and contract-repair timing;
- let a complete non-effectful `spoken_response` Goal proceed from Goal
  Association to response composition without Fast or Deep Planner merely to
  transport speech;
- adapt the existing response-composition owner and typed contract to accept
  that explicitly planless direct branch; do not synthesize a dummy Canonical
  Plan or add a second response authority;
- keep complete bounded capability work on Fast Planner and invoke Deep Planner
  only for a recorded semantic escalation, unresolved ambiguity/coverage,
  nontrivial dependency, material alternative, novelty or broader context,
  safety/resource reasoning that requires wider planning, or a structured
  semantic/plan validation rejection whose failure contract explicitly requires
  broader reasoning; technical schema/model-contract failure receives bounded
  same-tier repair, and any later Deep recovery remains explicitly classified,
  retains the Fast failure, and fails closed unless it produces a valid plan;
- treat confidence as one semantic observation, never as execution authority or
  permission to bypass effect and safety validation;
- schedule complete independently schema-valid `fast_speech` or `ResponseStage`
  values without waiting for unrelated later fields only after Host validation
  authorizes them against the applicable correlation, commitment/evidence
  state, claim guards, and cancellation generation;
- extend the existing response-stage and Host delivery owners so dedicated
  safety/control evidence may pre-empt output, ordinary progress/results remain
  ordered until an appropriate speech opening, and internal-only evidence
  updates state without creating a speech stage; result arrival alone never
  grants permission to interrupt;
- separate cancellation of already-playing or obsolete queued audio from
  eligibility of an independent Goal's later evidence-bound result, preserving
  that result across newer ordinary turns unless explicit scoped cancellation,
  supersession, or Core-authorized semantic interruption applies;
- consume correlated capability and Soridormi progress/terminal evidence through
  existing Goal, task-context, response, outcome, and trace contracts rather
  than waiting for unrelated work or introducing a generic live event bus;
- reduce repeated Agent Skill selection, oversized serial prompts, avoidable
  model calls, and contract-repair loops from trace evidence rather than
  weakening the checks that expose them;
- evaluate bounded two-request model concurrency only after independent work
  exists and compare it under shared LLM/TTS GPU load; measure queueing and
  starvation while prioritizing user-observable response and TTS work over
  deliberative or optional background work, without treating compute
  pre-emption as Goal cancellation; retain the current setting when concurrency
  worsens first-audio or reliability;
- overlap only work whose independence and provider/resource compatibility are
  established by existing contracts; physical TaskGraph nodes remain
  sequential;
- preserve one Core semantic authority, exact correlation, ordered speech,
  confirmation, cancellation, source-effect bounds, speech-claim validation,
  outcome reconciliation, and sequential physical TaskGraph execution.

True incremental PCM playback remains owned by **Extract Playback Delivery
Lifecycle** below. It is measured in the same end-to-end scenarios but is not a
substitute for reducing cognition before a valid speech stage exists.

### Non-goals

- no raw model tokens, partial JSON, private reasoning, or incomplete sentences
  sent to TTS;
- no independent speech model that can reinterpret Goals, promise effects, or
  claim outcomes;
- no second response-composition owner or dummy Plan used only to satisfy the
  current plan-bound response contract;
- no greeting/action phrase table or confidence-only route switch;
- no bypass of schema, completeness, capability, resource, confirmation,
  safety, claim, or evidence validation;
- no premature action, progress, result, or safe-state claim;
- no fixed realtime/deliberative/background model-slot architecture, two- or
  three-request default, or unmeasured GPU oversubscription;
- no new generic Frame/event plane, orchestration-framework dependency, or MCP
  Resource/Notification/Task surface in this Issue;
- no speculative partial-ASR effect or speech and no assumption that semantic
  end-of-turn or pre-emptive generation helps before retained traces prove it;
- no physical TaskGraph parallelism or TTS provider replacement.

### Exit criteria

- retained scenarios distinguish direct, Fast, and Deep paths and record the
  exact reason for every Deep invocation;
- a grounded greeting/direct answer uses no Fast or Deep Planner and emits one
  response, complete bounded work terminates at Fast when valid, and complex or
  safety/resource reasoning that genuinely needs the wider planning boundary
  escalates without semantic loss;
- independently scheduled speech passes the existing commitment/evidence
  validators and interruption/delivery contracts, with no duplicate act;
- retained overlap cases prove that a slow first task completing during a newer
  ordinary conversation delivers its evidence-bound result exactly once, while
  explicit cancellation/supersession still suppresses invalid late speech;
- retained result-arrival cases prove deterministic urgent-output pre-emption,
  ordered ordinary delivery, and no speech for internal-only evidence without
  suppressing a required user-facing obligation;
- warm and cold p50/p95 reports show a reviewed improvement in first truthful
  audible response for each affected request class without hiding hard failures
  or weakening terminal-response correctness;
- model-call and repair reductions are visible in retained traces, and any
  concurrency or priority change is justified by shared-load evidence without
  starvation or semantic cancellation;
- focused General Ability, interaction, latency, and speech-truth tests plus the
  maintained full gates pass; target claims remain limited to the retained
  evidence class.

## Issue: Classify Broad Runtime Exception Boundaries

Status: source classification review complete; retained live failure evidence remains open; depends on **Reduce Time to First Grounded Response**

Implementation note (2026-08-03): the dependency-light AST inventory records
each maintained broad handler by file, qualified symbol, and handler ordinal,
with an owner, contract, reviewed classification, exact normalized-body digest,
and mechanically derived failure signals. Any handler-body or control-signal
change now requires explicit re-review; new, missing, duplicate, stale, or
unreviewed entries fail the repository gate. This closes the source review and
does not claim retained live failure evidence for target-only boundaries.

### Problem

The existing repository policy rejects only broad handlers whose bodies are
trivially silent. The maintained runtime still contains 141
`except Exception` handlers, including 57 in `VoiceAssistant`. Some are valid
top-level containment or cleanup; a passing policy gate does not currently prove
that each one has a reviewed failure contract.

### Scope

- create a complete symbol-level inventory for maintained Orchestrator, Agent,
  and shared runtime handlers;
- classify each handler as narrow/re-raise, typed failure mapping, fail-closed
  boundary, or expected cleanup that preserves the primary error and records a
  diagnostic;
- replace broad catches where the handled failure set is known;
- add focused tests for model, Provider, execution, cancellation, state, audio,
  and evidence boundaries changed by the audit;
- mechanically reject new or unclassified broad handlers without relying on
  line-number-only exceptions.

### Non-goals

- no blanket conversion of every handler to an error log;
- no removal of required top-level service containment;
- no user-visible wording change unless a retained failure trace proves the
  current speech violates the interaction contract;
- no giant mechanical exception rewrite.

### Exit criteria

- every maintained broad handler has a checked classification and owner;
- operational failures re-raise, map to a typed result, or fail closed;
- expected cleanup cannot hide or replace the primary failure;
- unreviewed new broad handlers fail the repository policy gate;
- focused failure tests, the live speech-only regression, and full gates pass.

## Issue: Establish Typed Host Configuration Snapshots

Status: source implementation and checked ownership inventory complete; retained live proof remains open

Implementation note (2026-08-02): immutable typed startup groups now parse and
validate the maintained Host audio devices, audio input, cognition, conversation
state, mind-profile path, experience/episode storage, interaction runtime,
telemetry, playback/TTS, session, evidence, and model-generation settings before
`VoiceAssistant` composition. Maintained collaborators receive those settings
directly; legacy `from_env` factories remain only for standalone compatibility
and tests. A checked ownership gate discovers every direct Orchestrator
environment read, requires it in `HostSettingsSnapshot`, and rejects migrated
`from_env` factories from the maintained composition root. Invalid values name
the owning variable and expected bound, and the generated runtime configuration
inventory is checked in the canonical gate. Retained live startup evidence is
still required before operational requalification.

### Problem

`VoiceAssistant.__init__` spans 615 lines and directly or indirectly builds a
large environment-derived state. The ASR service already proves that an
immutable typed startup snapshot can preserve generated profile authority. The
Host still lacks equivalent narrow configuration ownership.

### Scope

- classify Host variables as operator-facing, profile-owned, service-internal,
  acceptance-only, or compatibility-only;
- define immutable typed settings groups for audio input, cognition,
  playback/TTS, session lifecycle, and evidence;
- parse and validate the environment once before `VoiceAssistant` composition;
- inject narrow settings groups into collaborators rather than one global
  settings object;
- preserve `.env.runtime`, hardware-profile precedence, safe diagnostics, and
  all current defaults;
- freeze new Host booleans while the inventory is active.

### Non-goals

- no simultaneous migration of Agent, TTS, and shared runtime settings;
- no behavior or default changes hidden inside parsing cleanup;
- no owner-editable personality or semantic policy in Python settings;
- no one-object configuration dumping ground.

### Exit criteria

- a checked inventory accounts for every Host environment read and duplicate
  parser;
- invalid values fail with the owning variable and expected type;
- `VoiceAssistant` receives typed settings and no longer performs scattered
  startup parsing for the migrated groups;
- precedence and supported-profile tests pass;
- configuration documentation is generated or checked against the owned
  inventory;
- the retained live voice loop and full gates pass unchanged.

## Issue: Extract Playback Delivery Lifecycle

Status: source extraction complete; live latency and audible-delivery evidence remain open

Implementation note (2026-08-02): playback lifecycle state owns ordering,
generations, start waiters, cancellation bookkeeping, pending audio, provider
queue/task state, synthesis concurrency, output-stream state and locks, and
current-turn delivered-speech events. A dedicated `PlaybackTransport` now owns
TTS WebSocket provider I/O, ordered queue consumption, resampling/output writes,
stream open/abort/close, and delivery evidence. `VoiceAssistant` keeps thin
public delegates so existing callers and trace decorators remain stable. The
composition root remains at 187 methods and one property, while initializer
state decreased to 144 attributes and 417 lines; ratchets forbid transport
state from returning. True provider-incremental PCM playback and retained live
first-PCM/audible timing evidence remain open because they require provider and
target measurement rather than more Host ownership.

### Problem

Ordered synthesis, playback-start waiters, chunking, echo detection,
cancellation, output streams, and delivery evidence currently occupy a large
contiguous part of `VoiceAssistant`. These responsibilities have one realtime
ordering contract but no independent owner.

### Scope

- extract one playback-delivery collaborator with explicit queues, policy,
  session/evidence callbacks, and lifecycle methods;
- distinguish provider transport streaming from audible incremental playback,
  and begin ordered playback from provider PCM chunks when the declared
  provider and Host cancellation/device contracts permit it;
- separate invalidation of already-playing or obsolete queued audio from an
  independent Goal's future result-delivery eligibility, retaining exact
  turn/Goal/evidence correlation across output generations;
- preserve ordered audible playback, bounded service-worker concurrency,
  generation cancellation, stale-output suppression, barge-in, echo handling,
  and playback start/end evidence;
- keep `VoiceAssistant` as composition root and make it delegate rather than
  duplicate the extracted logic;
- establish a structural ratchet so new playback behavior enters the
  collaborator.

### Non-goals

- no TTS provider replacement or pronunciation tuning;
- no change to confirmation barriers or deterministic interruption semantics;
- no line-count-only extraction or forwarding facade with shared mutable
  internals left behind.

### Exit criteria

- playback ownership, inputs, outputs, cancellation, and cleanup are explicit;
- retained warm/cold p50/p95 evidence distinguishes `tts_request_start`, first
  PCM, `first_audio_playback`, and stream completion without calling a transport
  `start` event audible evidence;
- black-box alignment, interruption, stale-output, and evidence tests run
  against the collaborator through the public Host path;
- `VoiceAssistant` method and initialized-state counts decrease and cannot grow
  back without a reviewed update;
- the current live voice proof and complete gates pass.

## Issue: Extract Input Turn and Session Lifecycle

Status: source extraction complete; live microphone and target evidence deferred

Implementation note (2026-08-02): `InputTurnLifecycle` owns all mutable
input/task state and `InputSessionRuntime` owns microphone callback delivery,
VAD framing, ASR WebSocket transport, routed-turn and protective-reflex task
mechanics, injected-audio framing, and idle-session sweeping. `SessionRegistry`
continues to own trace/session storage while `conversation_state.py` owns
semantic dialogue, Goal, and confirmation state; the input runtime imports
neither semantic boundary. Gateway/Core meaning, cancellation scope, and
Protective Reflex authority remain outside the collaborator. The remaining
direct-LLM call has one checked rollback-only owner and all maintained modes
disable it. Composition-root and lifecycle-state counts are monotonic gates.
Live microphone, default-device rollover, and target evidence remain deferred.

### Problem

Microphone callbacks, injected audio, VAD/ASR task ownership, session creation,
idle cleanup, and routed-turn tracking remain interleaved with cognition,
execution, and output delivery. `conversation_state.py` is also a 4,424-line
boundary whose persistence, Goal, confirmation, and lifecycle responsibilities
need an ownership audit.

### Scope

- extract microphone/VAD/ASR utterance and session-task lifecycle behind typed
  events and explicit cancellation;
- separate session registry mechanics from semantic conversation/Goal state;
- audit the remaining direct-LLM compatibility path before moving it: remove it
  when maintained apply lanes cannot reach it, or confine it behind an explicit
  rollback contract when still required;
- keep Protective Reflex effects immediate and Host-owned;
- preserve turn identity from audio capture through final response evidence.

### Non-goals

- no movement of Gateway admission or Core meaning into audio code;
- no movement of deterministic interruption or Soridormi safety authority;
- no rewrite of conversation semantics while extracting lifecycle mechanics.

### Exit criteria

- microphone/VAD/ASR tasks have one owner and deterministic shutdown;
- session registry and semantic state have documented, tested boundaries;
- direct-LLM reachability in maintained profiles is proved and its compatibility
  status is explicit;
- interruption, barge-in, injected-audio, idle-session, and current live voice
  regressions pass;
- structural counts decrease under a monotonic ratchet.

## Issue: Reduce Supported Configuration Combinations

Status: source implementation complete; target-profile qualification deferred

Implementation note (2026-08-02): four source-controlled operator modes now
own complete maintained combinations for services, speech, voice plus MuJoCo,
and qualification. The generated runtime manifest records the active mode and
source file; mode contradictions fail before startup. A machine-generated
inventory now classifies 450 discovered keys into public choice, profile
constant, service internal, or acceptance override. The maintained public
surface contains eight choices and one public Boolean. The last compatibility
alias (`CHROMIE_SOCIAL_ATTENTION_MODE`) was removed; the service-owned
`AGENT_SOCIAL_ATTENTION_MODE` value is composed by the maintained modes instead
of being a second operator switch. Public Boolean and alias counts are protected
by zero-growth ratchets, and launcher/profile tests enumerate all four modes.

### Problem

The repository documents 321 environment keys and has 295 literal runtime
environment reads. These counts mix legitimate service internals with public
deployment choices, but the operator documentation presents only four
deployment modes. The supported combination set is therefore unclear and much
larger than the tested profile set.

### Scope

- derive a machine-readable inventory from typed settings and generated
  profiles;
- designate each key as public choice, profile constant, service internal,
  acceptance override, or bounded compatibility alias;
- make maintained speech and MuJoCo profiles own complete tested combinations;
- keep physical operation experimental and fail closed until commissioned;
- deprecate redundant public booleans with warnings, migration tests, and
  removal criteria;
- report a measured public-switch reduction in every patch.

### Non-goals

- no forced removal of internal resource/model values needed by services;
- no arbitrary “under 15” closure if it hides required safety or hardware
  distinctions;
- no use of profile selection to bypass confirmation, Provider availability, or
  source-bound evidence.

### Exit criteria

- supported combinations are enumerable and covered by profile tests;
- an operator chooses a maintained mode without assembling dozens of booleans;
- contradictory and unsupported combinations fail before startup;
- public boolean and compatibility-alias counts are lower than the refreshed
  baseline and protected by a ratchet;
- Configuration, README, Runbook, and generated profile diagnostics agree.

## Issue: Expand Mypy by Owned Package

Status: source scope expansion complete; canonical Mypy execution remains an environment gate

Implementation note (2026-08-02): `config/mypy_scope.txt` now accepts owned
package directories and expands every Python module recursively, rejects
overlapping entries, and automatically includes newly added modules. All of
`shared/chromie_contracts/`,
`orchestrator/runtime/cognitive_gateway_modules/`, and
`orchestrator/schemas/` are selected as owned packages. Stable Host settings,
component factories, outcome delivery, playback transport, and input lifecycle
boundaries are explicitly selected files. Focused tests prove package expansion,
automatic inclusion, sorting, and overlap rejection. The archive environment
does not contain the pinned Mypy executable, so strict execution remains a
normal dependency-environment gate rather than unfinished source ownership.

### Problem

The strict Mypy mechanism is implemented, but its ratchet contains only four
files. That coverage is too small to protect cross-file contracts or the
runtime seams created by decomposition.

### Scope

- replace file-by-file contract entries with all of
  `shared/chromie_contracts/`;
- add independently owned Orchestrator runtime packages after their lifecycle
  boundaries stabilize;
- require new files in a checked package to enter automatically;
- retain strict optionality, return, ignore, and untyped-body rules.

### Non-goals

- no whole-tree strict conversion in one patch;
- no blanket `Any`, import skipping, or mass ignore baseline;
- no annotation churn mixed with behavior changes.

### Exit criteria

- all 23 current shared-contract Python files pass as one owned package;
- a package-scoped ratchet cannot silently omit a newly added module;
- the next runtime package is selected from the extracted ownership map and
  passes independently;
- Mypy scope grows monotonically and full gates pass.

## Issue: Reduce the Current Documentation Surface

Status: source implementation complete

Implementation note (2026-08-02): eight overlapping trace, event, lifecycle,
and recovery documents were consolidated into `RUNTIME_OBSERVABILITY.md` and
`RUNTIME_OBSERVABILITY_OPERATIONS.md`. Three dated in-tree archives were removed
after current facts and references were retained; Git history remains the
historical authority. The tree decreased from 125 to 116 Markdown files and
from 80 to 73 files directly under `docs/`; the core reading path is 14
documents. File/core-path ratchets and authority/link checks are now enforced.
The specialized-document audit is also complete: the documentation index no
longer counts as ownership, component entrypoints form the current ownership
graph, and Agent Skill package documents remain under explicit mechanically
checked contracts. Index-only specialized documents now fail the canonical
documentation gate. Further prose reduction may continue as ordinary
maintenance, but it is no longer an open Issue exit criterion.

### Problem

Chromie has strong evidence discipline but 125 repository Markdown files,
including 80 directly under `docs/`, and a core index that previously presented
dozens of “start here” links. Eight closely related trace/observability
documents and three large in-tree archives are the clearest consolidation
candidates.

### Scope

- keep the core reading path at no more than 15 documents;
- merge trace schema, instrumentation, lifecycle, event, resource, and recovery
  material into the smallest owned set that preserves real interfaces;
- remove the three 2026-07-30 archives from the working tree after verifying
  their commits and any still-current facts;
- require every specialized document to have a current component/operator
  entrypoint or a concrete mechanical contract beyond being listed in the
  documentation index;
- simplify prose and define necessary terms once.

### Non-goals

- no deletion of current safety, API, configuration, or evidence contracts;
- no replacement with one giant document;
- no loss of retained evidence identifiers or migration provenance that Git
  history cannot supply.

### Exit criteria

- the core reading path is short and sufficient for a new collaborator;
- trace documentation has one clear contract owner and no duplicated current
  procedures;
- historical archives no longer inflate or confuse the current tree;
- total file and line counts decrease from a refreshed baseline;
- `check_docs.py` enforces ownership rather than mere index presence;
- links, authority, documentation, and full repository gates pass.

## Issue: Requalify the Simplified Runtime

Status: source qualification workflow implemented; clean dependency-complete
execution and target requalification deferred

`config/source_qualification.json` now owns the deterministic source gate set,
and `scripts/run_source_qualification.py` binds every result to the current Git
revision, clean/dirty state, elapsed time, exit status, and bounded output. A
missing pinned Ruff or Mypy dependency is recorded as `unavailable` and blocks
qualification rather than being treated as a pass. The report always records
`target_validated=false` and `release_qualified=false` and enumerates the
excluded microphone, speaker, hot-plug, shared-GPU, simulator/robot, and LAN
claims.

The remaining closure is intentionally target-dependent: run the dependency-
complete source report from a clean revision, then rerun the same default
source-bound evidence profile and compare behavior, cancellation, safety
ownership, latency, and evidence completeness against the retained baseline.

## Issue: Secure Local Runtime Exposure

### Problem

The local Docker Compose profile publishes internal ASR, TTS, LLM, and Agent
ports without an explicit host address. On a host connected to an untrusted
network, that can expose unauthenticated local-development services beyond the
machine even though the intended trust boundary is local-only.

### Scope

- bind local host-published ports to `127.0.0.1`;
- keep services listening on their required container interfaces so Compose
  service-to-service traffic continues to work;
- document the local-only trust boundary;
- add a behavior/configuration test that rejects wildcard host publication;
- identify remote or multi-host deployment as a separate authenticated profile,
  not an exception to the secure local default.

### Non-goals

- no change to cognitive authority, tools, or physical execution policy;
- no ad-hoc shared token added to every internal endpoint;
- no CPU or memory limits in the main qualification profile;
- no assumption that loopback binding alone is a complete remote deployment
  security design.

### Exit criteria

- every maintained local-development host port is loopback-bound;
- container-to-container health and runtime paths still work;
- automatic tests reject an accidental wildcard publication;
- `SECURITY.md`, deployment/configuration ownership, and the runbook agree;
- the maintained full tests and documentation checks pass.

### Implementation status

The maintained Compose profile now binds ASR, maintained and evaluation TTS,
Ollama, and Agent host publications to `127.0.0.1`. In-container listeners
remain unchanged so Docker bridge-network service discovery and health checks
continue to work.

The dependency-light `scripts/check_local_runtime_exposure.py` checker audits
both maintained Compose source files and Docker Compose's resolved JSON. The
supported service launcher runs the resolved check before startup, and focused
unit tests reject unspecified hosts, IPv4/IPv6 wildcards, and host networking.

The maintained full gate passes 1,545 primary tests plus 20 legacy Agent tests,
including eight focused exposure-policy tests. This establishes implementation
and automatic verification. Local target acceptance still must confirm localhost
reachability, failed LAN reachability, and unchanged container-to-container
service health; those deployment facts are not inferred from automated tests.

Suggested commit:

```text
Bind local runtime services to loopback
```

## Issue: Make Runtime Failure Paths Explicit

Status: first-intake audit implemented and automatically verified; the broader
symbol-level classification is a separate current Issue.

### Problem

Some legacy paths suppress broad exceptions or rely on runtime `assert`
statements. Those constructs make intent unclear, can hide operational failures,
and may disappear under optimized Python execution.

### Scope

- inventory broad silent handlers and production assertions in maintained code;
- classify each occurrence as expected cleanup, defined degradation, operational
  failure, evidence failure, or impossible invariant;
- replace broad silent handling with narrow suppression, debug/warning evidence,
  typed fallback results, or fail-closed exceptions as appropriate;
- replace production assertions with explicit exception types and messages;
- add focused tests for each changed failure boundary.

### Non-goals

- no mechanical `pass` to `logger.exception` replacement;
- no noisy error logs for expected idempotent cleanup;
- no swallowing of model, provider, execution, cancellation, or evidence errors;
- no change to user-visible fallback semantics without separate behavioral
  evidence.

### Exit criteria

- every audited silent handler has an explicit documented intent;
- maintained runtime safety and evidence invariants do not rely on `assert`;
- optimized Python execution cannot remove required safety checks;
- failure-path tests cover changed behavior;
- the maintained full tests and documentation checks pass.

### Implementation status

The audit and classification are maintained in
[Runtime Failure Paths](RUNTIME_FAILURE_PATHS.md). Production assertions were
replaced with explicit contract, state, service, and execution exceptions.
State-changing semantic operations validate before mutation; malformed optional
compatibility records are narrowly omitted with diagnostics; expected cleanup is
debug-visible; and corrupt trace or episode evidence remains observable. Focused
tests verify invariant behavior and scan maintained runtime ASTs for remaining
`assert` statements.

Suggested commit:

```text
Make runtime failure invariants explicit
```

## Issue: Establish Repository Engineering Policy Checks

### Problem

Important repository rules currently live across `AGENTS.md`, contributing and
security guidance, and hand-written tests. Stable mechanical rules should fail
in one maintained checker rather than depend on every contributor remembering
all prose.

### Scope

Add a dependency-light policy checker, preferably AST- and structured-config
based, for stable rules such as:

- no unexplained broad silent exception handling in maintained runtime code;
- no new production assertions in guarded paths;
- no `eval`, `exec`, or unsafe shell invocation;
- no direct low-level motor, joint, torque, actuator, or controller-array fields
  crossing model-facing contracts;
- no wildcard host publication in the secure local Compose profile;
- no reintroduction of removed first-class architecture authorities;
- centralized, reasoned exceptions for cases that cannot yet be removed.

Integrate the checker into the maintained local test entrypoint and CI.

### Non-goals

- no semantic code review by regex;
- no phrase-to-action or prompt-content enforcement;
- no attempt to replace unit, integration, benchmark, or live evidence;
- no giant permanent baseline that silently permits all existing defects.

### Exit criteria

- the checker is deterministic, dependency-light, and fast enough for normal CI;
- each rule has a focused self-test and a documented ownership rationale;
- exceptions are centralized, minimal, and explain why they remain;
- `AGENTS.md` and contributing guidance point to the executable policy;
- the maintained full tests and documentation checks pass.

### Implementation status

The canonical `scripts/check_repository_policies.py` gate is implemented and runs
from the maintained local test entrypoint, GitHub Actions, and the Benchmark gate.
It combines AST checks for explicit runtime invariants, silent broad handlers,
dynamic execution, unsafe shells, model-contract actuation fields, passive Agent
Skill authority, and model-authored Skill selection with the maintained Compose
exposure and removed-Router guards. Rule ownership and exception governance are
defined in [Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md).

The central exception registry is empty. Any future entry must match one exact
rule/path/symbol, explain the reviewed reason and removal condition, and remain a
live finding; wildcards and stale exceptions fail closed.

Suggested commit:

```text
Add executable repository engineering policies
```

## Issue: Introduce High-Signal Ruff Gates

### Problem

The repository has strong annotations and runtime contracts but no standard
Python lint gate. High-signal static defects can therefore enter code and be
found only through review or execution.

### Scope

- pin Ruff in the appropriate development/test dependency boundary;
- configure defect-oriented rules first, including undefined/unused names,
  syntax-class errors, bugbear findings, and async misuse;
- inspect and fix the existing baseline deliberately;
- add the Ruff command to local and CI checks;
- require a reason for any local suppression.

Initial rule selection should favor `F`, high-value `E` families, `B`, and
`ASYNC`. Additional style or simplification rules require a separate evidence
review.

### Non-goals

- no repository-wide auto-formatting;
- no broad style-only rewrite;
- no enabling noisy rules merely to increase rule count;
- no suppressing real errors through a blanket ignore list.

### Exit criteria

- the selected rules pass on the maintained tree;
- CI and the normal developer workflow execute the same configuration;
- suppressions are local and justified;
- no user-visible or runtime behavior changes are introduced by cleanup;
- the maintained full tests and documentation checks pass.

### Implementation status

Ruff 0.16.0 is pinned in the test dependency boundary. `ruff.toml` explicitly
selects `E4`, `E7`, `E9`, `F`, `B`, and `ASYNC`; preview and formatting gates
remain disabled. `config/ruff_scope.txt` is a sorted, duplicate-free monotonic
ratchet over selected clean contract and tooling modules. `scripts/run_ruff.py`
validates the executable version and scope before invoking Ruff, and the
maintained test entrypoint runs the same command used by CI. No blanket ignore
baseline was introduced. The focused Ruff command passes on the 2026-07-31
tree together with the maintained full suite.

Suggested commit:

```text
Add high-signal Ruff enforcement
```

## Issue: Establish Incremental Type Checking

Status: initial four-file mechanism implemented and automatically verified;
package-level expansion is queued separately.

### Problem

Most functions are annotated, but annotations are not mechanically checked.
Applying strict typing to the entire dynamic orchestration tree at once would be
high-noise and risky; selected clean boundaries can provide value immediately.

### Scope

- pin and configure Mypy or an equivalently reviewed checker;
- begin with shared contracts, shared runtime primitives, and selected
  `orchestrator/runtime/` modules;
- resolve real optionality, container, callable, protocol, and async return
  defects rather than hiding them with broad `Any` conversions;
- record the checked module set as a monotonic ratchet;
- expand only when the current set is clean and stable.

### Non-goals

- no whole-tree strict-mode requirement in the initial Issue;
- no mass annotation rewrite in old orchestration code;
- no requirement to type unowned third-party internals;
- no weakening of Pydantic runtime validation because static checking exists.

### Exit criteria

- the initial module set passes from a clean environment;
- checked modules cannot silently leave the configured set;
- third-party gaps use narrow stubs or documented boundaries;
- CI executes the same type-check command;
- the maintained full tests and documentation checks pass.

### Implementation status

Mypy 2.3.0 is pinned in the test dependency boundary. `mypy.ini` enforces
complete definitions, typed bodies, explicit optionality, return-Any warnings,
stale-ignore warnings, and strict equality without skipping imports.
`config/mypy_scope.txt` is a sorted, duplicate-free monotonic ratchet over
selected shared contracts and tooling boundaries. `scripts/run_mypy.py` validates
the executable version and scope before invoking Mypy, and the maintained test
entrypoint runs it after Ruff. No whole-module ignore baseline was introduced.
The 2026-07-31 current-tree run passes the configured four-file scope without
ignores or scope removal. Package-level expansion remains a separate queued
Issue.

Suggested commit:

```text
Add incremental contract and runtime type checks
```

## Issue: Modernize Behavioral and Architecture Tests

### Problem

Some tests assert that implementation strings exist in source files. This can
break on harmless refactors and can pass while the intended runtime behavior is
wrong. Other source checks legitimately protect architecture or generated
artifacts, so the migration must preserve ownership rather than delete them
blindly.

### Scope

Classify each source-reading assertion as:

- user/runtime behavior, which should become an executable test;
- forbidden architecture, which should move to the engineering policy checker or
  a focused AST test;
- generated script/configuration content, which may remain an artifact-contract
  test or become an executed temporary-environment test;
- obsolete duplication, which may be removed only after unique assertions move
  to their canonical owner.

Also reduce unit-test dependence on importing the full `VoiceAssistant` graph by
introducing narrow collaborator or helper seams when behavior permits.

### Non-goals

- no test-count reduction as a quality objective;
- no deletion of historical regressions without preserving their unique
  boundary;
- no replacement of runtime evidence with snapshots;
- no broad production refactor solely to satisfy a test style preference.

### Exit criteria

- migrated tests assert behavior or an explicitly owned static/artifact contract;
- unique regression coverage is retained and documented;
- affected tests run faster or with a narrower import graph where practical;
- the test matrix continues to identify the earliest responsible boundary;
- the maintained full tests and documentation checks pass.

### Implementation status

Behavioral expectations for gratitude routing, Cognitive Core endpoint ownership,
temporal-scope Planner guidance, and failure responses now execute through rule,
API, prompt-capture, or user-visible boundaries. Redundant Router source-string
suites were removed because the canonical policy checker and retained Router
guard own that architecture. `scripts/check_test_ownership.py` rejects new
unclassified Python-source reads and validates the exact registry of genuine
generated-artifact contracts; stale approvals fail closed.

Suggested commit:

```text
Modernize behavioral and architecture test ownership
```

## Issue: Establish Typed Service Configuration Boundaries

Status: source implementation complete and automatically verified for Agent, ASR, TTS, the maintained Host, and narrow shared-runtime policy boundaries; live startup proof remains target evidence.


### Problem

Environment reads and small parsing helpers are repeated across services and
modules. This makes configuration ownership stringly typed and allows different
call sites to interpret the same value differently. The generated hardware
profile and validation system is already authoritative and must remain so.

### Scope

- define one typed settings snapshot per service or clear runtime boundary;
- parse and validate environment inputs once during service startup;
- inject typed settings into internal modules instead of repeatedly calling
  `os.getenv`;
- consolidate boolean, integer, duration, path, enum, and model-budget parsing;
- preserve `.env.runtime` generation and hardware/profile precedence;
- expose effective settings through existing safe diagnostics without leaking
  secrets.

### Non-goals

- no single global settings object spanning all services;
- no bypass of hardware auto-detection or profile-owned values;
- no simultaneous migration of every environment read;
- no configuration rename without compatibility, documentation, and tests;
- no placement of owner-editable identity or personality semantics into Python
  defaults.

### Exit criteria

- the selected first service parses configuration once and passes a typed object
  inward;
- duplicate parsing helpers in the migrated scope are removed;
- precedence and strict-profile tests prove generated runtime authority;
- startup fails clearly for invalid values;
- a follow-on migration map identifies remaining service boundaries;
- the maintained full tests and documentation checks pass.

Suggested commit:

```text
Add typed service configuration boundaries
```

## Issue: Decompose the VoiceAssistant Composition Root

Status: first-intake greeting extraction implemented and automatically verified;
the 2026-07-31 re-audit supersedes the earlier structural-closure interpretation.


### Problem

`VoiceAssistant` coordinates many valid responsibilities in one large class and
file. The problem is not that the Host owns audio and execution coordination;
the problem is that those responsibilities are physically entangled, increasing
regression risk and test coupling.

### Scope

Extract one independently testable collaborator at a time. Candidate seams are:

- runtime-ready greeting generation and validation;
- playback scheduling, barriers, and cancellation;
- audio turn lifecycle and VAD/ASR handoff;
- Cognitive Gateway/Core dispatch and turn result assembly;
- interruption, approval revocation, and task cancellation coordination;
- evidence, episode, and runtime-trace recording.

`VoiceAssistant` remains the composition root and public lifecycle owner until
extracted seams are proven. Each extraction must preserve ordering, cancellation,
confirmation, fallback, evidence, and user-visible behavior.

### Non-goals

- no big-bang Orchestrator rewrite;
- no movement of deterministic Host reflexes into the LLM;
- no movement of Soridormi physical safety into Chromie;
- no feature work combined with extraction;
- no new abstraction without a concrete responsibility and test boundary.

### Exit criteria

For every extraction activity:

- one collaborator has explicit inputs, outputs, dependencies, and ownership;
- existing behavior and evidence tests pass unchanged or become narrower without
  losing assertions;
- `VoiceAssistant` delegates rather than duplicates the extracted logic;
- no authority boundary moves;
- cancellation and failure semantics are retained;
- the maintained full tests and documentation checks pass.

The historical first-intake scope closed after the agreed greeting extraction.
It does not close the current typed-settings, playback-delivery, or
input/session lifecycle Issues.

Suggested commit pattern:

```text
Extract <semantic collaborator> from VoiceAssistant
```

## Issue: Consolidate Current Documentation Authority

Status: first-intake authority mapping implemented and automatically verified;
current-surface reduction is queued separately. Current ownership is defined in
`DOCUMENTATION_AUTHORITY.md`; detailed superseded narratives remain indexed
historical archives until the reduction Issue reviews them.


### Problem

The project correctly documents safety, architecture, status, evidence, and
operations, but current truth, historical migration, evidence narrative, and
resume instructions are sometimes repeated across several large documents.
Duplication increases drift and makes small updates expensive.

### Scope

- retain one authoritative home for each current fact;
- shorten status tables to claim, four-axis state, and owning evidence link;
- move superseded architecture and closed migration narrative into explicit
  historical documents or sections;
- keep `DEVELOPMENT_CHECKPOINT.md` short and current;
- keep `CHANGELOG.md` focused on notable changes rather than complete design
  history;
- preserve `scripts/check_docs.py` and strengthen ownership checks where useful;
- fix malformed headings or content placement when encountered.

### Non-goals

- no deletion of evidence required to support current claims;
- no replacement of authoritative documents with one giant overview;
- no reduction of documentation merely to meet a word-count target;
- no historical rewrite that overstates implementation or target validation.

### Exit criteria

- current normative architecture, status, evidence, roadmap, and resume ownership
  are unambiguous;
- duplicated current claims link to one owner instead of repeating full prose;
- historical material is discoverable but cannot be mistaken for current
  authority;
- documentation checks pass and index every maintained document;
- a new collaborator can identify the active Issue and required evidence from
  the checkpoint without reading historical narrative.

Suggested commit:

```text
Consolidate current documentation authority
```

## Program closure criteria

This planning program is complete only when every accepted Issue is either:

- closed with implementation and automatic verification evidence;
- explicitly removed from scope with a documented architectural reason and
  current-tree evidence; or
- transferred to another authoritative plan with an exact link and owner.

Closure does not itself imply target validation or release readiness. Runtime,
simulator, and physical evidence remain governed by their existing acceptance
contracts.
