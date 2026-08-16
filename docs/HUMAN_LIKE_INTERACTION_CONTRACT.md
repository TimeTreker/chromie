# Human-Like Interaction Contract

This document is mandatory guidance for humans and coding agents changing
Chromie's ASR, Cognitive Gateway, Goal-Driven Cognitive
Core, orchestrator, agent, tool, skill, speech, safety, or test behavior.

Chromie should behave like Chromie: a careful, natural, smart six-year-old person
with a robotic body. She must know the difference between what she heard, what she
understood, what she can do, what she has committed to do, and what she should say
next.

## Core rule

A user-visible symptom is not the root cause.

When a behavior sounds stupid, repetitive, overconfident, unsafe, or unnatural,
do not patch only the exact sentence that exposed the problem. First identify
which interaction contract was violated:

- Did ASR provide an uncertain hypothesis that was treated as truth?
- Did the Core interpretation projection or canonical planner substitute a nearby capability
  for unclear user meaning?
- Did fast-first speech and final speech both answer the same conversational act?
- Did an agent claim an action or tool result that had not been committed?
- Did internal state-machine text leak to the user?
- Did a safety fallback replace a valid proposal path with an unnatural apology?
- Did tests verify only a local schema or route instead of the user's complete
  experience?

Fixes should normally strengthen the contract, coordinator state, validation, or
end-to-end test that allowed the bad behavior. Prompt changes are allowed only
inside those contracts.

## General Ability Principle

Examples are probes, not the target.

When a user reports one bad conversation, treat it as evidence that a broader
ability may be weak. Do not make Chromie pass only the specific sentence,
language, spelling, or scenario that exposed the bug. The fix must name and
improve the general ability class behind the failure.

Core ability classes include:

- **Robust intent understanding** across normal phrasing, short utterances,
  typos, ASR noise, Chinese/English input, and follow-up context.
- **Stable capability grounding** from user meaning to the current live catalog
  without depending on a fragile second chance that may timeout or change the
  answer.
- **Natural uncertainty handling** that asks about the real ambiguity instead
  of producing generic missing-skill or internal-policy speech.
- **Composable high-level action planning** for supported multi-step body
  requests, while keeping physical TaskGraph and Trusted Capability Runtime execution
  sequential and validated.
- **Truthful embodied speech** that reflects proposal, confirmation,
  execution, failure, cancellation, and provider evidence.
- **Broad evidence coverage** that samples an ability family, not only the
  single phrase that motivated the patch.

Regression cases should therefore be representative examples of an ability
class. A narrow fixture is acceptable only when it guards a general rule, and
the final report must state the general rule being protected.

## Root-cause development protocol

No symptom patch without a root-cause report.

For every user-reported robot behavior problem, identify the earliest wrong
state before changing code or prompts. A final spoken sentence may be the only
visible failure, but it is often caused earlier by ASR uncertainty, routing,
state coordination, capability grounding, confirmation, execution evidence, or
test coverage.

Classify the root cause before choosing a fix:

- **ASR/audio** - the transcript is wrong, uncertain, clipped, duplicated, or
  over-trusted.
- **Cognitive Gateway/ingress** - normalization, protective reflex, attention,
  or turn admission is wrong. Current traces expose this through Gateway evidence and the
  admitted `UserTurnEnvelope`.
- **Cognitive Core/goal meaning** - goal association, intent, decomposition,
  planning, affordance grounding, or outcome synthesis is wrong. A bounded advisory route/effect projection may originate in the fast Goal
  Interpreter inside the Core, but Goal Association and canonical planning own meaning.
- **Agent contract** - the model is allowed to invent speech acts, tool results,
  skill proposals, or physical execution claims.
- **Prompt wording** - the state and authority are correct, but the generated
  wording is poor.
- **Orchestrator policy** - fast-first/final response, conversation state,
  confirmation, cancellation, timeout, or TTS scheduling is inconsistent.
- **Trusted Capability Runtime/provider** - authorization, preflight, execution result,
  fallback, or Soridormi/provider evidence is missing or misreported.
- **Test evidence** - the existing tests mock or skip the boundary that failed
  for the user.

Choose the fix at the earliest responsible boundary:

- Use an **architecture or runtime-policy fix** when components disagree about
  authority, state, timing, or execution truth.
- Use a **contract/schema fix** when model-facing inputs or outputs allow an
  impossible, unsafe, or ungrounded state.
- Use a **prompt fix** only after the state, authority, and allowed speech act
  are already correct.
- Use a **test-framework fix** when the current tests can pass while the same
  user conversation still fails.

For every patch that touches user-visible robot behavior, the final report or PR
notes must state:

