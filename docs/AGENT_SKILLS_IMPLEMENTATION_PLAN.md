# Agent Skills Implementation Plan

Status: Open architecture issue; documentation and delivery plan accepted,
runtime implementation not started
Related architecture: [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md)

## Issue

**Introduce Agent Skills on canonical Capability terminology without creating a second execution authority.**

Chromie already has LLM-driven Agents, Canonical Plans, typed executable
capabilities, a legacy-named Trusted Skill Runtime, provider validation, scoped memory, and
scenario-based evaluation. What is missing is a first-class way to package and
progressively load reusable task methods for those Agents.

The implementation must let Agents discover and use reusable methods while
preserving these invariants:

- Thinking belongs to the LLM.
- Skill selection is model-authored.
- Agent Skills have no independent Goal or execution authority.
- Canonical Plans remain the only cognitive proposal consumed by execution.
- Capability manifests and live provider schemas remain execution-authoritative.
- The Host validates identity, provenance, budgets, schemas, and policy; it does
  not solve ordinary semantic association.
- Benchmarks evaluate intelligence and must not implement it.

## Current problem

Task knowledge is currently distributed across broad model prompts, capability
descriptions, runtime validators, provider adapters, documentation, and tests.
This makes reusable domain methods difficult to review, version, select, trace,
and improve independently.

The recent weather conversation exposed the distinction:

- Goal Association must resolve `那边` from scoped discourse;
- the Planner must decide whether exact verified memory or a fresh lookup is
  appropriate;
- Response Composer must acknowledge without claiming a result;
- Tool Result Interpreter must answer from selected evidence;
- the weather provider must adapt an authoritative location to provider query
  forms;
- the Host must validate provenance and execution contracts.

The reusable method belongs in Agent Skills. The semantic choice remains in
Agents, and provider compatibility remains in Capabilities.

## Decisions already locked

- The reusable method concept is named **Agent Skill**.
- Agent Skill identity uses `agent_skill_id`.
- Executable Plan steps use `capability_id` as the canonical field.
- Legacy `skill_id` is accepted only at explicit compatibility boundaries and
  must normalize to the same canonical Capability ID.
- If `skill_id` and `capability_id` are both present and differ, validation
  fails closed.
- **Trusted Capability Runtime**, **CapabilityRequest**, **CapabilityResult**,
  and **named capability** are the canonical architecture terms. Current code,
  logs, APIs, and retained artifacts may keep legacy aliases during migration.
- New model-facing schemas, prompts, Plans, traces, and examples emit canonical
  Capability terminology.
- Agent Skills are stored under `agent-skills/`, separately from capability
  manifests.
- Agent Skills cannot register tools, providers, permissions, safety
  exemptions, or confirmation exemptions.
- Initial Agent Skill packages are repository-owned or explicitly
  owner-approved and read-only.
- Skill selection is an LLM output; retrieval may only provide bounded
  candidates.
- Agents may select multiple Skills or no Skill.
- Agent-specific projections are progressively disclosed.
- Plans record Agent Skill identity/version/digest and reference exact
  executable Capabilities.
- Weather is the first vertical slice.
- Third-party installation, remote marketplaces, and automatic script execution
  are deferred.

## Delivery slices

The work is intentionally divided by semantic responsibility rather than by
numbered phases or generic stages.

### Canonicalize executable Capability terminology

Migrate the typed execution contract before adding Agent Skill selection.
Introduce canonical DTO fields and names for:

- `capability_id` in Plan steps, execution requests, results, traces, outcomes,
  and model-facing schemas;
- `CapabilityRequest` and `CapabilityResult` as canonical DTO names;
- `TrustedCapabilityRuntime` as the canonical runtime concept;
- “named capability” in new prompts, logs, documentation, and APIs.

Preserve a bounded compatibility layer:

- accept legacy `skill_id` only at declared decode or persistence boundaries;
- normalize legacy input immediately to `capability_id`;
- emit `capability_id` from all new serializers and model-facing contracts;
- reject conflicting dual-field payloads;
- retain readers for historical episodes, traces, benchmark fixtures, and
  external callers during the compatibility window;
- preserve registry identity, authorization, confirmation, scheduling,
  provider, evidence, and Soridormi safety semantics unchanged.

Acceptance:

- new Canonical Plans and Interaction responses contain `capability_id`, not
  executable `skill_id`;
