# GigSim marketplace simulator. Build from the repo root:
#   docker build -f gigsim/Dockerfile -t gigbid-gigsim .
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

COPY gigsim ./gigsim
ENV PATH="/app/.venv/bin:$PATH" \
    GIGSIM_DATA_DIR=/app/data

RUN useradd --create-home --uid 10001 gigsim
USER gigsim
EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8100/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "gigsim.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
