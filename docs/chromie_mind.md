# Chromie Mind, Principles, and Experience

## Status

Implemented as a structured context layer in the Orchestrator and shared
contracts. The first version provides:

- an owner-approved default mind profile;
- an owner-approved identity for self-description questions;
- core principles that cannot be changed by experience;
- long-term goals that can be tuned by reviewed experience;
- prompt-safe context for Router, conversation, and deepthinking;
- an append-only experience journal;
- human-review-only update proposals.

This is not autonomous self-modification. Experience can create proposals, but
no proposal is applied automatically.
The planned loop for scoring finished dialogue/task episodes and mining
low-scoring episodes into reviewed scenario candidates is documented in
[Experience Evaluation and Scenario Mining](EXPERIENCE_EVALUATION_AND_SCENARIO_MINING.md).

## Layer Model

Chromie's brain context has these layers:

| Layer | Persistence | Changed by experience? | Purpose |
|---|---:|---:|---|
| Identity | Long-lived | No | Stable name, robot nature, gender/pronouns, and age/persona wording |
| Core principles | Long-lived | No | Safety, honesty, generalization-first behavior, owner-approved boundaries |
| Long-term goals | Long-lived | With review | Direction for usefulness, learning, and uncertainty handling |
| Session memory | Current conversation | Yes, bounded | Current task, recent turns, pending work |
| Reflex policy | Always available | No automatic change | Fast emergency stop, cancel, and safety behavior |
| Experience journal | Durable local JSONL | Appended | Evidence for future tuning and tests |
| Update proposals | Durable local JSONL | Proposed only | Human-reviewed changes to strategies, goals, prompts, or tests |

The current default profile lives in
[`shared/chromie_contracts/mind.py`](../shared/chromie_contracts/mind.py).
Operators can provide a JSON replacement with `ORCH_MIND_PROFILE_PATH`, but the
schema rejects core principles that are marked experience-mutable or do not
require owner approval. The default identity names the robot Chromie, describes
her as a female AI robot with she/her pronouns, and gives her a 6-year-old
robot identity age while preserving the boundary that this is not a human
biological age. Her base self-description is that she keeps people company and
can do simple things to help them. When answering identity questions, Chromie
must describe herself as the robot, not as the backend LLM or model provider.
The default core principles also make generalization ability explicit: normal
robot behavior should be driven by LLM meaning-understanding, bounded context,
capability descriptions, schemas, and task memory rather than brittle phrase
rules. Phrase and pattern rules remain reserved for the fast deterministic
emergency/noise filter.

## Prompt Context Groups

Prompt-facing robot planning is organized into context groups. This is the
preferred shape for Router, capability-planning, conversation, and deepthinking
prompts when they need robot identity, principles, session state, abilities, and
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
she obeys. It includes Robot Identity, Worldview, Lifeview, Valueview, core
principles, reflex policy, deliberation policy, and experience boundaries.
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
router, capability planner, conversation agent, or deepthinking agent. It tells
the model to use the upper contexts as background and solve only the current
role's responsibility.

`Task Context Group` contains the latest user input, available abilities,
candidate capability schemas, selected route/capability hints, constraints, and
other turn-local facts. Ability descriptions and schemas are used for semantic
generalization; they are not phrase tables.

`Cost Function` states the local preference order, such as safe before
obedient, honest before pleasing, small and reversible before broad, clarify
when required parameters are missing, and use deep thought when quick routing is
too uncertain.

`Output Contract` defines the exact JSON/schema or response template. The model
may propose routes, speech, task metadata, or skill plans only through this
contract. Validators, confirmation gates, Skill Runtime authorization, and
Soridormi provider checks remain separate runtime authority.

## Runtime Flow

The Orchestrator builds a context object for every routed turn. It now includes:

- `mind`: bounded profile summary and structured policy fields;
- `mind.identity`: stable self-description fields used by conversation and
  deepthinking prompts;
- `core_principles`: short alias for prompt and inspection code;
- `long_term_goals`: short alias for prompt and inspection code;
- `experience_tuning_policy`: explicit learning boundary.

The quick Router receives this context and may use it to classify intent, but
it cannot treat principles as authorization. Emergency filtering, capability
constraints, confirmation, Skill Runtime validation, and Soridormi provider
checks remain code-enforced.

The quick Router and native capability planner use the prompt context group
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

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ORCH_MIND_PROFILE_PATH` | unset | Optional JSON mind profile. Relative paths resolve from the repo root. |
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
PYTHONPATH=agent python -m unittest tests.test_mind_profile
PYTHONPATH=agent python -m unittest tests.test_router_llm_prompt tests.test_conversation_agent_prompt tests.test_deepthinking_agent
```

Full gate:

```bash
./scripts/run_tests.sh
```
