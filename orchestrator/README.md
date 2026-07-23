# Chromie Orchestrator

The Orchestrator is Chromie's host-side realtime runtime. It stays outside
Docker because it owns microphone capture, VAD, utterance boundaries, speaker
playback, barge-in, short-term conversation state, and trusted Skill Runtime
coordination.

For authoritative architecture, status, and configuration, see:

- [`../docs/COGNITIVE_GATEWAY.md`](../docs/COGNITIVE_GATEWAY.md)
- [`../docs/COGNITIVE_TURN_LOOP.md`](../docs/COGNITIVE_TURN_LOOP.md)
- [`../docs/STATUS.md`](../docs/STATUS.md)
- [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md)
- [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md)

## Service boundaries

- ASR converts complete PCM utterances to final text.
- Router produces deterministic or model-assisted `RouteDecision` objects.
- Agent exposes schema-constrained Goal Association, Fast/Deep Planning, and
  Response Composition, plus compatibility `AgentResult`/`InteractionResponse`
  surfaces.
- TTS streams PCM synthesis; the Orchestrator plays and interrupts it.
- The Skill Runtime resolves and schedules trusted named skills.
- Soridormi plans and executes embodied skills and owns physical safety.
- `hardware/daemon.py` is a legacy mock compatibility boundary, not the alpha
  embodiment path.

The Agent does not call TTS or low-level hardware. Separately gated TaskGraph
read/planning/guarded endpoints may use MCP, but normal embodied apply is
adapted and authorized by the host Skill Runtime. The language model is never
the final authorization boundary for a side effect.

## Cognitive ingress boundary

The [Cognitive Gateway / 认知网关](../docs/COGNITIVE_GATEWAY.md) is the logical
boundary between interaction transport and semantic cognition. It owns input
normalization, deterministic protective reflexes, attention review, bounded
context assembly, and turn admission. The Goal-Driven Cognitive Core owns
ordinary intent and goal understanding, planning, execution coordination,
outcome reconciliation, and final response composition.

The frozen version 1 `UserTurnEnvelope`, shared deterministic reflex contract,
host admission adapter, source/freshness context references, and local
stop/suppression paths are implemented. The host begins stop/cancel handling
before Router or model inference, records the requested and effective
cancellation scopes, and projects only admitted envelopes into the Core.
Output, embodied-motion, foreground-interaction, and global-emergency reflex
scopes are implemented. Exact named-goal cancellation requires a committed
plan binding; its Core-to-runtime dispatch/reconciliation bridge remains open.
The Router still hosts addressedness review and mixed compatibility semantics,
so physical extraction of the five Gateway modules remains open. Existing
Router APIs, service names, environment variables, and log fields remain
current compatibility surfaces.

## Current interaction paths

### Maintained goal-driven path

```text
microphone -> host VAD -> ASR -> Cognitive Gateway
  -> matched stop/cancel: interrupt current work and retain the envelope/outcome
  -> local suppression: record the envelope and start no ordinary cognition
  -> otherwise: compatibility attention/route review -> admitted UserTurnEnvelope
  -> Goal Association -> Fast Planner -> terminal Deep Planner when required
  -> prospective Response Composer -> host-built strict InteractionResponse
  -> InteractionCoordinator -> Skill Runtime
      -> Soridormi provider -> MCP -> simulator/robot
  -> exact plan/request/result/trace join -> per-goal outcome commit
  -> validated speech-only final response -> TTS -> playback
```

For an effectful cognitive response, the Orchestrator commits requests only
when plan ID/fingerprint, step, skill, arguments, timing, goal ownership, and
output-schema identity match. Terminal `SkillResult` and `SkillTrace` records
then produce an immutable `ExecutionOutcomeBundle`; missing results become
`not_run`, and only bounded schema-validated observations may appear in the
final result speech. Cancellation or a newer turn suppresses stale final audio
without discarding outcome evidence. A recoverable Soridormi failure can
propose only a fresh-confirmed child plan containing the failed recoverable
subset; it cannot replay or mutate completed parent work.

The common safe base enables this path for `chat`. The Soridormi launcher adds
the provider and widens authority to `robot_action`:

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat,robot_action
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

`/interaction` remains a real strict compatibility API and uses native
structured Agent output by default. It is not the maintained semantic planner
when unified `apply` owns the turn. Legacy-adapter mode and validation fallback
are explicit rollback controls.

Use `ORCH_ENABLE_SORIDORMI_SKILLS=0` for speech-only rollout. Named body skills
fail closed when their provider is disabled or unavailable.

