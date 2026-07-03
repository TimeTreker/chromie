# Catalog-Aware Router Tiers

This document records Chromie's catalog-aware routing contract for the fast
Router model and the deepthinking path.

## Principle

The skill catalog is a bounded menu of possible abilities. It is not the normal
intent-understanding brain.

For ordinary language, the Router should let the model infer meaning from the
user text, bounded context, and compact skill descriptions. Deterministic code
may partition, validate, reject, clarify, or fail closed, but it must not grow
into a rule table that chooses normal activities by phrase matching.

The exception is the deterministic emergency/noise layer. Stop, cancel,
emergency, silence, unusable audio, and obvious repeated filler stay rule-based
because they are realtime safety controls.

## Prompt Tiers

Catalog entries carry a `prompt_tier`:

| Tier | Used By | Purpose |
|---|---|---|
| `common` | Second Router / `qwen3:0.6b` | Usually used daily skills that should fit in the fast prompt. |
| `rare` | Deepthinking / larger Agent model | Seldom-used, operational, planning, commissioning, or specialized skills. |

The fast Router receives the compact common catalog. Deepthinking receives the
full compact catalog, including both common and rare entries.

This partition is owner-curated prompt budgeting. It is not semantic action
selection. The model still chooses the route and exact skill from meaning.

## Second Router Contract

The quick Router sees:

- latest ASR text;
- bounded session, memory, task, and robot/world context;
- the common compact skill catalog;
- query-biased catalog hints as optional context only.

It outputs one `RouteDecision`. That decision may contain one selected intent
or an ordered `actions` array when the request is a compound task made from
common catalog skills:

- `robot_action` with `intent=capability:<exact skill_id>` when a common skill
  clearly satisfies the request;
- `robot_action` with `intent=compound_common_catalog_task` and `actions[]`
  when multiple common skills should be proposed together;
- `chat`, `tool`, `memory`, or `clarify` for non-body or ambiguous requests;
- `deep_thought` when no common skill clearly fits, confidence is low, or the
  request needs careful reasoning.

`actions[]` is a task proposal surface, not execution authorization. Each item
must copy `capability_id` exactly from the common catalog and may include
schema-shaped `args`, `sequence`, `timing`, a short `reason`, and a 0.0-1.0
`confidence` for that specific skill choice and arguments. Speech inside a
physical task uses `chromie.speak` with `args.text`; it should not be dropped as
ordinary chat or a separate unstructured final answer.

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
- clarify or refuse when no safe supported capability exists.

Deepthinking still cannot invent skills or raw body controls. Every non-speech
task must use an exact supplied catalog skill ID and schema-valid arguments.

## Validation Contract

Validation is deterministic but not semantic recommendation.

Validators may check:

- the skill ID exists in the supplied catalog;
- the skill is available and interaction-executable when execution is requested;
- arguments satisfy the skill schema;
- safety class and confirmation gates;
- no raw motor, joint, torque, actuator, or controller-array fields are exposed;
- speech preludes do not claim completed/executing physical work.

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
delegate, or fail closed, but should not treat catalog search scores as the
normal semantic chooser.

See [Quick Router Task Planning](QUICK_ROUTER_TASK_PLANNING.md) for the
per-action confidence contract and low-confidence handoff plan.
