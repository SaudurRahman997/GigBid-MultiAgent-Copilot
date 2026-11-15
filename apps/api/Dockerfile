# GigBid API (FastAPI + LangGraph graphs). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t gigbid-api .
FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent ./agent
COPY rag ./rag
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY mcp_servers ./mcp_servers
ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 gigbid && mkdir -p /app/var && chown gigbid /app/var
USER gigbid
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
