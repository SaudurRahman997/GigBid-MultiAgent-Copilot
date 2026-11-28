# GigBid MCP servers (portfolio | marketplace | workspace) - one image, the command picks the server.
#   docker build -f mcp_servers/Dockerfile -t gigbid-mcp .
#   docker run gigbid-mcp python -m mcp_servers.portfolio
FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY agent ./agent
COPY rag ./rag
COPY mcp_servers ./mcp_servers
ENV PATH="/app/.venv/bin:$PATH" \
    MCP_HOST=0.0.0.0 \
    MCP_DATA_DIR=/app/data \
    FASTEMBED_CACHE_PATH=/app/var/models \
    GIGBID_UPLOAD_DIR=/app/uploads

# verify_claims downloads its models and caches embeddings under /app/var (a volume in compose)
RUN useradd --create-home --uid 10001 gigbid && mkdir -p /app/var && chown gigbid /app/var
USER gigbid
EXPOSE 8201 8202 8203
CMD ["python", "-m", "mcp_servers.portfolio"]
