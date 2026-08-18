# Agent Skills Architecture

Status: Implemented architecture with canonical Capability terminology, passive
contracts/Loader, model-authored selection, Agent-specific progressive
disclosure, Canonical Plan provenance, and the grounded-information/weather
domain Skills implemented; positive rebuilt-service diagnostic evidence exists,
while clean source-bound target evidence remains open
Scope: Goal-Driven Cognitive Core, Agent roles, reusable cognitive methods,
planning, capability execution, and evidence

## Current repository-owned domain methods

- `chromie.grounded-external-information`: reusable evidence strategy for exact
  Goal bindings, verified-memory versus fresh reads, freshness, truthful pending
  speech, typed failures, and grounded explanation.
- `chromie.weather-information`: weather specialization for canonical
  location/time/aspect scope, weather memory matching, lookup planning, and
  result interpretation. It declares the grounded method as its parent.

Both packages expose projections for the five maintained Agent roles. Parent
metadata informs model-authored composition; the Host does not automatically
select a parent or domain Skill. Neither package registers or executes a
Capability.

Both packages also declare `applicable_routes`. The selection service filters
bounded summaries by the current structured route before the model chooses
zero or more methods. This is package-owned applicability disclosure, not Host
semantic selection: empty metadata remains unrestricted for compatibility,
while an out-of-scope Skill is never disclosed as a candidate.

## Purpose

Chromie needs reusable task knowledge without creating a second planner, a
second capability registry, or a new source of execution authority.

This document defines **Agent Skills** as passive, reusable methods that an
LLM-driven Agent may discover and use when producing a plan. Agent Skills
help the Agent reason about a class of tasks. They do not own goals, execute
code, authorize effects, or replace the typed capability and provider path.

The governing relationship is:

```text
current Goal + bounded context + available evidence
        ↓
Agent selects zero or more Agent Skills
        ↓
Agent generates a typed Plan for this situation
        ↓
Plan references registered Capabilities through `capability_id`
        ↓
Trusted Capability Runtime (`CapabilityRuntime`) validates and dispatches
        ↓
Provider lifecycle/result evidence returns asynchronously to cognition
        ↓
Agent closes or replans the Goal
```

The architecture preserves the project principle:

> Thinking belongs to the LLM. Agent Skills teach methods; they do not
> implement hidden Host intelligence.

## Vocabulary

| Term | Meaning in Chromie | Owns a goal? | Makes semantic decisions? | Executes effects? |
|---|---|---:|---:|---:|
| Agent | An LLM-driven cognitive role with a defined responsibility, bounded context, and typed output | Within its assigned responsibility | Yes | No |
| Agent Skill | Passive reusable task knowledge, methods, constraints, examples, and capability guidance | No | No; it informs an Agent | No |
| Plan | A per-turn or per-replan typed proposal generated for the current Goal and situation | No | It records the Agent's decisions | No |
| Capability / Tool | An atomic executable contract with typed arguments and results | No | No | Only through Trusted Capability Runtime/provider authority |
| Workflow | A predefined fixed or partly fixed execution sequence | No | Usually limited | Potentially, if separately authorized |
| Trusted Capability Runtime / `CapabilityRuntime` | Deterministic validation, authorization, non-blocking dispatch, scheduling, lifecycle/cancellation, correlation, and evidence boundary | No | No ordinary semantic decisions | Yes, after validation |
| Provider | The implementation authority for a capability; Soridormi owns embodied planning and physical safety | No | Provider-local planning where declared | Yes |

### Agent

An Agent is an active decision-making role. It receives a responsibility,
current Goals, bounded context, contracts, and evidence. It may select Agent
Skills, generate a Plan, evaluate results, and request replanning.

Examples include:

- Goal Association: resolve discourse and Goal relationships;
- Fast Planner: produce a complete low-latency Plan, exact Communicative
  Activities, and evidence-bound follow-up when confidence is high;
- Deep Planner: reason over broader context and alternatives, including exact
  communicative wording when escalation is necessary.

