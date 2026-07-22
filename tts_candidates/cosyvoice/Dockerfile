ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

ARG COSYVOICE3_SOURCE_REVISION=074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128

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
    python3-dev \
    python3-pip \
    python3-venv \
    sox \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install pip==25.1.1 setuptools==80.9.0 wheel==0.45.1

RUN pip install --index-url "${PYTORCH_INDEX_URL}" \
    torch==2.10.0 torchaudio==2.10.0

RUN git init /opt/CosyVoice && \
    git -C /opt/CosyVoice remote add origin https://github.com/FunAudioLLM/CosyVoice.git && \
    git -C /opt/CosyVoice fetch --depth 1 origin "${COSYVOICE3_SOURCE_REVISION}" && \
    git -C /opt/CosyVoice checkout --detach FETCH_HEAD && \
    git -C /opt/CosyVoice submodule update --init --recursive --depth 1

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
      uvicorn==0.30.0 \
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
COPY tts/provider.py tts/streaming_worker.py tts/candidate_provider.py tts/candidate_server.py ./
COPY tts_candidates/cosyvoice/provider_impl.py ./

EXPOSE 5000
CMD ["python", "candidate_server.py"]
