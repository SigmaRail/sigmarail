ARG SIGMARAIL_BUILD_REVISION=unknown
ARG SIGMARAIL_BUILD_BRANCH=unknown
ARG SIGMARAIL_BUILD_TREE=unknown

FROM python:3.11-slim-bookworm

ARG SIGMARAIL_BUILD_REVISION=unknown
ARG SIGMARAIL_BUILD_BRANCH=unknown
ARG SIGMARAIL_BUILD_TREE=unknown

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

RUN apt-get update \
  && apt-get install -y --no-install-recommends gcc postgresql-client ca-certificates curl docker.io \
  && pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir uv==0.9.29 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /pkgs
COPY packages/sigmarail-spec/ /sigmarail-spec/
COPY packages/backend/uv.lock packages/backend/pyproject.toml ./
RUN uv sync --frozen

WORKDIR /app
COPY packages/backend/ /app/
COPY src/sigmarail/ /workspace/sigmarail/
COPY src/sigmarail_lab/ /workspace/src/sigmarail_lab/
COPY studio/api/ /workspace/api/
COPY studio/screens/ /workspace/screens/
COPY studio/sigmarail_studio_mcp/ /workspace/sigmarail_studio_mcp/
COPY trading_lab/ /workspace/trading_lab/
COPY deploy/lean/lean.json /workspace/deploy/lean/lean.json
COPY packages/backtest-worker/entrypoint.sh /app/scripts/runtime/backtest-worker-entrypoint.sh
COPY deploy/lean/lean.json /app/lean-workspace/lean.json

RUN uv pip install --python /pkgs/.venv/bin/python lean==1.0.229 \
  && chmod +x /app/scripts/runtime/backtest-worker-entrypoint.sh

ENV PYTHONPATH=/workspace:/workspace/src:/pkgs/.venv/lib/python3.11/site-packages \
    PATH=/pkgs/.venv/bin:$PATH \
    SIGMARAIL_BUILD_REVISION=${SIGMARAIL_BUILD_REVISION} \
    SIGMARAIL_BUILD_BRANCH=${SIGMARAIL_BUILD_BRANCH} \
    SIGMARAIL_BUILD_TREE=${SIGMARAIL_BUILD_TREE}

ENTRYPOINT ["/app/scripts/runtime/backtest-worker-entrypoint.sh"]
