# syntax=docker/dockerfile:1
# Build from the repo root:  docker build -f docker/Dockerfile -t cashier-checker:0.1.0 .
#
# Stage 1 builds the React UI; stage 2 is the CUDA runtime with Python deps, ffmpeg and model
# weights baked in, so the container needs no internet after build. Runs under docker compose
# (as user "app") and on GPU pod platforms such as RunPod (starts as root, drops to "app").

FROM node:22.12.0-bookworm-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# cuDNN variant: onnxruntime-gpu and similar need it; torch wheels bring their own CUDA libs.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # fully offline at runtime: never try to reach a model hub
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/models/hf \
    TORCH_HOME=/models/torch \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini util-linux \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /data && chown app:app /data

COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv

WORKDIR /app
# Dependencies first for layer caching; Python 3.11 comes from uv (Ubuntu 24.04 ships 3.12).
# The "ml" extra holds the analyzer's deps, pinned in uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv python install 3.11 \
 && uv sync --frozen --no-dev --extra ml --no-install-project --python 3.11

# Weights before source: editing code must not re-copy gigabytes. Owned by app because HF/torch
# write lock and cache files next to the weights.
COPY --chown=app:app models/ /models/

COPY src/ ./src/
COPY config/ ./config/
COPY schemas/ ./schemas/
COPY scripts/ ./scripts/
COPY --from=ui /ui/dist ./frontend/dist
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PATH=/opt/venv/bin:$PATH \
    DATA_DIR=/data \
    STATIC_DIR=/app/frontend/dist \
    RULES_PATH=/app/config/rules_legal.yaml

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=4 \
  CMD python -c "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
