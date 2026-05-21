# GitHub Master Merge Notes

Source inspected: `https://github.com/TimeTreker/chromie.git`, branch `master`.

## What was merged from GitHub master

- Added `LICENSE` because the online repository declares Apache-2.0.
- Added `.env.example` so laptop-specific runtime values can be copied safely.
- Added updated versions of `FINAL_RUNTIME_NOTES.md` and `MINIMAL_TTS_FIX_NOTES.md`.
- Added optional proxy support for ASR/TTS/Ollama containers and Docker builds:
  - `HTTP_PROXY`
  - `HTTPS_PROXY`
  - `NO_PROXY`
  - `host.docker.internal:host-gateway`
- Added explicit `chromie-net` Docker network.
- Added cache/data placeholder directories:
  - `hf_cache/.gitkeep`
  - `ollama_data/.gitkeep`
  - `recordings/.gitkeep`
- Added `llm.md` as a compatibility pointer to `llm_context.md`.

## What was intentionally not taken from GitHub master

- RTX 5090 / Blackwell defaults were not adopted.
- `CUDA_ARCHITECTURES=120` was not adopted for this laptop package.
- `TTS_N_GPU_LAYERS=99` was not adopted.
- The TTS source bind mount `./tts:/app` was not restored because it can hide image-built files and make production behavior less reproducible.
- Machine-specific `orchestrator/.env.local` is not included; use `orchestrator/.env.local.example`.

## Correct RTX 4090 Laptop GPU defaults

```env
TTS_CUDA_ARCH=89
TTS_N_GPU_LAYERS=-1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

## Publishing to GitHub

I cannot push to GitHub from this environment because no authenticated GitHub credential is available. To publish:

```bash
git clone https://github.com/TimeTreker/chromie.git
cd chromie
rsync -a --delete /path/to/extracted/chromie/ ./
git status
git add .
git commit -m "Merge RTX 4090 laptop GPU fix and runtime docs"
git push origin master
```

If your default branch is `main`, replace `master` with `main` in the final command.
