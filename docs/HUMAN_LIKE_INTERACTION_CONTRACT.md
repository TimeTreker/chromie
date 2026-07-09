# Human-Like Interaction Contract

This document is mandatory guidance for humans and coding agents changing
Chromie's ASR, router, orchestrator, agent, tool, skill, speech, safety, or test
behavior.

Chromie should behave like a careful, natural robot companion. It must know the
difference between what it heard, what it understood, what it can do, what it
has committed to do, and what it should say next.

## Core rule

A user-visible symptom is not the root cause.

When a behavior sounds stupid, repetitive, overconfident, unsafe, or unnatural,
do not patch only the exact sentence that exposed the problem. First identify
which interaction contract was violated:

- Did ASR provide an uncertain hypothesis that was treated as truth?
- Did the router substitute a nearby capability for unclear user meaning?
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
  requests, while keeping physical TaskGraph and Skill Runtime execution
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
- **Router/intent** - the route, intent, confidence, or affordance grounding is
  wrong.
- **Agent contract** - the model is allowed to invent speech acts, tool results,
  skill proposals, or physical execution claims.
- **Prompt wording** - the state and authority are correct, but the generated
  wording is poor.
- **Orchestrator policy** - fast-first/final response, conversation state,
  confirmation, cancellation, timeout, or TTS scheduling is inconsistent.
- **Skill Runtime/provider** - authorization, preflight, execution result,
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
Earliest wrong component: <ASR/router/agent/orchestrator/runtime/provider/test>
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
- A downstream agent can reinterpret a router clarification or refusal as an
  action.
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

For one simple conversational act, one natural response is usually enough. If
fast-first already answered a simple greeting or clarification, the final agent
must not answer the same act again.

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

## Router and affordance grounding

The router proposes interpretations. It is not final semantic authority.

The router should use the live tool and skill catalog as affordance grounding,
not phrase tables. However, catalog presence does not justify weak substitution.
A capability may be selected only when the user intent and required arguments
are sufficiently supported.

If no matching capability exists, Chromie should say what is missing or ask a
clarifying question. It should not substitute a vaguely related skill or tool.

## Tool behavior

Chromie may say it is checking something only when a real tool call will be made
with validated arguments.

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
proposal when the capability exists, and let SkillRuntime and Soridormi validate,
bound, confirm, or refuse. LLM confidence is not execution authorization.

Chromie must not say it has executed, will execute, or is sending a physical
command unless the corresponding proposal and runtime state support that speech.
If no valid proposal can be produced, the LLM should generate a natural
clarification or non-execution explanation within the allowed speech act. Do not
expose internal fallback text such as:

```text
我没有生成可验证的动作指令，所以我不会说已经执行。
```

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
   scheduled TTS text, interaction result, skill proposals, SkillRuntime result,
   and Soridormi/provider result from the same turn.
2. **Black-box interaction tests** - a user utterance enters the same public
   boundary used by the orchestrator or scenario runner, and assertions inspect
   route, speech, skills, confirmation, and forbidden output.
3. **Integrated component tests** - router, orchestrator, agent runtime, and
   SkillRuntime are connected with realistic catalog/provider fixtures.
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

- mocking the router or agent output to the desired answer and then asserting the
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
boundary. Use precise wording such as "schema coercion test passed" or "router
unit test passed" when that is all that was tested.

## Root-cause review checklist

Before submitting a fix for a user-visible interaction problem, write down:

1. What did the user actually say, and what did ASR produce?
2. What meaning did the router propose?
3. What uncertainty or missing argument existed?
4. Which component first violated the human-like interaction contract?
5. Which later component amplified the bad behavior?
6. Was the failure caused by missing architecture/policy, or only by wording?
7. What test would have caught this before a user heard it?
8. Does the fix generalize beyond the exact phrase in the report?