- old payloads using `skill_id` remain readable and normalize identically;
- conflicting `skill_id`/`capability_id` values fail closed;
- provider requests and results correlate through the canonical Capability ID;
- maintained tests, scenarios, traces, and legacy replay fixtures remain green;
- no Agent Skill contract exists yet, so the rename cannot accidentally add a
  second execution authority.

### Establish Agent Skill contracts and terminology

Define strict shared DTOs for:

- Agent Skill metadata and `agent_skill_id`;
- owner approval and content digest;
- Agent projection names;
- bounded Skill summaries;
- typed Skill selection;
- Plan-level selected-Skill provenance;
- loader and selection failure reasons.

Acceptance:

- schemas reject unknown authority modes and executable declarations;
- Agent Skill IDs and semantic versions are stable;
- duplicate IDs, malformed projection paths, and missing digests fail closed;
- Agent Skill contracts cannot carry executable steps or grant permissions;
- no behavior changes before the loader and selection boundaries exist.

### Add a read-only Skill registry and loader

Create a repository-owned `agent-skills/` root and a loader that:

- scans only explicitly configured roots;
- loads metadata but not full Skill bodies at startup;
- verifies owner approval, version, projection paths, and content digests;
- blocks path escape and unsafe symlink traversal;
- exposes bounded summaries and requested projections;
- never imports or executes package code;
- never modifies the capability registry.

The registry is a cognitive-content index, not an execution registry.

Acceptance:

- unapproved, malformed, duplicate, or path-escaping packages are excluded;
- capability catalog contents and execution permissions are unchanged;
- loader behavior is deterministic and covered by dependency-light tests.

### Add model-authored Skill discovery and selection

Expose bounded Skill summaries to the responsible Agent and add a typed
selection output containing:

- selected Skill IDs and versions;
- relevant Goal IDs;
- requested projection;
- concise model-authored rationale;
- confidence or explicit no-Skill decision.

Candidate retrieval may use semantic indexing or capability relationships to
reduce prompt size. It must not produce the final semantic selection.

Acceptance:

- no phrase or route table selects a Skill;
- the same user phrase can lead to different Skills when Goal/context differs;
- “the last task I told you” remains resolved through Goal Association, not a
  Host Skill rule;
- unknown or unapproved selections fail closed and can trigger model repair or
  continue without the optional Skill where safe.

### Add Agent-specific progressive disclosure

Implement bounded projections for:

- Goal Association;
- Fast Planner;
- Deep Planner;
- Response Composer;
- Tool Result Interpreter.

Only the selected projection enters each model boundary. References and examples
are loaded only when allowed by budget and requested by the Agent contract.

Acceptance:

- complete Skill packages are not copied into every prompt;
- projection identity and digest appear in trace metadata;
- optional Skill loading failure cannot fabricate execution or evidence;
- prompt budgets and context truncation remain observable.

### Bind Agent Skills to Canonical Plans

Extend the Plan contract with selected Agent Skill provenance while keeping
capability execution unchanged.

The Plan should make this distinction explicit:

```json
{
  "selected_agent_skills": [
    {
      "agent_skill_id": "chromie.weather-information",
      "version": "1.0.0",
      "projection": "planner"
    }
  ],
  "steps": [
    {
      "capability_id": "chromie.weather.lookup",
      "args": {
        "location": "河南省内乡县",
        "date": "today"
      }
    }
  ]
}
```

The first list explains the method used by the Agent. The second list uses the
canonical executable Capability field.

Acceptance:

- plan validation checks Skill identity and provenance only;
- execution validation ignores Agent Skill text and continues to validate
  exact Capability IDs, schemas, policy, confirmation, and provider state;
- removing a Skill package cannot create new execution authority;
- replay and traces identify the exact Skill content used by the model.

### Implement grounded external information Skill

Add the reusable base Skill for read-only external information tasks. Its
projections should cover:

- authoritative binding resolution before retrieval;
- explicit verified-memory retrieval versus fresh lookup;
- evidence freshness and exact material-argument matching;
- evidence-safe pre-query acknowledgement;
- typed failure-stage interpretation;
- relevant, concise result explanation.

The Skill must not contain domain-specific phrase rules or implement a generic
external-information Workflow in Host code.

Acceptance:

