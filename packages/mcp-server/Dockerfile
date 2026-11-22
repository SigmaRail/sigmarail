# Apollo MCP Server Dockerfile for production deployments
# This dockerfile is used for deploying to platforms like Render.com

# Apollo MCP Server 2.2.1 supports MCP 2026-07-28 `server/discover` while
# retaining the legacy initialize protocol. Pin the multi-architecture index
# digest so local ARM64 and deployment AMD64 builds resolve reproducibly.
FROM ghcr.io/apollographql/apollo-mcp-server:v2.2.1@sha256:62a803f8348a4ac1f38ecce50e515e25cf5ffbd672e50b06a3f30b4051fa6c0f AS mcp-source

FROM segment/chamber:2 AS chamber

# Stage 2: Runtime image with shell support (Debian for glibc compatibility)
FROM debian:bookworm-slim

# Install CA certificates for HTTPS connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy Chamber for runtime secret loading
COPY --from=chamber /chamber /bin/chamber

# Apollo MCP Server v2 packages the binary under /usr/local/bin and no longer
# needs the Nix store copied into the runtime image.
COPY --from=mcp-source /usr/local/bin/apollo-mcp-server /usr/local/bin/apollo-mcp-server

# Copy operations and schema files
COPY packages/mcp-server/operations /app/operations
COPY packages/webapp-libs/webapp-api-client/graphql/schema /app/schema
COPY packages/mcp-server/custom-scalars.json /app/custom-scalars.json

# Copy entrypoint script
COPY packages/mcp-server/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Set environment variables (can be overridden at runtime)
ENV MCP_LOG_LEVEL=info
# GRAPHQL_ENDPOINT should be set at runtime (e.g., https://your-backend.onrender.com/api/graphql/)

# Expose the default port
EXPOSE 4000

# Use entrypoint script to generate config at runtime
ENTRYPOINT ["/app/docker-entrypoint.sh"]
