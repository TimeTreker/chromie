# Goal-Driven Cognitive Architecture

## Provider-neutral resource acquisition and delivery

Physical fetching and external-information retrieval share one semantic responsibility: acquire a requested resource and make it available to the recipient. `SemanticGoal.resource_responsibility` carries this provider-neutral meaning. Goal Association never names Soridormi, a website, or another provider; the Planner selects an exact registered capability from declared semantic scope, and the Trusted Capability Runtime invokes the owning peer Provider. See [Resource Acquisition and Delivery](RESOURCE_ACQUISITION_AND_DELIVERY.md).


Status: Maintained architecture constitution
Scope: Chromie cognition, planning, interaction, validation, and execution
Implementation state: the maintained goal-association, planning, validation,
pre-execution composition, trusted-execution, and post-execution closure path is
implemented. Exact immutable plan/request/result reconciliation, per-goal
`ExecutionOutcomeBundle`, and speech-only final outcome response are integrated
as defined by the [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md). The upstream
boundary migration is also implemented: five explicit Cognitive Gateway modules
complete admission before ordinary Goal Interpretation, the frozen version 1
`UserTurnEnvelope` is required at Core entry, and a Core-owned interpretation
result isolates the digest-bound compatibility route projection. Retained
source-bound live-text and MuJoCo evidence remains open.

The direct no-planner `spoken_response` branch and independently scheduled
validated response stages described below are accepted post-evidence contract
work, not implementation claims created by this documentation update. Current
behavior and evidence remain authoritative in [STATUS.md](STATUS.md).


## One Core and three execution lanes

The Goal-Driven Cognitive Core remains the single semantic authority while the
maintained runtime coordinates three concurrent lanes: Social-Attention
proposals, Speaking execution, and Activity execution. These lanes do not own
independent Goals or personalities. Response Composer may author explicit
best-effort lane coordination around parallel Canonical Plan steps; provider
metadata and the Trusted Capability Runtime remain authoritative for actual
overlap. Soridormi is a peer Capability Provider below Activity and owns its
subtle-expression, locomotion/whole-body, and physical safety arbitration. See
[Execution Lanes and Coordination](EXECUTION_LANES_AND_COORDINATION.md).

## 1. Purpose

Chromie has migrated its maintained semantic-planning path from a skill-routed
interaction system to a goal-driven cognitive runtime. This document defines
the Goal-Driven Cognitive Core and the principles and contracts that current and
future Gateway, Goal Interpreter-compatibility, Agent, memory, planning, social
interaction, and execution work must follow.

The central change is simple:

> Chromie plans to satisfy user goals. It does not merely match utterances to
> skills.

This document is intentionally more stable than any individual prompt, model,
service, or implementation. Models, prompts, and internal modules may change.
The cognitive invariants defined here should change only through explicit
architecture review.

The Cognitive Gateway is immediately upstream of this Core. It owns normalized
turn ingress, urgent deterministic protective reflexes, and bounded
attention/admission review. It must preserve the original turn and relevant
control evidence, but it does not own user-goal meaning, decomposition,
planning, semantic agent coordination, outcome synthesis, or response
composition. Those belong to the Goal-Driven Cognitive Core.

The fast Goal Interpreter is an Agent-owned compatibility stage inside the
Goal-Driven Cognitive Core. It receives only an admitted `UserTurnEnvelope`
projection and may emit a bounded advisory route, intent, source-effect envelope,
affordance set, or candidate proposal for dependent contracts. It does not own
Gateway normalization, protective reflex, attention, or admission; it is not an
independent service, a second semantic planner, or execution authority.

The executable state machine that carries one admitted turn through specialist
delegation, trusted observations, per-goal reconciliation, and a final response
is defined in [Cognitive Turn Loop](COGNITIVE_TURN_LOOP.md). This constitution
defines what cognition must preserve; the loop document defines when each
contract is produced and consumed.

## 2. Motivation

A skill-first system tends to fail in predictable ways:

- a compound request is narrowed to the first recognized skill;
- every new utterance is treated as a new task;
- parameters are filled or rejected without considering consequence;
- a planner partially emits actions before the complete goal is understood;
- social gestures become user tasks;
- semantic interpretation leaks into deterministic runtime code;
- deep planning loops back through fast routing and loses context;
- speech claims diverge from committed execution.

The live interaction history that motivated this RFC includes examples such as:

- “walk forward for fifteen seconds while blinking” becoming only walking;
- “make it iced” becoming a new task instead of modifying the coffee goal;
- “what parameter is missing?” losing the original information gap;
- a generic clarification being spoken while a partial action still executes;
- a backend model describing itself instead of speaking as Chromie;
- fixed gestures being added to every chat turn regardless of context.

These are not isolated prompt defects. They are signs that the architecture
needs a stable semantic object above routes and skills: the user goal.

## 3. Constitutional principles

### 3.1 Outcome and unfinished responsibility first

The primary semantic object is the user-visible outcome, not a route, intent,
capability, or skill. A persistent Goal represents an outcome Chromie still
owes, is waiting on, or must continue reasoning about; it is prospective memory
for unfinished responsibility, not a mandatory ticket that every immediate
interaction act must acquire before useful progress can begin.

Fast cognition may complete a fully understood, low-risk responsibility directly
through a validated `native_response` or another locally ready progress act while
Goal Association continues. Work that is not yet complete, needs dependencies,
requires deeper reasoning, or must survive the current instant is retained as or
associated with canonical Goal state.

An executable capability is one possible means of satisfying a responsibility.
An Agent Skill is a reusable method that may help an Agent decide how to use one
or more capabilities. The same outcome may be satisfied through different
capabilities, Agent Skills, composed or incremental plans, observation,
clarification, or an alternative intention depending on context.

### 3.2 Continuity before creation

Every user turn must first ask:

> Does this belong to something Chromie is already doing, discussing, waiting
> for, or recently completed?

Only after goal association should Chromie decide whether the turn creates one
or more new goals.

This prevents task explosion and preserves conversational continuity.

### 3.3 Coverage before matching

A planner must evaluate whether the complete user goal is covered. Finding one
matching skill is insufficient.

For a request containing walking and blinking, recognizing `walk_forward` does
not establish complete coverage. Partial coverage must escalate or clarify; it
must never silently become execution.

### 3.4 Meaning before skills

The model interprets the user’s meaning, relationships, constraints, and
priorities before choosing implementation capabilities.

Normal semantic understanding must not be implemented through phrase tables,
regex intent rules, hidden skill maps, or action-name keyword branches.

### 3.4.1 Agent, Agent Skill, Plan, and Capability

Chromie distinguishes four objects that external Agent frameworks often call
"skills" interchangeably:

- an **Agent** is an LLM-driven decision role with bounded responsibility and
  typed output;
- a **Agent Skill** is passive, reusable task knowledge with no Goal or
  execution authority;
- a **Plan** is the Agent's situation-specific proposal for current Goals;
- a **Capability** is an atomic executable contract invoked only through the
  trusted runtime/provider path.

Agents may select zero, one, or several Agent Skills before generating a
Plan. Candidate retrieval may narrow the Skill catalog, but ordinary Skill
selection remains model-authored and typed. Agent Skill content cannot
register capabilities, grant permissions, bypass confirmation, or execute
scripts. See [Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md).

### 3.5 One semantic authority, multiple cognitive timescales

Chromie has one semantic Mind, but useful cognition does not have to serialize
into one wall-clock pipeline. Fast understanding, Goal continuity, ready
progress, Social Attention, observation handling, and deeper reasoning may
advance at different timescales from the same authoritative interaction state.

```text
                     fast understanding
                        /         \
              ready progress    unfinished responsibility
                    |                    |
             speak/read/prepare         Goal
                    |                    |
                    +------ observations+----> slower cognition as needed
```

A later, broader cognition may revise, cancel, redirect, or supersede work that
has not crossed an irreversible commitment boundary. The more consequential or
irreversible the effect, the stronger the semantic, evidence, authorization,
and safety prerequisites before progress may advance.

Fast and Deep Planner remain useful planning roles, but they are not two stages
that every responsibility must traverse. Deep Planner never sends a goal back to
Fast Planner for another semantic decomposition pass. The tiers differ in
context breadth, latency budget, horizon, and planning depth—not in capability
ownership or semantic authority.

### 3.6 Planning when needed; authorization before effect

No model may directly execute, authorize, or commit a side effect. Effectful or
otherwise commitment-bearing work must cross the applicable canonical
planning/intention, deterministic validation, confirmation, authorization, and
provider-safety boundaries.

Planning is not a mandatory barrier for progress whose responsibility is already
complete in current Mind/context or whose trusted capability contract permits a
non-effectful read to advance before canonical Goal closure. Such early progress
never gains Goal-completion or effect authority merely because it started.

### 3.7 Evidence before claim

Chromie may claim completion, observation, tool results, memory writes, or
physical execution only when trusted runtime evidence supports the claim.

A model proposal is not evidence.

### 3.8 Validator authority

The validator is the authority for structural correctness, current capability
availability, schemas, provider state, resource conflicts, confirmations,
versions, authorization, and execution grants.

The validator does not decide what the user meant or what alternative best
preserves the user’s goal.

### 3.8.1 Single semantic authority

For an enabled route, one turn has one authoritative semantic planner. In
maintained `apply` mode that owner is the Goal-Driven Cognitive Core, currently
implemented by the unified Goal-driven Runtime. Exact Goal Interpreter actions may be
consumed only as compatibility-adapter input; they do not form a second semantic
plan, and a turn acquired by the Goal-driven Runtime cannot fall through to the
old CapabilityAgent planner after a failure.

The old CapabilityAgent semantic planner is retained only as an explicit
emergency path. It requires the host gate, the Agent gate, and an authoritative
emergency claim whose non-empty `turn_id` exactly matches the request turn.
Missing, empty, or cross-turn claims fail closed before model planning. The
claim is internal routing metadata, not caller authentication or a consumed
single-use nonce. Emergency compatibility does not widen execution authority:
its output still crosses the same host validation, confirmation, Trusted Capability Runtime,
provider, and evidence boundaries.

### 3.9 Semantic choice, deterministic enforcement

LLMs decide semantic relationships, parameter importance, goal satisfaction,
alternative plans, and natural language.

Deterministic code enforces contracts and safety. It must not replace semantic
reasoning with action-specific rules.

### 3.10 Interaction is independent from task execution

Speech, social attention, and user-task execution are separate plans that may be
coordinated but must not be conflated.

Every admitted turn still has one Core-owned semantic and conversational
authority. Speech composition and user-task execution may be prepared or
scheduled independently, including through bounded parallel model calls, only
from the applicable immutable authoritative state: the same turn, plus Goal
versions, a Canonical Plan, and evidence when each exists. A response composer
cannot reinterpret the Goal or authorize an effect, and an execution specialist
cannot become the conversation authority. Every emitted request remains
correlated to its owning turn and, when they exist, Goal and Plan identities;
physical TaskGraph execution remains sequential.

A blink selected to express attention is not automatically part of the user’s
goal. An explicit user request to blink is.

Likewise, response transport is not a user-task step. `Converse` is a native
cognitive ability to complete a conversational responsibility from current Mind
and context; `chromie.speak` is only the trusted Speaking transport/evidence
boundary. A complete Fast-Understanding `native_response` may begin through that
Speaking runtime before Goal Association completes, then be explicitly bound to
a canonical `spoken_response` Goal if persistent Goal state is needed.

Fast and Deep Planning may still identify a later conversational delta when
planning or new evidence makes one necessary, but Planner text never authorizes,
executes, or proves an effect. Response composition coordinates only the
still-needed user-facing delta and must not repeat a substantive act already
delivered or pending for the same responsibility.

### 3.11 Truth over guessing

Chromie may use bounded ordinary defaults when the model judges a missing value
to be low-consequence and the schema permits it. Material, risky, costly,
irreversible, or authorization-related parameters require user input or trusted
context.

When uncertain, Chromie asks naturally and specifically.

### 3.12 Graceful degradation

Optional cognition may fail without corrupting the primary task. Social
attention, response polish, and report-only review must not block or fabricate
execution.

## 4. Core cognitive objects

### 4.1 User turn

A bounded user contribution containing the original utterance, ASR confidence
and quality signals, conversation identity, current environment snapshot, and
turn metadata.

A user turn is evidence. It is not itself a goal.

### 4.2 Semantic goal

A versioned persistent representation of a desired outcome that remains
unfinished, deferred, waiting, or otherwise relevant beyond an immediately
completed progress act.

A goal should preserve natural meaning rather than forcing every request into a
fixed taxonomy. An admitted turn may produce no persistent Goal when a complete
low-risk conversational responsibility is immediately satisfied; the delivered
act and evidence still remain part of interaction history. Conversely, a
well-understood responsibility that cannot yet be completed should survive as
Goal state rather than force synchronous deep thinking before the interaction
can move on.