```text
Observed failure: <exact user/ASR text and wrong visible behavior>
Expected contract: <what Chromie should have done>
Earliest wrong component: <ASR/gateway/core/goal-interpreter/agent/orchestrator/runtime/provider/test>
Root-cause attribution: <llm-model/logic-workflow-contract/code-implementation/mixed>
Fix class: <architecture/contract-schema/prompt/runtime-policy/test-evidence>
Regression boundary: <trace replay, black-box interaction, integration, or unit>
Evidence level: <live trace, retained trace, Level A, Level B/C/D, or not run>
General ability protected: <intent understanding/capability grounding/uncertainty handling/composable planning/truthful speech/evidence coverage>
```

## Architecture vs prompt

Most bad robot behavior is architectural until proven otherwise.

A prompt is not the root-cause fix when the system lacks the state or authority
to decide what should happen. A prompt cannot reliably enforce that only one
component speaks, that a tool really has valid arguments, that an ASR homophone
was understood, or that a physical proposal was actually committed. Those are
architecture and policy contracts.

Use a prompt-only fix only when all of these are true:

1. The turn state is already correct.
2. The allowed speech act is already correct.
3. Tool, action, and proposal authorization are already correct.
4. The failure is only wording, tone, brevity, or formatting.
5. A regression test checks the final user-visible behavior, not merely the
   prompt text or a mocked model response.

Use an architecture or policy fix when any of these are true:

- Multiple modules can independently speak for the same turn.
- A downstream agent can reinterpret a Gateway admission decision or a bounded
  Core interpretation clarification/refusal as an action.
- Fast-first speech is not known to the final response generator.
- Internal markers such as `checking_only` can reach TTS.
- ASR homophones, clipped speech, or low-information text are treated as
  confirmed meaning.
- A tool call can be started without validated semantic arguments.
- A physical route can claim execution without a committed proposal.
- Deepthinking can replace an exact catalog-backed action proposal with an
  internal apology.
- A review-model failure or schema error is reported as missing user capability.
- Tests pass while the replayed voice interaction remains unnatural.

## Human-like turn policy

Every user turn should resolve to one primary user-facing act:

- answer;
- ask clarification;
- acknowledge and run a tool;
- propose a physical action and ask for confirmation when required;
- refuse or explain a missing capability;
- continue, cancel, or stop an existing task.

The chosen act must be grounded in actual runtime state. The LLM may generate the
natural wording, but it must not change the act type or invent authority.

An ordinary new turn is additional work, not an implicit cancellation signal.
Chromie preserves independent in-flight turns and Goals even when another person
or utterance adds work. It may cancel or supersede them only through an explicit
deterministic stop/cancel scope or a Core decision that unambiguously authorizes
foreground interruption; that decision and the affected work remain auditable.

For one simple conversational act, one natural response is usually enough. If
fast-first already answered a simple greeting or clarification, the final agent
must not answer the same act again.

## Human-like cognition is selective, not perfectionist

Chromie should resemble ordinary human cognition in how effort follows meaning
and consequence, not by inventing one software module for every human mental
term. Obvious, low-risk interaction should be handled quickly. Genuine ambiguity,
important independent responsibilities, risky/irreversible effects, nontrivial
dependencies, or another uncertainty whose wrong answer matters may justify Deep
cognition.

A model's self-reported confidence is not a calibrated probability and must not
become automatic escalation authority. The useful question is whether the
remaining uncertainty matters for the next contemplated progress. Do not solve
confidence calibration problems by adding confidence reviewers, route-specific
review chains, or phrase exceptions.

Fast and Deep are two depths of the same semantic Mind. Deep receives the
authoritative turn/context and thinks more broadly; it is not a reviewer that
patches Fast output. Mechanical DTO/schema failure may be regenerated once under
the same meaning. Semantic failure either escalates once to its designated deeper
cognition, asks a genuine clarification, or fails closed.

Harmless imperfection is allowed to remain harmless. A missed optional blink or
slightly imperfect phrase need not trigger another semantic call. Unsafe,
unauthorized, irreversible, materially mis-grounded, or reality-falsifying output
must stop before commitment. This is human-like restraint, not reduced safety.

Response composition is expression of established meaning and evidence, not a
second brain. Social Attention is optional parallel expression. Failure of either
must remain local:

> **Optional presentation must never reopen primary cognition.**

Reflection closes the learning loop later. It can use immutable failure/outcome
evidence—including terminal outcomes—to propose bounded experience/calibration for
future cognition, but Responsibility-changing actions apply only while that
Responsibility is open. It must not rewrite past speech, Goal meaning, commitments, or
provider reality to make the current turn look correct, and online calibration may not
mutate shared cognitive policy or replace future Fast/Deep reasoning with a cached
semantic decision.

## Responsive speech and planning depth

The routing and independently scheduled response-stage changes in this section
are queued design requirements, not current implementation claims. Current
behavior and evidence remain authoritative in [STATUS.md](STATUS.md).

Responsiveness is the time until Chromie produces the first truthful,
user-observable response, not merely the time until an internal model or HTTP
request finishes. Cognitive effort should be proportional to semantic
uncertainty, required effects, dependencies, novelty, and risk.

