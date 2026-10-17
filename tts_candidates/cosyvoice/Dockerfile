ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

# Supplied by docker-compose.yml from .env.common (locked in release/model-lock.json).
ARG COSYVOICE3_SOURCE_REVISION
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ARG TTS_CUDA_ARCH=89
ARG CHROMIE_BUILD_PROFILE=unknown
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy
ARG NO_PROXY
ARG no_proxy

LABEL org.chromie.hardware-profile="${CHROMIE_BUILD_PROFILE}" \
      org.chromie.tts-cuda-arch="${TTS_CUDA_ARCH}"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    ffmpeg \
    git \
    libsndfile1 \
    libsox-dev \
    python3 \
    python3-pip \
    sox \
    && rm -rf /var/lib/apt/lists/*

# Ubuntu 22.04 ships Python 3.10, below the repository's declared 3.11 floor
# (shared/pyproject.toml, scripts/check_python_runtime.py) for the shared tts/*
# modules this image runs. Bootstrap a pinned uv and build the venv on a
# managed CPython 3.11. The interpreter is pinned exactly; 3.11.16 is the
# newest 3.11 build in uv 0.12.20's embedded download list, so changing either
# pin is a deliberate image change.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN python3 -m pip install --no-cache-dir uv==0.12.20 && \
    uv python install 3.11.16 && \
    uv venv --seed --python 3.11.16 /opt/venv && \
    /opt/venv/bin/python -c "import sys; assert sys.version_info[:3] == (3, 11, 16), sys.version"
ENV PATH=/opt/venv/bin:$PATH
RUN pip install pip==25.1.1 setuptools==80.9.0 wheel==0.45.1

RUN pip install --index-url "${PYTORCH_INDEX_URL}" \
    torch==2.10.0 torchaudio==2.10.0

RUN git init /opt/CosyVoice && \
    git -C /opt/CosyVoice remote add origin https://github.com/FunAudioLLM/CosyVoice.git && \
    git -C /opt/CosyVoice fetch --depth 1 origin "${COSYVOICE3_SOURCE_REVISION}" && \
    git -C /opt/CosyVoice checkout --detach FETCH_HEAD && \
    git -C /opt/CosyVoice submodule update --init --recursive --depth 1

# Most of these pins come from CosyVoice's own requirements at
# COSYVOICE3_SOURCE_REVISION, not from the repository requirements files, and
# they intentionally differ from them (for example numpy, pydantic,
# transformers, librosa and soundfile). numpy stays on 1.26.x
# because onnxruntime-gpu 1.18.1 below is built against the NumPy 1.x ABI, so
# it cannot move to the repository's numpy 2.x. The Chromie modules copied in
# (tts/candidate_server.py and its imports) use only the standard library and
# websockets, whose pin matches tts/requirements.txt. The CosyVoice server
# dependencies (fastapi, uvicorn) are not installed: candidate_server.py serves
# WebSockets itself.
RUN pip install \
      conformer==0.3.2 \
      diffusers==0.29.0 \
      gdown==5.1.0 \
      huggingface-hub==0.31.4 \
      hydra-core==1.3.2 \
      HyperPyYAML==1.2.3 \
      inflect==7.3.1 \
      librosa==0.10.2 \
      modelscope==1.20.0 \
      networkx==3.1 \
      numpy==1.26.4 \
      omegaconf==2.3.0 \
      onnx==1.16.0 \
      protobuf==4.25.8 \
      pyarrow==18.1.0 \
      pydantic==2.7.0 \
      soundfile==0.12.1 \
      transformers==4.51.3 \
      websockets==16.0 \
      wetext==0.0.4 \
      x-transformers==2.11.24

# TorchCodec 0.10 is the official match for Torch 2.10. Decode the shared
# reference WAV on CPU; candidate inference remains on CUDA.
RUN pip install --no-deps torchcodec==0.10.0

# Both imports are resolved while HyperPyYAML constructs the inference model:
# Matcha's logger uses Lightning and the referenced dataset processor imports
# PyWorld even though training data isn't opened by the service.
RUN pip install \
      lightning==2.2.4 \
      matplotlib==3.7.5 \
      pytorch-lightning==2.2.4 \
      pyworld==0.3.4 \
      rich==13.7.1 \
      tensorboard==2.14.0 \
      wget==3.2

# Upstream 20231117 metadata imports pkg_resources during its build. Current
# isolated build environments no longer provide it, so build against the
# already pinned runtime environment.
RUN pip install --no-build-isolation --no-deps \
      openai-whisper==20231117 \
      tiktoken==0.13.0

RUN pip install \
    --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ \
    onnxruntime-gpu==1.18.1

ENV PYTHONPATH=/opt/CosyVoice:/opt/CosyVoice/third_party/Matcha-TTS
WORKDIR /app
COPY tts/provider.py tts/streaming_worker.py tts/candidate_provider.py tts/candidate_server.py tts/voice_catalog.py tts/settings.py ./
COPY tts_candidates/cosyvoice/provider_impl.py ./

EXPOSE 5000
CMD ["python", "candidate_server.py"]
