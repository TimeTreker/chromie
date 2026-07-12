# Chromie Orchestrator

The Orchestrator is Chromie's host-side realtime runtime. It stays outside
Docker because it owns microphone capture, VAD, utterance boundaries, speaker
playback, barge-in, short-term conversation state, and trusted Skill Runtime
coordination.

For authoritative status and configuration, see:

- [`../docs/STATUS.md`](../docs/STATUS.md)
- [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md)
- [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md)

## Service boundaries

- ASR converts complete PCM utterances to final text.
- Router produces deterministic or model-assisted `RouteDecision` objects.
- Agent produces compatibility `AgentResult` or strict `InteractionResponse`.
- TTS streams PCM synthesis; the Orchestrator plays and interrupts it.
- The Skill Runtime resolves and schedules trusted named skills.
- Soridormi plans and executes embodied skills and owns physical safety.
- `hardware/daemon.py` is a legacy mock compatibility boundary, not the alpha
  embodiment path.

The Agent does not call TTS, MCP, or hardware. The language model is never the
final authorization boundary for a side effect.

## Current interaction paths

### Structured path

```text
microphone -> host VAD -> ASR -> deterministic operational routing
  -> Agent /interaction -> strict InteractionResponse
  -> InteractionCoordinator -> Skill Runtime
      -> local speech provider -> TTS -> playback
      -> Soridormi provider -> MCP -> simulator/robot
```

Enable it explicitly:

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

`/interaction` is a real strict API and now uses native structured Agent
output by default. The Agent revalidates the complete wire contract and reports
its active output mode in response metadata. Legacy-adapter mode and validation
fallback are explicit Agent-side rollback controls; both are separate from the
host rollout flag.

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
response instead of the generic conversational LLM path.

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
`fast_speech` path remains available for explicit compatibility use, while
`ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED=0` keeps full generative tool preludes
disabled.

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
lifecycles. A valid barge-in can therefore cancel stale turn processing while a
new utterance enters ASR. If another VAD utterance closes while ASR is still
decoding, the Orchestrator retains the newest pending audio instead of dropping
it; at most one pending utterance is kept to bound memory and latency.

The Interaction Coordinator validates the response and submits speech and skill
requests to the Skill Runtime. Scheduling is bounded by
`ORCH_SKILL_MAX_CONCURRENCY` and provider/exclusive-group policy.

Barge-in:

1. stops interruptible playback;
2. cancels the current interaction execution;
3. asks cancellable providers to cancel active work;
4. waits for required cleanup paths;
5. preserves Soridormi stop/emergency policy for embodied work.

One interaction's cancellation must not cancel unrelated work. Resource
arbitration is process-local; Soridormi is the cross-process robot authority.

## Confirmation status

The non-skippable spoken confirmation dialogue is implemented with an
action-specific prompt, bounded reply matching, request binding, expiry,
single-use approval, deterministic denial, and operational-interrupt
passthrough. Simulation-only auto-confirm exemptions remain separate. Retained
automatic and supervised approval/denial evidence is still an alpha gate.

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