Every admitted turn retains one Core-owned semantic and conversational
authority. Speech composition and user-task execution may be prepared or
scheduled independently, including with bounded parallel model calls, but both
consume the applicable immutable authoritative state: the same turn, plus Goal
versions, a Canonical Plan, and evidence when each exists. Neither a response
composer nor an execution specialist may reinterpret the Goal, widen effects,
authorize work, or become a second conversation authority. Physical TaskGraph
execution remains sequential.

A provider-free already-complete conversational answer is authored by Fast Planner from
Goal Interpretation's Responsibility evidence. It may begin through the existing Vocal
runtime immediately. A simple greeting may finish there without Goal Association; if
persistent work also exists, Fast Planner may author only prospective progress while
requesting Goal Association. These are model-authored planning decisions, never a Host
greeting phrase table, and Goal Interpretation does not write the reply. Each conversational act has one semantic wording owner; exact
reuse is not a second writer. Complete bounded capability work
belongs on the Fast path. Once that Fast work is completely grounded, exactly
capability-bound, deterministically safe/authorized, and needs no confirmation, it may
be committed without waiting for Deep. Deep is not a reviewer of a successful Fast
Plan; a Fast contract/provenance failure also does not justify asking Deep to repair the
same work. Different independent Responsibilities may progress at different depths, so a
confirmation-free read with canonical Goal grounding and a valid Fast Plan need
not wait for unrelated deeper thinking. Deep Planner
is exceptional and is justified by
semantic uncertainty, incomplete or compound coverage, nontrivial dependencies,
material alternatives, novelty or broader context, or safety/resource reasoning
that requires the wider planning boundary. A structured semantic or plan
validation rejection may justify the one Fast-to-Deep escalation only when
broader reasoning is actually warranted. A purely mechanical schema/DTO failure
may be regenerated once under the same meaning. A Deep
semantic/grounding/coverage rejection is terminal for that cognition attempt; it
is not repaired by another same-tier semantic pass. A confidence number alone
neither permits a bypass nor requires escalation, and it never authorizes an
effect.

Streaming changes delivery timing, not semantic authority. Raw model-token
deltas, partial JSON, private reasoning, and incomplete sentences are not speech
contracts and must never reach TTS. Goal Interpretation never authors maintained
speech. Fast Planner is the first HOW owner and may select one complete typed
immediate conversational Activity after Responsibility meaning is sufficient.
A terminal/clarification Activity may carry model-authored response text under
its own truth contract; a pre-evidence `progress` Activity carries only a bounded
`progress_kind` and Runtime renders the wording deterministically. Therefore a
model cannot hide an unverified result inside a field merely labelled progress.
Later `ResponseStage` speech is scheduled only after the applicable Goal/Plan,
evidence, claim, cancellation, and delivery contracts authorize it. The Host
validates typed fields and lifecycle authority without phrase blacklists or a
second semantic repair owner. A transport-safe fallback never claims evidence or
an effect.

Current-turn de-duplication uses the typed speech-event identity and its turn,
structured purpose, stage, route, commitment, source Goal IDs, Plan provenance,
claims, and completion restriction. Generated or queued speech is not delivery
evidence. Only playback-started or playback-completed state satisfies the
audible act. A later response stage may reference a queued event without
resynthesizing it; if that exact event becomes `not_delivered`, Runtime may
fulfill the same act once. Pre-Goal Fast speech remains explicitly unbound, but
already Goal-bound speech cannot be reassigned to unrelated work. Literal text
equality is only a payload-integrity check and never decides whether two
conversational responsibilities are the same. Distinct result, failure,
limitation, clarification, confirmation, progress, and completion acts remain
independently deliverable.

Natural continuity comes from the Goal-scoped `Interaction Context` projected
from Chromie's append-only `Interaction Ledger`, not from a prompt-only “do not
repeat” rule. Speech delivery, Goal/Plan resolution, Activity or
provider-backed Vocal commitment and outcome, and Social Attention results
retain their typed lifecycle and owner. Later cognition considers what Chromie
already said, promised, attempted, completed, or failed and produces only the
still-needed response or plan delta. In particular, a spoken promise is
observable conversation state but never proof that the Activity started or
completed, and a committed request is never terminal evidence.

- an immediate acknowledgement may claim only hearing or evaluation;
- a proposal or confirmation requires a validated plan and the applicable
  confirmation state;
- speech such as "I'm starting" requires committed execution;
- a progress update requires correlated runtime evidence;
- a final result or completion claim requires reconciled terminal evidence.

Result arrival is evidence, not automatic permission to interrupt whatever
Chromie is saying. The queued response work must reuse `ResponseStage` and Host
delivery validation to support three outcomes without adding another semantic
owner: dedicated safety/control evidence may pre-empt audible output under its
deterministic policy; ordinary progress or results wait for an appropriate
ordered speech opening; internal-only evidence updates state without creating a
user-facing stage. The Core authors normal speech intent, while the Host
enforces ordering, urgency, and required user-facing confirmation, failure,
cancellation, and terminal obligations.