Suggested shape:

```json
{
  "goal_id": "goal_123",
  "version": 3,
  "description": "Walk forward for fifteen seconds while blinking naturally",
  "source_text": "往前走十五秒，然后边走边眨眼睛",
  "beneficiary": "user",
  "constraints": {
    "duration_s": 15,
    "relationship": "concurrent"
  },
  "success_criteria": [
    "forward movement completes",
    "blinking occurs during movement"
  ],
  "status": "active"
}
```

### 4.3 Goal set

The set of independent goals found in one user turn after association with
existing goals.

One utterance may create zero, one, or multiple new goals. A modification to an
existing goal does not automatically create a new goal.

### 4.4 Goal relationship

The semantic relationship between the current turn and existing goals.

Supported relationships should include:

- `continue`
- `modify`
- `clarification_answer`
- `confirm`
- `reject`
- `cancel`
- `pause`
- `resume`
- `query_status`
- `correct`
- `replace`
- `merge`
- `split`
- `reference`
- `new`

These relationships are model-proposed and deterministically validated against
known goal IDs and lifecycle state.

### 4.5 Information gap

A structured fact required to continue planning.

```json
{
  "gap_id": "goal_123:duration_s",
  "description": "walking duration in seconds",
  "importance": "material",
  "blocking": true,
  "preferred_resolution": "ask_user"
}
```

Information gaps remain attached to the original goal and survive turns.

### 4.6 Canonical plan

The only plan format accepted by validation and execution, regardless of
planner tier.

```json
{
  "plan_id": "plan_456",
  "goal_id": "goal_123",
  "goal_version": 3,
  "plan_version": 2,
  "planner_tier": "deep",
  "coverage": "complete",
  "relation": "exact",
  "steps": [
    {
      "step_id": "step_walk",
      "capability_id": "soridormi.walk_forward",
      "args": {"duration_s": 15, "speed": "quick"},
      "timing": "parallel"
    },
    {
      "step_id": "step_blink",
      "capability_id": "soridormi.blink_eyes",
      "args": {"count": 4},
      "timing": "parallel"
    }
  ],
  "information_gaps": [],
  "requires_confirmation": true
}
```

### 4.7 Social attention plan

An auxiliary interaction plan describing optional nonverbal attention.

It is not a user goal unless the user explicitly requested the behavior.

### 4.8 Execution evidence

Trusted records from Trusted Capability Runtime, tools, memory stores, and Soridormi that
prove what was attempted and what completed.

### 4.9 Experience record

A retained interaction outcome used for evaluation, scenario mining, and
owner-reviewed improvement. Experience never silently changes safety policy or
core principles.

### 4.10 General progress candidate

`CognitiveProgressCandidate` is an implemented Fast-Understanding proposal for
work that is already semantically concrete enough to be considered for progress.
It is deliberately more general than a tool/read request. Current forms include:

- `native_response`: a complete substantive conversational act that current
  Mind/context can already support; and
- `capability`: an exact capability plus material arguments that Fast
  Understanding has already resolved.

A candidate is meaning, not authorization. Trusted readiness policy decides what
may advance now. Goal Association later supplies explicit canonical Goal binding
when the responsibility persists or needs reconciliation. The Host does not infer
Goal ownership from route names, text similarity, or capability resemblance.

### 4.11 Continuous Mind candidate vocabulary — retained problem-space inventory

The following vocabulary is retained as the broad problem-space inventory that
led to the compressed baseline in Section 4.14. These are **candidate conceptual
roles, not a decision to add one DTO, manager, database, or model call per item**:

1. **Observation/Event** — something newly perceived or reported by the user,
   body, provider, environment, clock, or runtime.
2. **Belief State** — what Chromie currently takes to be true about world, self,
   user, and common ground, including source, freshness, uncertainty, conflict,
   and evidence provenance.
3. **Responsibility State** — concerns, Goals, obligations/promises, dependencies,
   timing, and lifecycle for outcomes that remain open.
4. **Intention / Progress / Commitment** — the current direction for advancing a
   responsibility, what has already progressed, how ready the next progress is,
   and how far an idea has crossed from thought into promise, authorized action,
   observed outcome, or user-facing claim.
5. **Attention / Working Set** — what currently deserves scarce cognitive and
   execution resources, including salience, urgency, interruption, suspension,
   resume, and compute contention.
6. **Memory / Experience** — short-lived working context, retained episodes,
   stable user preferences/relationships, semantic knowledge, and reviewed
   experience candidates, with explicit retention and forgetting boundaries.
7. **Reflection / Metacognition** — on-demand reconsideration of surprising,
   failed, contradictory, important, or repeated outcomes; self-correction,
   calibration, deciding whether more thinking is useful, and proposing reviewed
   learning without self-authorizing policy/personality changes.

Safety, consent/permission, semantic authority, evidence truth, privacy, and
provider authorization are cross-cutting trusted boundaries rather than another
free-running cognitive subsystem. Stable identity/personality/worldview/values
remain the cache-friendly Mind background; current law, weather, news, prices,
policies, and other changing facts remain dynamically acquired information.

### 4.12 Complete Continuous Mind problem space — retained design inventory

The following problem space is the **retained design inventory** used for the
architecture synthesis. It remains a pressure-test checklist so future work does
not solve one visible example with another special-case mechanism. Each item must
still be mapped to an existing contract where possible, and only concepts with a
genuinely independent state, lifecycle, or authority boundary may become new
first-class structures.

#### A. Reality, knowledge, and epistemics

Questions:

- How do continuous perception, partial ASR, provider results, body telemetry,
  time, and environmental changes become bounded `Observation` events?
- What does Chromie currently believe about the world, herself, a user, and
  shared/common ground?
- How are source, provenance, freshness, uncertainty type, contradiction, and
  confidence/calibration represented without reducing cognition to one numeric
  threshold?
- How are expectation, prediction error, causality, and counterfactual reasoning
  represented so Reflection does not confuse correlation with cause?
- How do Capability plus current Belief/Self State expose affordances without
  turning deterministic Host code into a semantic planner?

Direction:

- observations update bounded belief/context rather than entering prompts as raw
  authority; external text is data, never instruction;
- uncertainty that can be resolved by evidence should normally trigger
  observation, information acquisition, or clarification instead of more empty
  inference; and
- contradictory or stale beliefs remain explicitly unresolved until evidence or
  cognition resolves them.

#### B. Self, competence, and homeostasis

Questions:

- What is Chromie's current self state: speaking, moving, holding something,
  resource constrained, low battery, degraded sensor, or cognitively busy?
- How does she know the difference between possessing a Capability and being
  competent/reliable with it in the current conditions?
- Which self-preservation signals create a concern, a Goal, a deterministic
  safety action, or only an observation?

Direction:

- self state is current evidence, not personality;
- competence is evidence-qualified expectation, not a Capability ID synonym; and
- homeostatic concerns may create cognition but never bypass effect authority.

#### C. Responsibilities, concerns, obligations, and time

Questions:

- When does a transient understood act need no persistent Goal, and when must an
  unfinished responsibility be materialized?
- How are a concern, user-requested Goal, promise/obligation, preference/drive,
  and self-generated Goal distinguished so Goal state does not explode?
- How do waiting, deferred, superseded, cancelled, completed, stale, deadline,
  condition, and dependency semantics reactivate slow cognition?
- Can Chromie autonomously notice a concern or propose a Goal without thereby
  gaining permission to act externally?

Direction:

- Goal is prospective memory for unfinished responsibility;
- a concern is lighter than a Goal and may simply request attention;
- a promise is a stronger commitment than an internal intention; and
- time/condition changes are cognition events, not polling rules hidden in a
  planner.

#### D. Intention, planning, progress, revision, and commitment

Questions:

- What is the distinction between desired outcome (Goal), current chosen
  direction (Intention), concrete Plan, progress already made, and commitment
  depth?
- When is full planning useful versus taking only the next meaningful,
  evidence-producing commitment and replanning incrementally?
- How can later cognition revise, redirect, cancel, or supersede unfinished Fast
  progress while irreversible/effectful work requires stronger commitment gates?
- How are delegation and multi-provider/multi-agent coordination represented
  without transferring user-semantic responsibility?

Direction:

- `Progress` is the cross-cutting abstraction; current forms already include
  native conversation and exact capability work;
- commitment is a dimension, not another mandatory module: thought < intention <
  promise/plan < authorized request < started action < observed outcome <
  user-facing claim; and
- planning should be incremental when future steps depend on observations not yet
  available.

#### E. Attention, salience, metacognition, and compute

Questions:

- Which open Goals, concerns, observations, users, or environmental changes enter
  the current cognitive working set?
- How do novelty, urgency, risk, user attention, dependency readiness, deadlines,
  and importance influence focus without becoming a brittle integer-priority rule
  engine?
- How does slow cognition suspend and resume when a new high-salience turn
  arrives?
- When should Chromie stop thinking, think deeper, acquire evidence, or defer
  work?
- How should local GPU/model contention allow fast cognition to remain responsive
  while slower cognition is active?

Direction:

- salience filters continuous observations before expensive cognition;
- open responsibilities reactivate from meaningful events, dependencies, time,
  or bounded idle opportunity rather than only synchronous Fast-Planner
  escalation; and
- metacognition should reduce useless review/repair loops instead of adding a
  mandatory review LLM after every stage.

#### F. Conversation, users, common ground, consent, and social behavior

Questions:

- What does Chromie believe the user knows, wants, is attending to, and has
  already heard? What is shared/common ground versus private belief?
- How do multiple users, ownership, privacy, sensitivity, consent, age/role, and
  authority scopes affect memory, disclosure, confirmation, and actions?
- When should Chromie explain a refusal, changed intention, correction, or
  high-impact decision without exposing private chain-of-thought?
- How do Speaking and continuous Social Attention represent real interaction
  progress even when the substantive Goal remains open?

Direction:

- user models and common ground are epistemic state, not permission;
- permission/consent are explicit cross-cutting authority facts;
- `Converse` is native cognition, while `chromie.speak` remains transport/evidence;
  and
- Social Attention reacts to interaction-state changes but never becomes a second
  Goal or semantic planner.

#### G. Outcome reconciliation, reflection, memory, and learning

Questions:

- Which ordinary outcomes simply close a responsibility, and which unexpected,
  contradictory, important, or repeated outcomes justify Reflection?
- How does Chromie distinguish current self-correction from pattern-level
  reflection and longer-term experience consolidation?
- Which events become working memory, episodic memory, stable preferences,
  relationship knowledge, semantic knowledge, or reviewed experience—and what
  should decay or be forgotten?
- How can repeated success become habit/procedural competence or a provider
  capability without allowing the Mind to self-authorize new effectful skills?
- Who may promote experience into memory, prompt/Skill guidance, provider
  learning, policy, worldview, values, or identity?

Direction:

- reconciliation is normal; Reflection is selective slow cognition and never a
  mandatory user-facing latency barrier;
- Reflection may create correction, replan, calibration change, or an experience
  candidate, but durable promotion remains reviewed and owner/authority bound; and
- learning must respect Chromie/Soridormi ownership: conversational experience
  does not silently become motor policy, and provider-local physical learning does
  not become Chromie semantic authority.

#### H. Reliability, recovery, security, and continuity

Questions:

- Which Goals, promises, beliefs, memories, and identity state survive process or
  robot restart, and which volatile perception/body facts must be revalidated?
- How do provider failure, model timeout, interrupted cognition, partial action,
  crash recovery, and resumed work preserve truthful commitment state?
- How are source trust, prompt injection from acquired information, and provider
  degradation contained?
- Which stable Mind elements may change through owner revision, and which may be
  influenced only through reviewed learning rather than arbitrary conversation?

Direction:

- recovery restores durable responsibility/identity only with explicit freshness
  and reconciliation;
- observations may update beliefs but cannot rewrite Mind authority; and
- "learning" and "changing who Chromie is" remain separate promotion boundaries.

### 4.13 Compression rule used for synthesis and future additions

The list above is a problem space, not an implementation inventory. The rule
that produced the compressed baseline in Section 4.14 remains mandatory before
each new architectural slice:

1. map the phenomenon onto existing Goal, Progress, Interaction Ledger,
   ExecutionOutcome, Memory, Capability, and provider contracts;
2. identify the independent lifecycle/authority that existing structures cannot
   represent cleanly;
3. promote the smallest missing concept only when that boundary is real;
4. remove or consolidate an obsolete concept when the new model supersedes it;
   and
5. retain scenarios that distinguish the general ability from the initiating
   example.

The result of applying this rule is the small truth-owner model in Section
4.14—not one class, prompt, manager, or LLM role per cognitive term.

### 4.14 Continuous Mind synthesis — compressed architecture baseline

