# Cognitive Gateway / 认知网关

Status: authoritative architecture and terminology decision. The versioned,
immutable `UserTurnEnvelope`, shared `ReflexOutcome`/`ReflexFilter`, host
admission adapter, deterministic stop/cancel path, and deterministic local
suppression path are implemented. Admitted envelopes are projected into the
current Goal-Driven Cognitive Core without changing the compatibility Router
or Agent wire contracts. Physical extraction of the five logical modules,
dedicated Soridormi E-stop/safe-idle evidence, and service-name migration
remain open. Current implementation and evidence are owned by
[STATUS.md](STATUS.md).

## 1. Name and purpose

- **English:** Cognitive Gateway
- **Chinese:** 认知网关

The Cognitive Gateway is Chromie's bounded ingress layer for user turns and
other interaction input. Its implemented version 1 contract converts
transport-specific input into a stable `UserTurnEnvelope`, while preserving
deterministic protection and attention policy before the Goal-Driven Cognitive
Core reasons about meaning.

`Gateway` means a controlled boundary between input transport and cognition.
It is not a general API gateway, a request router, or the robot's brain. The
Gateway prepares evidence for cognition; it does not perform cognition on the
Core's behalf.

## 2. Functional nervous-system analogy

The useful human analogy is functional, not anatomical. The Gateway resembles
sensory preprocessing, protective reflexes, orienting attention, and context
preparation before deliberate reasoning. The Goal-Driven Cognitive Core
resembles the later process that interprets meaning, associates goals, plans,
delegates work, evaluates outcomes, and decides what to communicate.

This does not claim that one software module corresponds one-to-one with a
specific brain region. Human attention, reflexes, language, planning, and motor
control are distributed and overlapping. The analogy only clarifies
responsibility and timing:

```text
incoming signal
  -> protect first when necessary
  -> decide whether usable input should enter cognition
  -> preserve and assemble bounded evidence
  -> deliberate about goals and actions
```

## 3. System position

The logical interaction path is:

```text
voice / text / trusted interaction event
  -> transport capture, VAD, ASR, and input-quality evidence
  -> Cognitive Gateway
       Input Normalization
       Protective Reflex
       Attention Review
       Context Assembly
       Turn Admission -> UserTurnEnvelope
  -> Goal-Driven Cognitive Core
       Goal Association and segmentation
       Fast / terminal Deep Planning
       deterministic validation and commitment
       agent, tool, memory, and embodied execution coordination
       outcome reconciliation against goal success criteria
       final response composition
  -> trusted Skill Runtime / tools / memory / Soridormi
  -> execution evidence returned to the Core
  -> validated speech and optional social-attention delivery
```

The Gateway answers, "What input evidence may enter cognition, and must a
protective control happen immediately?" The Core answers, "What does this mean,
what goal is present, what should be done, what actually happened, and what
should Chromie say?"

