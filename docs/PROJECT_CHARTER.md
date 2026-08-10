# Chromie Project Charter

This document defines the stable purpose and boundaries of Chromie. It should
change rarely. Current implementation and evidence belong in
[STATUS.md](STATUS.md); delivery order belongs in [ROADMAP.md](../ROADMAP.md).

### One resource responsibility, dynamically bounded capabilities

`AcquireAndDeliverResource` is one provider-neutral human responsibility.
`physical_object` and `information` are resource kinds, not sibling top-level
capability concepts. The semantic-authority boundary is stable: Chromie owns the
user Goal, cross-provider capability selection, ordering, and dependencies. The
execution-decomposition boundary is dynamic: each provider advertises the semantic
granularity it can currently guarantee, and Chromie plans over that live catalog.
A complete provider capability is one atomic planning unit to Chromie; when no one
capability covers the Goal, Chromie may compose multiple advertised capabilities
whose declared resource-state contracts collectively cover it. Provider-internal
substeps remain private unless the provider explicitly exposes them as capabilities.
Capability upgrades therefore move the decomposition boundary without changing the
Goal model, Host routing, or semantic authority.


## Mission

Chromie is a local-first realtime interaction control plane for voice assistants
that can invoke embodied capabilities safely.

The intended user experience is:

```text
natural speech
-> Cognitive Gateway: normalize, apply protective reflexes, and review attention
-> Goal-Driven Cognitive Core: understand goals, decompose, plan, and coordinate
-> validated speech and typed capability requests
-> trusted execution
-> observable completion, failure, cancellation, or recovery
-> concise spoken feedback
```

Chromie should make this loop responsive, interruptible, understandable, and
portable across a simulator and later physical robots without exposing low-level
robot controls to a language model.

## Product outcome

A successful Chromie release lets an operator:

- speak naturally and receive timely local responses;
- request a trusted high-level embodied skill;
- understand what will happen before risky work begins;
- approve, decline, interrupt, cancel, or stop work deterministically;
- see correlated evidence of what was proposed, authorized, executed, and
  recovered;
- move the same high-level interaction contract from simulation to a
  commissioned physical provider.

## System boundaries

### Chromie owns

- microphone capture, VAD, ASR coordination, playback, and barge-in;
- the Cognitive Gateway ingress boundary: input normalization, deterministic
  protective reflexes for stop, cancel, emergency, silence, and unusable audio,
  and bounded attention/admission review; attention review cannot authorize
  effects and direct or unclear turns fail open to cognition;
- conversation state and user-facing interaction semantics;
- the Goal-Driven Cognitive Core: goal meaning and continuity, semantic
  decomposition and planning, outcome reconciliation, and response composition;
- native structured Agent output and strict model-facing contracts;
- owner-approved Agent Skill discovery, bounded Agent projections, and
  selection provenance without granting Skill content execution authority;
- Trusted Capability Runtime validation, authorization, scheduling, timeout,
  and cancellation; legacy `SkillRuntime`, `SkillRequest`, `SkillResult`, and
  `skill_id` names remain only at explicit compatibility boundaries;
- evidence capture, acceptance tooling, deployment configuration, and release
  packaging.

### Soridormi owns

- provider-local embodied planning and execution inside advertised capability contracts;
- simulator and physical providers;
- robot resource exclusivity across processes;
- motion monitoring, stop, emergency stop, and recovery;
- device drivers, calibration, state estimation, and hardware commissioning.

### The language model may

- interpret user intent;
- produce concise speech;
- select zero or more owner-approved Agent Skills as reusable reasoning
  methods;
- select registered named capabilities for a typed Plan;
- propose validated TaskGraphs.

### The language model must never

- authorize its own side effects;
- bypass confirmation or safety policy;
- bypass Core semantic authority, Host authorization, or provider execution
  decisions;
- send raw motor, joint, actuator, torque, controller-array, or bus commands;
- decide deterministic operational controls;
- treat an Agent Skill, `SKILL.md`, bundled resource, or script as execution
  authorization;
