ARG PYTHON_IMAGE=python:3.12.10-slim-bookworm
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/app ./app
COPY agent-skills ./agent-skills
COPY shared/chromie_contracts ./chromie_contracts
COPY shared/chromie_runtime ./chromie_runtime

# Validate the packaged import layout during image construction. Source-tree
# imports must not survive until the container restart loop.
RUN python -c "from app.capabilities.catalog import CapabilityCatalog; from chromie_contracts.soridormi_body_contract import normalize_soridormi_body_contract; assert CapabilityCatalog and callable(normalize_soridormi_body_contract)"

EXPOSE 8092

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8092"]
