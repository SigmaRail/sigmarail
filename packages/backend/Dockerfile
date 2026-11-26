ARG SB_MIRROR_REPOSITORY=''
ARG SB_PULL_THROUGH_CACHE_REPOSITORY=''

##
# AppTension email renderer build stage
##
FROM node:20-slim AS email_builder

WORKDIR /build
RUN npm install -g pnpm@10

# This image is built with the FinanceProjects workspace as its context.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml nx.json tsconfig.base.json ./
COPY patches/ ./patches/
COPY packages/webapp-libs/ ./packages/webapp-libs/
COPY packages/webapp/package.json ./packages/webapp/package.json
COPY packages/internal/cli/package.json ./packages/internal/cli/package.json
COPY packages/internal/core/package.json ./packages/internal/core/package.json
COPY packages/internal/tools/package.json ./packages/internal/tools/package.json
COPY packages/internal/docs/package.json ./packages/internal/docs/package.json
COPY packages/internal/status-dashboard/package.json ./packages/internal/status-dashboard/package.json
COPY packages/contentful/package.json ./packages/contentful/package.json
COPY packages/infra/infra-shared/package.json ./packages/infra/infra-shared/package.json
COPY packages/infra/infra-core/package.json ./packages/infra/infra-core/package.json
COPY packages/backend/package.json ./packages/backend/package.json
COPY packages/workers/package.json ./packages/workers/package.json

RUN pnpm install --frozen-lockfile --ignore-scripts --filter "@sb/webapp-emails..."
RUN pnpm nx run webapp-emails:build

##
# Chamber installation stage
##

FROM ${SB_MIRROR_REPOSITORY}segment/chamber:2 AS chamber

##
# App build stage
##
FROM ${SB_PULL_THROUGH_CACHE_REPOSITORY}python:3.11-slim-bookworm AS backend_build

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off


RUN apt-get update && apt-get install -y gcc postgresql-client ca-certificates jq curl \
  && update-ca-certificates \
  && pip install --upgrade pip \
  && pip install --no-cache-dir setuptools uv==0.9.29 awscli==1.32.24


RUN curl -fsS https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get --no-install-recommends install -y nodejs

COPY --from=chamber /chamber /bin/chamber

ARG SIGMARAIL_BUILD_REVISION=unknown
ARG SIGMARAIL_BUILD_BRANCH=unknown
ARG SIGMARAIL_BUILD_TREE=unknown

WORKDIR /pkgs

COPY packages/sigmarail-spec/ /sigmarail-spec/
COPY packages/backend/uv.lock packages/backend/pyproject.toml /pkgs/
RUN uv sync --frozen \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packages/backend/ /app/
COPY --from=email_builder /build/packages/webapp-libs/webapp-emails/build/email-renderer/index.umd.js /app/scripts/runtime/email/renderer/index.umd.js
COPY src/sigmarail/ /workspace/sigmarail/
COPY src/sigmarail_lab/ /workspace/src/sigmarail_lab/
COPY studio/api/ /workspace/api/
COPY studio/screens/ /workspace/screens/
COPY studio/sigmarail_studio_mcp/ /workspace/sigmarail_studio_mcp/

RUN chmod +x /app/scripts/runtime/*.sh

FROM backend_build AS static_files
ENV HASHID_FIELD_SALT='' \
    DJANGO_PARENT_HOST='' \
    DJANGO_SECRET_KEY='build' \
    DB_CONNECTION='{"dbname":"build","username":"build","password":"build","host":"db","port":5432}' \
    REDIS_CONNECTION=redis://redis:6379 \
    WORKERS_EVENT_BUS_NAME='' \
    PYTHONPATH=/workspace:/workspace/src:/pkgs/.venv/lib/python3.11/site-packages

RUN ./scripts/runtime/build_static.sh


FROM backend_build AS backend
COPY --from=static_files /app/static /app/static
ENV PYTHONPATH=/workspace:/workspace/src:/pkgs/.venv/lib/python3.11/site-packages \
    PATH=$PATH:/pkgs/.venv/bin \
    SIGMARAIL_BUILD_REVISION=${SIGMARAIL_BUILD_REVISION} \
    SIGMARAIL_BUILD_BRANCH=${SIGMARAIL_BUILD_BRANCH} \
    SIGMARAIL_BUILD_TREE=${SIGMARAIL_BUILD_TREE}

CMD ["./scripts/runtime/run.sh"]