- claim execution succeeded without provider evidence.

The legacy host hardware daemon is mock compatibility infrastructure, not a
future production robot backend.

### Cognitive boundary

The Cognitive Gateway is the narrow ingress, protective-reflex, and attention
boundary. It decides whether a turn must be acted on immediately for operational
safety, admitted to cognition, or ignored as confidently ambient input. It does
not own final user-goal meaning, task decomposition, planning, agent selection,
or response composition.

The Goal-Driven Cognitive Core owns those semantic decisions. Stop and emergency
commands are still user inputs, but their immediate protective effect must not
wait for model inference; the resulting control and evidence can then be
incorporated into goal and response state.

The independent Router service and compatibility authority have been removed.
The fast Goal Interpreter now runs inside the Agent-owned Goal-Driven Cognitive
Core and receives only admitted `UserTurnEnvelope` projections. It does not own
Gateway admission, Host authorization, execution, safety, or provider evidence.

## Engineering principles

1. **High-level contracts stay stable.** Simulation and physical providers
   should implement the same capability and result semantics. Chromie's
   cognitive, personality, and Social Attention policies must not branch on
   whether the active Soridormi provider is simulated or physical. Backend
   selection, body adaptation, calibration, and physical safety remain below
   the Chromie semantic boundary.
2. **Robot thinking belongs to the Cognitive Core, models, and contracts.**
   Outside deterministic operational controls, normal conversation, memory,
   tool, robot-action,
   capability-selection, body-goal interpretation, planning, low-confidence
   correction, and deep-thought behavior must be decided by LLM reasoning over
   language meaning, bounded context, capability descriptions, schemas, and
   task memory. Catalog search, score thresholds, regression fixtures, regexes,
   and phrase tables may retrieve candidates or validate and reject model
   output, but they must not decide ordinary robot intent or planning by
   themselves.
3. **Generality comes before specialization.** Reported utterances and scenario
   fixtures are probes into broad robot abilities, not the product goal by
   themselves. Every bug fix and feature should first identify the reusable
   semantic rule or capability behind the observed case. Generalize the behavior,
   not the exception. A fix should improve the reusable capability class behind
   the failure, such as robust intent understanding, stable catalog grounding,
   natural uncertainty handling, composable high-level action planning,
   truthful embodied speech, or valid end-to-end evidence. Do not tune Chromie
   only to pass the last visible sentence while leaving the underlying ability
   brittle.
4. **Fixes explain causality, not only diffs.** Every defect repair must state
   the observed failure, expected contract, earliest responsible boundary,
   evidence-backed root cause, and the mechanism by which the change restores
   the contract. The explanation must distinguish the initiating trigger, root
   cause, downstream symptoms, contributing conditions, and evidence limits.
   It must explicitly attribute the primary root cause to **LLM/model
   behavior**, **logic/workflow/contract design**, **code implementation**, or
   a **mixed causal chain**, and explain the evidence for that attribution. A
   wrong or malformed model output is not automatically an LLM root cause: when
   a maintained contract, validator, fallback, or workflow should have contained
   that expected model failure, the earliest missing or incorrect containment
   boundary owns the root cause. Conversely, call it a code defect only when the
   implementation violates an otherwise correct owned contract or workflow. A
   patch without this explanation and regression evidence is incomplete.
5. **Risky behavior fails closed.** Disabled, unavailable, malformed, expired,
   or unconfirmed work does not execute.
6. **Operational controls stay deterministic.** Stop, cancel, emergency,
   silence, and unusable-audio paths do not depend on model judgment.
7. **Rule-based routing stays narrow.** Phrase and pattern rules belong only to
   the deterministic operational filter. Normal conversation, tool, memory,
   robot-action, and deep-thought intent must come from bounded model
   understanding and contract validation. When valid meaning cannot be
   established, the Core returns a typed unavailable, clarification, or refusal
   outcome; it never invents an ordinary lane.
8. **Simulation precedes hardware.** Logical closure, failure handling, and
   recovery are proven in simulation before physical commissioning.