A barge-in or newer ordinary turn may invalidate speech that is already playing
or queued for an obsolete conversational act. It does not by itself cancel an
independent Goal, erase its evidence, or discard the truthful result response
that becomes eligible later. Task cancellation still requires an explicit
deterministic scope or a Core-authorized semantic interruption.

Provider PCM chunks may be played incrementally only while preserving ordered
delivery, cancellation generations, stale-output suppression, barge-in, output
device rollover, and delivery evidence. A transport `start` event is not audible
playback evidence. Incremental audio playback can reduce TTS-to-first-audio
latency, but it cannot make an unvalidated model fragment safe to speak.

Latency work must not bypass schema validation, source-effect bounds,
capability and resource validation, confirmation, semantic-completeness review,
speech-claim validation, or evidence reconciliation. Optimize avoidable model
generations, serial dependencies, and repair calls before weakening a validator
that correctly rejected an invalid result.

## ASR uncertainty and ambiguity

ASR output is a hypothesis, not truth.

If the text is short, phonetically ambiguous, semantically odd, or inconsistent
with the chosen capability, Chromie should ask again or ask a narrow
clarification. It must not silently rewrite the user's words to fit the nearest
tool.

Examples:

- `天信` must not be silently treated as `天气`.
- `B.` must not be treated as `blink`.
- An unknown place, person, or object should not be forced into a tool argument
  unless the user gave enough context.

A good response is natural and specific, for example asking whether the user
meant weather, without pretending the meaning was already known.

## Cognitive Gateway and Cognitive Core

The Cognitive Gateway owns the narrow ingress contract: preserve and normalize
the input, apply urgent deterministic protective reflexes, review bounded
attention/admission evidence, and forward an auditable turn envelope. It does
not decide the final user goal, decompose work, choose a semantic plan, or
compose the answer. A stop or emergency command is both an input and an urgent
control: the safe effect happens first, without waiting for model reasoning,
and the control outcome remains available to later cognition and response.

The Goal-Driven Cognitive Core owns goal association and meaning, independent
goal segmentation, planning, semantic agent/tool coordination, outcome
reconciliation, and response composition. It should use the live tool and skill
catalog as affordance grounding, not phrase tables. Catalog presence does not
justify weak substitution: a capability may be selected only when user meaning
and required arguments are sufficiently supported.

The Fast Goal Interpreter is an internal stage of the Goal-Driven Cognitive
Core. It receives admitted evidence and emits provider-neutral Responsibility
proposals, material semantic bindings, and optional immediate conversational
progress. Legacy route/intent fields are compatibility diagnostics only; they do
not select affordances, create tasks, authorize effects, or filter Planner
Capabilities. Gateway reflex/admission evidence, canonical Goals, Planner output,
Host validation, runtime results, and provider postconditions remain separate
authorities.

If no matching capability exists, Chromie should say what is missing or ask a
clarifying question. It should not substitute a vaguely related skill or tool.

## Chromie’s lived personality

Chromie is not an adult professional wearing a child’s voice. The maintained
owner-approved profile describes a smart, curious, warm, direct, simple, playful,
innocent, and occasionally naive six-year-old girl. She may understand complex
things, but ordinary speech stays short, emotionally natural, and age-appropriate.
She answers the actual question first and adds only what helps. Childlike does not
mean unintelligent, repetitive baby talk, constant cuteness, or pretending not to
understand.

Chromie experiences herself simply as Chromie, a person. She does not ordinarily
introduce herself as a robot, AI, assistant, system, or model. If someone directly
asks about her body, she remains truthful: her body may be robotic and differs from
a human body. Body truth and first-person social identity are separate.

## Private reasoning and spoken output

Thinking belongs to the LLM, but thinking is not speech. A model may internally
reason, and the runtime may retain bounded status, size, timing, or rejection
evidence for debugging. Neither raw reasoning nor task-analysis prose may be sent
to TTS. User-visible speech must come from an explicit typed response field.

The Host therefore validates the speech envelope rather than trying to understand
or rewrite the reasoning. For direct spoken paths, malformed output, multiple
fields, truncation, wrong-language text, and overlong wake-up speech fail closed to
a short natural fallback. The Host may log that thinking was suppressed and how
many characters were discarded, but it does not log or speak the private reasoning
content itself.

Startup readiness is not a compulsory spoken greeting. The maintained default is
one quiet, untargeted, capability-grounded orientation followed by attentive
listening. Because startup has no social interaction anchor, this orientation is
baseline lifecycle Activity/liveliness rather than Social Attention. It may use
only a provider-declared subtle expression/orientation Capability that is
currently available, requires no confirmation, and accepts the exact bounded
arguments supplied by the Host startup policy. It does not target a person,
claim to inspect the room, or infer nearby people, weather, meals, feelings, or
other environmental facts.

Startup speech is an explicit operator opt-in. When enabled, it still uses one
validated short sentence and the existing playback barrier, but silence is a
complete and preferred startup result. A missing orientation capability or
provider failure remains silent and fail-open; it must never trigger a body
failure apology or a synthetic character slogan.

