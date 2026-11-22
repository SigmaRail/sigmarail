FROM golang:1.27-alpine AS builder
RUN apk add --no-cache git
WORKDIR /src

ARG TSIDP_REVISION=3c4364fa73369fc641652272b55f67c7fb73fbca
RUN git init && git remote add origin https://github.com/tailscale/tsidp.git \
    && git fetch --depth 1 origin ${TSIDP_REVISION} \
    && git checkout --detach FETCH_HEAD
COPY deploy/tsidp/metadata.patch /tmp/metadata.patch
RUN git apply /tmp/metadata.patch
RUN go test ./server -run '^TestMetadataEndpoints$' -count=1

ARG VERSION=sigmarail-dcr-relay
RUN CGO_ENABLED=0 go build -a -installsuffix cgo \
    -ldflags "-s -w -X github.com/tailscale/tsidp/server.version=${VERSION}" \
    -o /tsidp-server .

FROM alpine:3.22
RUN apk --no-cache add ca-certificates \
    && addgroup -g 1001 -S app \
    && adduser -u 1001 -S app \
    && mkdir -p /data \
    && chown app:app /data
WORKDIR /app
COPY --from=builder /tsidp-server /tsidp-server
USER app:app
ENTRYPOINT ["/tsidp-server"]