9. **Evidence is part of the product.** Implemented, automatically verified,
   target validated, and release ready are separate states.
10. **Physical rollout is progressive.** Shadow, dry-run, bounded single-skill,
   supervised multi-skill, and broader autonomy are distinct gates.
11. **Local-first does not mean opaque.** Failures, fallbacks, authorization,
   timing, and recovery causes remain inspectable.
12. **Benchmarks evaluate intelligence; they do not implement it.** Cognitive,
   personality, planning, and Social Attention choices remain model reasoning
   problems expressed through general prompts, bounded context, and contracts.
   Benchmark cases define acceptable behavior regions, hard safety and evidence
   invariants, and distribution measurements. They must not justify phrase
   tables, regular expressions, scenario-ID branches, fixed greeting gestures,
   or other Host rules that imitate intelligence merely to pass visible cases.
   LLMs may generate candidate scenarios and qualitative critique, but reviewed
   contracts and retained evidence remain authoritative for acceptance.
13. **Agent Skills teach; capabilities execute.** An Agent may select and
   combine owner-approved Agent Skills to inform a Plan, but a Skill has no
   independent Goal, provider registration, permission, confirmation exemption,
   or execution authority. All effects still use exact registered capabilities,
   Trusted Capability Runtime validation, and provider evidence. Skill retrieval may narrow
   candidates; it must not become phrase-based semantic selection.
14. **Use less to solve more.** Complexity is a cost, not evidence of progress.
   Prefer the smallest general solution that correctly solves the real problem.
   New modules, managers, abstractions, state machines, policy layers, and
   frameworks must justify their permanent maintenance cost. Prefer fewer
   concepts, clearer ownership, stronger invariants, and reuse or consolidation
   of existing logic when those choices remain correct.
15. **Restore invariants within the intended architecture.** A defect repair
   should identify the violated invariant and restore it with the smallest
   general change that fits the intended architecture. Minimal repair is the
   default, not a reason to preserve an architecture that the project owner has
   explicitly chosen to change. When an architectural direction is specified,
   move responsibility to that design and remove obsolete paths rather than
   layering compatibility machinery around the old design.
16. **Design fully, implement incrementally.** Document long-term architecture,
   ownership, evolution paths, and extension points in enough detail to keep the
   destination clear. Current runtime code should implement only complexity
   required by current validated needs. Design the future; do not prematurely
   build hypothetical future machinery.
17. **Solve behavior at the highest suitable semantic layer.** For semantic and
   conversational behavior, consider general prompts, bounded context, memory,
   and cognitive contracts before procedural exceptions. Prefer teaching the
   Cognitive Core one reusable rule over teaching Host code another case.
   Deterministic code remains responsible for mechanical correctness, safety,
   authorization, exact state transitions, and other invariants that must not
   depend on model judgment.
18. **Mechanisms report reality; cognition decides behavior.** Runtime mechanisms
   provide trustworthy facts about what was requested, scheduled, delivered,
   committed, completed, failed, cancelled, or observed. Cognitive layers decide
   meaning, communication, prioritization, and ordinary behavior from those
   facts. Low-level mechanisms must not quietly become owners of social or
   semantic judgment, and cognition must not invent runtime facts.
19. **Separate policy from mechanism.** Policy states what should happen and why;
   mechanisms provide the reusable means and trustworthy state needed to carry
   it out. Do not scatter one behavioral policy across special-case checks, and
   do not create a universal policy framework merely because one isolated rule
   needs enforcement. Generalize the rule before generalizing the machinery.
20. **Prompt complexity is still complexity.** LLM instructions are part of the
   architecture and accumulate maintenance cost just like code. Do not replace a
   code mountain with a prompt mountain. Prefer concise, general semantic rules
   over growing collections of scenario-specific instructions and examples.
