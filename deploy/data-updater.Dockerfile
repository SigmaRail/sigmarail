FROM clickhouse/clickhouse-server:26.5 AS clickhouse-client

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/New_York

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates tzdata util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY --from=clickhouse-client /usr/bin/clickhouse /usr/local/bin/clickhouse
RUN ln -s /usr/local/bin/clickhouse /usr/local/bin/clickhouse-client \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin sigmarail \
    && mkdir -p /var/lib/sigmarail \
    && chown sigmarail:sigmarail /var/lib/sigmarail

WORKDIR /app
COPY pyproject.toml README.md ./
COPY packages/sigmarail-spec ./packages/sigmarail-spec
COPY src ./src
COPY scripts/daily-update.sh ./scripts/daily-update.sh

RUN pip install --no-cache-dir ./packages/sigmarail-spec \
    && pip install --no-cache-dir . \
    && chmod 0755 /app/scripts/daily-update.sh

USER sigmarail
VOLUME ["/var/lib/sigmarail"]
CMD ["python", "-m", "sigmarail.scheduler"]
