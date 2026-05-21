# Final Runtime Notes

This package keeps the tested host-orchestrator architecture from the GitHub `master` baseline and merges it with the RTX 4090 Laptop GPU fix.

## Runtime architecture

```text
Host local orchestrator
  -> sounddevice microphone/VAD
  -> Docker ASR websocket ws://localhost:9001
  -> Docker Ollama http://localhost:11434
  -> Docker TTS websocket ws://localhost:5000
  -> sounddevice speaker playback
```

## Final TTS fixes preserved

- `TTS_CONTEXT_SIZE=4096`
- `TTS_MAX_LENGTH=4096`
- Text normalization and invalid-text filtering in both orchestrator and TTS server
- Retry handling for empty OuteTTS generations
- CUDA-enabled `llama-cpp-python` is installed last in the TTS image
- Runtime `LD_LIBRARY_PATH` does not include CUDA stub libraries
- `cfg.device="cuda"`
- `TTS_N_GPU_LAYERS=-1` for full llama.cpp layer offload

## Why 4096 still matters

OuteTTS prompts can use many prompt tokens before audio generation starts. Keeping both context and max length at 4096 avoids the old failure where too little room remained for generated audio tokens, which could lead to empty DAC frames and `torch.cat(): expected a non-empty list of Tensors`.

## RTX 4090 Laptop GPU-specific correction

The online GitHub `master` branch included RTX 5090 / Blackwell notes and `CUDA_ARCHITECTURES=120` in places. This package is corrected for RTX 4090 Laptop GPU:

```env
TTS_CUDA_ARCH=89
TTS_N_GPU_LAYERS=-1
```
