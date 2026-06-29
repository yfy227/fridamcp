# FridaMCP Dockerfile
# Multi-stage build for a containerized FridaMCP server
#
# Build:
#   docker build -t fridamcp .
#
# Run (stdio mode, for Claude Desktop):
#   docker run -i --rm fridamcp
#
# Run (HTTP mode, for remote access):
#   docker run -p 8768:8768 --rm fridamcp -t http -p 8768
#
# Run (SSE mode):
#   docker run -p 8768:8768 --rm fridamcp -t sse -p 8768

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy project files
COPY pyproject.toml setup.py ./
COPY fridamcp/ ./fridamcp/
COPY injector/ ./injector/
COPY README.md ./

# Install the package
RUN pip install --no-cache-dir .

# ============ Runtime stage ============
FROM python:3.11-slim

# Install runtime dependencies
# adb is needed for Android device communication
# apktool and zipalign are needed for APK injection
RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    openjdk-17-jre-headless \
    zipalign \
    apksigner \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/fridamcp /usr/local/bin/fridamcp

# Copy project files for injector access
COPY --from=builder /build/fridamcp/ /app/fridamcp/
COPY --from=builder /build/injector/ /app/injector/

WORKDIR /app

# Default to stdio transport (for Claude Desktop / Cursor)
# Override with: docker run fridamcp -t http -p 8768
ENTRYPOINT ["fridamcp"]
CMD ["-t", "stdio"]

# Metadata
LABEL org.opencontainers.image.title="FridaMCP"
LABEL org.opencontainers.image.description="Frida MCP Server - AI-powered dynamic instrumentation"
LABEL org.opencontainers.image.source="https://github.com/yfy227/fridamcp"
LABEL org.opencontainers.image.licenses="MIT"