- the Agent can choose memory, fresh lookup, clarification, or unavailable based
  on current Goal and evidence;
- stale evidence cannot resolve discourse or silently become a current result;
- no fixed acknowledgement length or wording is introduced.

### Implement weather information Skill

Add the first domain Skill extending grounded external information.

Its Agent projections should express:

- Goal bindings: location, time/date, and weather aspect;
- memory freshness and exact-match considerations;
- capability choices for weather lookup and verified memory;
- result interpretation for temperature, apparent temperature, rain,
  precipitation, wind, and condition;
- distinction among `location_not_found`, provider failure, network failure,
  and successful no-rain evidence;
- natural user-focused speech.

Provider-specific geocoding retries remain in the weather Capability adapter and
must not move into Skill-selection or discourse code.

Acceptance:

- an explicit Neixiang request produces a Neixiang weather Plan;
- the Chongqing result cannot override a later Neixiang binding;
- `那边` is resolved by Goal Association before weather methods are applied;
- exact fresh memory may be retrieved explicitly;
- mismatched or stale memory leads to a fresh lookup;
- the Skill improves related weather variants, not only one fixture sentence.

### Add observability and review evidence

Record:

- candidate Skill summaries shown to each Agent;
- model-selected Skill IDs;
- loaded projections and digests;
- Plan provenance;
- selection/loader repair or failure;
- resulting capability steps and outcomes.

Extend experience and scenario evidence without treating Skill selection as
execution success.

Acceptance:

- traces distinguish candidate, selected, loaded, applied, executed, and
  completed states;
- owner review can identify whether a defect came from Goal association, Skill
  selection, Skill content, Plan generation, capability execution, provider
  behavior, or result interpretation;
- no sensitive full Skill body is logged by default when a digest and projection
  identity are sufficient.

### Qualify through module, integration, and end-to-end scenarios

Add maintained tests for:

- Agent versus Skill responsibility boundaries;
- model-authored multi-Skill selection;
- explicit no-Skill decisions;
- malformed/unapproved package rejection;
- projection budget and provenance;
- weather first query;
- exact-memory weather follow-up;
- stale-memory fresh lookup;
- Chongqing correction to Neixiang;
- `那边` resolving to Neixiang;
- “the last task I told you” associating through Goal Association;
- provider `location_not_found` and successful hierarchical geocoding fallback;
- capability execution remaining unchanged by Skill package contents.

Benchmarks may assert acceptable behavior and architecture boundaries. They may
not add phrase maps, fixed Skill choices, or scenario-specific runtime branches.

Acceptance:

- dependency-light automated tests pass;
- maintained scenario inventory and migration parity pass;
- live text proves model-authored Skill selection and Plan provenance;
- live weather execution proves the selected method still crosses the existing
  trusted capability path;
- target validation remains separate from automated and diagnostic evidence.

## Explicitly deferred

- automatic installation from third-party repositories;
- remote Skill marketplaces;
- package-supplied execution permissions;
- automatic script execution;
- arbitrary Python/Shell plugin loading;
- Skill-authored provider registration;
- self-modifying Skills;
- unreviewed experience automatically rewriting owner-approved Skill content;
- a general-purpose Workflow engine;
- physical-robot autonomy justified only by Skill availability.

## Issue closure criteria

The issue may close only when:

- architecture and shared contracts clearly distinguish Agent, Agent Skill,
  Plan, and Capability;
- a secure read-only Skill registry exists;
- Skill selection is LLM-authored and observable;
- progressive Agent projections are implemented;
- Canonical Plans retain exact Skill provenance;
- Skills cannot authorize or execute capabilities;
- grounded external information and weather Skills are implemented;
- the complete weather and discourse scenario set passes;
- automated, live-text, and live-tool evidence are reported separately;
- documentation, changelog, roadmap, status, and contributor guidance agree.

## Immediate next implementation slice

After this documentation-only patch is reviewed and committed, begin with:

> **Make `capability_id` canonical while preserving a bounded `skill_id` compatibility reader.**

This migration must complete at the typed contract and model-facing boundaries
before Agent Skill selection is introduced. The following implementation slice
then establishes Agent Skill contracts and the read-only owner-approved loader.

Do not begin by writing a weather keyword selector, a fixed weather Workflow,
or an automatic Skill script loader. The rename is semantic cleanup only; it
must not change execution authority or behavior.
