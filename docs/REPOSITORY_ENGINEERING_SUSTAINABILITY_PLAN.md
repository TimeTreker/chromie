# Repository Engineering Sustainability Plan

Status: Secure Local Runtime Exposure is implemented and automatically
verified; local target validation is pending; later Issues remain queued

This document records the engineering recommendations accepted after the
repository-wide external review and decomposes them into independently closable
Issues. It exists so useful work is not lost when the active product or
qualification context changes.

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

## Delivery rules

- Work one Issue at a time. Only one Issue from this program may be active.
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

## Issue registry

| Issue | State | Depends on | Purpose |
|---|---|---|---|
| Secure Local Runtime Exposure | implemented and automatically verified; local target validation pending | none | Remove unintended LAN exposure from the default local Compose profile. |
| Make Runtime Failure Paths Explicit | implemented and automatically verified | none | Replace silent operational failures and production assertions with intentional, observable invariants. |
| Establish Repository Engineering Policy Checks | implemented and automatically verified | Runtime Failure Paths audit complete | Convert stable source and deployment principles into dependency-light AST/configuration checks. |
| Introduce High-Signal Ruff Gates | implemented and automatically verified | Engineering Policy Checks | Add defect-oriented lint enforcement without broad formatting churn. |
| Establish Incremental Type Checking | active | Engineering Policy Checks | Type-check clean contracts and runtime boundaries, then ratchet coverage outward. |
| Modernize Behavioral and Architecture Tests | queued | Policy Checks and static gates | Replace implementation-string coupling with behavioral, AST-policy, or artifact-contract ownership. |
| Establish Typed Service Configuration Boundaries | queued | static gates; tests modernized where touched | Preserve profile authority while removing repeated internal environment parsing. |
| Decompose the VoiceAssistant Composition Root | queued | test modernization; typed settings where relevant | Extract independently testable collaborators without changing interaction behavior or authority. |
| Consolidate Current Documentation Authority | queued | may proceed after policy checks; final consolidation follows structural work | Separate current normative truth, status, evidence, and history while keeping documentation validation. |

Closing one Issue does not automatically activate the next. The current tree,
product milestone, and retained evidence determine whether the next queued Issue
is still the correct priority.

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
baseline was introduced. Focused Ruff gate tests and the maintained behavioral
suite pass; actual Ruff execution requires the pinned dependency in the clean
development/CI environment.

Suggested commit:

```text
Add high-signal Ruff enforcement
```

## Issue: Establish Incremental Type Checking

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

Suggested commit:

```text
Modernize behavioral and architecture test ownership
```

## Issue: Establish Typed Service Configuration Boundaries

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

The Issue closes only after the agreed first decomposition set is complete and a
new audit shows that remaining responsibilities are intentionally composed.

Suggested commit pattern:

```text
Extract <semantic collaborator> from VoiceAssistant
```

## Issue: Consolidate Current Documentation Authority

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
