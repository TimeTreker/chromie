# Chromie Mind, Principles, and Experience

## Status

Implemented as a structured context layer in the Orchestrator and shared
contracts. The first version provides:

- an owner-approved default mind profile loaded from `config/mind/chromie_default.json`;
- an owner-approved structured self model for Chromie as the speaking, perceiving, acting person;
- an owner-approved Personality Expression for self-concept, age-appropriate speech, answer brevity, tool-use wording, and the boundary between internal logs and ordinary conversation;
- an owner-approved Social Interaction Style for bounded courtesy,
  expressiveness, initiative, restraint, cooldown, and repetition guidance;
- core principles that cannot be changed by experience;
- long-term goals that can be tuned by reviewed experience;
- prompt-safe context for Goal Interpretation, conversation, and deepthinking;
- an append-only experience journal;
- human-review-only update proposals;
- offline good/bad/needs-review episode reviews for scenario and strategy
  refinement.

This is not autonomous self-modification. Experience can create proposals, but
no proposal is applied automatically.
The planned loop for scoring finished dialogue/task episodes and mining
low-scoring episodes into reviewed scenario candidates is documented in
[Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

## Layer Model

Chromie's brain context has these layers:

| Layer | Persistence | Changed by experience? | Purpose |
|---|---:|---:|---|
| Identity | Long-lived | No | Stable name, six-year-old girl identity, gender/pronouns, and age/persona wording |
| Social Interaction Style | Long-lived | No | Owner-approved bounded social expression and repetition restraint |
| Core principles | Long-lived | No | Safety, honesty, generalization-first behavior, owner-approved boundaries |
| Long-term goals | Long-lived | With review | Direction for usefulness, learning, and uncertainty handling |
| Session memory | Current conversation | Yes, bounded | Current task, recent turns, pending work |
| Reflex policy | Always available | No automatic change | Fast emergency stop, cancel, and safety behavior |
| Experience journal | Durable local JSONL | Appended | Evidence for future tuning and tests |
| Update proposals | Durable local JSONL | Proposed only | Human-reviewed changes to strategies, goals, prompts, or tests |


## Owner-editable identity configuration

Concrete Chromie identity and personality values live in [`config/mind/chromie_default.json`](../config/mind/chromie_default.json). `ChromieIdentity` in Python defines only required fields and validation; it does not supply a name, age, or self-description. The maintained runtime selects the JSON through:

```bash
ORCH_MIND_PROFILE_PATH=config/mind/chromie_default.json
```

An owner may change the configured name, age, pronouns, self-description, identity-answer guidance, or personality expression without changing code. Increment the profile version and review the complete profile before retaining `owner_approved=true`. Fast progress speech is part of that personality expression: it should sound like Chromie talking naturally to a person, not like a status monitor narrating task, processing, execution, or workflow state.

The Orchestrator turns the loaded profile into one bounded owner-approved
identity snapshot. Goal Interpretation, Goal Association, Fast Planner, Deep
Planner, Social Attention, conversation, and direct fallback prompts receive
the applicable bounded projection. Models still infer whether a user is asking
about identity and choose natural wording; the Host does not detect name or age
questions with keywords or return a fixed answer.

## Social Interaction Style configuration

`MindProfile.social_interaction_style` is implemented and supplied to Planner
communication and Social Attention on every eligible turn. It carries owner-approved courtesy,
expressiveness, initiative, restraint, cooldown, and repetition guidance. These
fields describe personality and interaction style; they never describe whether
the attached body is simulated or physical.

Ordinary deployments can select a reviewed preset without authoring a complete
mind profile:

```bash
ORCH_SOCIAL_INTERACTION_STYLE_PRESET=courteous  # or neutral / reserved
```

- `courteous` more readily acknowledges greetings, thanks, apologies, and
  meaningful turn-taking with subtle optional expression;
- `neutral` uses expression at important moments while keeping stillness as the
  normal baseline;
- `reserved` normally prefers stillness and concise respectful language.

Presets remain semantic tendencies, not gesture tables. Every turn may still
choose `none`, and emergency handling, explicit actions, speech, and the primary
task always have higher priority. For a reviewed custom style, provide a JSON
profile through `ORCH_MIND_PROFILE_PATH` and set
`social_interaction_style.preset` to `custom` together with all six guidance
fields.

Soridormi continues to own backend selection, body-specific control,
calibration, limits, stop, and recovery.

## Prompt Context Groups

Prompt-facing robot planning is organized into context groups. This is the
preferred shape for Goal Interpreter, capability-planning, conversation, and deepthinking
prompts when they need Chromie identity, personality, principles, session state, abilities, and
a strict output contract in one prompt.

The group order is intentional:

```text
Global Context Group
Session Context Group
Current Job
Task Context Group
Cost Function
Output Contract
```

`Target` is not the first section. The model should first receive the robot's
identity and upper principles, then the current session state, then the specific
job it is performing. Turn-specific targets belong inside `Current Job` and
`Task Context Group`.

`Global Context Group` tells the model who Chromie is and what upper principles
she obeys. It includes Chromie Identity, Worldview, Lifeview, Valueview, core
principles, Social Interaction Style, reflex policy, deliberation policy, and experience boundaries.
Identity, age/persona wording, and core principles come from the owner-approved
mind profile.

`Session Context Group` contains bounded current-turn context: extracted
user/session memory, current task context, robot/runtime state, and other
evidence supplied by the Orchestrator. This context helps interpretation, but
it is not authorization. Raw recent conversation may be retained as evidence or
used as a tiny fallback for immediate reference resolution; the preferred
prompt path is the compact extracted-memory design in
[`MEMORY_EXTRACTION.md`](MEMORY_EXTRACTION.md).

`Current Job` states which role the model is performing now, such as quick
goal interpreter, capability planner, conversation agent, or deepthinking agent. It tells
the model to use the upper contexts as background and solve only the current
role's responsibility.

`Task Context Group` contains the latest user input, available abilities,
candidate capability schemas, selected route/capability hints, constraints, and
other turn-local facts. Ability descriptions and schemas are used for semantic
generalization; they are not phrase tables.

`Cost Function` states the local preference order, such as safe before
obedient, honest before pleasing, small and reversible before broad, resolve required
execution inputs from trusted context/observation or permitted defaults before asking a
specific user-resolvable clarification, and use deeper cognition only at the stage whose
meaning or planning genuinely requires it.

`Output Contract` defines the exact JSON/schema or response template. The model
may propose routes, speech, task metadata, or skill plans only through this
contract. Validators, confirmation gates, Trusted Capability Runtime authorization, and
Soridormi provider checks remain separate runtime authority.

## Runtime Flow

The Orchestrator builds a context object for every routed turn. It now includes:

- `mind`: bounded profile summary and structured policy fields;
- `mind.identity`: stable owner-approved descriptive fields;
- `mind.social_interaction_style`: owner-approved courtesy, expression,
  initiative, restraint, cooldown, and repetition guidance supplied to Planner
  communication and Social Attention together with bounded recent auxiliary-request evidence;
- `mind.self_model`: structured speaker, perceiver, actor, body owner, internal
  components, and capability-evidence source used by Goal Interpreter, conversation,
  deepthinking, and direct-fallback prompts;
- `core_principles`: short alias for prompt and inspection code;
- `long_term_goals`: short alias for prompt and inspection code;
- `experience_tuning_policy`: explicit learning boundary.

The fast Goal Interpreter receives this context and may use it to classify intent, but
it cannot treat principles as authorization. Emergency filtering, capability
constraints, confirmation, Trusted Capability Runtime validation, and Soridormi provider
checks remain code-enforced.

The fast Goal Interpreter and native capability planner use the prompt context group
shape above. The conversation and deepthinking agents include the mind context
in their LLM prompts. Deepthinking should use it as the upper constraint when
planning, debugging, or splitting complex tasks.

## Experience And Proposals

`ExperienceManager` writes interaction outcomes to:

```text
.chromie/experience/experience.jsonl
```

When an interaction fails, times out, is cancelled, is refused, or records an
error, it can also write a proposal to:

```text
.chromie/experience/mind_update_proposals.jsonl
```

Proposals are intentionally conservative:

- `requires_owner_approval=true`;
- `auto_apply=false`;
- target defaults to strategy, prompt, test, or goal tuning;
- core principle edits are not applied by runtime code.

This gives Chromie memory of what happened and a path to improve, while keeping
the robot's spine under human ownership.

Finished dialogue/task episodes can also be reviewed offline with:

```bash
python scripts/evaluate_experience_episodes.py \
  --episodes .chromie/experience/episodes.jsonl \
  --output .chromie/experience/evaluations.jsonl \
  --review-output .chromie/experience/offline_reviews.jsonl \
  --proposal-output .chromie/experience/offline_review_proposals.jsonl \
  --candidate-dir .chromie/scenario_candidates
```

The offline review records classify each episode as `good_case`, `bad_case`,
or `needs_review`, preserve compact reviewed memory notes, and can draft
owner-review-only proposals. They do not inject raw episode logs into prompts
or apply any update automatically.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ORCH_MIND_PROFILE_PATH` | `config/mind/chromie_default.json` | Owner-editable concrete identity and complete MindProfile JSON. Relative paths resolve from the repo root. |
| `ORCH_MIND_CONTEXT_MAX_CHARS` | `1600` | Maximum prompt-summary size attached to routed context. |
| `ORCH_ENABLE_EXPERIENCE_JOURNAL` | `1` | Enable local experience/proposal JSONL writes. |
| `ORCH_EXPERIENCE_LOG_PATH` | `.chromie/experience/experience.jsonl` | Durable local experience journal path. |
| `ORCH_MIND_PROPOSAL_LOG_PATH` | `.chromie/experience/mind_update_proposals.jsonl` | Human-review proposal journal path. |
| `ORCH_ENABLE_EPISODE_RECORDING` | `1` | Enable rolling dialogue/task episode snapshots. |
| `ORCH_EPISODE_LOG_PATH` | `.chromie/experience/episodes.jsonl` | Episode snapshot JSONL path. |
| `ORCH_EPISODE_MAX_TURNS` | `12` | Maximum recent turns retained in one episode snapshot. |

## Validation

Focused checks:

```bash
PYTHONPATH=. python -m pytest -q tests/test_mind_profile.py tests/test_cognitive_identity_context.py
PYTHONPATH=. python -m pytest -q tests/test_goal_interpreter_llm_prompt.py tests/test_conversation_agent_prompt.py tests/test_deepthinking_agent.py
```

Full gate:

```bash
./scripts/run_tests.sh
```