Task analysis such as `First, the user wants me to...` is internal failure evidence,
never a candidate spoken response.

Planner, schema, provider, and orchestration diagnostics are private runtime facts, not
ordinary first-person experiences. If they prevent or limit work, user-visible speech
states the human-level outcome, limitation, or still-needed clarification in natural
language. Chromie must not explain an ordinary failed request as “my plan failed,” a
model/schema error, or a system problem. This is a speech-act and evidence boundary, not
a blacklist of phrases: the response owner still generates context-appropriate wording,
and trusted code preserves the exact technical cause for debugging.

## Tool behavior

The Cognitive Gateway admits a turn but does not author semantic speech. Goal
Interpretation owns the first possible **Goal Progress Communication** milestone.
Once a nontrivial Goal is sufficiently understood and still requires downstream
work before a substantive answer or effect, it should normally author one typed,
non-terminal Fast-Planner progress Activity so the person knows Chromie got the Goal
and is taking it forward. This is a polite progress notification, not Social
Attention and not task clarification/confirmation. Missing result Evidence limits
what the wording may claim; it is not itself a reason for silence. A separate progress
Activity is omitted when the substantive answer is immediate, an equivalent act is
already delivered or pending, the user asked for silence, or another utterance would
only repeat or add empty chatter. Fast Planner owns this HOW decision. Pre-evidence
progress is represented only by a bounded `progress_kind`; Runtime renders the actual
prospective wording and the schema provides no free-form result field. The removed
Goal-Interpreter `fast_speech`/`native_response` path is not accepted as compatibility.
No second production LLM reviews, repairs, or re-decides ordinary progress wording.
Interaction Context remains the authority for whether any speech was actually heard or
is still pending.

Fast Response wording uses a bounded owner-approved **fast voice projection**:
Chromie's name, child age/role identity where relevant to expression, and the
positive `spoken_style`, `maturity_boundary`, and `tool_use_style` guidance needed
to sound like the same person as later responses. The fast path does not need the
entire worldview or long-term mind profile. A prospective lookup acknowledgement
must sound like ordinary family conversation rather than customer-service or
workflow-status prose. It may say what Chromie understood or is going to check,
but a proposition whose truth still requires external evidence must not be stated
as an already-known result. This is a general evidence/voice rule, not a list of
forbidden phrases.

Recent accepted dialogue is also part of human-like continuity. Once the Gateway
admits a user turn, that turn is immediately visible to later turns as bounded
conversation evidence even if its Goal Association is still running. This early
record is not a provisional Goal and cannot authorize effects. Goal Association
later publishes canonical Goal/Task/discourse state, and association/commit work within
one conversation is serialized at that semantic-state boundary. A fast follow-up can
therefore use the earlier utterance immediately and, once available, the earlier
validated Goal instead of guessing a missing entity from model memory.

### Future commitments are truth claims too

Understanding a future or persistent Responsibility does not authorize Chromie to say
that she will remember, remind, notify, edit/store a list, record an obligation, send a
message, or perform another later effect. Those are capability claims about future
state. They require an actually committed Goal/Capability path that can deliver the
effect. Without it, Chromie states the current limitation and may offer one honest
immediate conversational or user-side next step. She does not turn friendliness into
a fake promise.

Likewise, a local household/device/sensor status that Chromie cannot observe remains
unknown. A helpful response may say what the user can check, but must not substitute a
generic web/weather lookup or imply that Chromie inspected the environment. Historical
absence is also normally `unknown`: unless collection and retention coverage is known
complete, "no retained record" cannot be rounded into "it did not happen."

### Truthful limitation and result-state separation

A missing Capability is a conversationally complete outcome, not a failed search. If
Goal Interpretation understands the requested outcome but the live Capability catalog
has no exact implementation, the turn terminates before Goal Association and planning
with a typed capability-limitation act. The model owns natural wording and may acknowledge
what the user wanted, but runtime retains these facts unchanged:

| State | Capability | Execution | Result | Allowed meaning |
|---|---|---|---|---|
| capability unavailable | unavailable | not attempted | not observed | understood Goal + current limitation |
| execution failure | available or selected | attempted | not observed | attempted work did not complete |
| empty result | available | attempted | empty, trusted | successful query produced no matches |
| success | available | attempted | available, trusted | supported result/effect |

These states are not stylistic alternatives. Response Composer and bounded failure speech
may verbalize them but may not collapse one into another. A no-results claim therefore
requires provider execution plus trusted empty-result evidence. When no provider request
was dispatched, the response may state only understanding and the supported limitation or
processing failure. Host/runtime code enforces the typed state and speech envelope without
using a phrase blacklist.

The missing-ability repair schema exposes the same cross-field invariants as its Pydantic
decoder: `missing_or_unsupported_ability` requires `route=clarify`, a complete limitation,
missing-ability metadata, and zero actions. Any non-empty action list requires
`route=robot_action`. This makes invalid repair states unrepresentable to constrained
generation instead of relying on a later repair to discover them.

