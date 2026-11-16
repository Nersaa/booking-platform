# syntax=docker/dockerfile:1.7
# Build context: backend/ (the folder with all services and the shared contracts).

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src/payment-mock

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=payment-mock/uv.lock,target=uv.lock \
    --mount=type=bind,source=payment-mock/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app payment-mock/payment_mock /app/payment_mock
WORKDIR /app
USER app

EXPOSE 8000
# One worker: the mock keeps its state in memory.
CMD ["uvicorn", "payment_mock.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