`ORCH_AUTO_CONFIRM_SIM_SKILLS=1` applies only to Soridormi-declared simulation
exemptions. It must not waive confirmation for real hardware motion.

### Compatibility path

```text
ASR -> Router -> Agent /run -> AgentResult
  -> compatibility speech/actions -> TTS and optional mock hardware daemon
```

This path remains for regression coverage and gradual migration. It must not be
used to turn a failed named-skill request into an unvalidated low-level action.

### Direct conversational fallback

When `ORCH_ENABLE_ROUTER=false`, or when configured compatibility components
fail, the Orchestrator can use a speech-only Ollama streaming path:

```text
ASR -> Ollama -> TTS -> playback
```

This fallback produces speech only. It does not gain permission to invoke
skills or hardware. If the Router fails while the utterance or active pending
task looks embodied, the Orchestrator uses a deterministic safe-fallback speech
response instead of the generic conversational LLM path. Deterministic local
silence/unusable-input suppression is applied before Router enablement or
failure handling, so suppressed input cannot fall through to this LLM path.

## Configuration precedence

At startup, the recommended scripts generate root `.env.runtime`. The
Orchestrator then fills still-unset host values from
`orchestrator/.env.local`. Values already exported by the launching process
retain precedence. `scripts/start_orchestrator.sh` can additionally source an
`ORCH_RUNTIME_OVERRIDE_FILE` after `.env.runtime`; this is intended for
acceptance runs that must not rewrite local configuration.

Prepare the host environment:

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set explicit `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE` values. Relative
`RECORDINGS_DIR` paths are resolved from the repository root.

Conversation settings have both current `ORCH_CONVERSATION_*` names and legacy
`ORCH_CONTEXT_*` aliases. New deployments should use the conversation-prefixed
names documented in [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md).

## Acceptance audio modes

Normal operation uses:

```text
ORCH_AUDIO_INPUT_MODE=device
ORCH_AUDIO_OUTPUT_MODE=device
```

The alpha automatic runner can instead set:

```text
ORCH_AUDIO_INPUT_MODE=stdin
ORCH_AUDIO_OUTPUT_MODE=discard
ORCH_DISCARD_PLAYBACK_REALTIME=1
```

In stdin mode the Orchestrator accepts a bounded binary PCM16 framing protocol
only through its inherited standard input. It does not open a network test
endpoint. The injected stream is resampled and fed through the same VAD and ASR
path used by the microphone. Discard output mode keeps playback timing and
interruption checks while avoiding a physical speaker.

`virtual-mic` acceptance keeps `ORCH_AUDIO_INPUT_MODE=device`, sets
`PULSE_SOURCE` to a temporary null-sink monitor, and uses discard output to
avoid feedback.

## Start

Recommended:

```bash
./scripts/start_orchestrator.sh
```

This generates runtime configuration, activates the selected Conda environment,
installs changed requirements, warms Ollama, avoids duplicate processes, and
starts the module from the repository root.

The Orchestrator has a true fast-first audio path for slow tool, planning,
memory, and embodied turns. At startup it primes a small speaker-specific
English/Chinese acknowledgement cache through the configured TTS service and
loads the PCM into host memory. During a turn, an adaptive hedge timer waits
`ORCH_FAST_FIRST_AUDIO_HEDGE_MS` (750 ms by default): if the final Agent/tool
response is ready first, no acknowledgement plays; otherwise the cached audio
is queued directly without another LLM or TTS request. A cue that is queued but
has not started is cancelled when the final response wins the race.

These cues are intentionally generic low-commitment states such as “One
moment” or “我先确认一下”. They are presentation mappings after semantic routing,
not phrase-based intent decisions, and they never claim a tool result, memory
commit, physical execution, or completion. The older Router-generated dynamic
`fast_speech`/`speak_first` path is retained for wire compatibility but is
default-off behind `ORCH_ROUTER_GENERATED_FAST_SPEECH_ENABLED=0`. Bare strings
and partial FastSpeech objects are parseable but not playable. An operator who
enables the gate still gets immediate audio only from a structured object with
an allowed `purpose`, a non-terminal `commitment`,
`must_not_claim_completion=true`, and text that passes the completion-claim
guard. `ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED=0` independently keeps tool-route
fast-first scheduling off. Startup-cached cues and host-validated
`metadata.response_plan` immediate speech remain available without enabling
Router-generated dynamic wording.

Manual development start:

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

Do not run `cd orchestrator && python orchestrator.py`; package imports and
repository-relative files assume the repository root.

## Conversation state

