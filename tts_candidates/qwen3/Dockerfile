ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE}

ARG QWEN3_TTS_SOURCE_REVISION=022e286b98fbec7e1e916cb940cdf532cd9f488e
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    libsndfile1 \
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

RUN git init /opt/Qwen3-TTS && \
    git -C /opt/Qwen3-TTS remote add origin https://github.com/QwenLM/Qwen3-TTS.git && \
    git -C /opt/Qwen3-TTS fetch --depth 1 origin "${QWEN3_TTS_SOURCE_REVISION}" && \
    git -C /opt/Qwen3-TTS checkout --detach FETCH_HEAD

RUN pip install --no-deps /opt/Qwen3-TTS && \
    pip install \
      accelerate==1.12.0 \
      einops==0.8.1 \
      huggingface-hub==0.36.0 \
      librosa==0.11.0 \
      numpy==2.2.6 \
      onnxruntime==1.23.2 \
      safetensors==0.6.2 \
      soundfile==0.13.1 \
      sox==1.5.0 \
      transformers==4.57.3 \
      websockets==16.0

WORKDIR /app
COPY tts/provider.py tts/streaming_worker.py tts/candidate_provider.py tts/candidate_server.py ./
COPY tts_candidates/qwen3/provider_impl.py ./

EXPOSE 5000
CMD ["python", "candidate_server.py"]