The architecture discussion over the complete problem space in Sections 4.11–4.13
has now produced a compressed baseline. This section records the current
architecture conclusion; it does **not** claim that every detail below is already
implemented. `STATUS.md` remains the authority for implementation and retained
evidence.

The result is intentionally smaller than the problem-space vocabulary. Terms such
as Belief, Concern, Intention, Commitment, Attention, Reflection, Homeostasis,
Common Ground, Experience, Learning, Recovery, and Autonomy remain useful for
reasoning about behavior, but they do not each earn a DTO, manager, database,
prompt role, or LLM call.

A concept becomes first-class only when removing it would collapse two states
that require different future behavior and that distinction cannot already be
owned by an existing contract. Semantic importance alone is not sufficient.
Likewise, a concept may be architecturally first-class without requiring a new
class or service.

#### 4.14.1 Small truth-owner model

The current target separates **Mind state** from the grounding/action substrate
that keeps the Mind honest.

Durable Mind state:

1. **Stable Mind** — owner-controlled identity, personality, worldview, values,
   interaction/expression style, and compact hard-boundary principles.
2. **Goal** — the canonical representation of an unfinished Responsibility that
   must retain semantic continuity.
3. **Memory** — selectively retained meaning that may matter again after it is no
   longer part of the current live context.

Live Mind state:

4. **Situation** — Chromie's bounded, revisable, currently relevant
   interpretation of reality. Situation is soft cognitive state: semantically
   first-class, runtime-live, mostly reconstructable, and not historical or
   external authority.

Existing grounding/action substrate:

5. **Evidence / Interaction Ledger** — what was actually observed, reported,
   delivered, requested, or otherwise authoritatively recorded by its source.
6. **Progress / CanonicalPlan / request / execution / outcome artifacts** — the
   existing contracts that represent what may advance, what course was selected,
   what effect was requested, and what actually happened. `Work` is useful
   architecture vocabulary for this family; it is not a new required contract.
7. **Capability/provider contracts and runtime state** — provider-owned truth
   about executable ability, schemas, current availability, and provider-side
   safety/control boundaries.

This is a truth-ownership model, not a seven-manager architecture. Before adding
anything new, implementation must attempt to express the behavior through these
owners and remove redundant state rather than mirror the same truth twice.

#### 4.14.2 Situation is soft, bounded, and mostly reconstructable

Situation answers one question that Evidence, Goal, Plan, and Memory do not:

> What does Chromie currently think is relevantly true, given the available
> grounding and current responsibilities?

Situation must not become a second database for facts already owned elsewhere.
Provider availability remains provider/runtime truth; execution results remain
`ExecutionOutcome` truth; Goal meaning remains Goal truth; durable learned meaning
remains Memory. Situation may contain the **current cognitive implication** of
those facts when that implication is needed for behavior.

Examples of Situation-like meaning include an unresolved or likely referent, a
current interpretation that a route is blocked for the active responsibility, a
judgment that an old observation is too stale for the present question, or the
current common-ground implication that the user probably has not received a
needed answer. Copying `goal.status`, `execution.success`, or a provider's
capability availability into a competing mutable Situation truth is prohibited.

Situation should be aggressively bounded to what current or near-future cognition
needs. Memory, history, the full capability catalog, and unrelated world facts are
retrieved or projected only when relevant. Role-specific prompt projections may
select different bounded views of the same live Situation; the architecture does
not require one giant global `SituationManager` or a complete world/Belief graph.

Losing Situation should cause re-interpretation cost, not semantic catastrophe.
After restart, Chromie should restore durable Mind state and required historical
artifacts, refresh provider/runtime truth and current observations, then
reconstruct Situation. Volatile body, scene, user-location, freshness, and
provider-availability assumptions must be revalidated rather than blindly
restored as current truth.

When a provisional interpretation becomes too important to lose, the question is
*why*. Promote only the meaning that needs continuity into the existing owner
whose semantics require it:

- an unfinished owed outcome -> Goal;
- a selected course or resumable cognitive/work product -> Plan/Progress or
  another existing continuation artifact;
- an authorized or dispatched effect -> trusted request/execution artifact;
- reusable future meaning -> Memory; and
- a delivered user-facing claim -> Speaking/Interaction evidence.

Otherwise the interpretation may remain in Situation and expire when irrelevant.
This "promotion escape hatch" keeps Situation soft rather than turning it into a
durable Belief database.

#### 4.14.3 Goal is unfinished Responsibility, not an execution ticket

`Responsibility` is architecture vocabulary; `Goal` is its canonical persistent
representation. Do not create a parallel Responsibility object whose truth must
be synchronized with Goal.

A Goal materializes only when Chromie owns an outcome that remains unfinished
after currently available progress and therefore needs stable semantic continuity
across future cognition, evidence, dependency, interruption, authorization, or
time. Understanding a request does not automatically create a Goal; acceptance
does not automatically create a Goal; and effectful work is not required to wait
for a Goal merely so the Goal can act as a work permit.

A complete native conversational responsibility may be understood, spoken
through the trusted Speaking path, and completed without durable Goal state. A
safe exact information read may begin while Goal Association continues; if an
owed outcome remains while the provider result is pending, that unfinished
responsibility is then represented/bound as Goal state. Effectful work still
requires the applicable planning, confirmation, authorization, resource, and
provider-safety boundaries regardless of how early its meaning is understood.

Goal identity follows **responsibility continuity**. The current meaning of the
same responsibility may be refined as referents, constraints, or intent become
clearer without creating a new Goal for every clarification. A genuinely new or
replacement responsibility receives a new Goal; the old Goal is cancelled or
superseded as appropriate. Current Goal meaning may therefore be canonical and
revisable at the same time: `canonical` means one current semantic owner, not
`immutable forever`.

Goal completion is also a reconciliation judgment, not an immutable historical
event. Later evidence may show that a previously closed Goal was never actually
satisfied and justify reopening/revising it. The underlying execution outcome or
past completion claim remains historical evidence and is never rewritten.

The canonical Goal lifecycle must therefore stay responsibility-level and small.
`planning`, `needs_context`, `waiting_for_user`, `awaiting_confirmation`,
`scheduled`, `running`, `recoverable`, provider `failed`, and request `timed_out`
are Work/runtime conditions, not Goal lifecycle states. They may explain why an
open Goal cannot progress, but they must not become competing answers to whether
the Responsibility is still owed. Likewise, a trusted `ExecutionOutcome` owns
what execution actually did; it may supply evidence to Goal reconciliation but
must not directly redefine the Responsibility as satisfied or abandoned.

#### 4.14.4 Decomposition belongs to Work unless responsibility becomes independent

Goals are a set of unfinished responsibilities, not a mandatory parent/child
workflow tree. `Task`, `SubGoal`, `Concern`, and intermediate planning steps do
not automatically become Mind-level responsibility objects.

Plan decomposition is normal and may change as provider granularity changes.
Today a provider may expose `walk`, `look`, `grasp`, and `fill`; tomorrow it may
expose one qualified `bring_water` capability. The Goal remains the same while
Work decomposition changes.

Promote a work item into another Goal only when an independently owned
responsibility has actually emerged. A useful semantic test is whether Chromie
would still owe that outcome if the originating Goal disappeared. Mere duration,
waiting, delegation, or planner decomposition is insufficient.

Likewise, most "dependencies" are conditions on current reality rather than
Goal-to-Goal edges. A package arrival, user clarification, time threshold,
provider result, permission, resource availability, or changed environment
should normally enter as Evidence/Situation and make progress newly possible.
Responsibilities usually depend on outcomes/world conditions, not another Goal
object's lifecycle. Do not introduce a generic Goal dependency graph until a
behaviorally necessary relation cannot be represented by Goal constraints,
Situation, evidence, and existing Work bindings.

Work and Evidence may advance more than one Goal. A read-only weather request may
both complete an information responsibility and advance an existing outdoor-plan
responsibility. Shared Work must therefore be bindable to the responsibilities it
actually advances; cancelling one Goal does not automatically cancel useful Work
still serving another open Goal.

#### 4.14.5 Commitment is expressed by artifact boundaries

Do not add a global `CommitmentState` or numeric commitment level. Commitment is
cross-cutting semantics expressed by the authoritative artifact that another
actor, future cognition, or external reality is now allowed or required to rely
on:

```text
Situation interpretation
    -> Goal responsibility commitment
    -> Plan/current-work commitment
    -> authorized/dispatched effect commitment
    -> observed execution/outcome history
    -> delivered communicative commitment
```

These are different kinds of commitment with different owners; collapsing them
into one mutable number loses information and creates another truth that must be
reconciled.

Meaning should remain provisional in Situation until continuity or external
reliance requires promotion. Once meaning has crossed into external action or
speech, correction happens forward through cancellation, compensation, new Work,
or corrective communication rather than by pretending the old commitment never
occurred.

#### 4.14.6 Truth and revision semantics

Core artifacts have different truth semantics:

- **Historical fact** — Evidence, trusted execution/outcome records, and delivered
  speech record what occurred. Later cognition may append new evidence or a
  correction but must not silently rewrite them.
- **Current canonical meaning** — Goal, current Plan/Work choice, and durable
  Memory each have one current semantic owner and may be revised with retained
  provenance when better evidence or intent requires it.
- **Soft interpretation** — Situation is cheap to revise, expire, or reconstruct.
- **Normative/external authority** — Stable Mind, provider contracts, explicit
  authorization/consent, privacy authority, and trusted safety boundaries can be
  consumed by ordinary cognition but cannot be rewritten merely because a model
  infers something different.

The general revision invariant is:

> **Revise the present; preserve the past.**

Equivalently, current meaning is revisable while committed history is monotonic.
When upstream meaning changes, downstream Work is not blindly invalidated by a
version mismatch. Re-evaluate whether existing Work remains semantically
compatible with the current Goal and Situation; retain compatible Work and
revise, supersede, cancel, or replan only the part that no longer advances the
current responsibility.

`Goal changed -> invalidate every plan` is therefore too coarse. A deadline
relaxation may leave all Work valid, while a small referent correction may make a
specific manipulation step invalid. Existing Goal/Plan/Progress/request/result
bindings should be reused before introducing a general semantic dependency or
invalidation graph.

Execution success and Goal satisfaction remain distinct. A provider may
successfully perform the wrong action; the execution record remains successful
while reconciliation leaves/reopens the responsibility as unfinished. Likewise,
a presentation/interpreter failure cannot rewrite trusted execution truth.

#### 4.14.7 Grounding must not be polluted by intention

Reality enters cognition through Evidence and authority-owned current state, not
through Chromie's own desired outcome or selected Plan. In particular:

```text
Goal != Evidence
Plan != Evidence
model inference != Evidence
Memory != fresh Evidence
```

A Goal that names `cup_17` does not prove that `cup_17` is the correct physical
referent. A Plan that chooses route A does not prove route A remains open. Memory
may provide priors and relevant history, but current high-commitment action may
require fresh grounding. Committed intent must not feed back as evidence and
create a self-confirming world model.

Source trust and authority are proposition/domain scoped rather than one global
numeric ranking. The user may be authoritative about an explicit current
preference; a provider is authoritative about its capability contract/runtime
state; trusted execution owns what request completed; perception supplies scene
evidence; Situation owns only Chromie's current interpretation. Avoid a universal
confidence score or giant conflict resolver unless concrete requirements prove it
necessary.

When uncertainty can be resolved cheaply by reality, prefer acquiring evidence
through perception, a provider/tool read, or clarification over spending longer
LLM inference guessing. Deeper commitment requires stronger evidence,
authorization, and provenance.

#### 4.14.8 Event-driven cognition without a Mind-level scheduler

Continuous Mind does not mean continuous LLM inference. Raw sensor frames and
runtime churn should be filtered near their source into meaningful observations.
Even a meaningful observation should wake cognition only when its state delta is
relevant to an open responsibility, current interaction, current Work,
authority/safety boundary, or another material concern.

`Attention`, `Salience`, `Readiness`, `Affordance`, and `Working Set` therefore do
not currently justify independent persistent Mind state:

- salience is a relation between what changed and what currently matters;
- readiness is a derived decision over current meaning, evidence, dependencies,
  risk, authority, and capability state;
- affordance is derived from provider capability plus current Situation and
  constraints;
- working set is a bounded projection of relevant Situation, Goals, Work, Memory,
  and interaction evidence; and
- compute preemption/scheduling belongs to runtime, while valuable resumable
  cognition belongs in existing Work/continuation artifacts.

A relevant state change may produce no cognition, a deterministic/local reaction,
fast cognition, slow cognition, or overlapping fast progress plus slower
reasoning. Fast and Slow cognition are different cognitive timescales/resources,
not mandatory sequential stages.

