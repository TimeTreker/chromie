# Chromie High-Level Ability Registry

Chromie's high-level ability registry is the robot's current self-model of
what it can do. It sits above concrete Soridormi skills and host services.
Routers, planners, and host orchestration should request abilities such as
`speech.thinking_ack` or `social.thinking_pose`, then let the runtime decide
whether the ability is fulfilled now.

The registry is implemented in `orchestrator/runtime/abilities.py`.

## Status Model

| Status | Meaning |
|---|---|
| `available` | The ability can be fulfilled in the current host runtime. |
| `sim_only` | The ability is fulfilled only in the simulator-safe path. |
| `hardware_only` | The ability is reserved for a hardware-only implementation. |
| `stub` | The ability is known but not implemented yet. |
| `disabled` | The ability has an implementation but is disabled by runtime flags. |

Optional social abilities may be skipped silently when unavailable. If the user
directly asks for an ability that is not fulfilled, Chromie should answer with a
language-matched unavailable message:

- English: `Sorry, I don't have that ability yet.`
- Chinese: `抱歉，我现在还没有这个能力。`

## Initial Ability Map

The registry currently names normal human-like ability families:

| Family | Examples |
|---|---|
| Cognition | `cognition.quick_route`, `cognition.deep_think`, `cognition.plan_task`, `cognition.split_task` |
| Speech | `speech.thinking_ack`, `speech.answer`, `speech.confirm`, `speech.report_progress` |
| Memory | `memory.remember_session_context`, `memory.recall_session_context`, `memory.forget_current_task` |
| Social | `social.look_at_user`, `social.listen_pose`, `social.thinking_pose`, `social.micro_nod`, `social.nod_yes` |
| Body | `body.walk_forward`, `body.turn_left`, `body.stop_motion`, `body.recover_balance` |
| Task | `task.execute_skill`, `task.confirm_before_action`, `task.cancel_current_action`, `task.monitor_action` |
| Safety | `safety.check_capability`, `safety.check_motion_allowed`, `safety.refuse_unsafe_request` |
| State | `state.report_robot_status`, `state.report_sim_or_hardware_mode`, `state.report_missing_ability` |

Most abilities are deliberately `stub` until a trusted implementation exists.
This lets Chromie be honest about missing abilities while preserving stable
names for future implementation.

## Fast-First Speech Loop

The host may speak a short route-level first phrase before the slower Agent
finishes. This is the first implemented slice of the live proposal/arbiter
model: fast output is preferred, and later Agent or deep-thinking output may
clarify, correct, confirm, cancel, or complete the turn.

The first phrase must be a truthful state signal, not an execution claim:

- chat: `I'm here.` / `我在。`
- factual or non-small-talk chat: `I'll answer.` / `我来回答。`
- robot action: no host fast-first phrase; the committed Agent `chromie.speak`
  task owns the single spoken acknowledgement.
- tool lookup: `I'll check that.` / `我查一下。`
- memory request: `I'll note that.` / `我记一下。`
- deep thought: `Okay, let me think about that.` / `好的，我想一下。`

`ORCH_FAST_FIRST_RESPONSE_ENABLED=1` enables this behavior by default. It does
not authorize skills, memory writes, tools, or body motion. It only reduces the
silence between Router completion and Agent completion.

## Deep-Thinking Fulfilled Loop

The first ability-backed social/body loop remains the deep-thinking handoff:

```text
User asks for complicated planning
-> Emergency filter passes because this is not stop/cancel/noise
-> Quick intent router chooses explicit deep_thought
-> Chromie executes speech.thinking_ack
-> Chromie optionally executes social.thinking_pose in simulator-safe mode
-> Deepthinking agent plans
-> Chromie speaks the final answer
```

Low-confidence routing handoffs do not automatically execute
`speech.thinking_ack` or `social.thinking_pose`; Chromie should avoid saying
“let me think” for short operational commands or ambiguous follow-ups. Stop,
cancel, emergency, silence, and unusable-audio paths stay deterministic and
bypass this loop.

`social.thinking_pose` resolves to `soridormi.express_attention` only when all
simulator-safe gates are enabled:

- structured interaction response is enabled;
- Soridormi skills are enabled;
- simulator auto-confirm is enabled;
- host action mode is dry-run.

Outside that mode, the ability remains a `stub` and is not executed.

Validate this scenario against a running voice-MuJoCo stack with:

```bash
./scripts/run_deep_thought_response_case.sh --no-speaker
```