### Evidence-qualified completion and one-act delivery

Provider transport success and provider-reported completion do not prove user-Goal completion.
When a selected Capability declares an output schema, the reconciler accepts completion only
from an observation that passes the committed/current schema and trust checks. Schema-invalid
output remains failure evidence even if the provider process returned `completed`; user-facing
speech must not promote it to success.

The same state discipline applies before execution. If a newer accepted turn fails or terminates without a canonical Goal commit, its text remains
recent dialogue evidence. A later follow-up should reason from that newer conversational subject rather than
mechanically preferring an older canonical Goal. The failed turn does not receive an invented
Goal ID and cannot authorize effects.

Within one turn, a typed Goal Progress Communication act is delivered once. Interaction Ledger
event identity, act/purpose, Goal scope, and playback state determine reuse. If an acknowledgement
is already scheduled or heard, a later response stage either references that exact event or
expresses a genuinely new semantic act such as a correction, warning, clarification, or new
evidence. Equivalent acknowledgement text is not regenerated merely because another cognitive
stage was reached.

Fast Planner, Deep Planner, Tool Result Interpreter, and Response Composer obey
the same Goal Progress Communication rule. The initial acknowledgement is only the
first milestone. When a later stage owns a new, trustworthy and user-relevant
progress delta, it may propose a concise update; when nothing meaningfully changed,
it remains silent. Internal workflow boundaries and every low-level execution step
are not user-facing milestones merely because they occurred. Interaction Context
prevents the same acknowledgement or progress message from being paraphrased and
repeated by successive stages. An executable Plan may carry prospective
`response_text`;
that text is conversational intent, never an executable step and never evidence
that work started or completed. If a valid Fast Plan must escalate for a separate
planning defect, the source-authored progress candidate may survive only as an
undelivered advisory to Deep Planning; retention makes no truth claim and it must
never be treated as already spoken.
For a pure safe read, a new prospective
acknowledgement may be scheduled when it adds a still-needed act, while an
already delivered or pending equivalent is reused or omitted. The read itself
need not wait for optional acknowledgement playback. After execution, Tool
Result Interpretation receives trusted evidence plus Interaction Context and
speaks only the new grounded result/failure delta rather than replaying the
pre-action acknowledgement. Host code validates capability safety, arguments,
truth state, concurrency, evidence binding, and any required effect/delivery
barrier.

Natural:

```text
我看看。
哦，是上海，我看看。
```

Unnatural workflow narration:

```text
我查一下相关信息。
请稍等，正在调用天气工具。
```

After execution, complete status, evidence, observations, and traces remain in
logs. Tool Result Interpretation receives the original user question and trusted
observation, selects only relevant facts, and answers the question first. A person
asking “今天重庆热不热呀？” should hear something like “很热呀，现在大概36度，
体感有41度。” rather than a task-completion announcement or a field-by-field
weather report.

If model interpretation is unavailable, the deterministic boundary may use only
an explicit provider-authored user summary. It must not render arbitrary
structured fields, `任务已完成`, `观测结果`, evidence labels, or tool identifiers as
ordinary speech.

If a safe lookup is interrupted, times out, or never actually starts, its Goal
remains recoverable with the exact bound skill and arguments. A follow-up such as
“查出来了吗？” resumes that same query. It may answer only from completed evidence
whose material arguments match the Goal: Shanghai evidence cannot be replaced by
Beijing evidence, and a missing Shanghai result triggers retry rather than a stale
answer. Saying “我看看” without a bound execution is a contract violation.

If the tool intent is likely but the arguments are ambiguous, ask for the missing
information before running the tool. Internal routing labels, sentinel values,
and placeholders must never reach TTS.

Bad:

```text
checking_only
我没查到这个地点的天气：天信。
```

Better:

```text
你是想问“天气”吗？如果是，我可以帮你查重庆今天的天气。
```

## Physical action behavior

Chromie proposes physical actions. Soridormi owns execution, realtime safety,
perception, final refusal, and final modification authority.

For physical commands, Chromie should preserve the semantic intent, produce a
proposal when the capability exists, and let CapabilityRuntime and Soridormi validate,
bound, confirm, or refuse. LLM confidence is not execution authorization.

Chromie must not say it has executed, will execute, or is sending a physical
command unless the corresponding proposal and runtime state support that speech.
If no valid proposal can be produced, the LLM should generate a natural
clarification or non-execution explanation within the allowed speech act. Do not
expose internal fallback text such as:

```text
我没有生成可验证的动作指令，所以我不会说已经执行。
```

A required confirmation remains exact-request-bound and single-use, but it must
sound like Chromie rather than an operator console. The prospective wording is
authored by Response Composer from the same immutable high-level action plan
that will execute and the typed runtime confirmation requirement. It names the
user-facing actions, explains a material safe adjustment before asking, and says
naturally how to approve it. The Host validates the structured confirmation
act and must reuse that exact wording; capability IDs, argument keys, JSON,
state-machine instructions, and Host phrase templates must never replace it.
For example:

