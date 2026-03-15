# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app/src \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        p7zip-full \
        unar \
        unrar-free \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

FROM base AS deps-base

COPY backend/pyproject.toml backend/README.md backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --no-install-project

FROM deps-base AS deps-vision

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --no-install-project --extra ai-vision

FROM base AS runtime-base

COPY backend ./src/backend
COPY alembic ./src/alembic
COPY alembic.ini ./src/alembic.ini

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime-base AS backend-runtime

COPY --from=deps-base /app/.venv /app/.venv

FROM runtime-base AS backend-vision-runtime

COPY --from=deps-vision /app/.venv /app/.venv