The current store retains bounded turns, pending task hints, active interaction
metadata, compact task contexts, and one conversation identifier across
utterances until reset or expiry. Each utterance still receives its own SID.

State is process-local by default. When `ORCH_ENABLE_TASK_CONTEXT_STORE=1`,
unfinished compact task contexts are saved locally and restored as recoverable
after restart; physical work still requires fresh confirmation and never resumes
blindly. This is not a long-term personal memory system. See
[`../docs/conversation_state.md`](../docs/conversation_state.md).

## Scheduling, interruption, and cancellation

The microphone path keeps ASR decoding and routed-turn execution as separate
lifecycles. A valid barge-in immediately invalidates audible output but waits
for the transcript before choosing a cognitive or runtime cancellation scope.
If another VAD utterance closes while ASR is still decoding, the Orchestrator
retains the newest pending audio instead of dropping it; at most one pending
utterance is kept to bound memory and latency.

The Interaction Coordinator validates the response and submits speech and skill
requests to the Skill Runtime. Scheduling is bounded by
`ORCH_SKILL_MAX_CONCURRENCY` and provider/exclusive-group policy.

Cancellation:

1. dispatches scoped runtime cancellation and dedicated E-stop work without
   waiting for audible-output device cleanup;
2. classifies a fixed reflex as output, embodied motion, foreground
   interaction, or global emergency;
3. selects both active and queued requests and prevents selected queued work
   from starting;
4. asks only selected interruptible providers to cancel and records failures or
   non-interruptible work without claiming it stopped;
5. widens the effective scope explicitly when a provider, including current
   Soridormi motion cancellation, exposes only global-domain cancellation;
6. dispatches Soridormi's dedicated E-stop for global emergency, retaining its
   result separately from safe-idle proof;
7. calls the authenticated Agent TaskGraph cancel endpoint for selected
   TaskGraph work and treats a missing/negative cancellation receipt as failure.

Independent unselected Skill Runtime work continues; existing sequencing,
dependency, and required-delivery barriers still apply. A request shared by
targeted and untargeted goals is reported as a conflict. Resource arbitration
is process-local; Soridormi is the cross-process robot authority.

## Confirmation status

The non-skippable spoken confirmation dialogue is implemented with an
action-specific prompt, bounded reply matching, request binding, expiry,
single-use approval, deterministic denial, and operational-interrupt
passthrough. Simulation-only auto-confirm exemptions remain separate. Retained
automatic and supervised approval/denial evidence is still an alpha gate.
One pending token may cover multiple requests. A motion stop revokes that whole
token if any confirmed request is motion-bound or cannot be safely classified;
this conservative widening can also revoke unrelated unused approvals and is
recorded separately from runtime execution cancellation.

## Diagnostics

Useful commands:

```bash
python orchestrator/list_devices.py
./scripts/show_profile.sh
./scripts/gpu_smoke_test.sh
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
python scripts/interaction_text_mujoco_check.py --no-speaker
```

Session timing logs can be enabled with `ORCH_SESSION_TIMING_LOGS=1`. Set
`ORCH_EVENT_LOG_PATH` to append correlated JSONL records containing UTC time,
SID, elapsed milliseconds, event name, rendered details, and severity. Evidence
writing is best-effort and never authorizes or changes execution. Suspicious
nodes such as speech-only `robot_action` routing or action-refusal speech are
logged as warnings; failed skill, runtime, or TTS nodes are logged as errors.
LLM budget failures are also promoted into visible session events: `done_reason=length`,
`eval_count >= num_predict`, or `prompt_eval_count >= num_ctx` produce red
truncation logs, while near-limit prompt/output budgets produce yellow pressure
logs with tuning suggestions. The operator CLI colors warning lines yellow and
error lines red when attached to a color-capable terminal. Set
`ORCH_CLI_COLOR=1` to force Orchestrator session color or `ORCH_CLI_COLOR=0` to
disable it. Agent and Router Ollama diagnostics also respect
`CHROMIE_CLI_COLOR=1` for forced color, falling back to the same auto/NO_COLOR
terminal behavior. Finished sessions also write
`session_workflow` and `session_workflow_graph` evidence covering
VAD, ASR, Router, Agent, Skill Runtime, TTS, playback, per-stage deltas, and
final timing. The operator console keeps only a compact
`session_workflow_summary` line with the slowest steps.

Run the complete guided matrix with:

```bash
python scripts/voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

Audio capture retention is controlled by `ORCH_SAVE_AUDIO`; both recordings and
session events may contain private speech and require review before sharing.