An Agent is not defined merely by a prompt file. It is defined by its semantic
responsibility, context boundary, typed output, and place in the cognitive loop.

### Agent Skill

An Agent Skill is a passive reusable playbook. It may describe:

- when a method is applicable;
- which facts or bindings matter;
- how capabilities may be combined;
- what evidence is required;
- common failure modes and recovery options;
- quality and truth constraints;
- a small number of reviewed examples;
- references needed for domain reasoning.

An Agent Skill has no independent Goal, no autonomous loop, no durable task
state, and no execution authority. It cannot start itself or commit a side
effect. The Agent remains responsible for selecting the Skill and deciding what
to do in the current situation.

### Plan

A Plan is an instance, not reusable domain knowledge. It captures what the Agent
proposes **this time**, including:

- Goal coverage and satisfaction;
- selected capability steps;
- exact arguments and provenance;
- ordering or concurrency;
- clarification, confirmation, or alternative requirements;
- expected evidence and completion conditions;
- the Agent Skills that informed the proposal.

The same Agent Skill can lead to different Plans for different users,
contexts, evidence freshness, providers, or capability availability.

### Capability / Tool

A Capability is the executable atomic contract. Examples are:

- `chromie.weather.lookup`;
- `chromie.memory.retrieve_verified_tool_result`;
- `soridormi.look_direction`;
- `soridormi.walk_velocity`.

Capabilities remain registered through typed manifests or authoritative live
provider schemas. An Agent Skill may declare that a capability is required
or useful, but that declaration does not register or authorize the capability.

## Canonical naming and executable-Skill removal

Chromie uses the word **Skill** only for passive **Agent Skills**. Executable runtime
operations are **Capabilities**. The canonical vocabulary is:

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

Canonical terms:

- **Agent Skill / `agent_skill_id`**: passive LLM-usable task method;
- **Capability / `capability_id`**: executable typed contract;
- **CapabilityRequest / CapabilityResult**: exact execution request and intermediate/terminal result DTOs;
- **CapabilityRuntime**: source name for the Trusted Capability Runtime;
- **Capability Provider**: implementation authority behind an exact registered Capability.

Chromie's canonical executable runtime uses `capability_id`, `capability_version`,
`CapabilityRequest`, `CapabilityResult`, `CapabilityRuntime`, `CapabilityDefinition`,
`CapabilityRegistry`, and `CapabilityProvider`. The retired executable names `skill_id`,
`skill_version`, `SkillRequest`, `SkillResult`, `SkillRuntime`, `SkillDefinition`,
`SkillRegistry`, and `SkillProvider` are not live Chromie contracts or compatibility aliases.
Soridormi may still expose provider-local wire `skill_id`; its adapter translates that field
to Chromie's canonical `capability_id` and does not transfer identity authority upstream.
Agent Skill vocabulary remains separate and intentionally uses `agent_skill_id`. Historical
artifacts that genuinely require old-field readability must be migrated/versioned at an
explicit ingestion/archive boundary rather than widening live runtime contracts.

The naming cleanup changes no semantic or physical authority. Capability registration,
schema validation, confirmation, authorization, resource arbitration, provider ownership,
physical safety, request/result correlation, and Evidence remain independently enforced.

## Architectural principles

### Skills teach; Agents decide

An Agent Skill may explain how to approach a task class. It must not decide
that the current user request belongs to that class. Final Skill selection and
all ordinary semantic decisions belong to the LLM-driven Agent.

Candidate retrieval may narrow the available Skill set using metadata,
embeddings, capability links, or bounded catalog search. Candidate retrieval is
not semantic authority. The model may select none, one, or several Skills.

Prohibited:

```python
if "天气" in user_text:
    selected_skill = "weather-information"
```

Allowed:

```text
retrieve bounded candidate summaries
→ Agent evaluates current Goal and context
→ Agent emits typed selected Agent Skill IDs
→ Host validates that those IDs and versions exist
```

### Skills describe composition; they do not hardcode every execution

An Agent Skill can describe how several capabilities may contribute to a
class of tasks. It must not require a fixed sequence when context could justify
a different Plan.

