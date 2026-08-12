# Chromie Orchestrator

The Orchestrator is Chromie's host-side realtime runtime. It stays outside
Docker because it owns microphone capture, VAD, utterance boundaries, speaker
playback, barge-in, short-term conversation state, and Trusted Capability Runtime
coordination.

For authoritative architecture, status, and configuration, see:

- [`../docs/COGNITIVE_GATEWAY.md`](../docs/COGNITIVE_GATEWAY.md)
- [`../docs/COGNITIVE_TURN_LOOP.md`](../docs/COGNITIVE_TURN_LOOP.md)
- [`../docs/STATUS.md`](../docs/STATUS.md)
- [`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md)
- [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md)

## Service boundaries

- ASR converts complete PCM utterances to final text.
- Goal Interpretation produces deterministic or model-assisted `RouteDecision` objects.
- Agent exposes schema-constrained Goal Association, Fast/Deep Planning, peer
  Social-Attention proposals, and Response Composition, plus compatibility
  `AgentResult`/`InteractionResponse` surfaces.
- TTS delivers PCM synthesis chunks; the current Orchestrator buffers one
  complete request through the provider `end` event before ordered playback and
  interruption handling.
- The Trusted Capability Runtime resolves and schedules trusted named capabilities.
- Soridormi plans and executes embodied skills and owns physical safety.
- `hardware/daemon.py` is a legacy mock compatibility boundary, not the alpha
  embodiment path.

The Agent does not call TTS or low-level hardware. Separately gated TaskGraph
read/planning/guarded endpoints may use MCP, but normal embodied apply is
adapted and authorized by the Trusted Capability Runtime. The language model is never
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
before Goal Interpretation model inference, records the requested and effective
cancellation scopes, and projects only admitted envelopes into the Core.
Output, embodied-motion, foreground-interaction, and global-emergency reflex
scopes are implemented. Exact named-Goal cancellation is also implemented in
the cognitive path: the Core selects semantic Goal IDs, the host resolves exact
plan/runtime bindings, validates Trusted Capability Runtime receipts, atomically reconciles
Goal state, and rebuilds an unaffected confirmation remainder when possible.
A shared-owner pending request fails closed without changing its token, while a
post-dispatch reconciliation failure is surfaced as an uncertain final state.
Input Normalization, Protective Reflex, Context Assembly, focused Attention
Review, and Turn Admission are physically distinct modules. Admission completes
before ordinary Goal Interpretation. The Core endpoint accepts only an admitted
`CoreTurnRequest`; it returns a Core-owned `CoreInterpretationResult`, while the
legacy `RouteDecision` shape survives only as a digest-bound internal projection
for dependent planner contracts. Existing compatibility service names, environment
variables, and log fields remain migration surfaces rather than semantic authority.

## Current interaction paths

### Maintained goal-driven path

```text
microphone -> host VAD -> ASR -> Cognitive Gateway
  -> matched stop/cancel: interrupt current work and retain the envelope/outcome
  -> local suppression: record the envelope and start no ordinary cognition
  -> otherwise: attention review -> admitted UserTurnEnvelope
  -> Fast Understanding
       |-> complete native response -> existing Vocal runtime may start
       |-> exact capability candidate -> trusted safe read may start when ready
       |-> background Social Attention may prepare optional body decoration
       `-> Goal Association resolves scoped references, Goal relations, and exact candidate bindings
  -> fully bound native conversation: deterministic canonical speech adoption
     fully bound information work: adopt canonical Plan without Fast Planner
     otherwise: Fast Planner -> terminal Deep Planner when required
  -> reuse already-started Vocal / execution-only ready read when sufficient
     otherwise: Response Composer -> host-built strict InteractionResponse
  -> InteractionCoordinator -> Trusted Capability Runtime
      -> Soridormi or peer provider
  -> exact plan/request/result/trace join -> per-goal outcome commit
  -> validated speech-only final response -> TTS -> playback
```

For an effectful cognitive response, the Orchestrator commits requests only
when plan ID/fingerprint, step, capability, arguments, timing, goal ownership, and
output-schema identity match. Terminal `CapabilityResult` and `CapabilityTrace` records
then produce an immutable `ExecutionOutcomeBundle`; missing results become
`not_run`, and only bounded schema-validated observations may appear in the
final result speech. Barge-in may invalidate stale audible output, but an
ordinary newer turn does not cancel the earlier routed turn or discard its Goal
and outcome evidence. Explicit deterministic control or a Core-authorized
foreground interruption may cancel only its bound scope. A recoverable
Soridormi failure can
propose only a fresh-confirmed child plan containing the failed recoverable
subset; it cannot replay or mutate completed parent work.

The common safe base enables this path for `chat,memory,tool`, with local tools limited
to explicitly registered safe read-only providers. The Soridormi launcher adds
the body provider and additionally enables `robot_action`:

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat,memory,robot_action,tool
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

`/interaction` remains a real strict compatibility API and uses native
structured Agent output by default. It is not the maintained semantic planner
when unified `apply` owns the turn. Legacy-adapter mode and validation fallback
are explicit rollback controls.

Use `ORCH_ENABLE_SORIDORMI_SKILLS=0` for speech-only rollout. Named body skills
fail closed when their provider is disabled or unavailable.

Soridormi's live named-skill catalog supplies the effective confirmation
requirement for each skill. Chromie does not inspect simulator or hardware mode
to add or remove authorization. Interaction-level rules such as material
alternatives and post-interrupt physical resume may still require fresh user
confirmation regardless of the provider declaration.

### Compatibility path

```text
ASR -> Cognitive Gateway -> Goal-Driven Cognitive Core /run -> AgentResult
  -> compatibility speech/actions -> TTS and optional mock hardware daemon
```

This path remains for regression coverage and gradual migration. It must not be
used to turn a failed named-capability request into an unvalidated low-level action.

### Explicitly gated direct-conversation compatibility

The emergency compatibility gates can authorize a speech-only Ollama streaming
path for a legacy turn that has not entered a maintained Goal-driven apply lane:

```text
ASR -> Ollama -> TTS -> playback
```

This compatibility path produces speech only. It does not gain permission to
invoke skills or hardware, and it is not ordinary degradation for maintained
`apply` lanes. Once Goal-driven authority is selected, Goal Interpretation or
later failure stays fail-closed and cannot enter this path. A legacy embodied or
pending-task turn uses deterministic safe-fallback speech instead of generic
conversation. Deterministic silence/unusable-input suppression runs before any
compatibility decision, so suppressed input cannot fall through to the LLM.

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

Python 3.11 is the minimum supported host runtime. Both supervised voice
preflight and `scripts/start_orchestrator.sh` validate the selected Conda
environment before evidence creation, dependency installation, or model
warm-up. To use another conforming environment, set `CHROMIE_CONDA_ENV` explicitly; an older environment is rejected rather than
treated as partial runtime evidence.

For normal plug-and-use operation, select the preferred microphone/headphones in
the operating system and leave `ORCH_INPUT_DEVICE`/`ORCH_OUTPUT_DEVICE` empty or
set to `default`/`auto`. The Host resolves and validates those OS defaults before
opening streams, then follows later OS-default changes while it is running.
PortAudio defaults are polled and PipeWire metadata is observed read-only when
available. An affected input stream is reopened with its unfinished VAD segment
discarded; output rolls over between ordered playback items. Explicit device
names or indices remain pinned and fail clearly when unavailable rather than
silently falling back. Chromie never changes the OS route, default, mute, or
volume. Relative `RECORDINGS_DIR` paths are resolved from the repository root.

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
checks Python 3.11+ support, installs changed requirements, warms Ollama, avoids
duplicate processes, and starts the module from the repository root.

The Orchestrator has a fast-first presentation path for Goal Progress
Communication. Once Goal Interpretation has sufficiently understood a nontrivial
Goal that still requires downstream work before a substantive answer or effect,
the source Goal Interpreter should normally propose one typed, non-terminal
`fast_speech` notification so the person knows Chromie got the Goal and is taking
it forward. Missing result evidence limits what that notification may claim; it
is not itself a reason for silence. A separate Fast Response is omitted when the
substantive answer is immediate, an equivalent notification is already delivered
or pending, the user requested silence, or another utterance would only repeat or
add empty chatter. Goal Interpretation is the sole semantic owner of that first
notification: there is no second production LLM that re-decides or repairs the
speech-versus-silence choice. The Host validates the structured FastSpeech,
correlation, evidence, cancellation, and transport boundaries only; it does not
infer semantic equivalence from route names or wording. Tool routes use the typed
`acknowledge_and_check`/`checking_only` prospective contract before result evidence;
memory routes may likewise carry only a prospective acknowledgement and never a
commit claim. Results and failures remain separate evidence-bound acts.

At startup the Orchestrator may also prime a small speaker-specific
English/Chinese acknowledgement cache through the configured TTS service and
load the PCM into host memory. Cached cues are generic, low-commitment
presentation fallbacks such as “One moment” or “我先确认一下”. They are used only
when dynamic speech is not admissible, missing, invalid, or cannot be scheduled;
an adaptive hedge timer then waits `ORCH_FAST_FIRST_AUDIO_HEDGE_MS` (750 ms by
default) so a final response may still win the race. Cache entries never claim
a tool result, memory commit, physical execution, or completion.

The Host never authors the semantic sentence. Bare strings and partial
FastSpeech objects remain parseable but not playable: immediate dynamic audio requires
an allowed `purpose`, a non-terminal `commitment`,
`must_not_claim_completion=true`, and text that passes the completion-claim
guard. Physical work is limited to a safety prelude or confirmation, never an
execution claim. At the fast-speech review boundary the body action has not
started, so the ordinary wording must remain prospective; typed
`claim_state=none` cannot excuse a sentence that says Chromie is already inside
an ongoing movement. The queued dynamic utterance is projected into Response
Composer context as a non-evidentiary current-turn commitment. If it already
serves the required acknowledgement, the Composer references the exact speech
event with `reuse_current_turn_speech=true` and `reused_speech_event_id`;
Runtime reuses an audible event, waits for a pending one, or fulfills the act
once if that event becomes `not_delivered`. Playback start, not generation or
scheduling, satisfies the audible act. Text is checked only for event payload
integrity and is not the de-duplication key. Final result or failure speech
remains a distinct, evidence-bounded act.

Pure safe-read and other executable Plans use the same still-needed-delta rule as
all cognitive stages. If the exact Fast acknowledgement is already audible or
pending, later stages reference/reuse that event instead of repeating its meaning.
If no equivalent act exists, a Planner or Response Composer may author one new
prospective acknowledgement or correction, but it still cannot claim a result
before provider evidence. Tool Result Interpretation then contributes only the
new grounded post-execution result, failure, or correction that remains necessary.

Complete non-effectful Vocal-output Goals already use the direct Core branch
after Goal Association, without Fast or Deep Planner. Runtime records that path
separately from terminal Fast planning and reasoned Deep escalation. True
incremental PCM playback remains separate playback-lifecycle work; a
`tts_stream_start` transport event is not currently audible playback evidence.

Manual development start:

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

Do not run `cd orchestrator && python orchestrator.py`; package imports and
repository-relative files assume the repository root.

## Conversation state

The current store retains bounded turns, pending task hints, active interaction
metadata, compact task contexts, scoped discourse referents/focus, a
provenance-only verified-tool-memory index, and one conversation identifier across
utterances until reset or expiry. Each utterance still receives its own SID.

State is process-local by default. When `ORCH_ENABLE_TASK_CONTEXT_STORE=1`,
unfinished compact task contexts are saved locally and restored as recoverable
after restart; physical work still requires fresh confirmation and never resumes
blindly. This is not a long-term personal memory system. See
[`../docs/conversation_state.md`](../docs/conversation_state.md) and
[`../docs/DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md`](../docs/DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md).

## Scheduling, interruption, and cancellation

The microphone path keeps ASR decoding and routed-turn execution as separate
lifecycles. A valid barge-in immediately invalidates audible output but waits
for the transcript before choosing a cognitive or runtime cancellation scope.
If another VAD utterance closes while ASR is still decoding, the Orchestrator
retains the newest pending audio instead of dropping it; at most one pending
utterance is kept to bound memory and latency.

After transcription, independent ordinary routed turns are retained together;
launching a newer turn is not a cancellation operation. If protective reflex
work is active, every later ordinary transcript waits in FIFO order and is
released when the reflex closes successfully. Only an explicit deterministic
control scope or a Core-authorized semantic interruption cancels routed work.
`current_interaction` targets the foreground turn, while `global_emergency`
targets all eligible ordinary turns. Audible playback remains a shared ordered
resource, so a barge-in can silence stale audio without erasing the underlying
work.

Final outcome delivery separates obsolete audio from an independent Goal's
result obligation. When a newer ordinary turn changes playback generation, a
completed earlier Goal waits for the foreground session to finish and for an
idle output window, then delivers its evidence-bound result. Explicit scoped
cancellation or supersession invalidates the affected Goal; timeout is retained
as a delivery failure rather than being relabelled as success. Output-only
barge-in may silence current audio without cancelling the underlying work.

The Interaction Coordinator validates the response and submits speech and capability
requests to the Trusted Capability Runtime. Scheduling is bounded by
`ORCH_SKILL_MAX_CONCURRENCY` and provider/exclusive-group policy.

Cancellation:

1. dispatches scoped runtime cancellation and dedicated E-stop work without
   waiting for audible-output device cleanup;
2. classifies a fixed reflex as speech output, media output, embodied motion,
   foreground interaction, or global emergency; `output_only`, `media_output`,
   and `current_interaction` remain distinct stop-talking, stop-media, and
   stop-all scopes;
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

TaskGraph execution itself is also terminal-evidence bound. Only explicit
`success` completes the CapabilityResult; absent, `pending`, `running`, or unknown
status fails closed. The provider exposes a closed summary/result contract to
the cognitive turn while detailed Agent-side TaskGraph traces remain the
authoritative execution record.

Independent unselected Trusted Capability Runtime work continues; existing sequencing,
dependency, and required-delivery barriers still apply. A request shared by
targeted and untargeted goals is reported as a conflict. Resource arbitration
is process-local; Soridormi is the cross-process robot authority.

## Confirmation status

The non-skippable spoken confirmation dialogue is implemented with an
action-specific prompt, bounded reply matching, request binding, expiry,
single-use approval, deterministic denial, and operational-interrupt
passthrough. Confirmation is derived from the provider contract plus backend-neutral
Host safety rules. Retained
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
disable it. Agent and Goal Interpretation Ollama diagnostics also respect
`CHROMIE_CLI_COLOR=1` for forced color, falling back to the same auto/NO_COLOR
terminal behavior. Finished sessions also write `session_workflow` and
`session_workflow_graph` events plus paired JSON/Markdown reports under
`.chromie/evidence/cognitive-runtime/session-workflows/`. The reports show the
ASR, Cognitive Gateway, Goal-Driven Cognitive Core, Goal Association,
Fast/Deep Planner, canonical validation/rejection, Response Composer, Trusted
Capability Runtime, TTS, playback, per-stage input/output, diagnostics, and
timing observed for that SID. They state whether validation blocked requested
Work and scope provider-start trace evidence separately to requested Work,
`chromie.speak` delivery, and any runtime provider; fallback speech cannot prove
that the requested capability dispatched. Abandoned sessions are retained too,
and each completed SID refreshes a rolling
conversation-correlated report so follow-up turns appear in the same ordered
flow. Raw conversation follows
`ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT`; both formats are private evidence. The
operator console keeps only a compact `session_workflow_summary` line with the
slowest steps. `scripts/collect_debug_bundle.sh` includes the latest report
pairs.

Run the complete guided matrix with:

```bash
python scripts/voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

The narrower proof-before-refactor profile uses no Soridormi authority:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --cases speech-only \
  --start-services \
  --acceptance-id <acceptance-id>

python scripts/verify_voice_evidence.py \
  .chromie/acceptance/voice/<acceptance-id> \
  --profile current-revision-live-voice \
  --require-clean
```

That profile proves only one source-bound physical microphone-to-audible chat
loop and always reports `release_qualified=false`. The verifier's default
profile remains the complete seven-case voice/MuJoCo matrix.

Operator/debug WAV retention is controlled by `ORCH_SAVE_AUDIO`. Policy-governed
Data Loop input audio is independent: it is default-off, reuses the exact
validated VAD buffer without another microphone path, and requires an enabled
`chromie.interaction_session_capture` snapshot. Both forms may contain private
speech and require governance review before collection or sharing. See
[Chromie Data Loop](../docs/SCENARIO_CANDIDATE_DATA_LOOP.md).

The static, non-routing responsibility ontology used by the Orchestrator is
documented in the [Chromie High-Level Ability Registry](../docs/chromie_ability_registry.md).