21. **Cognition advances by the still-needed delta.** Every model-driven cognitive
   stage reasons from the authoritative Goal state plus Interaction Context and
   proposes only what remains meaningfully unsaid or undone. Actually delivered
   speech and trusted terminal execution evidence may satisfy prior work;
   generated text, scheduled speech, Plans, and committed requests do not become
   delivery or completion merely because they exist. Repetition is legitimate
   only when meaning requires it, such as an explicit repeat, retry after failure,
   correction, changed state, new evidence, clarification, or another genuinely
   new conversational responsibility. This is one shared continuity rule, not a
   growing set of pairwise module-suppression rules.
22. **Prompts teach principles; models supply ordinary semantic knowledge.**
   Production prompts state general reasoning and evidence contracts, while
   authoritative Capability descriptions, schemas, runtime state, and provider
   evidence state Chromie-specific facts the model cannot safely guess. Ordinary
   distinctions and world semantics remain model reasoning. Concrete examples
   such as one action differing from another belong primarily in regression and
   benchmark scenarios, not in a production-prompt answer library. If a complete,
   internally consistent prompt and correct system facts still produce a wrong
   semantic inference, measure and attribute that model failure instead of
   automatically hiding it behind another example-specific instruction.

23. **Goal progress communication is a shared responsibility with one cognitive owner per milestone.**
   Once a nontrivial Goal is sufficiently understood and still requires downstream
   work before a substantive answer or effect, Goal Interpretation should normally
   give one tiny polite prospective notification so the person knows Chromie got
   the Goal and is taking it forward. Missing result evidence limits what that
   notification may claim; it is not itself a reason for silence. A separate Fast
   Response is omitted when the substantive answer is immediate, an equivalent
   notification is already delivered or pending, the user requested silence, or
   another line would only repeat or add empty chatter. At the model-facing Goal
   Interpretation boundary, the **decision is mandatory even though speech is
   optional**: `fast_speech` must be either one brief notification or explicit
   `null`; omission is not a silence decision. The model chooses only that semantic
   text-or-silence decision. Host code materializes deterministic claim-envelope
   fields and validates evidence/authority without becoming a second semantic
   owner. Later cognitive or
   execution stages may surface a new trustworthy user-relevant milestone,
   limitation, wait state, failure, correction, or completion when doing so helps
   the person understand meaningful progress. Internal implementation steps are
   not milestones merely because they occurred. Every speech-capable stage must
   consult the Interaction Ledger and communicate only the still-needed semantic
   progress delta; equivalent delivered or already-pending speech is not repeated.
   The stage that owns a progress judgment owns whether and what to say: production
   must not insert a second LLM merely to re-decide or repair that ordinary
   communication choice. Deterministic code may reject malformed typed fields,
   unsupported authority, or evidence violations. If the semantic communication
   choice is systematically wrong, fix and qualify the source prompt/model rather
   than hiding the defect behind another model. Social Attention,
   clarification/confirmation, task progress communication, and final result
   delivery remain distinct responsibilities even when they happen close together.

## Non-goals

Chromie is not:

- a low-level robot controller or replacement for vendor control loops;
- a general-purpose distributed workflow engine;
- a durable personal-memory platform;
- an unattended physical-robot autonomy product in the current development scope;
- proof that every hardware profile, GPU, audio device, or robot is supported.

## Definition of success

Work advances the project only when it improves at least one of these outcomes
without weakening the others:

- interaction quality and latency;
- deterministic safety and recovery;
- contract portability across providers;
- measurable simulator or target evidence;
- operability, privacy, and release supportability.

New features that do not help close the current milestone, remove a documented
blocker, or strengthen one of these outcomes should normally wait.

## Detailed architecture owners

The stable mission above is authoritative. Current semantic, execution, and
brain/body contracts are maintained in:

- [Cognitive Gateway](COGNITIVE_GATEWAY.md);
- [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md);
- [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md);
- [Execution Lanes and Coordination](EXECUTION_LANES_AND_COORDINATION.md);
- [Resource Acquisition and Delivery](RESOURCE_ACQUISITION_AND_DELIVERY.md);
- [Single Semantic Authority](SEMANTIC_AUTHORITY.md).