For weather information, the method may include:

- use exact fresh verified memory when appropriate;
- otherwise perform a fresh weather lookup;
- do not claim a result before evidence exists;
- answer the user's actual weather concern;
- distinguish location resolution failure from provider or network failure.

The current Agent decides whether memory lookup, fresh lookup, clarification, or
an unavailable response is appropriate.

### Skills have no execution authority

An Agent Skill directory, `SKILL.md`, example, reference, or bundled script
never receives execution authority merely because the Agent loaded it.

All effects still require:

```text
model-authored Plan
→ exact registered Capability ID and arguments
→ deterministic schema and policy validation
→ confirmation where required
→ `CapabilityRuntime` validation and non-blocking dispatch
→ provider validation and execution
→ correlated lifecycle events and terminal result evidence
```

If a Skill package contains code or scripts for interoperability, they are
inert resources unless separately reviewed and registered as capabilities
through the existing authority path.

### One semantic authority per turn

Agent Skills do not create sub-planners that compete with Goal Association,
Fast Planner, or Deep Planner.

A “weather skill” must not independently resolve `那边`, select an old Goal,
query memory, execute a provider, and compose final speech behind the canonical
Plan. That would be a hidden Weather Agent or fixed Workflow, not an Agent
Skill.

### Agent-specific projections

Different Agents need different parts of a Skill. Chromie should progressively
load a bounded projection rather than inject every Skill document into every
model prompt.

A weather Skill may expose:

| Agent | Projection |
|---|---|
| Goal Association | Semantic Goal bindings such as location, date, and weather aspect; discourse resolution remains model-authored |
| Fast/Deep Planner | Evidence strategy, capability options, freshness, alternatives, failure recovery, exact pre/post-evidence wording, and result relevance |

The Host selects the requested projection only after the responsible Agent has
selected the Skill or after an earlier authoritative Agent has supplied the relevant
Skill selection for the same canonical Goal. Goal Association has no canonical Goal
identity yet, so its pre-association Agent-Skill path receives no historical
active/recent Goal IDs and deterministically returns `no_skill` without a model call.
This prevents an unrelated unfinished Goal from injecting a stale domain method into
new user meaning. Domain-method selection begins only after Goal Association has
established the relevant canonical Goal identity. The Host never infers the domain
from phrases.

### Progressive disclosure

Skill loading should be bounded:

```text
Skill index: ID, version, title, concise description, applicability metadata
        ↓
Agent selects candidate Skill IDs
        ↓
load only the relevant Agent projection
        ↓
load references/examples only when requested within budget
```

This keeps prompts small, makes selection observable, and avoids turning the
entire Skill library into permanent system-prompt text.

The current implementation completes this flow for the five responsible Agent
roles. Planner selection is narrowed to the Goal IDs accepted by the current
Goal Association result; retained Goals remain available to Goal Association
for model-authored continuity, but an unrelated terminal Goal cannot contribute
planner Skill provenance to a new Plan. Exact provenance validation remains
strict. If the HTTP planner boundary cannot attach a disclosure to the returned
Plan, it returns a structured non-executable escalation or unavailable Plan
instead of an unhandled service error.

### Evidence and provenance

Every loaded Skill projection should have stable provenance:

- Skill ID and semantic version;
- owner-approved status;
- content digest;
- projection name;
- source path or package identity;
- selection-producing Agent and turn/Goal identity.

Canonical Plans and traces should record which Agent Skills informed the
Plan. Skill provenance explains the method supplied to the model; it does not
prove that execution succeeded.

### Skills are not memory

A Skill is reusable method knowledge. Conversation facts, user preferences,
verified tool results, environment observations, and task state remain in their
existing scoped memory/evidence systems.

Examples:

- “When should a weather result be considered stale?” may belong to a Skill;
- “Chongqing was 37.4°C at 18:28” is verified tool evidence;
- “the user corrected the location to Neixiang” is a discourse referent update;
- “the robot is currently in the living room” is physical state.

A Skill must not maintain hidden mutable state that competes with those systems.

