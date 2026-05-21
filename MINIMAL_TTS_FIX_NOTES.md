# Minimal TTS Fix Notes

This package includes the GitHub `master` minimal TTS stability fixes plus the accepted RTX 4090 Laptop GPU CUDA/offload fix.

## TTS server behavior

`tts/server.py` includes:

- Text normalization
- Minimum and maximum text length guards
- Retry around OuteTTS generation
- Defensive handling for empty audio generation
- CUDA llama.cpp configuration with `cfg.device="cuda"`
- `n_gpu_layers=-1` to offload all possible llama.cpp layers
- Verbose llama.cpp loading logs so GPU offload can be verified

## Environment additions

`.env` and `.env.example` include:

```env
TTS_MIN_TEXT_CHARS=4
TTS_MAX_TEXT_CHARS=220
TTS_GENERATION_RETRIES=2
TTS_TEMPERATURE=0.4
TTS_REPETITION_PENALTY=1.1
TTS_MAX_CONCURRENT_SYNTHESIS=1
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

## Docker / llama-cpp correction

`tts/requirements.txt` intentionally does not own the final `llama-cpp-python` installation. The Dockerfile installs normal requirements first, uninstalls any CPU wheel, then builds CUDA-enabled `llama-cpp-python` last:

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
RUN pip uninstall -y llama-cpp-python || true &&     LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH}     LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:${LIBRARY_PATH}     CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=${TTS_CUDA_ARCH}"     FORCE_CMAKE=1     pip install --no-cache-dir --no-deps --force-reinstall --no-binary=llama-cpp-python llama-cpp-python
```

At runtime the CUDA stub path is not left in `LD_LIBRARY_PATH`; the container must use the real NVIDIA driver libraries exposed by NVIDIA Container Toolkit.
