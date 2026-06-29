# ASR Backend Migration Plan

This document defines the goal and staged implementation plan for evaluating
sherpa-onnx without destabilizing the current Chromie voice path.

## Goal

Keep the current final-utterance Faster-Whisper path as the supported default
while adding an explicit ASR backend boundary that can host a future
sherpa-onnx implementation. The migration should improve local realtime speech
operation only when benchmarks and retained evidence show that it preserves or
improves the current user-facing contract.

The ASR layer is perception, not robot thinking. Outside deterministic
operational controls such as stop, cancel, emergency, silence, and
unusable-audio handling, recognized text must still flow to Router and Agent
LLM reasoning for normal language understanding, capability selection, and
robot planning. ASR backends may expose confidence, timing, endpointing, and
transcript metadata, but they must not add phrase tables or regexes that decide
ordinary robot intent.

## Current Baseline

- `chromie-asr` accepts one complete PCM16 utterance over WebSocket and returns
  one `final` transcript.
- The host Orchestrator owns microphone capture, VAD, utterance boundaries,
  barge-in, interruption, and ASR timeout handling.
- The supported backend is `ASR_BACKEND=faster_whisper` with `ASR_MODE=final`.
- Faster-Whisper model and revision locks are maintained through hardware
  profiles and `release/model-lock.json`.
- ASR inference runs off the WebSocket event loop behind a bounded executor.
- `ASR_BACKEND=sherpa_onnx` is planned but intentionally fails closed until the
  backend, dependency, model lock, benchmark, and acceptance evidence exist.

## Implementation Sequence

1. Add the backend boundary while preserving the current WebSocket protocol and
   Faster-Whisper default.
2. Add configuration and health metadata for `ASR_BACKEND` and `ASR_MODE`.
3. Add a non-streaming sherpa-onnx backend behind
   `ASR_BACKEND=sherpa_onnx`, using complete utterances and returning only
   `final` results at first.
4. Pin sherpa-onnx runtime dependencies, selected models, and immutable model
   sources in the same release-provenance path used by maintained profiles.
5. Add Level A tests for backend selection, fail-closed unavailable providers,
   and final transcript normalization.
6. Add Level B smoke checks that report backend name, mode, model identity,
   latency, and service health.
7. Run Chromie-specific A/B benchmarks before changing defaults.
8. Only after final-mode evidence is stable, design an optional streaming ASR
   protocol with `partial`, endpoint, and `final` messages.

## Benchmark Criteria

Benchmark candidates with the same Orchestrator capture, VAD, timeout, and
barge-in path. Record:

- character/word error rate on English, Chinese, and mixed commands;
- final transcript latency from completed utterance to ASR response;
- first partial and endpoint latency if streaming is later added;
- CPU, GPU, memory, model-load time, and Docker cold-start cost;
- robustness under room noise, short commands, filler speech, and silence;
- behavior on Jetson-class profiles and the RTX reference profile;
- failure mode clarity when the provider, model, GPU, or dependency is absent;
- impact on confirmation, cancellation, stop, and barge-in acceptance cases.

## Default Change Gate

Do not make sherpa-onnx the default until:

- `ASR_BACKEND=sherpa_onnx` passes the same final-utterance protocol tests as
  Faster-Whisper;
- maintained profiles have exact dependency and model provenance;
- documentation, release notes, and compatibility claims distinguish
  implementation, automated verification, target validation, and release
  readiness;
- retained evidence shows equal or better latency and recognition quality for
  the intended deployment profile;
- emergency, stop, cancel, silence, unusable-audio, confirmation, timeout, and
  fallback semantics remain unchanged.

## Open Questions

- Which sherpa-onnx model should be evaluated first for English, Chinese, and
  mixed Chromie commands?
- Should the first sherpa-onnx profile prioritize RTX/GPU performance, Jetson
  deployment, or CPU-only fallback?
- What transcript metadata, if any, should be exposed to Router and Agent
  without letting ASR become an intent router?
- Does streaming ASR materially improve Chromie's barge-in and turn-taking once
  host VAD already owns utterance boundaries?
