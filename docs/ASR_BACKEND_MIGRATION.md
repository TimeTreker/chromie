# ASR Backend Migration Plan

This document records the staged migration from Faster-Whisper to sherpa-onnx
while preserving Chromie's final-utterance voice contract.

## Goal

Run the current final-utterance WebSocket contract on sherpa-onnx SenseVoice as
the maintained default, while keeping Faster-Whisper as a selectable fallback.
The migration should improve local realtime speech operation only when
benchmarks and retained evidence show that it preserves or improves the current
user-facing contract.

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
- The supported default backend is `ASR_BACKEND=sherpa_onnx` with `ASR_MODE=final`.
- The maintained sherpa-onnx SenseVoice model path and revision lock are
  managed through hardware profiles and `release/model-lock.json`.
- ASR startup performs a synthetic warm-up decode before opening the WebSocket
  server; inference then runs off the event loop behind a bounded executor.
- Faster-Whisper remains installed and selectable with `ASR_BACKEND=faster_whisper`
  for fallback and comparison.

## Implementation Sequence

1. Done: add the backend boundary while preserving the current WebSocket protocol and
   the Faster-Whisper path.
2. Done: add configuration and health metadata for `ASR_BACKEND` and `ASR_MODE`.
3. Done: add a non-streaming sherpa-onnx backend behind
   `ASR_BACKEND=sherpa_onnx`, using complete utterances and returning only
   `final` results at first.
4. Done for the first evaluation path: pin sherpa-onnx runtime dependencies and
   selected SenseVoice source metadata in the release-provenance path.
5. Done: add Level A tests for backend selection, fail-closed unavailable providers,
   and final transcript normalization.
6. Done: add Level B smoke checks that report backend name, mode, model
   identity, latency, and service health for a downloaded SenseVoice model.
7. Done for the initial local evidence set: run A/B WER/CER/RTF comparison on
   clean SenseVoice English and Chinese samples and switch maintained defaults.
8. Done for the desktop path: add startup warm-up and make CUDA the maintained
   desktop provider default.
9. Next: expand retained evidence with physical microphone, noisy-room, and robot command benchmarks.

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

## Remaining Release Evidence

Keep the sherpa-onnx default under active evidence until:

- `ASR_BACKEND=sherpa_onnx` passes the same final-utterance protocol tests as
  Faster-Whisper;
- maintained profiles have exact dependency and model provenance;
- documentation, release notes, and compatibility claims distinguish
  implementation, automated verification, target validation, and release
  readiness;
- retained evidence shows equal or better latency and recognition quality for
  the intended deployment profile;
- emergency, stop, cancel, silence, unusable-audio, confirmation, timeout, and
  fallback semantics remain unchanged in physical microphone acceptance.

## Open Questions

- Does SenseVoice zh/en/yue remain the right first model after mixed-command
  benchmarks, or should a Whisper/Paraformer sherpa-onnx model be added too?
- Should the first maintained sherpa-onnx profile prioritize RTX/GPU performance, Jetson
  deployment, or CPU fallback?
- What transcript metadata, if any, should be exposed to Router and Agent
  without letting ASR become an intent router?
- Does streaming ASR materially improve Chromie's barge-in and turn-taking once
  host VAD already owns utterance boundaries?
