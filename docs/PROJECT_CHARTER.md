# Chromie Project Charter

This document defines the stable purpose and boundaries of Chromie. It should
change rarely. Current implementation and evidence belong in
[STATUS.md](STATUS.md); delivery order belongs in [ROADMAP.md](../ROADMAP.md).

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

- embodied planning and execution;
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
   cause, downstream symptoms, contributing conditions, and evidence limits. A
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
