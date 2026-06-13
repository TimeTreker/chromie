# Development Checkpoint

**Chromie base revision:** `8c448e2de2cd8a602b0d48e31461f9be9f1b8d08`; pin the exact post-patch revision in acceptance/release manifests
**Soridormi manifest revision:** `a092dc704f1ab797fb1d4f542696fe75026eb171`
**Verified date:** 2026-06-13
**Current milestone:** **M13 — Native Interaction Agent and end-to-end voice acceptance**

This is the exact resume point for the supplied repository snapshot. Current
status authority is [docs/STATUS.md](docs/STATUS.md).

## What is already present

- Five-service Docker runtime and host Orchestrator.
- Hardware-profile detection and generated `.env.runtime`.
- Realtime audio/VAD/ASR/TTS/playback and interruption.
- Deterministic Router and multi-agent `/run` path.
- Short-term conversation state across VAD utterances.
- Strict interaction contracts and `POST /interaction`.
- Native `InteractionRuntime` output with direct `InteractionSpeech` and
  `SkillRequest` accumulation.
- Strict native-output validation, fail-closed behavior, explicit compatibility
  mode, and opt-in legacy fallback.
- `AgentResultInteractionAdapter` retained for rollback compatibility, including
  named-skill translation for nod, head shake, and look-at-user actions.
- Trusted Skill Runtime with local speech and Soridormi providers.
- Live Soridormi named-skill catalog import and opaque plan/monitor/execute
  sequence.
- Capability registry, manifest materialization, schema probe, and acceptance
  tools.
- TaskGraph planning, validation, dry run, read-only/planning/guarded execution,
  confirmation grants, cancellation, traces, and shared scheduling.
- Headless text-to-live-MuJoCo structured interaction acceptance.
- Correlated JSONL session-event evidence plus synthetic, virtual-microphone, and supervised seven-case runners with a strict evidence verifier.
- `0.1.0-alpha.1` candidate notes, compatibility metadata, archive/checksum generator, and release gate.

## What is not complete

- Complete non-skippable confirmation conversation.
- Reviewed reference-host output from the final supervised M13 matrix; automatic synthetic and virtual-microphone modes are implementation/regression evidence only.
- Retained target GPU and supervised M5 evidence.
- Verified Jetson container packaging.
- Physical hardware release support.
- Published alpha release; candidate packaging and compatibility policy are prepared but blocked.

## Verification baseline

Run:

```bash
./scripts/run_tests.sh
```

At this checkpoint the expected baseline is:

```text
155 current unittest cases passed
20 legacy Agent tests passed
documentation checks passed
```

This is GPU-free evidence only.

## Resume sequence

1. Confirm the clean baseline:

   ```bash
   ./scripts/run_tests.sh
   ```

2. Verify native interaction mode and rollback controls in:

   ```text
   agent/app/main.py
   agent/app/interaction.py
   agent/app/runtime.py
   docs/interaction_agent_skill_runtime.md
   docs/STATUS.md
   ```

3. Keep stop, cancel, emergency, silence, and unusable-audio handling
   deterministic.
4. Add request-bound confirmation dialogue and tests for approve, decline,
   timeout, interruption, and replay rejection.
5. Run `scripts/m13_voice_acceptance.py --mode synthetic`, then
   `--mode virtual-mic`, and finally the complete `--mode supervised`
   microphone/MuJoCo matrix. Verify automatic bundles with
   `--allow-automated` and the final bundle with `--require-clean`.
6. Review private speech, audible quality, simulator safe idle, cancellation,
   and recovery notes; close applicable M3/M5 target evidence tracks.
7. Remove the spoken-confirmation blocker only after implementation/evidence,
   then generate the clean alpha bundle with
   `scripts/prepare_alpha_release.py`.

## Useful commands

```bash
./scripts/show_profile.sh
BUILD=1 ./scripts/start_services.sh
./scripts/start_orchestrator.sh
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/m13_voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

With a live Soridormi endpoint:

```bash
export SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
PYTHONPATH=agent python -m app.probe_capabilities \
  --manifest capabilities/soridormi.json
PYTHONPATH=. python scripts/interaction_text_acceptance.py nod
```

## Safety invariants

- Do not replace named skills with raw robot controls.
- Do not let model output authorize itself.
- Do not treat simulation auto-confirmation as hardware confirmation.
- Keep physical execution default-off and Soridormi-owned.
- Keep cancellation and emergency fallbacks active during refactors.
- The host hardware daemon is mock compatibility only.

## Historical checkpoint

The earlier tag `checkpoint-m5-runtime-target-ready-2026-06-08` remains useful
for historical comparison. It is not the current project status.