Open responsibilities wait passively until reality makes new progress possible.
Provider results, user clarification, timer events, scene/body changes, memory
retrieval, or other relevant Evidence may reactivate cognition. Do not implement
a background `while true: think()` loop or a giant numeric priority engine.

#### 4.14.9 Memory, learning, and recovery

Evidence history is not Memory. Evidence answers what happened; Memory is the
selective retention of meaning worth making available to future cognition.
Situation answers what matters now; Memory answers what may matter again later.
The default should be not to promote ordinary transient facts into durable
Memory.

`Experience` does not currently require a separate first-class store. Repeated or
important outcomes may produce an experience candidate; selective Reflection may
turn a supported reusable interpretation into Memory. Provider-internal
procedural learning remains provider-owned, and ordinary cognition cannot promote
experience directly into Stable Mind identity/values or invent a new provider
capability.

Learning is therefore a promotion process with explicit authority boundaries,
not a `LearningState`. Forgetting/decay is retention policy, not another cognitive
subsystem. Reflection is selective slow cognition that may propose revisions to
Situation, Goal, Plan/Work, or Memory; it cannot rewrite historical Evidence,
trusted outcome records, prior speech, provider authority, or Stable Mind.

Across restart, durable unfinished Goals, Memory, Stable Mind, and the minimum
trusted Work/Evidence required for continuity may survive according to their
owners' durability rules. Volatile Situation and provider/environment state are
revalidated/reconstructed. `Recovery` and `Identity Continuity` emerge from those
persistence/revalidation boundaries rather than requiring another Mind-state
object.

#### 4.14.10 Mutation authority

Cognitive roles are distinguished not only by model/prompt but by which semantic
owner they may establish or revise:

- Fast Understanding and perception/result interpretation may propose/update
  revisable Situation meaning but do not rewrite Evidence;
- Goal Association owns canonical responsibility continuity and Goal refinement,
  replacement, cancellation, reopening, and binding decisions;
- Planner roles own chosen Work/Plan semantics but do not casually rewrite Goal
  meaning or execution history;
- trusted validation/runtime owns authorization, request correlation, execution,
  and outcome records but does not reinterpret user meaning;
- Reflection may challenge current Situation/Goal/Plan/Memory within those
  owners' rules but cannot become a second authority for Evidence, provider
  contracts, effects, or Stable Mind; and
- external text enters as data/Evidence and cannot acquire authority over Stable
  Mind, safety, privacy, or capability contracts through prompt content.

Implementation should encode these ownership boundaries using existing contracts
where possible rather than creating a universal `AuthorityManager`.

#### 4.14.11 Continuous Mind constitution

The synthesis above reduces to a small set of invariants:

1. **Reality enters through Evidence, not through intention.**
2. **Situation is revisable interpretation, not historical authority.**
3. **Persist an unfinished owned responsibility as Goal only when continuity is
   needed.**
4. **Progress whenever meaning, dependencies, readiness, authorization, and
   safety are sufficient; Goal or Planner is not a universal barrier.**
5. **Planning is Work formation when direct progress is insufficient, not a
   mandatory stage.**
6. **Promote meaning only when another canonical artifact needs continuity,
   authority, or durable reuse.**
7. **Current canonical meaning may be revised with provenance; committed history
   is never silently rewritten.**
8. **After upstream meaning changes, revalidate downstream semantic compatibility
   and preserve compatible Work.**
9. **Once an error has crossed into external action or speech, repair forward.**
10. **Memory provides reusable past meaning; it does not replace fresh grounding.**
11. **Stable Mind and external/trusted authority boundaries cannot be rewritten by
    ordinary cognition.**
12. **When reality can cheaply resolve material uncertainty, acquire evidence
    instead of thinking harder.**

The architectural shape is therefore not a new `ContinuousMind` manager. It is
the continuous evidence-driven evolution of a few truth owners:

```text
                    Stable Mind
                         |
                         | constrains
                         v
Evidence ----------> Situation <---------- Memory
   ^                     |
   |                     | understand / revise
   |                     v
   |              ready Progress OR Goal
   |                     |
   |               Work / Plan if needed
   |                     |
   |              trusted externalization
   |                     v
   +------------------ Reality
```

Capability/provider truth constrains which Work is actually possible. New
Evidence continuously revises Situation and may make open responsibilities ready,
invalidates assumptions, close/reopen Goals, or make selective deeper cognition
worthwhile.

This synthesis is now the architecture baseline for the next implementation
slices. The minimum Situation projection is now implemented as bounded live
reference state. Remaining detail questions—exact Goal revision provenance,
resumable cognitive artifacts, durable scoped
consent/privacy, and multi-user identity—must be solved against these invariants
without reopening the whole ontology or pre-creating one manager per concept.

## 5. Continuous cognitive loop

The maintained architecture is a state-driven loop with multiple cognitive
timescales, not a mandatory module pipeline:

```text
Admitted Observation / User Turn
  ↓
Fast Understanding
  ├─ complete native conversational progress ───────────────→ Speaking
  ├─ exact capability progress candidate ──────────────────→ readiness gate
  │                                                           ├─ ready safe progress → trusted runtime
  │                                                           └─ not ready → Goal/planning path
  └─ unfinished / uncertain responsibility ────────────────→ Goal cognition

In parallel from the same interaction state:
  Goal Association / continuity / relationship reasoning
  Social Attention proposal lane
  existing ready work and observations

Goal/slow cognition as needed:
  Goal state → intention/planning → deterministic validation/authorization
             → trusted execution → observation/evidence

Every new observation:
  → reconcile current responsibility/progress
  → close, correct, replan, clarify, reactivate, or continue
  → optionally trigger bounded Reflection when surprise/importance warrants it
```

The loop preserves one semantic authority even when work overlaps in time. A
Fast candidate does not authorize itself; a started read or spoken response does
not complete a Goal until the applicable canonical binding/evidence proves what
responsibility it satisfied; an effectful Intention still crosses trusted
planning and authorization.

Goal Association is therefore a continuity and responsibility-relation boundary,
not a global start barrier. Planner is an intention-forming mechanism used when
the responsibility is not already complete or cannot safely advance from current
understanding. Response Composer is a still-needed-delta coordinator, not the
only place conversation or Social Attention may originate. Provider observations
are cognition events, not merely terminal inputs to a speech formatter.

The implemented General Progress substrate covers immediate native conversation,
exact capability candidates, explicit Goal binding, trusted early safe-read
readiness, and peer Social Attention. Sections 4.11–4.13 retain the broader
problem-space inventory and the compression discipline that produced Section
4.14. They are no longer an instruction to pre-create the candidate concepts as
persistent state; future implementation starts from the compressed baseline and
adds a new owner only when a concrete lifecycle or authority gap proves it
necessary.

### 5.1 Model-facing Goal Association boundary

Goal Association must not expose Chromie's persistence and lifecycle objects
directly to the language model. Its model-facing output is intentionally small
and explicitly discriminated:

- `associate` for relationships to exact active goal IDs;
- `create_goals` for one natural-language description per independent new goal;
- `clarify` for one concise user-facing question.

The declared decision selects the active branch. Harmless content emitted in an
inactive branch is ignored structurally; it does not trigger semantic repair.
`clarification` never carries reasoning, translations, route labels, model
failures, or validator diagnostics. Goal Association also does not receive prior
routing or validation failures as semantic evidence; the admitted user turn,
bounded Goal/dialogue state, and trusted evidence remain authoritative.

The host owns all transport and persistence mechanics, including turn IDs,
association IDs, goal IDs, versions, source text, default object/constraint
containers, metadata, and construction of the canonical
`GoalAssociationResolution`. Ignoring model-authored transport noise such as an
extra `id` is not semantic interpretation; semantic descriptions and
relationships still come only from the model and remain subject to schema and
host validation.

Typed entity provenance is part of that validation. When the model declares a
new directly named location binding without a supplied referent, its value must
remain a contiguous verbatim span of the authoritative current user turn in the
user's language. A translated, transliterated, or otherwise ungrounded value is
rejected and may receive the same single schema-constrained model repair as
other invalid Goal Association output. Indirect references instead retain the
canonical value and referent ID selected by Goal Association from the supplied
bounded discourse state. The Host checks provenance shape; it does not extract a
place name, choose a referent, or decide the user's meaning.

Fast Goal Interpreter route and retrieval results are advisory projections.
Query-matched capabilities may lead the semantic-review catalog, but they do
not erase the supplied common or full catalog. Semantic repair receives a
candidate-first, de-duplicated union so an incorrect first route cannot remove
the exact affordance needed to correct itself. The Host may order and validate
that supplied evidence; it may not infer the route from the user's wording.

Structured semantic review has one logical model contract even when an Ollama
model template does not honor JSON Schema on `/api/chat`. After a structurally
invalid chat completion, the Goal Interpreter may retry that exact model,
schema, prompt content, decoder options, and output budget once through
`/api/generate`. This is transport compatibility containment, not semantic
escalation or a model-name exception. The result crosses the same catalog and
route validators. If either transport remains malformed or ungrounded, review
fails closed to typed clarification rather than preserving the suspect route.

### 5.2 Stable-to-volatile model prompt ordering

