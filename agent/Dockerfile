ARG PYTHON_IMAGE=python:3.12.10-slim-bookworm
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY agent/requirements.txt .
# Package downloads live in BuildKit cache mounts outside the image: a changed
# dependency layer reinstalls from them instead of downloading every package again.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY agent/app ./app
COPY agent-skills ./agent-skills
# Agent code imports the shared packages as shared.chromie_contracts and
# shared.chromie_runtime, the same import root the host and tests use.
COPY shared/chromie_contracts ./shared/chromie_contracts
COPY shared/chromie_runtime ./shared/chromie_runtime

# Validate the packaged import layout during image construction. Source-tree
# imports must not survive until the container restart loop.
RUN python -c "from app.capabilities.catalog import CapabilityCatalog; from shared.chromie_contracts.soridormi_body_contract import normalize_soridormi_body_contract; assert CapabilityCatalog and callable(normalize_soridormi_body_contract)"

EXPOSE 8092

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8092"]
