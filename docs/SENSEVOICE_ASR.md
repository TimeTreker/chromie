# SenseVoice ASR

## Decision

Chromie uses sherpa-onnx SenseVoice as its single supported ASR runtime.
The previous alternate runtime and backend-selection path have been retired.
Historical comparison evidence remains available through Git history rather
than through a second production dependency.

This decision follows the maintained profiles and current target evidence: all
supported profiles already select the same multilingual SenseVoice model, while
the alternate backend added dependency weight, configuration branches, model
locks, and tests without serving a maintained deployment.

## Responsibility boundary

The host Orchestrator owns:

- microphone capture;
- VAD and utterance boundaries;
- barge-in and interruption;
- ASR timeout handling;
- forwarding recognized text into Router and Agent reasoning.

The ASR service owns:

- loading the pinned local SenseVoice model;
- accepting one complete PCM16 utterance;
- returning one normalized final transcript;
- reporting model identity and provider health.

ASR must not use phrase tables, regexes, or transcript content to decide normal
robot intent. Recognized text continues through the language-model reasoning
path.

## Runtime contract

- WebSocket service: `chromie-asr`, normally port `9001`.
- Protocol mode: `ASR_MODE=final` only.
- Backend identity reported in health: `sherpa_onnx`.
- Model family: SenseVoice through `OfflineRecognizer.from_sense_voice`.
- Host VAD remains authoritative; the service receives complete utterances.
- Blocking inference runs through the bounded `TranscriptionExecutor` rather
  than on the WebSocket event loop.
- Startup performs a synthetic warm-up decode before accepting requests unless
  explicitly disabled.

## Model and dependency provenance

Maintained profiles point to:

```text
/root/.cache/huggingface/sherpa-onnx/
sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
```

The exact source and revision are locked in `release/model-lock.json`. The ASR
image pins sherpa-onnx in `asr/requirements.txt`; x86_64 installs the CUDA wheel
and ARM profiles install the CPU wheel.

## Evaluation

Use `scripts/evaluate_asr_accuracy.py` for repeatable WER, CER, decode-time, and
real-time-factor measurement. The built-in `sensevoice-smoke` set is only a
sanity check. Product claims require a retained JSONL manifest covering the
intended language, room, microphone, and robot-command distribution.

Required evidence before expanding voice support:

- English, Chinese, and mixed-command accuracy;
- noisy-room and short-command behavior;
- physical microphone latency and endpoint behavior;
- CUDA and CPU provider startup/failure clarity;
- silence and unusable-audio handling;
- unchanged stop, cancel, emergency, confirmation, timeout, and barge-in
  semantics;
- model revision, service image, and hardware profile provenance.

## Future ASR changes

A future model or streaming protocol is a new architecture decision. It must be
introduced with its own dependency lock, model provenance, compatibility tests,
and retained target evidence. It should not be added as an unqualified runtime
fallback.