The [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
remains authoritative for the Core's goals, continuity, planning, validation,
execution evidence, and response behavior.

## 4. Exact Gateway modules

The Cognitive Gateway contains exactly these five logical modules. They may be
deployed together or separated physically, but their contracts and ownership
remain distinct.

| Module | Chinese name | Owns | Produces |
|---|---|---|---|
| Input Normalization | 输入规范化 | Transport-independent shaping, original-input preservation, language/timing hints, input-quality attachment, bounded decoding and size checks | Normalized input evidence without semantic reinterpretation |
| Protective Reflex | 保护性反射 | Deterministic stop, cancel, emergency, silence, and unusable-input controls that must not wait for model judgment | Immediate `ReflexOutcome` plus evidence attached to the turn |
| Attention Review | 注意审查 | Bounded addressedness and ambient-input review that can suppress only policy-permitted non-effectful input | Attention finding with admit/suppress recommendation and reason |
| Context Assembly | 上下文组装 | Bounded, source-attributed snapshots of conversation, active goals, engagement, environment, capability availability, and input quality | Immutable context references with freshness/provenance metadata |
| Turn Admission | 话轮准入 | Final deterministic validation of the ingress envelope and one admission disposition | A `UserTurnEnvelope`, or an explicit suppressed/unusable/reflex-only record |

### 4.1 Input Normalization / 输入规范化

Input Normalization preserves what arrived. It may normalize encoding,
whitespace, language tags, timestamps, channel identity, and bounded quality
signals. It may reject malformed transport data or mark an ASR hypothesis as
uncertain. It must not silently rewrite an utterance to match a likely tool,
skill, intent, or prior goal. Original input remains immutable evidence.

### 4.2 Protective Reflex / 保护性反射

Protective Reflex is the only Gateway module allowed to trigger an immediate
operational effect. Its authority is narrow and deterministic:

- interrupt or stop current speech;
- cancel current interaction work;
- request the trusted embodied stop or emergency path;
- suppress silence, malformed input, or unusable audio;
- emit correlated evidence of what was requested and what the trusted runtime
  actually stopped.

It does not plan a replacement task, decide ordinary meaning, select a normal
capability, or claim cancellation succeeded without runtime evidence.

In the current implementation, `trigger=emergency_stop_command` records only
recognition of the input; recognition alone proves neither dispatch nor a safe
state. The host then dispatches both global runtime cancellation and the
dedicated Soridormi E-stop path, and the cancellation receipt records E-stop
success, failure, or unavailability. Reaching safe idle still requires an
explicit correlated Soridormi postcondition.

### 4.3 Attention Review / 注意审查

Attention Review decides whether otherwise usable input should be presented to
the Core. It is an interaction policy, not an intent classifier. It may suppress
only bounded, high-confidence ambient speech when engagement is inactive and
policy permits suppression.

A direct question, request, greeting, Chromie's name, active-goal continuation,
unclear review, malformed model output, or contradiction between question form
and an ambient label fails open to Core review. Attention Review cannot
authorize an effect.

### 4.4 Context Assembly / 上下文组装

Context Assembly gathers only bounded evidence the Core needs to reason. Every
item identifies its source, freshness, and confidence when applicable. Missing
context remains unknown; it is never filled with invented facts.

Context Assembly does not decide that a turn belongs to an active goal. It
provides bounded active-goal candidates and evidence; Goal Association in the
Core decides the semantic relationship.

### 4.5 Turn Admission and `UserTurnEnvelope` / 话轮准入与用户话轮封装

Turn Admission creates one stable record for every received input, including a
stop command. The implemented version 1 envelope is represented by the
following abbreviated example:

```json
{
  "schema_version": 1,
  "turn_id": "turn_...",
  "session_id": "session_...",
  "conversation_id": "conversation_...",
  "received_at": "...",
  "channel": "voice",
  "original_input": {"text": "Stop now."},
  "normalized_input": {"text": "Stop now.", "language": "en-US"},
  "quality": {
    "source": "asr_final",
    "usable": true,
    "asr_confidence": 0.97,
    "reason": ""
  },
  "attention": {
    "disposition": "admit",
    "source": "cognitive_gateway.protective_reflex",
    "confidence": 1.0,
    "reason": "protective control is retained for cognitive reconciliation"
  },
  "reflex": {
    "schema_version": 1,
    "matched": true,
    "action": "interrupt",
    "trigger": "stop_command",
    "interrupt_current": true
  },
  "context_refs": [
    {
      "context_type": "active_goal_snapshots",
      "reference_id": "ctx_active_goal_snapshots_...",
      "source": "orchestrator.conversation_state",
      "captured_at": "...",
      "freshness": "current",
      "age_ms": 0
    }
  ],
  "admission": "reflex_and_admit"
}
```

The shared model is frozen and rejects unknown fields. Normalized text may
change whitespace only; context references are bounded, unique, and
source/freshness attributed; admission must agree with quality, attention, and
reflex evidence. A `UserTurnEnvelope` does not contain a Gateway-authored normal
intent, goal, route, selected capability, plan, or final response.

## 5. Explicit non-ownership

The Cognitive Gateway does **not** own:

- normal-language intent interpretation;
- user-goal discovery, association, segmentation, or lifecycle decisions;
- capability, tool, agent, or skill selection;
- task decomposition, ordering, concurrency, or replanning;
- tool, memory, or physical execution;
- evaluation of whether execution satisfied a user goal;
- final user-facing response composition, TTS wording, or social expression;
- authorization of ordinary side effects.

Those responsibilities belong to the Goal-Driven Cognitive Core, deterministic
validators, the host Skill Runtime, tools, memory providers, and Soridormi.

`Semantic Triage`, `Affordance Grounding`, and `Turn Proposal` were useful names
during exploration, but are not Gateway modules in the settled boundary:

- semantic triage belongs to Core understanding and goal analysis;
- affordance grounding belongs to Core planning against trusted capability
  evidence;
- a turn proposal is replaced by the evidence-preserving `UserTurnEnvelope`;
  any proposed action or response belongs downstream.

## 6. Stop is both input and reflex

A stop command is a real user input. Chromie retains it as a correlated turn so
later cognition, audit, and response can understand what the user did. It is
also a protective control that cannot wait for ordinary semantic analysis.

```text
receive stop-like input
  -> assign and retain turn identity
  -> deterministically trigger the protective stop/cancel path
  -> collect a trusted cancellation dispatch receipt
  -> attach ReflexOutcome and the receipt to the turn audit
  -> (target) let the Core reconcile affected goals from terminal evidence
```

The reflex may begin before the complete envelope or model review is ready.
Recording must never delay stopping, and stopping must not erase the turn or
leave the cancellation unaudited. Later semantic correction must never undo an
already-applied stop or silently resume physical work. The current host records
the dispatch receipt with the reflex turn. Exact named-Goal cancellation has a
separate implemented receipt-to-Goal transaction; automatic reconciliation of
broad fixed reflex receipts into every affected canonical Goal remains open.

Output invalidation, scoped Skill Runtime cancellation, and the dedicated
E-stop are dispatched in one safety-first phase. Device/audio teardown may wait
on a playback lock, but it cannot serialize runtime cancellation or E-stop
behind that wait. The receipt distinguishes provider cancellation failures,
host dispatch failures, and dedicated E-stop evidence; none of those fields is
itself a safe-idle claim.

For `global_emergency`, the host also cancels every unfinished interaction
workflow, including work still blocked in preflight. This fail-closed sweep is
independent of a successful Skill Runtime receipt, so a runtime dispatch
failure cannot leave an older host interaction able to start later. The receipt
records every host interaction for which task cancellation was requested.

### 6.1 Cancellation scope is not goal guessing

The deterministic path does not choose one goal from natural-language meaning.
It first assigns one closed cancellation scope:

| Input class | Cancellation scope | Deterministic target |
|---|---|---|
| `Stop talking`, `别说了` | `output_only` | The host's shared audible-output resource plus interruptible speech requests in the bound interaction |
| `Stop moving`, `停止移动` | `embodied_motion` | Current and queued requests explicitly declared to have a physical-motion effect |
| Bare `Stop`, `Cancel`, `停止` | `current_interaction` | Every unfinished request in the foreground interaction; completed goals and unrelated remembered goals are unchanged |
| Exact structured target selected by Core | `specific_goal` | Structured skill/effect requests whose committed `source_goal_ids` are wholly contained in the exact target set and whose plan identity matches |
| `Emergency stop`, `急停` | `global_emergency` | Every unfinished request and host interaction workflow plus a dispatch attempt through the dedicated Soridormi E-stop path |

`ReflexOutcome` carries only the fixed reflex scopes. The trusted runtime
contract accepts `specific_goal` only from the Core-managed cognitive path. The
Core resolves semantic Goal IDs; the host supplies the exact committed
interaction, plan ID, fingerprint, and runtime request binding. The model never
invents runtime request IDs, delays an emergency stop, or authorizes automatic
resumption. The host validates exact dispatch receipts before atomically
applying target and provider-coaffected Goal transitions. A missing, stale,
shared-owner, non-interruptible, or provider-failed receipt leaves Goal state
unchanged and produces a conservative response.

Goal-owned cognitive speech carries the same Goal and plan binding into Skill
Runtime. The local playback provider is shared rather than request-isolated, so
a named speech cancellation may widen to `output_only`; the host invalidates
the shared output resource and the receipt identifies all coaffected Goals.
This does not claim that already completed or already heard speech can be
retracted.

The runtime selects both running and queued requests. A selected queued request
is closed as `cancelled` with `reason_code=cancelled_before_start` and is never
sent to a provider. A completed request remains completed. Unselected Skill
Runtime requests that are independent continue; existing sequencing,
dependency, and required-delivery barriers still apply. For example, cancelling
a required pre-action speech cue prevents its dependent physical request from
starting. Selected non-interruptible requests and provider cancellation
failures are reported separately; neither is evidence that the effect stopped.
If one canonical step is jointly owned by a target goal and an untargeted goal,
exact isolation is impossible: the runtime reports a shared-owner conflict and
does not pretend that only one goal was affected.

Pending confirmation has one approval token for the staged response. Fixed
reflex behavior remains conservative: `output_only` preserves that token, while
a motion stop revokes the whole token when any confirmed request is
motion-bound or cannot be classified safely. Named `specific_goal` cancellation
can narrow a pending multi-Goal confirmation. It rejects shared-owner steps,
removes the targeted requests, creates an immutable child plan and fresh request
identities for the preserved Goals, and replaces the old token only after the
Conversation State cancellation transaction succeeds.

Exact isolation also depends on provider granularity. Current Soridormi motion
cancellation is global-domain, so a specific physical target widens to
`embodied_motion`; the receipt explicitly records `widened`, the reason, and
every coaffected request and goal. It must never be presented as exact
goal-only cancellation. A deterministic hold for ambiguous safety-relevant
language is a future policy, not current implementation.

`embodied_motion` is ledger-bound: it selects motion registered in the host
Skill Runtime. It is not an unconditional controller stop for motion started
outside that ledger. `global_emergency` is the scope that additionally
dispatches Soridormi's dedicated E-stop regardless of the host request ledger.

## 7. Compatibility with the current Router

The repository currently exposes these compatibility names and surfaces:

- Docker service `chromie-router` and component directory `router/`;
- `POST /route`, `GET /routes`, and `RouteDecision`;
- `ROUTER_*` configuration and `router_*` logs;
- routes such as `chat`, `tool`, `memory`, `robot_action`, `interrupt`, and
  `ignore`.

They remain valid current interfaces until a separate migration changes them.
This decision does not rename an API, environment variable, container, file,
log field, or deployment unit.

The current service mixes responsibilities that the target architecture
separates: parts of Input Normalization, Protective Reflex, Attention Review,
semantic classification, capability grounding, and compatibility route
production. Therefore:

- current Router behavior is the compatibility implementation, not the whole
  Cognitive Gateway;
- Router is not a synonym for the Goal-Driven Cognitive Core;
- Cognitive Gateway is not a cosmetic rename of the mixed service;
- `RouteDecision` may bridge current consumers, but is not the target
  `UserTurnEnvelope` contract;
- existing logs and APIs remain evidence under their current names; the host
  now dual-records the envelope and correlation IDs while compatibility
  surfaces remain deployed.

## 8. Migration state and path

Migration is contract-first and behavior-preserving. The state markers below
describe repository implementation only; retained environment evidence remains
owned by [STATUS.md](STATUS.md).

1. **Implemented:** adopt Cognitive Gateway / 认知网关 in architecture documents
   while retaining current Router compatibility names.
2. **Implemented:** use shared frozen version 1 `ReflexOutcome` and
   `UserTurnEnvelope` contracts with immutable input, quality, attention,
   context provenance, admission, and correlation fields.
3. **Implemented:** run the shared Protective Reflex locally in the host,
   reuse it in Router compatibility rules, revoke pending approval before the
   first await, and keep the reflex lifecycle from being cancelled by a later
   utterance.
4. **Implemented logical boundary:** build and dual-record the envelope for
   reflex, confirmation, direct-fallback, compatibility-route, and suppression
   outcomes; project only admitted envelopes into the Core.
5. **Implemented for configured authoritative lanes:** send admitted turns
   through Goal Association and canonical planning under one Core semantic
   authority, then return structured goal-scoped results through deterministic
   outcome reconciliation and a speech-only final response.
6. **Open module extraction:** separate Attention Review from ordinary Router
   intent/capability work, and extract the five logical modules without
   changing the implemented envelope contract.
7. **Open topology migration:** derive `RouteDecision` only for compatibility
   consumers and widen Core authority to remaining supported lanes only with
   rollback and retained evidence.
8. **Open evidence and deprecation:** retain live-text, stop/cancellation,
   dedicated E-stop/safe-idle, tool-result, simulator, rollback, and
   source-provenance evidence before deprecating Router APIs or operational
   names.

No migration step may broaden model authority, weaken confirmation, expose
low-level robot controls, or move embodied safety out of Soridormi.

## 9. Invariants

1. Every received input has a stable turn identity, including reflex-only and
   suppressed input.
2. Original input is immutable evidence; normalization never substitutes a
   nearby capability or meaning.
3. Protective stop, cancel, emergency, silence, and unusable-input behavior does
   not depend on an LLM.
4. A reflex takes effect without waiting for Core planning, while its outcome is
   returned to cognitive and goal state.
5. Attention suppression is non-effectful, bounded, evidence-based, and fails
   open on direct or unclear speech.
6. Context is bounded, source-attributed, freshness-aware, and never invented.
7. The Gateway emits no normal intent, goal, capability choice, plan,
   authorization, execution claim, or final response.
8. One admitted turn has one downstream semantic authority.
9. Agents and tools execute assigned goal-scoped work; they do not widen the
   user's goal or independently own the final answer.
10. Completion, failure, cancellation, and observation claims require trusted
    evidence and downstream outcome reconciliation.
11. Physical TaskGraph work remains sequential and validated; admission cannot
    relax execution safety or resource policy.
12. Compatibility names remain truthful until implementation, evidence, and
    migration are complete.

## 10. Acceptance cases

These are contract acceptance requirements. Automated and target-environment
evidence status is reported separately in [STATUS.md](STATUS.md).

| Case | Gateway expectation | Downstream/end-to-end expectation |
|---|---|---|
| Direct Chinese or English question | Admit original input without choosing route or capability | Core understands the goal, uses evidence when needed, and answers once |
| Mixed-language compound request | Preserve the complete utterance without narrowing it | Core segments independent goals and plans complete coverage |
| `Stop now.` / `停止` during speech | Record input and trigger deterministic cancellation before model work | No stale audio resumes; affected speech goal receives cancellation evidence |
| Emergency stop during simulated motion | Trigger trusted stop and retain `ReflexOutcome` | Provider evidence closes affected goals and proves safe idle |
| `Explain what “stop” means` | Do not trigger reflex; admit the contextual question | Core answers without treating it as an operational stop |
| Inactive ambient narration | Suppress only with policy-qualified evidence | No tool, memory, or physical effect is authorized |
| Direct weather question mislabelled ambient | Fail open because question form contradicts suppression | Core may use weather evidence and reconcile its result |
| Unusable or empty audio | Produce a deterministic unusable/suppressed record | No model, tool, action, or TTS work starts |
| Completed weather goal followed by unrelated action | Assemble only genuinely active goals | Core does not inherit stale weather meaning or authority |
| Tool success, partial failure, or timeout | Preserve turn and correlations | Goal-scoped outcomes return to Core for closure, replan, clarification, or truthful report |
| Compatibility client calls `POST /route` | Preserve current API during migration | Parity evidence exists before deprecation |

Acceptance asserts required and forbidden behavior. A Router unit test alone
cannot prove stop-to-provider cancellation, and a planner test alone cannot
prove result reconciliation or final spoken truth.

## 11. Terminology summary

| Term | Meaning |
|---|---|
| Cognitive Gateway / 认知网关 | Input, protection, attention, context, and admission boundary |
| `UserTurnEnvelope` | Evidence-preserving admitted/suppressed/reflex turn record |
| Protective Reflex / 保护性反射 | Immediate deterministic operational-control path |
| Goal-Driven Cognitive Core / 目标驱动认知核心 | Semantic goal understanding, planning, delegation, reconciliation, and response authority |
| Router / `chromie-router` | Current compatibility component and API name during migration |
| `RouteDecision` | Current compatibility routing contract, not the target cognitive object |