Issue [#17](https://github.com/TimeTreker/chromie/issues/17) owns the architecture
and documentation contract; dependent Issue
[#18](https://github.com/TimeTreker/chromie/issues/18) owns the runtime boundary
and evidence. Prompt layering is an inference-efficiency contract inside the
Cognitive Core; it does not create another semantic authority or cache a model
decision.

Every Agent request through the maintained Ollama boundary must be designed in
this order:

| Layer | Content owner | Mutability and invalidation |
|---|---|---|
| 0. Constitutional foundation | Cognitive constitution | Stable Chromie identity, proposal/evidence rules, and authority invariants only; any contract revision invalidates the prefix. |
| 1. Exact identity/world projection | Identity and world-context owners | Owner-approved identity, personality, relationship, and genuine world assumptions only while their exact rendered version is unchanged. Age, relationship, locale, policy, or world updates invalidate the projection. |
| 2. Agent operating contract | Exact prompt family | Goal Association, Fast Planner, Deep Planner, Response Composer, safety, truthfulness, commitment, and output responsibilities. A role or schema-contract change invalidates the prefix. |
| 3. Exact capability contract | Capability/Agent Skill/schema owners | Bounded catalog, schema, and Agent Skill projections only while exact availability, content, ordering, and version remain unchanged. Any difference invalidates the projection. |
| 4. Session context | Core context assembly | Conversation, active and retained Goals, the Goal-scoped Interaction Context projection, discourse state, memory indexes, scene observations, runtime state, and evidence. Always volatile. |
| 5. Current turn | Admitted turn and current attempt | Authoritative user input, current time, temporary observations, validation feedback, and attempt-local repair state. Always last and volatile. |

Layers 0 through 3 are a stable-prefix candidate only when the same model and
prompt family receive an identical final rendering. “Stable” is a property of
exact content, not of a field name. Capability availability, owner-approved
identity/personality data, relationship facts, locale, and world assumptions
may change and must change the stable-prefix digest when they do.

Layer 0 may say that Chromie is the single user-facing identity, that model
output is a proposal until validated, and that effects require trusted
evidence. It must not contain a scene description, current time, owner
observation, relationship state, active Goal, capability availability, or
execution result. Layers 4 and 5 never move ahead of a supposedly stable block.
The current action intent belongs to the authoritative Goal/turn suffix; making
it explicit can improve inspectability, but prefix ordering does not itself fix
an incorrect Goal Association decision.

Ollama owns the provider KV/prompt cache. Chromie supplies an identical leading
request sequence to make reuse possible; it does not invent a cache-key API,
retain KV tensors, or infer a cache hit from matching source characters.
Different models cannot share that state, and unloading a runner can discard
it. Prompt layering therefore cannot remove a Qwen-to-Gemma model reload and
must be evaluated separately from model residency.

The final assembled request is still subject to the complete existing context
budget, schema decoder, repair, validation, confirmation, and fail-closed
contracts. Each layer is counted exactly once. A local version or SHA-256 digest
is invalidation and observability evidence only, not an Ollama cache key. Stable
placement never upgrades prompt text into policy or execution authority.

The Agent implements this contract with `LayeredPrompt`. The existing Ollama
`system` text is layer 0; exact identity/personality projections, fixed role
contracts, and exact Skill/catalog fragments are promoted ahead of one volatile
suffix. `OllamaClient` is the only final renderer. JSON Schema and generation
options remain out-of-band Ollama request fields: their digest participates in
the stable request-contract comparison, but their bytes are not falsely counted
as a model prompt prefix.

## 6. Goal continuity

### 6.1 Association precedes segmentation

The system must not begin by asking how many goals the current sentence
contains. It must first determine whether the sentence continues existing work.

Example:

```text
User: 给我拿杯咖啡。
Later: 冰的。
```

The second turn modifies the existing coffee goal. It does not create a new
“iced” goal.

Example:

```text
User: 给我拿杯咖啡。
Later: 顺便查一下天气。
```

The second turn creates a new weather goal while leaving the coffee goal
active.

When a user materially corrects an entity on an external-read Goal, Goal
Association creates a fully bound replacement Goal while retaining the old Goal
as history. If the corrected answer still depends on external facts, planning
must perform a new exact read. It may not relabel evidence produced for the old
entity as evidence for the replacement Goal. A direct response without a new
Capability is valid only when delivered evidence-bound dialogue names the same
Goal being answered.

### 6.2 Bounded candidate context

Goal association should consider a bounded projection of:

- recent Gateway-admitted dialogue turns, even when an earlier turn has not yet
  finished Goal Association;
- active goals;
- goals waiting for user input;
- goals awaiting confirmation;
- recently completed or cancelled goals when reference is plausible.

It also receives the bounded task/progress projection for those Goals. Dialogue
history answers *what was just said*; Goal snapshots answer *what semantic work
has already been validated*; task/progress snapshots answer *what is currently
planning, waiting, committed, running, recoverable, or terminal*. These are
different evidence classes and must not be collapsed into one recency heuristic.

It must not load unlimited history.

Candidate retrieval may narrow the context, but retrieval scores, recency,
entity overlap, and keyword matches are advisory only. They cannot decide the
relationship.

### 6.2.1 Accepted dialogue versus canonical Goal state

Conversation continuity has two publication boundaries.

1. After Cognitive Gateway admission, the exact normalized user turn is appended
   immediately to bounded conversation history as **accepted dialogue evidence**.
   This record carries no Goal ID, semantic binding, Task commitment, or execution
   authority.
2. After Goal Association validates, its model-owned Goal/association result is
   committed to canonical Goal/Task/discourse state. That semantic state may then
   guide later turns and planning.

Goal Interpretation therefore sees recent accepted dialogue plus whatever
canonical Goal/Task state already exists. Goal Association uses the same dialogue
evidence but is the only stage that decides how the current turn relates to the
bounded Goal set. Within one conversation, Goal Association is serialized at this
semantic-state boundary: a later association refreshes continuity after any association
already occupying that boundary commits, then reasons over the newest validated Goal
and Task state. Fast acknowledgement and Gateway admission remain outside that
serialization, so conversational responsiveness does not require semantic races.

The Host never manufactures a provisional Goal from the early dialogue record.
If a prior association is unavailable or fails, the later model may still reason
from accepted dialogue, but it must not pretend that an uncommitted Goal exists.

A failed or superseded-before-commit turn is annotated as such on its accepted dialogue
record. This is causal/transport evidence for later semantic reasoning, not a Host judgment about
what the failed turn meant. Consequently, a newer failed turn can remain the current conversational
subject even while an older Goal is the newest canonical Goal.

### 6.3 Ambiguity handling

When more than one active goal plausibly matches, Chromie asks a natural
question.

Bad:

> Select task ID goal_123 or goal_456.

Good:

> 你是说咖啡不用了，还是天气也不用查了？

The clarification wording is model-generated from goal summaries. Runtime code
only validates that referenced goal IDs exist.

### 6.4 Goal versioning

Every material goal modification increments the goal version.

A new goal version may invalidate:

- the previous plan;
- request-bound confirmation;
- queued work;
- an execution grant;
- stale response commitments;
- information gaps no longer relevant.

Old versions remain auditable and become superseded.

### 6.5 Goal continuity versus task lifecycle

Goal continuity is cognitive. Task lifecycle is operational.

- Goal continuity decides what the user is referring to.
- Runtime tasks record planning, waiting, confirmation, execution, completion,
  failure, or cancellation.

The two must be linked but not conflated.

The link is explicit and scoped. A model-facing semantic `goal_id` is not the
same identifier as the host `task_id`; the host resolves the semantic goal to
its owning task context and binds each canonical speech or skill request by
`source_goal_ids`. Provider completion, refusal, failure, timeout, or
cancellation updates every bound goal independently. A conversational
`respond` goal likewise remains active until its scoped speech request has
runtime delivery evidence; producing Response Composer text is not completion.
This prevents a completed compound action from remaining in the active-goal
projection and being accidentally associated with a later turn.

Goal Association also receives a separate bounded projection of recently
terminal Goals. A semantic `continue` or `reference` relationship may point to
one of them, but the Host records only a continuity marker and preserves the
terminal state. This permits questions about a just-completed result without
reopening work or treating recency as semantic authority.

### 6.6 Active goals protect conversational continuity

A goal remains conversationally active while it is planning, waiting for user
input, awaiting confirmation, executing, paused, or recoverably blocked. It does
not become disposable merely because no provider request is currently running.

Soft-topic and idle-boundary heuristics must not clear active goals. A short
answer after a long pause may still resolve an existing information gap.
Candidate history remains bounded, but goal lifecycle is the authority for
whether continuity is still possible.

For a completed external-read Goal, a conversational follow-up may use only the
Host-marked evidence-bound dialogue that was already delivered for that Goal.
A verified-result index without that dialogue is provenance, not factual answer
evidence, and requires explicit retrieval, a fresh read, or escalation.

### 6.7 Conversation reset is a semantic control

Natural-language whole-conversation reset is a semantic decision and must reach
the Cognitive Core. The Host may apply a validated typed reset decision, but it
must not infer reset from a whole-utterance phrase table. Ambiguous cancellation
or reset language reaches Goal Association so the model can determine whether
one goal, several goals, a proposal, or the conversation is being changed.

## 7. Multi-goal segmentation

### 7.1 Independent responsibility test

A turn contains multiple goals when it creates independent user outcomes that
may be planned, completed, cancelled, or reported separately.

Example:

> 记住我只喝美式，然后帮我拿杯咖啡，再查一下天气。

Possible goals:

1. remember a coffee preference;
2. obtain coffee;
3. retrieve weather.

### 7.2 Plan steps are not goals

Example:

> 先看看有没有咖啡，没有就做一杯。

This is one goal with a conditional plan, not two user goals.

### 7.3 Segmentation output

```json
{
  "associations": [],
  "new_goals": [
    {
      "description": "remember that the user drinks only Americano",
      "independent": true
    },
    {
      "description": "obtain a coffee for the user",
      "independent": true
    },
    {
      "description": "report the current weather",
      "independent": true
    }
  ]
}
```

### 7.4 Response composition

Multiple goals do not require multiple awkward acknowledgements. A response
composer may naturally consolidate them while preserving independent lifecycle
and evidence.

Semantic composition belongs to a model. The Orchestrator validates references,
commitments, versions, and evidence; it does not concatenate strings to imitate
understanding.

### 7.5 Independent goals may end the same turn differently

A multi-goal turn does not require one global terminal outcome. One independent
goal may be executable while another needs clarification, is unavailable, is
refused, or can be answered immediately. The canonical plan therefore records a
per-goal outcome and associates every executable step and information gap with
the goals it serves.

Example:

```text
User: 点一下头，再往前走。
Goal A: nod once          -> execute
Goal B: walk forward      -> clarify duration
```

The valid result may execute Goal A while keeping Goal B in
`waiting_for_user`. It must not execute an incomplete step for Goal B, and Goal
B must not prevent a fully independent, safe Goal A from completing.

A `mixed` canonical-plan disposition means complete accounting of all goals,
not complete satisfaction of every goal. Each goal retains its own disposition,
coverage, satisfaction, response, information gaps, and execution evidence.

## 8. Hierarchical planning

### 8.1 Fast Planner

The Fast Planner is a low-latency semantic planner over:

- the complete current goal;
- bounded summaries or projections of model-selected Agent Skills;
- a compact self model;
- bounded active-goal context;
- common capabilities;
- essential provider and safety state.

It may:

- plan a bounded conversational Goal that actually requires planning; a
  complete non-effectful `spoken_response` Goal uses the direct response path;
- produce a complete direct common-skill plan;
- propose a low-consequence bounded default;
- produce a social attention plan;
- escalate.

It must report coverage:

```text
complete | partial | uncertain
```

Only complete, high-confidence, structurally valid coverage may proceed to
validation.

The planner model emits a flat semantic DTO, not the canonical transport
envelope. Plan identity, schema version, planner tier, and authoritative
top-level Goal IDs are host-owned. Model-authored steps must name the exact
Goal IDs they serve through `source_goal_ids`.

For an explicit numeric parameter, the planner also authors the step ID,
argument key, resolved value, strategy, and `source_goal_ids`. Deterministic
validation checks that the value equals the claimed step argument and that
every explicit numeric value in an executable Goal is accounted for by a
resolution owned by that Goal. Provenance does not require the model to copy a
second free-text excerpt: the immutable Goal ID is the stable reference. The
Host neither infers the argument mapping nor substitutes a default.

For a Fast Planner request containing multiple authoritative goals, the model
emits one required decision record per Goal ID rather than a CanonicalPlan-shaped
step/outcome graph. Each decision selects exactly one common-catalog skill, a
direct conversational response, or semantic escalation. The host generates
step IDs and compiles ownership mechanically from the keyed decisions before
shared CanonicalPlan validation. Simple common-catalog `execute + respond`
combinations may terminate as `mixed`; goals requiring more than one skill,
clarification, unavailable or refused judgment, material alternatives, rare
capabilities, or broader context escalate. Contract failure is not semantic
escalation. The implemented contract and qualification matrix are defined in
[Agent Skills Architecture](AGENT_SKILLS_ARCHITECTURE.md).

### 8.2 Deep Planner

The Deep Planner receives:

- the original user turn;
- bounded projections of model-selected Agent Skills and their provenance;
- complete associated goal state;
- any advisory fast-planner draft;
- the full capability registry;
- schemas and affordances;
- provider, environment, resource, and safety context;
- memory and trusted services;
- current information gaps and confirmations.

Deep Planner is exceptional. It is invoked when semantic uncertainty,
incomplete or compound coverage, nontrivial dependencies, material
alternatives, novelty or broader context, or safety/resource reasoning requires
the wider planning boundary. A structured semantic or plan validation rejection
may justify Deep only when its failure contract explicitly requires broader
reasoning. Technical schema/model-contract failure receives bounded same-tier
repair. Any later Deep recovery is explicitly classified as recovery, retains
the Fast failure evidence, and fails closed unless it produces a valid plan; it
is not semantic escalation. Model confidence alone neither grants a direct/Fast
bypass nor forces escalation, and it never replaces deterministic effect and
safety validation.

It may produce:

- exact plan;
- safe adjustment;
- alternative plan;
- partial plan requiring approval;
- context acquisition;
- specific clarification;
- unavailable;
- refused.

Deep Planner and single-goal Fast Planner use the shared flat
`PlannerModelOutput` boundary. Multi-goal Fast Planner uses the decoder-tight
`FastPlannerMultiGoalPlanOutput` boundary. In every case, the planner model owns
all semantic plan fields: capability choice, arguments, ordering, the
`steps[].source_goal_ids` ownership judgment, per-goal disposition and response
content, coverage, and satisfaction judgments.

For complete multi-goal planning, per-goal outcomes form an exact object keyed
by every authoritative Goal Association ID. The key is the identity; an outcome
value cannot repeat or replace it. `goal_outcomes.*.step_ids` and the top-level
aggregate disposition are redundant transport projections of the model-authored
step ownership and per-goal dispositions. The Host may mechanically normalize
those cross-references so nonexistent or stale IDs cannot discard an otherwise
coherent plan. It cannot create a step, choose a capability, or assign an
unowned Goal: an `execute` outcome with no model-authored owned step remains
invalid and returns to model repair. After validation, the Host adds the
canonical identity envelope and converts the goal-keyed object to the ordered
canonical outcome list; it does not infer semantic plan content from the user
utterance.

A typed effectful Goal cannot be declared satisfied merely because a planner
returns complete coverage or response text. Before canonical planning, each
`executable_action`, `capability_dependent`, or otherwise provider-required Goal
must own an executable step, have delivered evidence-bound dialogue for that
same Goal, or carry an explicit `clarify`, `escalate`, `unavailable`, or
`refused` outcome. An unresolved effectful Goal with zero owned steps and no
such evidence is a contract failure: Fast receives its bounded same-tier repair
and then escalates; Deep receives its bounded replan and then clarifies. The
Host validates typed Goal metadata and ownership only; it does not infer effect
from phrases.

`plan_relation` and `user_confirmation_required` are typed semantic decisions
at the model boundary. A safe adjustment or alternative must be executable and
must require confirmation. They are validated before being transferred to the
host-owned canonical envelope.

### 8.3 No planner loop

The Deep Planner does not send simple steps back to the Fast Planner.

Executable capabilities are leaf nodes in either planner's canonical plan and
use canonical `capability_id`. Agent Skills are reusable planning methods and do
not belong to a planner tier. Legacy `skill_id` remains a bounded compatibility
input until retained artifacts and callers migrate; conflicting dual fields fail
closed.

### 8.4 Shared planner primitives

Both planners may use shared deterministic or retrieval primitives:

- project active goals;
- retrieve capability candidates;
- inspect schemas;
- fetch provider state;
- obtain environment observations;
- validate a canonical plan;
- compare goal and plan versions.

Shared primitives must not introduce a second semantic authority.

### 8.5 Bounded replan loop

A limited loop between a planner and the validator is allowed when validation
returns a structured rejection.

Example:

```text
plan v1: walk and blink concurrently
validator: concurrency not supported
plan v2: walk, then blink
result: material alternative requiring confirmation
```

Requirements:

- maximum replan count;
- explicit rejection reason;
- monotonically increasing plan version;
- no identical retry;
- same goal version unless the goal itself changes;
- clarification or unavailable result when the budget is exhausted.

## 9. Goal satisfaction and coverage

The planner’s objective is not “find a skill.” It is:

> Find a verifiable plan that maximizes satisfaction of the user’s goal within
> current safety, capability, authorization, and environment constraints.

Suggested output:

```json
{
  "coverage": "complete",
  "satisfaction": {
    "requested_outcomes": 2,
    "covered_outcomes": 2,
    "material_changes": [],
    "unresolved_constraints": []
  }
}
```

A numeric score may be useful diagnostically but must not replace semantic
explanation of what is covered, changed, or unresolved.

Planner satisfaction is prospective plan adequacy: it evaluates what the
proposed response and steps would satisfy if they complete successfully. It is
not execution progress. A fully covering plan may therefore be `exact` before
execution, while pending execution by itself is not an unmet planning
requirement. Completion speech and terminal Goal state still require trusted
runtime evidence.

Partial satisfaction is not authorization to execute a degraded plan.

Responsibility type also constrains the outcome. A `spoken_response` Goal is
satisfied by authored conversational output and cannot own a generic response-transport
executable step. A
`capability_dependent` Goal cannot use `respond` as a shortcut around execution
unless delivered evidence-bound dialogue names that exact Goal. This validation
uses typed Goal and evidence provenance; it does not classify user wording.

For a mixed multi-goal plan, satisfaction thresholds apply to each executable
or directly answered goal. An unavailable, refused, or waiting goal may lower
the aggregate diagnostic score without invalidating a fully satisfied,
independent executable goal. Aggregate satisfaction remains useful for audit,
but it must not silently turn all-or-nothing behavior back on.

## 10. Parameter resolution

### 10.1 Semantic ownership

The planner decides whether a missing parameter can be supplied by:

- explicit user language;
- schema default;
- owner-approved preference;
- low-consequence ordinary default;
- current observation;
- trusted service;
- user clarification;
- or no valid source.

### 10.2 Consequence-aware choice

Low-consequence, reversible, bounded parameters may receive a model-selected
ordinary value when allowed by schema and policy.

Material examples that normally require stronger evidence include:

- duration or destination for movement;
- safety-sensitive speed;
- external cost;
- authorization;
- irreversible changes;
- privacy-sensitive disclosure;
- physical interaction with a person.

This is not a fixed field-name table. The model reasons from field description,
effects, bounds, provider constraints, and current context.

### 10.3 Specific clarification

Chromie should ask for the actual missing fact.

Bad:

> I need more parameters.

Good:

> 你希望我往前走多久？

When useful, the model may offer bounded choices naturally.

### 10.4 Persistence

A blocking information gap keeps the original goal active in
`waiting_for_user`. A later answer updates that goal and triggers replanning.

## 11. Alternative planning

### 11.1 Plan relations

Canonical plans should declare one of:

- `exact`
- `safe_adjustment`
- `alternative`
- `partial`
- `none`

### 11.2 Material alternatives require confirmation

If the requested goal cannot be satisfied exactly but a meaningful alternative
exists, Chromie proposes it naturally and executes nothing until the user
confirms.

Example:

> 我还不能确认边走边眨眼是否安全，但可以先走十五秒，再眨眼。可以吗？

### 11.3 Safe autonomous adjustment

A safe adjustment may proceed without an additional confirmation only when:

- it preserves the user’s material outcome;
- policy explicitly allows that class of adjustment;
- it does not add cost, risk, or irreversible effects;
- the adjustment is recorded and explained when relevant.

Reducing speed for stability may qualify. Dropping an explicitly requested
blink action usually does not.

### 11.4 Atomic commitment

All steps in a complete or alternative plan are validated before any effectful
step is committed. An invalid second step must not leak a valid first step into
execution.

Goal-state mutation also follows a two-phase boundary:

```text
associate and plan
-> compose response
-> trusted host prepares and validates the InteractionResponse
-> atomically commit all goal operations
-> confirm / execute
```

If host preparation, capability validation, or any goal operation fails, none of
the staged goal mutations from that turn become durable. Execution request IDs
and terminal provider evidence are then recorded against every source goal they
serve; optional social-attention requests never enter the primary user-goal
lifecycle.

Effect authority is also monotonic within one turn. The configured cognitive
lane allowlist says which kinds of plans the deployment can support. The
Core-owned interpretation result supplies the turn's maximum source-effect
envelope; that safety constraint is not semantic goal ownership or a Plan. A
speech-only `chat` turn cannot become `robot_action` after Goal
Association or planning merely because both lanes are enabled. Such escalation
stops at the authority boundary before Response Composition, capability
validation, or any SkillRequest is emitted.

For an accepted effectful plan, executable wording from the Response Composer
is not treated as execution evidence. The trusted adapter preserves that
model-authored wording while validating the immutable plan fingerprint, goal
coverage, structured speech act, commitment state, actual confirmation
requirement, and absence of premature completion authority. It excludes
pre-execution progress/final stages and requires playback to start before a
dependent physical request may begin. If that delivery barrier fails or times
out, all queued chunks from the response are invalidated so delayed synthesis
cannot announce an action after the runtime has stopped it. The Host never
reconstructs action meaning from capability-specific phrase templates.

## 12. Social interaction layer

### 12.1 Social Attention is a behavior domain

A turn coordinates an immutable user task plan with response language and an
optional Social Attention expression plan. Social Attention is not one skill and
not a deterministic utterance-to-gesture mapping. It is a model-authored
interaction objective that may be expressed through language, body behavior,
both, or deliberate stillness.

The coordinated shapes are:

```text
Canonical User Task Plan
Response Plan
Auxiliary Social Attention Plan
```

### 12.2 Explicit goals and auxiliary expression

A concrete user request such as "blink twice" or "look at me" remains an
explicit CanonicalPlan goal. It is non-droppable and cannot be replaced with a
more convenient gesture.

Autonomous interaction expression uses
`interaction_role=auxiliary_expression`. It may support acknowledgement,
listening, engagement, empathy, turn taking, deference, neutral presence, or
another model-stated purpose. It cannot satisfy, replace, authorize, or claim
completion of a user goal.

### 12.3 Model authority

Response Composer sees the immutable terminal plan, actual response stages,
turn context, target evidence, and catalog candidates tagged with the
`social_attention` behavior domain. The model owns:

- whether expression is useful;
- the social purpose;
- speech style and pacing adaptation;
- exact candidate skill IDs, arguments, timing, social function, and target;
- the choice to use body expression, language adaptation, both, or neither.

The host does not map purposes or user phrases to actions. It validates catalog
membership, schemas, target evidence, resource conflicts, confirmation and
safety policy, low-level-field exclusion, auxiliary limits, and execution
evidence.

### 12.4 Capability taxonomy is not planning

Capabilities may declare multiple behavior domains. Gaze, blink, nod, head
orientation, posture, and bow are current Social Attention candidates, but the
same underlying motion can serve perception, navigation, or another domain in a
different plan. `capabilities/behavior_domains.json` supplies semantic taxonomy;
simulator or hardware provider metadata never participates in candidate
discovery or social policy.

Soridormi backends preserve the same named-skill and semantic-argument
contracts. Backend selection, controller adaptation, calibration, motion
limits, collision safety, stop, and recovery are provider responsibilities and
are not represented in Chromie's Social Attention policy.

### 12.5 Target evidence and conflict policy

Target priority is:

1. live perceived user;
2. structured conversational target;
3. no targeted behavior.

Chromie never accepts installation calibration or body coordinates as target
evidence. Soridormi resolves the semantic target for its active embodiment.

Invalid, sequential, or conflicting auxiliary body behaviors are dropped. A
speech-only adaptation may remain when body behavior is rejected. Auxiliary
expression never delays speech, emergency handling, or primary task execution.
The Response Composer receives the owner-approved Social Interaction Style and
bounded recent accepted-request evidence for cooldown and repetition restraint;
that evidence never proves provider completion.

See [Social Attention Behavior Domain](SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md).

## 13. Deterministic validation and commitment

The validator checks:

- goal and plan versions;
- plan structure;
- exact skill IDs;
- argument schemas and bounds;
- capability availability;
- provider registration and state;
- resource claims and conflicts;
- timing declarations;
- confirmation requirements;
- policy and authorization;
- stale or superseded grants;
- forbidden low-level controls;
- claim/evidence consistency.

The validator must not:

- decide whether “ice it” modifies coffee;
- infer that blinking four times is natural;
- choose which active goal “cancel that” references;
- create an alternative plan;
- write user-facing clarification language.

## 14. Execution and evidence

Execution is owned by trusted runtimes:

- Trusted Capability Runtime;
- tools and trusted services;
- memory providers;
- Soridormi for embodied planning and execution.

Execution never rewrites the user goal. Runtime observations may trigger a new
plan version, but only the cognitive layer proposes a semantic goal change.

Every committed step records or binds:

- request, plan ID, and immutable plan fingerprint;
- exact step skill/version, arguments, and execution timing;
- goal and plan versions;
- provider;
- the full committed output-schema SHA-256 identity;
- start and end state;
- cancellation state;
- result evidence;
- failure reason;
- resource and safety events.

The host joins those records into an immutable `ExecutionOutcomeBundle` by
canonical plan fingerprint, exact step skill/arguments/timing, request ID,
source goal ID, result, and trace. An absent result is `not_run`, never inferred
success. `partial` requires completed and unresolved work; heterogeneous
all-uncompleted states aggregate conservatively while exact per-goal and
per-step statuses remain present. Pre-action speech and auxiliary social
attention cannot satisfy an effectful goal.

Provider output may enter model-facing final composition only through a bounded
projection that passes the declared non-empty output schema and low-level-field
filter. Retained evidence keeps provenance and an output digest even when the
model-facing projection is unavailable. Provider postcondition evidence such
as Soridormi safe idle is recorded separately; it supports only the claims its
contract proves.

## 15. Response architecture

### 15.1 Pre-execution response

Before effectful execution, a response plan may contain:

- immediate low-commitment acknowledgement;
- pre-action confirmation;
- progress update;
- clarification;
- refusal or unavailable explanation.

Prospective planning output cannot contain a final completion claim.

A clear request whose required Capability is absent has an earlier terminal path. Goal
Interpretation may acknowledge the understood outcome and return
`missing_or_unsupported_ability`; Cognitive Runtime then emits one capability-limitation
interaction with no Goal Association, Plan, or provider request. The interaction records
`capability_state=unavailable`, `execution_state=not_attempted`, and
`result_state=not_observed`. This state is categorically different from an executed query
whose trusted result is empty. Speech delivery can express the distinction but cannot
change it, and `chromie.speak` cannot stand in for the missing substantive Capability.

The Host may schedule a complete, schema-valid source-authored `fast_speech` or
`ResponseStage` only after mechanical validation authorizes it against the
applicable turn/Goal correlation, commitment or evidence state, claim guards,
and cancellation generation; it need not wait for unrelated later response
fields. Raw model-token deltas, partial JSON, private reasoning, and incomplete
sentences are not response contracts. Goal Interpretation owns the exact dynamic
Fast Response wording and the semantic decision to speak or remain silent. Its
model-facing structured output must make that decision explicitly: `fast_speech`
is one brief natural string or JSON `null`, never an omitted field. This makes the
communication decision required without making speech mandatory. The Host derives
route-specific purpose/commitment and other deterministic claim-envelope facts;
the model does not redundantly copy those system invariants. No second production
LLM re-decides or repairs that ordinary communication choice. Dynamic pre-Goal
speech must carry `claim_state=none` with empty capability and
Goal claim IDs. Tool speech uses the typed `acknowledge_and_check`/
`checking_only` contract before result evidence; a memory acknowledgement is
likewise purely prospective and cannot claim that the commit already happened.
The Host does not classify ordinary wording by keywords. An immediate
acknowledgement may claim only understanding/evaluation and prospective intent;
a proposal or confirmation requires a validated plan, starting speech requires
committed execution, progress requires correlated runtime evidence, and final
speech requires reconciled terminal evidence.

Response stages reuse earlier current-turn speech by exact speech-event ID and
structured act fields, not text comparison. The playback event preserves turn,
source Goal IDs, canonical Plan identity/fingerprint, delivery role, claims,
and the completion-claim restriction emitted by the Core. Pre-Goal Fast speech
stays explicitly unbound; Goal-bound speech cannot later be reassigned to an
unrelated Goal or Plan. Only playback-started or completed events satisfy an
audible act. A scheduled event remains pending; if it never becomes audible,
Runtime may fulfill the referenced act once. This does not suppress independent
result, failure, limitation, clarification, confirmation, progress, or
completion responsibilities.

### 15.1.1 Interaction Ledger and Interaction Context

`Interaction Ledger` is the bounded, append-only journal through which Chromie
reports her own already-performed interaction history to later cognition. Its
model-facing audience includes Goal Interpretation, Goal Association, Fast
Planner, Deep Planner, Tool Result Interpretation, Response Composer, and any
later cognitive stage that can otherwise repeat a Goal-scoped conversational or
effectful responsibility. Runtime owners append the qualified facts. This
architecture document is the authoritative owner of the term because the
contract spans Speaking, Activity, Social Attention, and cognition; no
component-only document can own that cross-lane boundary.

Every entry is immutable, replay-safe, typed by owner, lane, event type, state,
Goal IDs, turn, Plan provenance, subject, time, and evidence references. Existing
owners append only facts they are qualified to observe:

| Owner | Ledger facts | What those facts do not prove |
|---|---|---|
| Cognitive Runtime | Goal association and validated Plan resolution | That a planned effect started or completed |
| Playback Delivery | speech scheduled, playback started, or not delivered | Activity execution or completion |
| Trusted Capability Runtime | Activity, provider-backed Speaking, or Social Attention request committed; Social Attention terminal result | Completion of an unrelated Goal |
| Execution closure | Goal-scoped Activity or provider-backed Speaking terminal outcome with `ExecutionOutcomeBundle` evidence references | A stronger result than the referenced bundle proves |

The Ledger neither edits nor replaces playback evidence,
`TaskProposalLedger`, recent auxiliary-behavior evidence, Goal state, or
`ExecutionOutcomeBundle`. A repeated event identity must reproduce the same
immutable content. A proposal, Plan, scheduled utterance, committed request, or
provider postcondition never becomes completion merely because it appears in
the Ledger. Terminal Activity entries require trusted execution evidence.
Runtime may append a validated terminal bundle even when the separate Goal-state
commit later fails; that event reports only the bundle's execution fact and
does not claim that Goal state was updated.

`Interaction Context` is the deterministic, model-facing projection of that
journal, not another store. Runtime selects a bounded chronology for the
relevant Goal IDs and includes same-turn unbound Fast speech without inventing
Goal ownership. It exposes already audible speech, pending speech, Activity and
provider-backed Speaking work, Social Attention actions, Goal/Plan history, and
unresolved waits. Before canonical Goal IDs exist, Goal Interpretation and Goal
Association receive bounded recent session context; after association, later
cognition receives the Goal-scoped projection.

Every model stage applies the same continuity rule: combine the current Goal,
what Chromie actually delivered, what trusted evidence says actually completed
or failed, and any new observation, then produce only the still-needed semantic
or effectful delta. Scheduled speech is pending rather than heard, and a Plan or
committed request is pending rather than complete. A later stage may repeat an
act only when the current meaning justifies it, for example an explicit repeat,
retry, correction, changed state, new evidence, or clarification. The Ledger is
therefore shared state, not a source of pairwise rules such as “Deep Planner must
not repeat Fast Planner.”

The current runtime retains at most 160 in-memory events per session and
projects at most 48 recent relevant events into volatile Prompt Layer 4. This
is current interaction context, not durable Global Memory. Retention eviction
does not rewrite a retained event, and no source claim is made for continuity
across process restart. A future persistence requirement must preserve the same
owner, replay, evidence, and bounded-projection contracts rather than silently
promoting the Ledger into long-term memory.

### 15.1.2 Goal Progress Communication

Goal Progress Communication is the shared user-facing communication responsibility
that spans the lifetime of one Goal. The familiar Fast Response is its earliest
common milestone: after Goal Interpretation has sufficiently understood a
nontrivial Goal that still requires downstream work before a substantive answer or
effect, Chromie should normally give one tiny polite prospective notification so
the person knows the Goal was understood and is being taken forward. Missing
result evidence limits what that notification may claim; it is not itself a
reason for silence. A separate Fast Response is omitted when a substantive answer
is immediate, an equivalent notification is already delivered or pending, the
user requested silence, or another line would only repeat or add empty chatter.
That act is not Social Attention and is not clarification or confirmation of an
unclear Goal. At this boundary optional speech does not mean an optional decision:
the source model must return either notification text or explicit `null`. A missing
field is a contract defect, not evidence that silence was intended.

The same responsibility continues after the initial acknowledgement. A planner,
trusted result interpreter, response composer, or later cognitive stage may propose
concise speech when it owns a genuinely new and trustworthy user-relevant delta,
such as a material plan limitation, a meaningful wait state, an important achieved
milestone, a failure or retry state, a correction, or completion. Stages without a
user-facing speech field preserve the milestone in authoritative Goal/runtime state
so a later speech-capable stage can communicate it. The architecture does not add a
parallel speech pipeline for every module merely to expose implementation progress.

After the initial Fast Response, later progress speech remains selective. The
cognitive stage that owns a new milestone reasons about whether it is worth telling
the person; it should not narrate internal modules, schemas, provider plumbing,
planning mechanics, or every execution step. The objective is responsive, polite,
low-noise interaction rather than minimum word count or maximum status reporting.
Each milestone has one cognitive communication owner. The runtime does not call a
second LLM to re-decide or repair an ordinary speech-versus-silence judgment.
Mechanical schema, authority, evidence, cancellation, and delivery checks remain
deterministic; semantic mistakes are fixed at the source prompt/model boundary and
measured in regression and benchmark scenarios. If a structurally valid Fast Plan
is escalated for an unrelated planning/coverage defect, its source-authored progress
`response_text` may be retained only as an **undelivered advisory** for Deep
Planning. Retention makes no truth or playback claim and does not satisfy the
communication act; Deep Planning still reasons from Interaction Context and
current evidence before using any such candidate.

Every stage uses Goal-scoped Interaction Context before proposing speech. Only
audible playback counts as already told to the user; scheduled speech is merely
pending. Planned or committed work is not an achieved milestone, and a completion
claim still requires trusted terminal evidence. Equivalent delivered or pending
progress acts are reused or omitted rather than paraphrased at successive stages. For current-turn
speech, the runtime can enforce this mechanically from the typed speech act and Interaction Ledger
event identity: a later stage that wants the same act must reference the existing event instead of
requesting new audio. A genuinely new supplement carries a different semantic act. A new
notification is justified by a new semantic progress delta, not by a module boundary.

### 15.2 Post-execution response

After execution, the host's deterministic closure reconciles every executable
canonical goal against the `ExecutionOutcomeBundle` and commits the resulting
goal state. The current conservative final composer receives the immutable plan
and reconciled evidence. It returns speech only, with exact goal and evidence
references. It cannot add a skill, action, retry, authorization, or goal
change. A future model-assisted final composer must consume the same bounded
contract and obey the same validator.

The host validates that:

- every relevant goal is covered exactly once;
- every claimed outcome matches the reconciled goal status;
- every evidence reference exists and belongs to that goal;
- completion language is unavailable for partial, failed, timed-out, refused,
  cancelled, or `not_run` outcomes;
- a stale or preempted interaction cannot emit final speech.

If outcome-response validation or composition fails, the host retains the
trusted outcome bundle and emits no unvalidated completion claim. The current
deterministic composer is itself the conservative language-matched status path.

### 15.3 Recovery child plans

A recoverable Soridormi failure may produce a retry proposal only by creating a
new immutable child `CanonicalPlan` containing the failed recoverable subset.
The child records the parent plan ID and fingerprint, receives its own plan
fingerprint, new request/idempotency identities, and fresh request-bound
confirmation. It then re-enters ordinary validation, execution, and
reconciliation. Completed parent steps are neither mutated nor replayed; an
invalid subset, non-recoverable sibling, exhausted budget, or missing
confirmation means no retry.

### 15.4 Claim validation

Speech claims must be structurally tied to task and evidence state.

Examples:

- “I’m checking” may be valid before a tool result.
- “I found…” requires tool evidence.
- “I’m walking” requires committed execution state.
- “Done” requires completion evidence.

### 15.5 Natural multi-goal composition

The response composer may combine updates naturally:

> 我已经记住你只喝美式。咖啡我先看看怎么拿，天气也在查。

The individual goals remain separately tracked even when speech is consolidated.

The model-facing pre-execution composer contract contains only response stages,
optional social attention, confidence, and rationale, with response coverage
constrained to the immutable plan's Goal IDs. The post-execution contract
contains only final text, exact goal/evidence claims, confidence, and rationale.
The host owns both composition identities, the embedded canonical plan and
fingerprint, and the execution-outcome fingerprint. Invalid model output may
receive one bounded repair in the same composer stage using the exact schema
and validation errors; it cannot trigger another semantic planner.

## 16. Scenario-driven development

Every meaningful behavior change follows:

```text
real interaction or explicit requirement
→ retained scenario
→ scenario fails
→ design review if needed
→ implementation
→ scenario passes
→ full regression
→ merge
```

The companion document
[Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md) defines the
required fixture structure, evidence boundaries, and review process.

## 17. Design invariants

The following are merge-blocking invariants for the current and next Continuous
Mind architecture:

1. One Cognitive Core owns ordinary semantic meaning even when cognition runs at
   multiple timescales. Parallel progress does not create a second semantic
   authority.
2. A persistent Goal represents unfinished responsibility; an immediately
   completed low-risk act need not wait for persistent Goal materialization
   before useful progress begins.
3. Goal Association owns continuity and explicit progress-to-Goal binding; Host
   code does not infer ownership from route labels, recency, text similarity, or
   capability resemblance.
4. A typed progress candidate is meaning, not authorization or completion.
5. Planning is required when an intention needs decomposition, alternatives,
   dependencies, or stronger commitment; it is not a mandatory transport stage
   for complete native conversation or trusted ready non-effectful acquisition.
6. Effectful work never bypasses deterministic validation, confirmation when
   required, authorization, resource policy, or provider safety.
7. Partial coverage never becomes implicit execution, and no material alternative
   silently replaces the user's responsibility.
8. Later cognition may revise, redirect, cancel, or supersede progress that has
   not crossed an irreversible commitment boundary; already observed reality is
   preserved as evidence rather than rewritten.
9. Observation/evidence may reactivate cognition and update current state, but
   external data cannot rewrite Mind authority or instructions.
10. Claims about execution, observation, memory, or completion require trusted
    evidence; presentation failure cannot rewrite a trusted outcome into user
    misunderstanding or capability failure.
11. Social Attention and Speaking are genuine interaction progress but do not
    independently own user Goals or effect authorization.
12. Fast and Deep planning share canonical execution contracts when planning is
    needed; Deep does not route semantic decomposition back to Fast.
13. Uncertainty is resolved by the cheapest trustworthy means appropriate to the
    responsibility—observation, information acquisition, clarification, waiting,
    or deeper reasoning—not by a confidence threshold alone.
14. Reflection is selective slow cognition, not a required synchronous stage of
    every interaction; it cannot self-authorize policy, identity, values, or
    effectful learned behavior.
15. Stable Mind identity/personality/worldview/values and hard-boundary principles
    remain distinct from dynamic externally acquired facts.
16. New cognitive concepts must justify an independent lifecycle or authority and
    should replace/consolidate obsolete concepts rather than only increase the
    permanent architecture surface.

The implemented General Progress substrate is intentionally narrower than the
full problem space in Sections 4.11–4.13. Those sections define immediate design
work, not implementation claims.

## 18. Prohibited anti-patterns

The following patterns violate this architecture:

- regex or phrase-table planning for normal language;
- hidden keyword-to-skill mapping or `route == chat/tool` as a semantic readiness
  rule;
- a mandatory `Gateway → Goal Association → Planner → Composer → Execute`
  wall-clock pipeline when no true dependency requires it;
- one new persistent Goal per utterance or per implementation step;
- treating Goal as an execution ticket rather than unfinished responsibility;
- Host-inferred progress ownership from recency, text similarity, or capability
  resemblance;
- Fast Understanding output being treated as authorization for an effect;
- partial action leakage from an invalid compound responsibility;
- model output directly authorizing execution;
- deterministic code choosing ordinary conversational meaning;
- a numerical confidence threshold acting as the sole readiness, truth, or
  authorization decision;
- thinking longer when a blocking uncertainty can be resolved by available
  evidence, observation, or clarification;
- an unlimited background-thought or Reflection loop;
- a Reflection/review LLM after every normal action regardless of surprise, risk,
  or learning value;
- creating one manager/class/model role for every term in the Continuous Mind
  problem-space list;
- self-generated concern automatically becoming external execution authority;
- automatic promotion of experience into policy, personality, values, motor
  skills, or provider capabilities without the owning review/authority boundary;
- fixed gesture after every response or Social Attention made dependent on
  speech;
- social gestures recorded as user-requested tasks when they were auxiliary;
- speech claiming results before evidence;
- external/provider text treated as instruction authority;
- implementation-component identity replacing Chromie's speaking identity; and
- unlimited active-goal, belief, observation, or conversation context.

## 19. Implementation record

This constitution was implemented through staged PR1-PR9 work. The stage
descriptions below are an implementation record, not a statement that the
maintained runtime still runs those components as independent report-only
observers. Each stage began with retained scenarios and did not claim
later-stage behavior.

PR1-PR9 established the Goal-Driven Cognitive Core and closed one admitted
effectful turn through evidence-bound final response. The subsequent Gateway
work completed the five-module admission boundary and removed the independent
Goal Interpreter service. Target live behavior remains a separate evidence
claim tracked by the current status and qualification documents.

### PR1 — Goal contracts and continuity projection

Deliver:

- shared `SemanticGoal`, `GoalSet`, `GoalRelationship`, and version contracts;
- bounded active-goal projection;
- compatibility mapping from current semantic-task contracts;
- replay-safe operation IDs;
- no runtime behavior change by default.

Exit criteria:

- contract tests;
- active-goal projection tests;
- compatibility fixtures;
- documentation and dependency-light suite pass.

### PR2 — Goal association and segmentation

Deliver:

- model endpoint that associates a turn with existing goals;
- independent new-goal segmentation;
- natural ambiguity clarification proposal;
- report-only comparison against current routing/task proposals.

Exit criteria:

- coffee modification scenario;
- “cancel that” ambiguity scenario;
- multi-goal memory/coffee/weather scenario;
- no phrase/recency decision rules.

### PR3 — Canonical plan and Fast Planner

Deliver:

- shared canonical-plan schema;
- fast coverage decision: complete, partial, uncertain;
- direct simple chat and common-skill planning;
- partial coverage always escalates;
- common catalog remains an accelerator, not a boundary.

Exit criteria:

- simple blink direct plan;
- simple chat response;
- walk-and-blink cannot narrow to walking;
- identical validator path for fast plans.

### PR4 — Deep Planner and bounded replan

Deliver:

- full-registry deep planning;
- exact, safe-adjustment, alternative, clarification, unavailable, refused;
- structured validator rejection feedback;
- bounded same-tier replan;
- explicit no-return-to-fast invariant.

Exit criteria:

- conditional and composed plans;
- resource conflict alternative;
- replan-budget exhaustion behavior;
- no planner recursion.

### PR5 — Parameter resolution and goal satisfaction

Deliver:

- consequence-aware parameter-source decisions;
- structured information gaps;
- goal satisfaction/coverage report;
- natural specific clarification;
- resume original goal after a later answer.

Exit criteria:

- low-consequence blink default scenario;
- material movement-duration clarification scenario;
- observation-derived parameter scenario;
- no internal schema wording reaches users.

### PR6 — Response and social interaction plans

Deliver:

- multi-goal response composition;
- validated response commitments;
- independent social attention plan;
- target-evidence and resource-conflict validation;
- latency-bounded optional behavior.

Exit criteria:

- attention and no-attention scenarios;
- live-target override scenario;
- long task acknowledgement without false completion;
- social behavior excluded from user tasks.

### PR7 — Runtime migration and retained evidence

Implementation status: the unified runtime, lane-gated rollout, rollback,
operational evidence recorder, classified acceptance tooling, and cognitive
text-to-MuJoCo entry point are implemented and automatically verified. Retained
live-text and MuJoCo target evidence remain open and must be collected on the
intended deployment.

Deliver:

- staged `off`, `report_only`, and `apply` rollout;
- lane-gated application with compatibility and fail-closed fallback policy;
- migration from task continuity to atomic Goal continuity application;
- trusted host validation and one bounded same-tier Deep revision;
- complete dependency-light cognitive runtime scenarios;
- operational evidence classification and rollback;
- live-text and MuJoCo evidence collection entry points.

Exit criteria:

- all dependency-light tests pass;
- cognitive scenario library passes;
- apply records are written only after trusted preparation and atomic Goal
  state application;
- retained live-text and simulator evidence are reviewed before target behavior
  is claimed;
- no release claim exceeds collected evidence.

Operational details are maintained in
[Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md).

### PR8 — Single semantic authority and model-facing contract hardening

Implementation status: the unified runtime is authoritative for configured
lanes, exact Goal Interpreter actions are adapter-only, and the legacy CapabilityAgent
planner is emergency-only behind matching per-turn authority. Goal Association
uses the exact model-facing schema while the host constructs canonical
persistence objects.

Exit criteria:

- authoritative turns do not fall through to a second semantic planner;
- emergency fallback requires both service gates and a non-empty matching-turn
  claim;
- model-facing Goal Association values are schema constrained and receive at
  most one bounded contract repair;
- contract exhaustion fails closed;
- automated authority and schema-boundary checks pass;
- retained live-text and MuJoCo evidence is reviewed before target behavior is
  claimed.

### PR9 — Cognitive turn closure

Implementation status: integrated in the host manager path with focused
automated contract and host-integration coverage. Retained provider-backed
live-text, simulator, microphone, dedicated E-stop/safe-idle, and physical
robot evidence remains open.

This stage closes the two contract gaps around PR1-PR8 without redesigning its
semantic planners:

- a versioned `UserTurnEnvelope` is the preserved Gateway-to-Core input;
- a compatibility adapter preserves bounded Goal Interpreter and Agent data
  contracts inside the Core without restoring a service or fallback authority;
- a deterministic `ExecutionOutcomeBundle` joins exact canonical
  step/skill/arguments/timing, committed requests/schema identity, and trusted
  runtime results/traces to exact goal IDs;
- outcome reconciliation updates goal state from evidence rather than
  prospective planner output;
- a deterministic post-execution composer produces one evidence-bound,
  speech-only final response with no executable work;
- cancellation and newer-turn preemption suppress stale final speech while
  preserving outcome evidence;
- recoverable retries create independently fingerprinted,
  confirmation-bound child plans over only the failed recoverable subset.

Exit criteria:

- original input, reflex, attention, admission, and context provenance survive
  the Gateway/Core boundary;
- success, partial failure, refusal, timeout, cancellation, and missing results
  are distinct per-goal outcomes;
- unknown plan, goal, step, request, or evidence references fail closed;
- provider output is model-visible only after declared-schema validation and
  bounded low-level-field filtering;
- effectful interactions produce at most one post-execution final response;
- response-composition failure retains evidence and emits no unvalidated
  completion claim;
- no automated test is reported as live provider, simulator, microphone, or
  physical-robot evidence.

## 20. Retained compatibility and evolution rules

Routes, route items, semantic tasks, and task-proposal ledgers may remain only as
bounded, versioned compatibility or evidence surfaces around the maintained
Goal-driven Runtime.

Evolution rules:

- preserve deterministic safety, authorization, cancellation, and evidence
  boundaries;
- keep Cognitive Gateway normalization, protective reflex, attention, context,
  and admission distinct from Core semantics;
- keep goal meaning, association, decomposition, affordance grounding, planning,
  semantic coordination, outcome synthesis, and response composition inside one
  Goal-Driven Cognitive Core authority;
- treat `RouteDecision` route/intent/action/proposal fields as digest-bound
  advisory inputs only, never as a service, canonical Plan, or execution grant;
- use `report_only` only for explicit observation or rollout diagnosis, not as
  the maintained authority mode;
- compare complete Goal coverage and committed capabilities before widening an
  apply lane;
- after Core authority is acquired, fail closed rather than falling through to a
  second semantic planner;
- remove remaining compatibility aliases only through an explicit contract
  version change with retained regression and target evidence.

## 21. Observability

The cognitive loop should record, without exposing private model reasoning:

- normalized observation/input identity, protective-reflex result, and admission;
- Fast-Understanding progress candidates and their typed kind;
- readiness decisions and the trusted facts that allowed or blocked progress;
- explicit progress-to-Goal bindings and Goal relationship/lifecycle changes;
- native Speaking, capability, and Social-Attention progress start/terminal state;
- planner invocation only when planning was actually needed, including escalation
  reason and duration;
- canonical plan/commitment identity when one exists;
- information gaps, uncertainty source, and resolution method;
- validation/authorization rejection codes and confirmation binding;
- observations/evidence and the responsibilities they reconcile;
- corrections, cancellation/supersession, and bounded reactivation events; and
- Reflection/experience-promotion events if later implemented, with the trigger
  that justified them.

Current traces may still preserve direct/Fast/Deep compatibility classifications,
but observability must report the readiness-driven reality rather than imply that
all roles ran serially. Exact warm/cold, compute contention, shared-resource
latency, cognitive reactivation, and future Reflection cost remain target-evidence
claims and must come from retained runs.

Logs show state transitions, decisions, authority, and evidence—not hidden
chain-of-thought.

## 22. Non-goals

This architecture does not claim:

- human-equivalent consciousness or a literal neuroscience model;
- general autonomous operation or unattended physical-robot authority;
- unrestricted self-generated external Goals or self-modifying prompts/policy;
- one persistent DTO, manager, database, or model call for every cognitive
  phenomenon named in the problem space;
- an always-running background LLM or mandatory Reflection after every turn;
- unbounded long-term memory or permanent retention of every observation;
- automatic approval of learned behavior, habits, values, identity changes, or
  provider skills;
- removal of deterministic safety, consent, permission, authorization, or
  evidence controls;
- that every responsibility needs a Goal, Planner, Deep reasoning, or Response
  Composer;
- that a numerical confidence/satisfaction score alone can authorize progress; or
- production physical-robot readiness.

## 23. Review checklist

Every cognition-related change should answer:

1. What general cognitive responsibility or invariant is being improved, beyond
   the initiating example?
2. Is the input an Observation, existing state update, new/continued unfinished
   Responsibility, progress candidate, or trusted effect-control event?
3. Can the responsibility be completed immediately, or what makes persistent Goal
   state necessary?
4. If progress may start now, which typed meaning, dependency, risk, permission,
   and evidence facts make it ready?
5. If progress cannot start, should Chromie wait, acquire evidence, clarify, plan,
   defer, or use slower cognition?
6. Does Goal Association explicitly preserve continuity and bind progress without
   Host semantic guessing?
7. If planning is used, is it forming the smallest useful intention/commitment,
   and can later observation revise unfinished work safely?
8. What is the commitment depth, and which trusted boundary authorizes the next
   step?
9. What observation/evidence is expected, and what happens if reality contradicts
   that expectation?
10. Does the change affect attention/working set, user/common ground, privacy,
    consent, memory, or restart continuity?
11. Is Reflection truly warranted, or would another review call only add latency?
12. Is a proposed new concept already representable by Goal, General Progress,
    Interaction Ledger, Plan, ExecutionOutcome, Memory, Capability/provider state,
    or existing authority?
13. What obsolete concept/path can be removed or consolidated if a new one is
    introduced?
14. Which retained general-ability scenario fails before the change, and what
    evidence supports the resulting source/target claim?

## 24. Definition of architectural success

Chromie satisfies this architecture when:

- simple, fully understood responsibilities can progress at human-useful latency
  without waiting for unrelated cognition;
- unfinished responsibilities survive as coherent Goal/prospective-memory state
  and reactivate from meaningful observations, dependencies, time, or user input;
- the same turn may contain progress at different maturity levels without
  collapsing them into one synchronous workflow;
- later cognition can correct or supersede unfinished progress while irreversible
  commitments remain strongly gated;
- observation, current belief/context, Goal, intention/progress, commitment, and
  evidence are not silently conflated;
- uncertainty is resolved through trustworthy evidence acquisition when possible
  rather than hallucination or unnecessary deeper inference;
- attention and compute remain responsive while slow cognition continues;
- Speaking and Social Attention feel continuous without becoming separate semantic
  authorities;
- Reflection improves correction/calibration/experience selectively without
  becoming a latency tax or self-modification loophole;
- multi-user privacy, consent, promises, recovery, and learning promotion remain
  authority-bound as those capabilities are introduced;
- the final architecture uses a small number of clear state concepts that explain
  the complete problem space rather than one subsystem per cognitive term; and
- every material behavior and architectural widening is protected by retained
  general scenarios and evidence proportional to its claim.
