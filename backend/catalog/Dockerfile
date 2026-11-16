# syntax=docker/dockerfile:1.7
# Build context: backend/ (the folder with all services and the shared contracts).

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src/catalog

# Shared libraries are installed as regular packages (--no-editable), so the
# runtime image needs only the virtualenv.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=contracts,target=/src/contracts,rw \
    --mount=type=bind,source=catalog/uv.lock,target=uv.lock \
    --mount=type=bind,source=catalog/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-editable --no-install-project

COPY catalog/ /app/
WORKDIR /app
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=sqlite:// REDIS_URL=redis://localhost \
    /opt/venv/bin/python manage.py collectstatic --noinput


FROM python:3.13-slim AS runtime
# Metrics of all worker processes are merged from this directory (a tmpfs in Compose).
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/metrics

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app \
    && install -d -o app -g app /var/lib/catalog/keys /tmp/metrics

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app
WORKDIR /app
USER app

EXPOSE 8000
# No access log here: the gateway logs every request with its id.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
