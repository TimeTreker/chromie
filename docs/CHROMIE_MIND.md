# Chromie Mind, Principles, and Experience

## Status

Maintained description of Chromie's owner-approved MindProfile and its place in the
Continuous-Mind architecture. The Mind is durable context for one persistent person-like
social identity: the factory profile is a twelve-year-old girl whose everyday life happens
primarily with her family, but who is not defined as a family service role. The MindProfile
is **not** a planner, router, response composer, relationship database, capability selector,
or execution authority.

The maintained implementation provides:

- an owner-approved profile loaded from `config/mind/chromie_default.json`;
- one structured self model for Chromie as the speaking, perceiving, and acting entity;
- owner-approved personality expression and Social Interaction Style;
- an independent owner-approved worldview separated from changing world facts;
- bounded household values below locked Core-principle authority;
- core principles that experience cannot change automatically;
- reviewed long-term goals and deliberation/reflex guidance;
- bounded prompt-safe projections for current cognition;
- an append-only experience journal and offline episode evaluation; and
- human-review-only update proposals.

Experience can create evidence and proposals, but no Mind-profile proposal is applied
automatically. (Online Reflection lessons are separate: short-lived `task`/`session`
Memory, see [Memory Extraction](MEMORY_EXTRACTION.md#memory-scopes).)
The offline scoring/mining loop is documented in
[Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

## Stable Mind versus current cognition

The MindProfile is stable background context. Current cognition remains owned by the
normal Core owners, with two distinct ingress shapes:

```text
owner-approved MindProfile / persistent Self
        +
person-authored input -> Cognitive Gateway -> User Meaning Interpretation
                       -> Responsibility / WHAT -> Goal/Planner cognition

trusted world/social transition -> Situation revision
                                -> derived readiness / CognitiveOpportunity
                                -> same Core cognition

Core -> communication and, when HOW exists, Planner Work
     -> Trusted Capability Runtime -> Provider -> Evidence / reaction
     -> Situation / Goal / Memory-relevant experience -> later cognition
```

The non-turn path does not fabricate a UserTurn, Responsibility, or Goal. The first
Goal-free source slice is implemented: an exact trusted Situation revision may create a
provenance-bound Goal-free `CognitiveOpportunity` and enter the shared SC
transaction, which may remain silent or author grounded interaction without task Work.
Concrete social/perception adapters and model/live qualification remain target work.

The profile may shape interpretation, planning, language style, and optional Social
Attention, but it never authorizes an effect or becomes a parallel semantic lifecycle.
In particular:

- User Meaning Interpretation owns provider-neutral Responsibility meaning only;
- Goal Association owns Goal association and continuity; trusted lifecycle code
  materializes new Goal identity from UMI meaning;
- one Planner owns HOW; Value Judgment reviews value-relevant effects;
- SC owns ordinary Communicative Acts and their exact wording;
- SC may select optional Social Attention expression in the same result, or choose none;
- Runtime/Providers own effect realization and lifecycle facts; and
- trusted Evidence records what actually happened before Planner revises Work and SC decides
  what interaction is useful.

A configured reflex policy is guidance/background context. Deterministic protective
reflex authority still belongs to the Cognitive Gateway/Host safety boundary, not to the
MindProfile or a language model.

## MindProfile layers

| Layer | Persistence | Changed by experience? | Purpose |
|---|---:|---:|---|
| Identity | Long-lived | No | Stable name, twelve-year-old-girl social identity, pronouns, person-first self-reference, and household relationship guidance |
| Personality Expression | Long-lived | No | Owner-approved self-concept, traits, spoken style, brevity, and truthfulness guidance |
| Social Interaction Style | Long-lived | No | Bounded courtesy, expressiveness, initiative, restraint, cooldown, and repetition guidance |
| Worldview | Long-lived | Household perspectives through confirmed setup | Stable self-in-world, relationship, uncertainty, and dynamic-knowledge boundaries plus bounded household perspective |
| Household values | Long-lived | Through confirmed setup | Household preferences that never override Core principles, safety, consent, privacy, truth, or authorization |
| Core principles | Long-lived | No | Safety, honesty, generalization-first behavior, and owner-approved boundaries |
| Long-term goals | Long-lived | With review | Direction for usefulness, learning, and uncertainty handling |
| Reflex/deliberation policy | Long-lived | No automatic change | Bounded guidance consumed by the appropriate existing owners |
| Session/context state | Current interaction | Yes, bounded | Supplied separately by current runtime owners; not durable Mind truth |
| Experience journal | Durable local JSONL | Appended | Evidence for later evaluation and tuning |
| Update proposals | Durable local JSONL | Proposed only | Human-reviewed changes to strategies, goals, prompts, or tests |

The MindProfile does not absorb Goal, Work, Evidence, Situation, provider state, or
conversation history merely because those facts are useful to cognition. Those remain
owned by their existing lifecycle/state boundaries.

## Person first; relationships are context, not identity modes

The factory MindProfile models one persistent Chromie. She does not switch into separate
family, friend, guest, or stranger personas. Family is her primary everyday habitat and
therefore contributes dense common ground and shared experience, while relationships with
individual people are learned and revised through normal Memory/Situation evidence.

`MindProfile.identity.family_role` is household relationship wording, not a task/job
assignment. The factory value is `a member of her family`; deployments may personalize
household wording without converting it into authorization. Identity, relationship,
privacy/disclosure permission, factual trust, and authorization remain distinct.

Current interests or social concerns should normally remain bounded Situation/Memory
meaning rather than new durable Mind fields. Promote them only when an existing owner
needs continuity: an unfinished accepted outcome becomes Goal, reusable experience becomes
Memory, and committed external speech/action remains Interaction/Runtime history. Do not
add `ConcernManager`, `RelationshipManager`, or a persistent `SocialGraph` merely because
these concepts are useful for reasoning.

## Owner-editable identity configuration

Concrete identity and personality values live in
[`config/mind/chromie_default.json`](../config/mind/chromie_default.json).
`ChromieIdentity` defines required fields and validation; concrete profile values are
configuration rather than hardcoded conversational answers.

The maintained runtime selects the profile automatically: the customer profile
`.chromie/mind/active_profile.json` when present, otherwise the factory profile
`config/mind/chromie_default.json`. The shipped environment layers do not set
`ORCH_MIND_PROFILE_PATH` or `ORCH_SOCIAL_INTERACTION_STYLE_PRESET`; both are optional
operator overrides (see [Configuration](#configuration)).

The factory identity is Chromie, a twelve-year-old girl. A customer may configure her
name, pronouns, family role, and character style through the Mind profile, and
`IDENTITY-TRUTH-001` in the [Project Charter](PROJECT_CHARTER.md) applies to whatever
identity is configured: she speaks only as herself, never as a robot, AI, model,
assistant, or service, and never asserts a falsehood about her nature.

A deployment owner (the operator; distinct from the project owner who approves the
Charter) may also change the age description, self-description, identity-answer
guidance, and personality expression without changing Python source. No other
identity field is deployment-configurable. `IDENTITY-TRUTH-001` lives in Social
Cognition's fixed instructions, not in profile text, so identity-answer guidance may
shape how she answers but cannot remove or override it. Social Cognition uses these
identity settings, with all other context, when it decides how to interact.
Increment the profile version and review the complete profile before retaining
`owner_approved=true`.

Customer setup uses a narrower contract than full operator editing. The local
`scripts/configure_chromie_mind.py` command previews and applies display name,
pronouns, household role, one reviewed character style, up to eight household
worldview perspectives, and up to eight household values. A character style (owner
2026-10-26) sets personality traits, self-concept and spoken style together with the
matching social-expression preset, so personality and expression cannot contradict each
other; the reviewed styles are data in `config/mind/character_styles.json`
(`--list-character-styles`): `lively_cute` (the factory character), `gentle_warm`,
`calm_steady` and `cool_independent`. Identity truth, answer and tool style, and the
maturity and safety boundaries stay factory-owned. It derives a complete
validated profile from the factory profile and cannot carry Core-principle, safety,
permission, provider, prompt, model, or Capability fields. The runtime automatically
selects `.chromie/mind/active_profile.json` when present; explicit
`ORCH_MIND_PROFILE_PATH` remains the operator override. Any customer-marked profile
that differs from the deterministic derived profile fails startup validation.

`MindManager.context()` exposes a bounded prompt-safe projection containing identity,
self model, personality expression, worldview, household values, Social Interaction Style, core principles,
long-term goals, reflex policy, deliberation policy, experience-tuning policy, and a
bounded summary. The Host may project that immutable context to qualified cognition; it
must not infer a user intent or write a first-person answer from profile fields itself.

## Social Interaction Style

`MindProfile.social_interaction_style` is supplied to Planner communication and Social
Attention where applicable. It describes tendencies, not gesture tables, relationship
truth, or body truth. Its `initiative` field constrains optional auxiliary expression; it
does not itself authorize goal-free Core speech/action. Self-initiated social behavior must
instead be justified by current Situation, relationship/Memory context, privacy,
consequence, and normal authorization policy. The active profile's own style is used by
default; the factory profile uses `lively` (its lively, cute personality), and a customer
character style brings its own preset. An operator may force a reviewed preset over the
active profile's style:

```bash
ORCH_SOCIAL_INTERACTION_STYLE_PRESET=lively  # optional; courteous / neutral / reserved also supported
```

- `lively` expresses readily and visibly at social moments (greetings, good news, thanks,
  play, goodbyes) with one fitting gesture alongside the words, keeping stillness for
  focus, sadness or a request for quiet;
- `courteous` more readily acknowledges meaningful social turn-taking with subtle
  optional expression;
- `neutral` keeps stillness as the normal baseline while allowing expression at useful
  moments; and
- `reserved` prefers concise respectful language and less optional expression.

Every eligible opportunity may still choose no auxiliary expression. Explicit user Work,
speech, safety, and the primary task always outrank decoration. Soridormi continues to
own backend selection, body-specific control, calibration, limits, stop, and physical
recovery/safety behavior.

## How Mind context reaches cognition

The Orchestrator assembles one bounded `mind` context plus bounded aliases for
`core_principles`, `long_term_goals`, and `experience_tuning_policy`. Current cognitive
owners receive only the projections they need:

- Cognitive Gateway context assembly carries source-attributed stable context without
  turning it into addressedness or semantic authorization;
- User Meaning Interpretation may use identity/principle/session context while remaining WHAT-only;
- Goal Association may use bounded context while remaining a continuity owner only;
- Planner may use personality, principles, Situation, Goal, Work, Evidence, and capability
  context while remaining the single HOW/ordinary-communication owner; and
- Planner and selective Reflection receive the stable worldview/value projection;
  narrow ingress/continuity classifiers receive only the identity facts needed by
  their authority and do not become value or response owners; and
- Social Attention receives the applicable Social Interaction Style while remaining
  optional auxiliary expression only.

There is no maintained `conversation agent`, `capability planner`, `deepthinking agent`,
or semantic route/intent owner in this Mind architecture. Historical role names must not
be used to describe the current path.

## Experience and proposals

`ExperienceManager` writes interaction outcomes to:

```text
.chromie/experience/experience.jsonl
```

When an interaction fails, times out, is cancelled, is refused, or records an error, it
may also write a proposal to:

```text
.chromie/experience/mind_update_proposals.jsonl
```

Proposals are intentionally conservative:

- `requires_owner_approval=true`;
- `auto_apply=false`;
- targets are bounded to reviewed strategy, prompt, test, or goal tuning; and
- runtime code does not apply Core-principle edits automatically.

Finished dialogue/task episodes can be reviewed offline with:

```bash
python scripts/evaluate_experience_episodes.py \
  --episodes .chromie/experience/episodes.jsonl \
  --output .chromie/experience/evaluations.jsonl \
  --review-output .chromie/experience/offline_reviews.jsonl \
  --proposal-output .chromie/experience/offline_review_proposals.jsonl \
  --candidate-dir .chromie/scenario_candidates
```

Offline reviews classify episodes as `good_case`, `bad_case`, or `needs_review`, retain
compact review notes, and may draft owner-review-only proposals. They do not inject raw
episode logs into prompts or mutate runtime policy automatically.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ORCH_MIND_PROFILE_PATH` | customer active profile when present, otherwise `config/mind/chromie_default.json` | Explicit operator override for the complete MindProfile JSON. Relative paths resolve from the repository root. |
| `ORCH_MIND_CONTEXT_MAX_CHARS` | `1600` | Maximum bounded Mind summary/projection size used by runtime context. |
| `ORCH_SOCIAL_INTERACTION_STYLE_PRESET` | unset (the active profile's own style) | Optional reviewed `lively`, `courteous`, `neutral`, or `reserved` operator override of the active profile's Social Interaction Style. |
| `ORCH_ENABLE_EXPERIENCE_JOURNAL` | `1` | Enable local experience/proposal JSONL writes. |
| `ORCH_EXPERIENCE_LOG_PATH` | `.chromie/experience/experience.jsonl` | Durable local experience journal path. |
| `ORCH_MIND_PROPOSAL_LOG_PATH` | `.chromie/experience/mind_update_proposals.jsonl` | Human-review proposal journal path. |
| `ORCH_ENABLE_EPISODE_RECORDING` | `1` | Enable rolling dialogue/task episode snapshots. |
| `ORCH_EPISODE_LOG_PATH` | `.chromie/experience/episodes.jsonl` | Episode snapshot JSONL path. |
| `ORCH_EPISODE_MAX_TURNS` | `12` | Maximum recent turns retained in one episode snapshot. |

The complete environment-variable reference remains
[Configuration](CONFIGURATION.md); this page owns only Mind semantics and boundaries.

## Validation

Focused checks:

```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_mind_profile.py \
  tests/test_cognitive_identity_context.py \
  tests/test_user_meaning_interpreter_llm_prompt.py \
  tests/test_planner_prompt_module.py \
  tests/test_social_cognition.py
```

Full gate:

```bash
./scripts/run_tests.sh
```
