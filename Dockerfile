FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
RUN uv sync --locked --no-dev --no-install-project --no-install-workspace

COPY alembic.ini ./
COPY backend/migrations backend/migrations
COPY backend/src backend/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend/src"

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn nexora_backend.main:app --host 0.0.0.0 --port 8000"]
