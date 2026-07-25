# Chromie High-Level Ability Registry

Chromie's high-level ability registry is a static cognitive ontology of abilities
it can understand and discuss. It is not a body-backend selector and it is not an
executable Soridormi catalog.

The registry is implemented in `orchestrator/runtime/abilities.py`.

## Status Model

| Status | Meaning |
|---|---|
| `available` | A trusted Chromie-local implementation can fulfill the ability now. |
| `stub` | Placeholder entry without an executable implementation. |
| `planned` | A reviewed roadmap ability, not executable yet. |
| `known_missing` | Chromie understands the ability, but no trusted implementation exists now. |
| `forbidden` | The ability must not be offered or implemented under current safety/policy rules. |
| `disabled` | A Chromie-local implementation exists but is disabled by a runtime gate. |

The ontology deliberately has no simulator-only or hardware-only status. Chromie
does not decide whether Soridormi is simulated or physical. A backend change must
not change Chromie's personality, social policy, semantic skill choice, or user
authorization logic.

Only `available` entries with a non-stub Chromie-local implementation are
executable through this static registry. Provider-backed embodied abilities are
resolved from the live provider catalog at planning/execution time instead.

Optional social abilities may be skipped silently when unavailable. If the user
directly requests an unavailable ability, Chromie should answer with a
language-matched message:

- English: `Sorry, I don't have that ability yet.`
- Chinese: `抱歉，我现在还没有这个能力。`

## Initial Ability Map

The ontology names normal human-like ability families:

| Family | Examples |
|---|---|
| Cognition | `cognition.quick_route`, `cognition.deep_think`, `cognition.plan_task`, `cognition.split_task` |
| Speech | `speech.thinking_ack`, `speech.answer`, `speech.confirm`, `speech.report_progress` |
| Memory | `memory.remember_session_context`, `memory.recall_session_context`, `memory.forget_current_task` |
| Social | `social.blink_eyes`, `social.look_at_user`, `social.listen_pose`, `social.micro_nod`, `social.nod_yes` |
| Body | `body.walk_forward`, `body.turn_left`, `body.stop_motion`, `body.recover_balance` |
| Manipulation | `manipulation.pick_up_object`, `manipulation.place_object` |
| Navigation | `navigation.follow_user`, `navigation.go_to_location` |
| Environment | `environment.open_door`, `environment.turn_on_light`, `environment.clean_surface` |
| Task | `task.execute_skill`, `task.confirm_before_action`, `task.cancel_current_action`, `task.monitor_action` |
| Safety | `safety.check_capability`, `safety.check_motion_allowed`, `safety.refuse_unsafe_request` |
| State | `state.report_robot_status`, `state.report_missing_ability` |

Many human-like abilities remain `known_missing` or `planned` until a trusted
implementation exists. This lets Chromie understand broad requests, answer
honestly, and preserve stable semantic names without claiming execution.

## Static Ontology Versus Live Provider Catalog

The static ontology and the live execution catalog have different jobs:

```text
Static ability ontology
  -> understands broad human intent and missing abilities

Live provider catalog
  -> supplies exact named skills, schemas, effective availability,
     confirmation requirements, scheduling constraints, and resources

Skill Runtime
  -> validates and executes only exact live definitions
```

A `known_missing`, `planned`, or `stub` ontology entry may appear in a proposal
ledger as missing, but it must never be sent to Skill Runtime. Executable body
work requires an exact live provider skill and the normal planner, Host,
authorization, runtime, and provider gates.

The Host does not infer body availability from dry-run mode, simulator identity,
hardware identity, or a launcher profile. Soridormi/provider owns backend
selection and returns the effective semantic contract for the active body.

See [Dream Broadly, Execute Honestly](DREAM_BROADLY_EXECUTE_HONESTLY.md) for the
understanding-versus-execution contract.

## Fast-First Speech Loop

The Host may speak a short route-level acknowledgement before slower reasoning.
It must be a truthful state signal, not an execution claim:

- chat: `I'm here.` / `我在。`
- factual or non-small-talk chat: `I'll answer.` / `我来回答。`
- robot action: no Host-authored body or execution claim;
- tool lookup: `I'll check that.` / `我查一下。`
- memory request: `I'll note that.` / `我记一下。`
- deep thought: `Okay, let me think about that.` / `好的，我想一下。`

`ORCH_FAST_FIRST_RESPONSE_ENABLED=1` enables this speech behavior. It does not
authorize skills, memory writes, tools, or body motion.

Optional Social Attention is selected separately by Response Composer from the
live provider catalog under the owner-approved Social Interaction Style. It is
parallel-only, optional, and lower priority than speech, emergency handling, and
explicit user actions. The static ability registry does not define or generate a
fixed thinking gesture, and the Host does not inject one when deep thought starts.

Validate the maintained text-to-provider path with:

```bash
./scripts/run_voice_mujoco_text_case.sh --no-speaker "Please nod twice."
```
