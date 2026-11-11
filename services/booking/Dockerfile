# syntax=docker/dockerfile:1.7
# Build context: repository root.

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src/services/booking

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=libs,target=/src/libs,rw \
    --mount=type=bind,source=services/booking/uv.lock,target=uv.lock \
    --mount=type=bind,source=services/booking/pyproject.toml,target=pyproject.toml \
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
COPY --chown=app:app services/booking/alembic.ini services/booking/logging.json /app/
COPY --chown=app:app services/booking/migrations /app/migrations
COPY --chown=app:app services/booking/app /app/app
WORKDIR /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--log-config", "logging.json"]
