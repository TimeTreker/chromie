ARG ASR_CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
FROM ${ASR_CUDA_IMAGE}

# Proxies arrive as Docker's predefined build args (HTTP_PROXY, NO_PROXY, ...): RUN sees
# them without an ARG line, and undeclared they stay out of the layer cache key and
# the image history, so building with or without a proxy reuses the same layers.

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY requirements.txt .
# Package downloads live in BuildKit cache mounts outside the image: a changed
# dependency layer reinstalls from them instead of downloading every package again.
RUN --mount=type=cache,target=/root/.cache/pip pip install pip==25.1.1 setuptools==80.9.0 wheel==0.45.1 && pip install -r requirements.txt

COPY backends.py server.py settings.py transcription.py ./
CMD ["python", "server.py"]
