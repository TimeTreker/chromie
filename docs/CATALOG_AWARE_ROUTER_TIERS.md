# Catalog-Aware Router Tiers

This document records Chromie's catalog-aware routing contract for the fast
Router model and the deepthinking path.

## Principle

The skill catalog is a bounded menu of executable abilities. It is not the
normal intent-understanding brain.

For ordinary language, the Router should let the model infer meaning from the
user text, bounded context, and compact skill descriptions. Deterministic code
may partition, validate, reject, clarify, or fail closed, but it must not grow
into a rule table that chooses normal activities by phrase matching.

The model may understand broader human-like desired abilities before execution
exists. That broad understanding belongs in non-executable proposals, not in
`actions[]`. See [Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md).

The exception is the deterministic emergency/noise layer. Stop, cancel,
emergency, silence, unusable audio, and obvious repeated filler stay rule-based
because they are realtime safety controls.

## Prompt Tiers

Catalog entries carry a `prompt_tier`:

| Tier | Used By | Purpose |
|---|---|---|
| `common` | Second Router / `qwen3:0.6b` | Usually used daily skills that should fit in the fast prompt. |
| `rare` | Deepthinking / larger Agent model | Seldom-used, operational, planning, commissioning, or specialized skills. |

Catalog entries also carry:

- `prompt_tier_locked`: when true, the entry is safety-locked out of the fast
  common prompt even if a provider or experience overlay labels it `common`;
- `prompt_tier_source`: `preset`, `provider`, `experience`, or `safety_lock`;
- `prompt_tier_reason`: short audit text explaining the source decision.

The fast Router receives only unlocked `common` entries as
`common_ability_catalog`. Deepthinking receives the full compact catalog,
including common, rare, and safety-locked entries.

This partition starts as owner/provider-curated prompt budgeting in
`capabilities/prompt_tiers.json`, then may be updated by reviewed experience
through an auditable overlay. It is not semantic action selection. The model
still chooses the route and exact skill from meaning.

Experience tuning may move ordinary unlocked skills between `common` and
`rare`, with audit records. Safety-sensitive skills are the exception: entries
marked `prompt_tier_locked`, or classified as safety-critical/restricted/
guarded/commissioning/safety-control, are forced to `rare` with
`prompt_tier_source=safety_lock`. Experience cannot promote them into the fast
Qwen prompt; the full-catalog/deepthinking path can still reason about them
under normal confirmation and provider policy.

The offline helper `scripts/tune_capability_prompt_tiers.py` can build
`.chromie/experience/capability_prompt_tier_overrides.json` from the experience
journal and append candidate/skip events to
`.chromie/experience/capability_prompt_tier_audit.jsonl`. The Agent can load
that overlay with `AGENT_CAPABILITY_PROMPT_TIER_OVERRIDES`.

## Second Router Contract

The quick Router sees:

- latest ASR text;
- bounded session, memory, task, and robot/world context;
- `common_ability_catalog` and `common_ability_ids`, containing the compact
  commonly used, unlocked ability menu for the small Qwen-class model.

It outputs one `RouteDecision`. That decision may contain one selected intent
or an ordered `actions` array when the request is a compound task made from
unlocked common catalog skills:

- `robot_action` with `intent=capability:<exact skill_id>` when an unlocked
  common skill clearly satisfies the request;
- `robot_action` with `intent=compound_common_catalog_task` and `actions[]`
  when multiple unlocked common skills should be proposed together;
- `chat`, `tool`, `memory`, or `clarify` for non-body or ambiguous requests;
- `deep_thought` when no unlocked common skill clearly fits, confidence is low,
  or the request needs careful reasoning.

`actions[]` is a task proposal surface, not execution authorization. Each item
must copy `capability_id` exactly from the unlocked common catalog and may
include schema-shaped `args`, `sequence`, `timing`, a short `reason`, and a
0.0-1.0 `confidence` for that specific skill choice and arguments. Speech
inside a physical task uses `chromie.speak` with `args.text`; it should not be
dropped as ordinary chat or a separate unstructured final answer.
If a fast Router output selects a capability outside `common_ability_ids` while
the unlocked common catalog is available, validation delegates to `deep_thought`
instead of treating that rare, locked, or full-catalog ability as an immediate
fast-lane action.

When the quick Router understands a desired ability but no unlocked common
executable skill safely matches it, it should choose `deep_thought` or
`clarify` and may include `metadata.desired_abilities[]` with `ability_id`,
`intent`, `status=missing_ability`, `confidence`, and `reason`. These entries
become shared task-proposal ledger records, but they never execute.

When delegating to `deep_thought`, the quick Router may include `speak_first`.
That text is a model-chosen speech task/prelude, such as a natural request for a
moment to think. It must not claim that a physical action, tool result, memory
write, or completion has happened.

## Deepthinking Contract

Deepthinking sees the full catalog and the quick Router output. It may:

- accept a quick proposal;
- revise or supersede it;
- emit speech through `chromie.speak`;
- emit exact catalog skill tasks;
- emit non-executable `task_proposals[]` for understood desired abilities that
  are missing from the executable catalog;
- clarify or refuse when no safe supported capability exists.

Deepthinking still cannot invent skills or raw body controls. Every non-speech
task must use an exact supplied catalog skill ID and schema-valid arguments.
Missing or planned abilities must stay in task proposals and truthful speech,
not executable tasks.

## Validation Contract

Validation is deterministic but not semantic recommendation.

Validators may check:

- the skill ID exists in the supplied catalog;
- the skill is available and interaction-executable when execution is requested;
- arguments satisfy the skill schema;
- safety class and confirmation gates;
- no raw motor, joint, torque, actuator, or controller-array fields are exposed;
- speech preludes do not claim completed/executing physical work.
- missing-ability proposals carry `state=missing_ability` and do not enter the
  executable task list.

Validators should not decide that a normal phrase means a normal skill. That
meaning decision belongs to the LLM stage that saw the catalog.

## Failure Posture

If the fast Router is uncertain, it should delegate rather than guess.

If the fast Router returns no safe skill or any required action is below the
Router confidence threshold, the Orchestrator may speak a safe thinking prelude
and let deepthinking continue. If there is no safe model-provided prelude,
Chromie should stay silent or use the existing fail-closed fallback for that
path.

If the fast Router is unavailable, deterministic code may preserve context,
delegate, or fail closed, but should not replace the model with per-query
catalog matching as the normal semantic chooser.

See [Quick Router Task Planning](QUICK_ROUTER_TASK_PLANNING.md) for the
per-action confidence contract and low-confidence handoff plan.
