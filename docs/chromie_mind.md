# Chromie Mind, Principles, and Experience

## Status

Maintained description of Chromie's owner-approved MindProfile and its place in the
current Goal-driven architecture. The Mind is durable context for one person-like
identity; it is **not** a planner, router, response composer, capability selector, or
execution authority.

The maintained implementation provides:

- an owner-approved profile loaded from `config/mind/chromie_default.json`;
- one structured self model for Chromie as the speaking, perceiving, and acting entity;
- owner-approved personality expression and Social Interaction Style;
- core principles that experience cannot change automatically;
- reviewed long-term goals and deliberation/reflex guidance;
- bounded prompt-safe projections for current cognition;
- an append-only experience journal and offline episode evaluation; and
- human-review-only update proposals.

Experience can create evidence and proposals, but no proposal is applied automatically.
The offline scoring/mining loop is documented in
[Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

## Stable Mind versus current cognition

The MindProfile is stable background context. Current cognition remains owned by the
normal Goal-driven loop:

```text
owner-approved MindProfile
        +
Person / World -> Perception -> Cognitive Gateway
                               -> Goal Interpretation -> Responsibility / WHAT
                               -> Goal Association -> canonical Goal continuity
                               -> Planner fast/deep -> HOW / Work / communication
                               -> Trusted Capability Runtime -> Provider -> Evidence
                               -> Situation / Goal / Work update -> Planner re-entry
```

The profile may shape interpretation, planning, language style, and optional Social
Attention, but it never authorizes an effect or becomes a parallel semantic lifecycle.
In particular:

- Goal Interpretation owns provider-neutral Responsibility meaning only;
- Goal Association owns canonical Goal identity and continuity;
- Fast and Deep are cognition depths/passes of the same Planner HOW authority;
- Planner owns ordinary Communicative Activities and their exact wording;
- Social Attention may author only optional auxiliary expression and may choose none;
- Runtime/Providers own effect realization and lifecycle facts; and
- trusted Evidence records what actually happened before Planner interprets what it means
  for the person.

A configured reflex policy is guidance/background context. Deterministic protective
reflex authority still belongs to the Cognitive Gateway/Host safety boundary, not to the
MindProfile or a language model.

## MindProfile layers

| Layer | Persistence | Changed by experience? | Purpose |
|---|---:|---:|---|
| Identity | Long-lived | No | Stable name, six-year-old-girl social identity, pronouns, family role, and self-reference guidance |
| Personality Expression | Long-lived | No | Owner-approved self-concept, traits, spoken style, brevity, and truthfulness guidance |
| Social Interaction Style | Long-lived | No | Bounded courtesy, expressiveness, initiative, restraint, cooldown, and repetition guidance |
| Core principles | Long-lived | No | Safety, honesty, generalization-first behavior, and owner-approved boundaries |
| Long-term goals | Long-lived | With review | Direction for usefulness, learning, and uncertainty handling |
| Reflex/deliberation policy | Long-lived | No automatic change | Bounded guidance consumed by the appropriate existing owners |
| Session/context state | Current interaction | Yes, bounded | Supplied separately by current runtime owners; not durable Mind truth |
| Experience journal | Durable local JSONL | Appended | Evidence for later evaluation and tuning |
| Update proposals | Durable local JSONL | Proposed only | Human-reviewed changes to strategies, goals, prompts, or tests |

The MindProfile does not absorb Goal, Work, Evidence, Situation, provider state, or
conversation history merely because those facts are useful to cognition. Those remain
owned by their existing lifecycle/state boundaries.

## Owner-editable identity configuration

Concrete identity and personality values live in
[`config/mind/chromie_default.json`](../config/mind/chromie_default.json).
`ChromieIdentity` defines required fields and validation; concrete profile values are
configuration rather than hardcoded conversational answers.

The maintained runtime selects the profile with:

```bash
ORCH_MIND_PROFILE_PATH=config/mind/chromie_default.json
```

An owner may change the configured name, age, pronouns, self-description,
identity-answer guidance, or personality expression without changing Python source.
Increment the profile version and review the complete profile before retaining
`owner_approved=true`.

`MindManager.context()` exposes a bounded prompt-safe projection containing identity,
self model, personality expression, Social Interaction Style, core principles,
long-term goals, reflex policy, deliberation policy, experience-tuning policy, and a
bounded summary. The Host may project that immutable context to qualified cognition; it
must not infer a user intent or write a first-person answer from profile fields itself.

## Social Interaction Style

`MindProfile.social_interaction_style` is supplied to Planner communication and Social
Attention where applicable. It describes tendencies, not gesture tables and not body
truth. Ordinary deployments may select a reviewed preset:

```bash
ORCH_SOCIAL_INTERACTION_STYLE_PRESET=courteous  # neutral / reserved also supported
```

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
- Goal Interpretation may use identity/principle/session context while remaining WHAT-only;
- Goal Association may use bounded context while remaining a continuity owner only;
- Planner may use personality, principles, Situation, Goal, Work, Evidence, and capability
  context while remaining the single HOW/ordinary-communication owner; and
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
| `ORCH_MIND_PROFILE_PATH` | `config/mind/chromie_default.json` | Owner-editable concrete identity and complete MindProfile JSON. Relative paths resolve from the repository root. |
| `ORCH_MIND_CONTEXT_MAX_CHARS` | `1600` | Maximum bounded Mind summary/projection size used by runtime context. |
| `ORCH_SOCIAL_INTERACTION_STYLE_PRESET` | unset | Optional reviewed `courteous`, `neutral`, or `reserved` Social Interaction Style override. |
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
  tests/test_goal_interpreter_llm_prompt.py \
  tests/test_planner_prompt_module.py \
  tests/test_social_attention_current.py
```

Full gate:

```bash
./scripts/run_tests.sh
```
