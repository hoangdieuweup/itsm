FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
RUN uv sync --no-dev && chmod +x scripts/*.sh

ENV PATH="/srv/.venv/bin:${PATH}"

RUN useradd -m appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000
CMD ["./scripts/start.sh"]
