ARG SB_MIRROR_REPOSITORY=''
ARG SB_PULL_THROUGH_CACHE_REPOSITORY=''
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

ARG SIGMARAIL_SOURCE_DIR=.
ARG SIGMARAIL_BUILD_REVISION=unknown
ARG SIGMARAIL_BUILD_BRANCH=unknown
ARG SIGMARAIL_BUILD_TREE=unknown

WORKDIR /pkgs

COPY ${SIGMARAIL_SOURCE_DIR}/packages/backend/uv.lock ${SIGMARAIL_SOURCE_DIR}/packages/backend/pyproject.toml /pkgs/
RUN uv sync --frozen \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ${SIGMARAIL_SOURCE_DIR}/packages/backend/ /app/
COPY ${SIGMARAIL_SOURCE_DIR}/src/sigmarail/ /workspace/sigmarail/
COPY ${SIGMARAIL_SOURCE_DIR}/studio/api/ /workspace/api/
COPY ${SIGMARAIL_SOURCE_DIR}/studio/screens/ /workspace/screens/
COPY ${SIGMARAIL_SOURCE_DIR}/studio/sigmarail_studio_mcp/ /workspace/sigmarail_studio_mcp/
COPY VeraBase/src/vera_query_core/ /opt/vera-base/src/vera_query_core/
COPY VeraBase/src/vera/config.py VeraBase/src/vera/__init__.py /opt/vera-base/src/vera/
COPY VeraBase/sql/schema/ /opt/vera-base/sql/schema/
COPY VeraSpec/src/vera_spec/ /opt/vera-spec/src/vera_spec/

RUN chmod +x /app/scripts/runtime/*.sh

FROM backend_build AS static_files
ENV HASHID_FIELD_SALT='' \
    DJANGO_PARENT_HOST='' \
    DJANGO_SECRET_KEY='build' \
    DB_CONNECTION='{"dbname":"build","username":"build","password":"build","host":"db","port":5432}' \
    REDIS_CONNECTION=redis://redis:6379 \
    WORKERS_EVENT_BUS_NAME='' \
    PYTHONPATH=/workspace:/pkgs/.venv/lib/python3.11/site-packages

RUN ./scripts/runtime/build_static.sh


FROM backend_build AS backend
COPY --from=static_files /app/static /app/static
ENV PYTHONPATH=/workspace:/pkgs/.venv/lib/python3.11/site-packages \
    PATH=$PATH:/pkgs/.venv/bin \
    SIGMARAIL_BUILD_REVISION=${SIGMARAIL_BUILD_REVISION} \
    SIGMARAIL_BUILD_BRANCH=${SIGMARAIL_BUILD_BRANCH} \
    SIGMARAIL_BUILD_TREE=${SIGMARAIL_BUILD_TREE}

CMD ["./scripts/runtime/run.sh"]
