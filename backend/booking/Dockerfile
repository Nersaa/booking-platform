# syntax=docker/dockerfile:1.7
# Build context: backend/ (the folder with all services and the shared contracts).

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src/booking

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=contracts,target=/src/contracts,rw \
    --mount=type=bind,source=booking/uv.lock,target=uv.lock \
    --mount=type=bind,source=booking/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-editable --no-install-project


FROM python:3.13-slim AS runtime
# Metrics of all worker processes are merged from this directory (a tmpfs in Compose).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/metrics

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app \
    && install -d -o app -g app /tmp/metrics

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app booking/alembic.ini /app/
COPY --chown=app:app booking/migrations /app/migrations
COPY --chown=app:app booking/app /app/app
WORKDIR /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
