# Cognitive Gateway / 认知网关

Status: authoritative architecture with the production implementation complete. Input
Normalization, Protective Reflex, Context Assembly, Attention Review, and Turn
Admission are explicit modules. The normal order completes admission before
ordinary Goal Interpretation; the admitted immutable `UserTurnEnvelope` and
digest-bound `GatewayContextSnapshot` form `CoreTurnRequest`; and the Core returns
`CoreInterpretationResult`. `RouteDecision` survives only as a digest-bound
internal compatibility projection for dependent planner contracts. Dedicated
Soridormi E-stop/safe-idle evidence and source-bound target qualification remain
open. Current implementation and evidence are owned by [STATUS.md](STATUS.md).

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
  -> trusted Trusted Capability Runtime / tools / memory / Soridormi
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
unresolved unclear review, malformed model output, or contradiction between
question form and an ambient label fails open to Core review. The classifier
must use an explicit ambient speech act with `addressed=false`; a directed or
unclear act paired with `addressed=false` receives one schema-constrained model
repair and still fails open if that repair remains inconsistent. Attention
Review cannot authorize an effect.

### 4.4 Context Assembly / 上下文组装

Context Assembly gathers only bounded evidence the Core needs to reason. Every
item identifies its source, freshness, and confidence when applicable. Missing
context remains unknown; it is never filled with invented facts. The production
projection does not copy aggregate Conversation State beside the same state's
leaf projections: top-level canonical leaves win, aggregate-only compatibility
input is mechanically flattened, and retained full task history plus duplicate
Mind/Memory aliases stay outside the Gateway snapshot. The 256 KiB snapshot
contract remains fail-closed for genuinely oversized canonical ingress evidence;
it is not enlarged or bypassed to accommodate duplicate state.

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
validators, the host Trusted Capability Runtime, tools, memory providers, and Soridormi.

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

Output invalidation, scoped Trusted Capability Runtime cancellation, and the dedicated
E-stop are dispatched in one safety-first phase. Device/audio teardown may wait
on a playback lock, but it cannot serialize runtime cancellation or E-stop
behind that wait. The receipt distinguishes provider cancellation failures,
host dispatch failures, and dedicated E-stop evidence; none of those fields is
itself a safe-idle claim.

For `global_emergency`, the host also cancels every unfinished interaction
workflow, including work still blocked in preflight. This fail-closed sweep is
independent of a successful Trusted Capability Runtime receipt, so a runtime dispatch
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
Trusted Capability Runtime. It is not an unconditional controller stop for motion started
outside that ledger. `global_emergency` is the scope that additionally
dispatches Soridormi's dedicated E-stop regardless of the host request ledger.

## 7. Implemented ownership and topology

The independent Router service, `/route` API, Router client, container, and
Router-owned model configuration have been removed. The maintained path is:

```text
transport input
  -> host Cognitive Gateway
  -> immutable UserTurnEnvelope
  -> Agent-owned Goal Interpretation and Goal-Driven Cognitive Core
  -> validated planning, execution, reconciliation, and response composition
```

The Gateway remains a narrow ingress boundary. Goal Interpretation may emit a
structured advisory decision for downstream contracts, but the Gateway itself
never authors an ordinary intent, goal, capability choice, plan, or response.
Historical `RouteDecision` names may remain inside versioned data contracts
until a separate contract-version update; they do not represent an active
Router component or service.

## 8. Implemented closure

The production topology and authority boundaries are complete:

1. the shared `ReflexOutcome` and `UserTurnEnvelope` contracts are authoritative;
2. Protective Reflex runs locally before model-dependent cognition;
3. only admitted envelopes enter the Goal-Driven Cognitive Core;
4. Goal Interpretation is Agent-owned and shares the Agent service lifecycle;
5. the Orchestrator has no Router client, URL, health dependency, or fallback authority;
6. deployment, diagnostics, Benchmark adapters, and current documentation no
   longer expose a first-class Router component;
7. historical evidence retains its original terminology and revision scope.

No future change may reintroduce a Router service, broaden model authority,
weaken confirmation, expose low-level robot controls, or move embodied safety
out of Soridormi.

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
12. Historical compatibility names are evidence-only and must not re-enter current topology or authority.
13. An ordinary admitted turn never implies cancellation of another turn;
    interruption requires an explicit protective scope or an unambiguous Core
    decision and retains auditable cancellation evidence.

## 10. Acceptance cases

These are contract acceptance requirements. Automated and target-environment
evidence status is reported separately in [STATUS.md](STATUS.md).

| Case | Gateway expectation | Downstream/end-to-end expectation |
|---|---|---|
| Direct Chinese or English question | Admit original input without choosing route or capability | Core understands the goal, uses evidence when needed, and answers once |
| Mixed-language compound request | Preserve the complete utterance without narrowing it | Core segments independent goals and plans complete coverage |
| Independent request while another turn is in flight | Admit and preserve both turn identities; do not synthesize a cancellation reflex | Both turns remain eligible for closure unless explicit control or the Core authorizes scoped interruption |
| `Stop now.` / `停止` during speech | Record input and trigger deterministic cancellation before model work | No stale audio resumes; affected speech goal receives cancellation evidence |
| Emergency stop during simulated motion | Trigger trusted stop and retain `ReflexOutcome` | Provider evidence closes affected goals and proves safe idle |
| `Explain what “stop” means` | Do not trigger reflex; admit the contextual question | Core answers without treating it as an operational stop |
| Inactive ambient narration | Suppress only with policy-qualified evidence | No tool, memory, or physical effect is authorized |
| Direct weather question mislabelled ambient | Fail open because question form contradicts suppression | Core may use weather evidence and reconcile its result |
| Unusable or empty audio | Produce a deterministic unusable/suppressed record | No model, tool, action, or TTS work starts |
| Completed weather goal followed by unrelated action | Assemble only genuinely active goals | Core does not inherit stale weather meaning or authority |
| Tool success, partial failure, or timeout | Preserve turn and correlations | Goal-scoped outcomes return to Core for closure, replan, clarification, or truthful report |

Acceptance asserts required and forbidden behavior. A Goal Interpretation unit
test alone cannot prove stop-to-provider cancellation, and a planner test alone
cannot prove result reconciliation or final spoken truth.
 The maintained live-service and MuJoCo evidence procedure is [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md).

## 11. Terminology summary

| Term | Meaning |
|---|---|
| Cognitive Gateway / 认知网关 | Input, protection, attention, context, and admission boundary |
| `UserTurnEnvelope` | Evidence-preserving admitted/suppressed/reflex turn record |
| Protective Reflex / 保护性反射 | Immediate deterministic operational-control path |
| Goal-Driven Cognitive Core / 目标驱动认知核心 | Semantic goal understanding, planning, delegation, reconciliation, and response authority |
| Goal Interpretation | Agent-owned Cognitive Core boundary; no independent routing service |
| `RouteDecision` | Historical/versioned advisory contract name used inside the Core path; not an active Router service |