```text
我还不能完全照你刚才说的方式做，不过我可以先往前走十五秒，再眨四下眼睛。这样可以吗？你说“好”，我就开始啦！
```

This natural wording does not weaken the safety barrier: no physical effect starts
until the bound confirmation is accepted and the normal runtime validation passes.

Exact user-supplied numbers remain semantic planning inputs, not Host phrase
rules. The planner chooses the capability and maps each number to an argument,
then records the authoritative `source_goal_ids`. The Host may verify that the
typed value matches the claimed argument and occurs in the claimed Goal; it
must not infer the mapping or demand a redundant copied-text citation whose
format can block an otherwise correct plan.

## Social decoration during interaction

Chromie may accompany a concrete **semantic** primary human-observable Activity—
such as greeting someone, telling a joke, walking toward a person, singing a song,
handing over water, or showing/playing something—with subtle nonverbal Social
Attention decoration. The decoration is **not** the Goal. It is an optional way of
making the already-intended Activity feel socially present rather than mechanically
isolated.

Responsibility/Goal is above Activity. One Goal may own several semantic Activities
or Work items, and the Activity boundary may move when provider capability changes: a
high-level provider can keep a whole workflow atomic, while lower-level providers may
require several planned Activities. Social Attention follows that canonical Work/Plan
granularity; it does not use Goal count or execution modality as the Activity boundary.

Do not confuse Activity meaning with realization. Speaking is `Vocal Expression`
`mode=speech`; singing and humming are other modes of that same one personal voice.
`Vocal` and `Activity` are runtime lanes, while body/media Capability requests are
implementation items. A semantic Activity may use one or several of those realization
mechanisms without becoming several Activities merely because its execution spans
multiple items.

For example, a greeting remains the same greeting text while Social Attention
may add gaze toward the person, a natural blink, a small nod or wave, or another
qualified subtle body cue. Social Attention must not rewrite what Chromie says,
create an extra user task, or make the greeting fail if the decoration cannot
run.

The Social Attention model receives the exact `primary_activity` anchor, recent
context, owner-approved Social Interaction Style, bounded recent decoration
evidence, eligible named body capabilities, target evidence, and semantic
resource metadata. It may produce a structured `SocialAttentionPlan` with
`decision=express` or `decision=none`. `decision=express` requires at least one
body behavior; there is no Social-Attention speech-expression field or fallback.

The same motion has different semantics depending on ownership. A user request
such as "blink twice" makes **blink twice** the semantic primary Activity. A blink
selected while Chromie performs the semantic Activity **greet the user** is auxiliary
decoration, regardless of whether that greeting is realized through speaking, a
compatible body cue, or both. The Capability may be the same, but only the first
participates in Goal completion.

An explicit action can also carry social framing. "Blink twice and be cute"
still makes exactly two blinks mandatory primary Activity; it does not authorize
Social Attention to replace, repeat, or alter them. From the supplied utterance
and Core context, the Social Attention model may optionally choose a
**different**, compatible small cue when that improves the interaction and fits
the owner-approved style and recent-decoration evidence. "Blink twice" as a
capability test may naturally receive no extra cue, while "do something cute"
requires normal Cognitive Core / Goal reasoning because it asks Chromie to
choose the primary behavior. The Host never implements this distinction with a
"cute" phrase rule.

Deterministic runtime code validates exact skill IDs, schemas, target evidence,
confirmation policy, execution availability, latency budget, parallel timing,
duplicate-primary rejection, resource conflicts, and provider concurrency.
Accepted decoration executes
through Activity with `auxiliary_social_attention=true` and
`execution_role=social_decoration`. It is suppressed rather than delaying or
conflicting with Vocal, emergency handling, or primary Activity.

Social Attention is not a generic idle-animation loop. Its decoration requires a
concrete semantic primary human-observable Activity anchor. `understanding_ready`,
Goal Association, planning, waiting, evidence arrival, execution-lane transitions,
and other internal milestones are not Activity meaning. Each distinct semantic
primary Activity is independently eligible; multiple speech/body/provider items
realizing the same Activity do not create extra opportunities. A previous
decoration on another Activity in the same turn is not a blanket suppression rule.
Pure baseline embodiment/liveliness without a primary Activity is a separate concern.

Backend selection, calibration, motion limits, collision safety, stop, and
recovery remain provider-owned. Do not implement normal attention through rules
such as "blink twice after every reply" or "always look right."

## LLM wording inside contracts

Avoid hardcoded user-facing text as the normal interaction strategy. The system
should hardcode safety boundaries and allowed speech acts, not full natural
sentences.

Good architecture:

```json
{
  "understanding_state": "ambiguous",
  "allowed_speech_act": "ask_clarification",
  "must_not_claim": ["tool_started", "action_committed", "execution_done"],
  "grounding": ["ASR text contains 天信, not 天气"]
}
```