## Proposed repository contract

The first implementation should use a separate, read-only Agent Skill root:

```text
agent-skills/
  grounded-external-information/
    skill.yaml
    SKILL.md
    projections/
      goal_association.md
      fast_planner.md
      deep_planner.md
    references/
    examples/
  weather-information/
    skill.yaml
    SKILL.md
    projections/
      goal_association.md
      fast_planner.md
      deep_planner.md
    references/
    examples/
```

The initial package contract should include:

```yaml
schema_version: "1.0"
agent_skill_id: chromie.weather-information
version: 1.0.0
title: Weather Information
description: Grounded methods for understanding, planning, and explaining weather requests.
authority: agent_method_only
execution_authority: none
owner_approved: true
content_digest: sha256:<digest of every package file except skill.yaml>
extends:
  - chromie.grounded-external-information
required_capabilities:
  - chromie.weather.lookup
optional_capabilities:
  - chromie.memory.retrieve_verified_tool_result
applicable_routes:
  - tool
  - chat
projections:
  goal_association: projections/goal_association.md
  fast_planner: projections/fast_planner.md
  deep_planner: projections/deep_planner.md
```

This is now the implemented `skill.yaml` schema. `schema_version`, both
Authority fields, owner approval, and `content_digest` are explicit. Metadata
uses strict safe YAML with unknown and duplicate keys rejected. Projection paths
are normalized package-relative Markdown paths and may not escape through `..`,
absolute paths, or symlinks.

The digest deterministically frames every package-relative path and byte length
for all files except `skill.yaml`, then hashes their bytes. Generate it with:

```bash
python scripts/agent_skill_digest.py agent-skills/<package>
```

The following invariants are enforced:

- `authority` is cognitive only;
- `execution_authority` is none;
- only owner-approved packages are model-visible;
- a package cannot register a capability or provider;
- unknown or malformed Skill packages fail closed and are not loaded;
- package content is mounted read-only in the maintained Compose profile;
- startup retains bounded metadata summaries, not full `SKILL.md` or projection text;
- explicit body/projection reads recheck the package digest before returning text;
- package Python or scripts are inert and are never imported or executed;
- Skill selection is model-authored and typed through a bounded boundary;
- the matching Agent receives only selected role-specific projections after exact
  package/projection digest verification and prompt-budget checks;
- untrusted caller-supplied projection context is stripped before disclosure;
- selection/disclosure identity and digests are observable without logging content;
- Canonical Plans retain content-free exact planner Skill provenance; domain Skills remain the next separate slices.

## Weather vertical slice

Weather is the first proposed end-to-end Agent Skill because it exercises
Goal association, memory, external tools, response coordination, provider
failure, and evidence-grounded explanation without adding physical side
effects.

### Domain Skills

```text
chromie.grounded-external-information
        +
chromie.weather-information
```

`grounded-external-information` should provide the reusable method for:

- resolving material query bindings before retrieval;
- deciding between exact verified memory and a fresh external lookup;
- not claiming current results before evidence;
- coordinating acknowledgement with lookup;
- interpreting typed failure stages accurately;
- answering from selected trusted evidence.

`weather-information` should add:

- location, date/time, and weather-aspect semantics;
- weather freshness considerations;
- temperature, apparent temperature, rain, precipitation probability, wind,
  and condition interpretation;
- provider location resolution as a capability concern;
- user-focused concise answer guidance.

### Example Plans

First query:

```text
Goal: determine whether it is raining in Neixiang today
Selected Agent Skills:
- chromie.grounded-external-information
- chromie.weather-information
Plan:
- execute chromie.weather.lookup(location=Neixiang, date=today)
- produce an immediate evidence-safe acknowledgement in parallel
- interpret returned precipitation evidence
```

Recent exact result:

```text
Goal: remind the user of the Chongqing temperature just checked
Selected Agent Skills:
- chromie.grounded-external-information
- chromie.weather-information
Plan:
- execute chromie.memory.retrieve_verified_tool_result for exact Chongqing/date bindings
- use a fresh lookup only if memory is absent, stale, or mismatched
```

