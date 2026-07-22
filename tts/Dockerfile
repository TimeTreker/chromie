ARG TTS_CUDA_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu24.04
FROM ${TTS_CUDA_IMAGE}

ARG TTS_CUDA_ARCH=89
ARG CHROMIE_BUILD_PROFILE=unknown

LABEL org.chromie.hardware-profile="${CHROMIE_BUILD_PROFILE}" \
      org.chromie.tts-cuda-arch="${TTS_CUDA_ARCH}"
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy
ARG NO_PROXY
ARG no_proxy

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
    cmake \
    git \
    ninja-build \
    pkg-config \
    libsndfile1 \
    ca-certificates \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH

RUN pip install pip==25.1.1 setuptools==80.9.0 wheel==0.45.1

RUN if [ -f /usr/local/cuda/lib64/stubs/libcuda.so ]; then \
      ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1; \
    fi

ENV CUDA_HOME=/usr/local/cuda
ENV CUDAToolkit_ROOT=/usr/local/cuda
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}
ENV LIBRARY_PATH=/usr/local/cuda/lib64:${LIBRARY_PATH}
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

COPY requirements.txt .

# Install a torch/torchaudio pair built for the same CUDA runtime as the
# base image. Installing these from the default PyPI index can select a
# newer CUDA build (for example cu130), which then fails at import time
# because libcudart.so.13 is not present in the CUDA 12.8 container.
RUN pip install --no-cache-dir \
    --index-url "${PYTORCH_INDEX_URL}" \
    torch==2.10.0 \
    torchaudio==2.10.0

RUN pip install --no-cache-dir -r requirements.txt

# Reinstall CUDA-enabled llama-cpp-python LAST.
# This overwrites any CPU version installed by outetts.
RUN pip uninstall -y llama-cpp-python || true && \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH} \
    LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:${LIBRARY_PATH} \
    CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=${TTS_CUDA_ARCH}" \
    FORCE_CMAKE=1 \
    pip install --no-cache-dir --no-deps --force-reinstall --no-binary=llama-cpp-python llama-cpp-python==0.3.9

COPY server.py cancellable_worker.py model_sources.py performance.py provider.py oute_provider.py ./
COPY create_speaker.py .

RUN mkdir -p /app/speakers

EXPOSE 5000

CMD ["python", "server.py"]