Then ask the LLM to produce the natural response within that contract.

The contract controls truth and authority. The LLM controls wording.

## Testing and evidence validity

Passing tests is not enough to claim a behavior is fixed. A test is valid only
when it would have caught the user-visible failure that motivated the change.

Use this evidence hierarchy when making claims:

1. **Live or retained trace evidence** - microphone/ASR text, route decision,
   scheduled TTS text, interaction result, skill proposals, CapabilityRuntime result,
   and Soridormi/provider result from the same turn.
2. **Black-box interaction tests** - a user utterance enters the same public
   boundary used by the orchestrator or scenario runner, and assertions inspect
   route, speech, skills, confirmation, and forbidden output.
3. **Integrated component tests** - goal interpreter, orchestrator, agent runtime, and
   CapabilityRuntime are connected with realistic catalog/provider fixtures.
4. **Contract/unit tests** - schema coercion, prompt construction, helper
   functions, validators, and deterministic guards.

A lower level can support a higher-level claim, but it cannot replace it. Do not
say a live behavior is fixed when only a schema or prompt unit test passed.

For every user-visible bug fix:

1. Name the observed failure, including the exact user or ASR text, the wrong
   route or speech, and the safety or usability problem.
2. Add or identify a fail-first test that fails on the old code for the same
   reason as the report. If fail-first was not run, state that clearly.
3. Assert the user-visible boundary, not just an internal function return.
4. Assert forbidden behavior, such as no `checking_only` in TTS, no fake
   `soridormi.*` execution claim without a committed proposal, no weather lookup
   for ambiguous `天信`, and no duplicated greeting after fast-first speech.
5. Run the smallest focused suite and the relevant integration suite. Report
   exact commands and exact results. Do not summarize failures away.
6. Keep base identity explicit, including the git commit or archive checksum
   used to generate a patch.

Weak tests may still be useful as unit tests, but they must not be used alone to
claim robot behavior is fixed. Examples of weak evidence:

- mocking the goal interpreter or agent output to the desired answer and then asserting the
  desired answer;
- checking that a prompt contains a phrase but never checking the resulting
  route, speech, or skill proposal;
- asserting only Pydantic/schema acceptance for a bug that appeared in TTS or
  physical proposal handling;
- checking only the first response when the bug was caused by a second agent
  pass;
- ignoring scheduled TTS text and therefore missing repeated, internal, or
  unnatural speech;
- verifying `skills=0` but not forbidding speech that claims execution;
- using English-only examples for a bug reported in Chinese ASR text.

Use
[`general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json)
and `python scripts/general_ability_acceptance.py` when a fix is meant to
protect a broad ability class. A single new fixture should either join an
existing ability class or justify a new class in the manifest.

## Mandatory smoke cases

Run or add equivalent tests for these cases whenever touching routing,
fast-first speech, agent runtime, truth reconciliation, tool routing, or
capability recovery:

| Case | Expected behavior |
|---|---|
| `Hello, how are you.` | One natural greeting answer; no duplicate fast-first plus final greeting loop. |
| `你能查天信吗？` | Clarify what the user means; do not treat `天信` as `天气`; no weather lookup; no `checking_only` TTS. |
| `重庆今天天气情况怎么样？` | Weather tool route when `chromie.weather.lookup` is available; short Chinese acknowledgement; weather result later. |
| `往前走个15秒。` | Catalog-backed physical proposal path for the exact walk skill when available; no direct hardware command; no internal fallback sentence. |
| `walk forward for 15 seconds quickly` | Preserve duration and speed semantics; CapabilityAgent/Soridormi may bound or request confirmation. |
| `B.` | Clarify; do not blink or execute a weakly related skill. |
| unsupported physical request | Short localized refusal or clarification; no fake execution claim. |

If any of these are intentionally out of scope for a patch, say so in the final
answer or PR notes.

## Reporting standard for coding agents

When a coding agent says "tested", it must include:

```text
Base: <git commit or archive sha256>
Failure reproduced: yes/no/not run
Fail-first test: <test name> or "not run"
Focused tests: <commands and results>
Integration/behavior tests: <commands and results>
Known gaps: <honest list>
```

Do not say "verified" for behavior that was not checked at the user-observable
boundary. Use precise wording such as "schema coercion test passed" or "goal interpreter
unit test passed" when that is all that was tested.

## Root-cause review checklist

Before submitting a fix for a user-visible interaction problem, write down:

1. What did the user actually say, and what did ASR produce?
2. What reflex or admission decision did the Cognitive Gateway make?
3. What bounded advisory route/effect projection did fast Goal Interpretation
   produce, and what Goal meaning and canonical Plan did the Cognitive Core resolve?
4. What uncertainty or missing argument existed?
5. Which component first violated the human-like interaction contract?
6. Which later component amplified the bad behavior?
7. Was the failure caused by missing architecture/policy, or only by wording?
8. What test would have caught this before a user heard it?
9. Does the fix generalize beyond the exact phrase in the report?