Correction and follow-up:

```text
User: 不是重庆，我说的是内乡。
User: 今天那边下雨了吗？
Goal Association:
- resolves 那边 to the scoped Neixiang referent
- preserves the earlier Chongqing Goal and its evidence
- creates a replacement Goal binding location=Neixiang when the model judges
  that the explicit correction changes the material location
Planner:
- applies weather methods only after the binding is authoritative
- never uses old Chongqing evidence to resolve the reference
```

The Skill does not implement `那边 -> 内乡`. Goal Association remains the
semantic authority. The Host observes only typed association relationships and
validates the returned Goal/referent DTO; it does not infer a correction from
phrases, place names, binding differences, or recency.

## Security and trust model

Agent Skill content is prompt input and must be treated as potentially
powerful instruction material.

The initial implementation must therefore:

- load only repository-owned or explicitly owner-approved Skills;
- pin versions and content digests in traces;
- reject path traversal, symlinks escaping the Skill root, malformed metadata,
  and duplicate IDs;
- prevent Skill text from overriding higher-priority project and Agent
  contracts;
- prevent Skill packages from adding tools, providers, permissions, or
  confirmation exemptions;
- keep physical safety and refusal authority in Soridormi;
- keep deterministic operational reflexes outside Skill selection;
- make loaded Skill IDs and projections observable.

Third-party installation and remote Skill marketplaces are outside the first
issue. Interoperability may be evaluated later through an explicit import and
review process.

## Observability

A cognitive trace should eventually record:

```json
{
  "selected_agent_skills": [
    {
      "agent_skill_id": "chromie.weather-information",
      "version": "1.0.0",
      "projection": "planner",
      "digest": "sha256:...",
      "selected_by": "deep_planner",
      "goal_ids": ["goal_weather_neixiang"]
    }
  ]
}
```

Important distinctions:

- selected: the Agent chose the Skill;
- loaded: the Host supplied a validated projection;
- applied: the Plan cites the Skill as informing its method;
- executed: only capability steps execute;
- successful: provider and outcome evidence close the Goal.

Skill selection alone is not evidence of task success.

## Prohibited anti-patterns

Do not implement:

- phrase-to-Skill maps for ordinary requests;
- a weather-specific Host branch that selects `weather-information`;
- automatic execution of scripts from a Skill directory;
- a second capability registry owned by Skills;
- Skill-owned durable Goal or conversation state;
- a Skill that resolves discourse outside Goal Association;
- a Skill that bypasses CanonicalPlan or Trusted Capability Runtime;
- scenario-ID branches added only to satisfy benchmarks;
- permanent injection of every Skill into every Agent prompt;
- model-visible third-party Skill content without review and provenance.

## Relationship to mainstream Agent Skills

Chromie Agent Skills intentionally follow the useful part of the common
Agent Skills model: a reusable, progressively disclosed task playbook that a
general Agent can select when useful.

Chromie narrows that model for a long-running embodied system:

- Skills are passive Agent method assets;
- Skills have no implicit script execution;
- Skills cannot register capabilities;
- Agent semantic authority remains explicit;
- Plans are typed and observable;
- all effects use the existing trusted capability path;
- Soridormi retains physical planning and safety authority.

## Architectural acceptance

The architecture is correctly implemented only when all of the following hold:

- an Agent can select zero, one, or several Agent Skills from bounded
  summaries;
- selection is model-authored, typed, and traceable;
- the Host cannot select ordinary Skills from user phrases;
- different Agents receive bounded projections rather than the complete Skill;
- Plans record Skill provenance but execute only registered Capabilities;
- malformed or unapproved Skills are not loaded;
- Skill content cannot grant execution or confirmation authority;
- the weather vertical slice improves general weather-task behavior without
  hardcoding the Chongqing/Neixiang sentences;
- benchmarks evaluate selection, plan quality, grounding, and failure behavior
  without implementing any of them;
- live execution still crosses Trusted Capability Runtime and provider safety boundaries.
