FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
# 開発用（compose.override.yml）だけ pytest などの開発用の部品も入れる。本番のイメージには入れない
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then uv sync --locked; else uv sync --locked --no-dev; fi
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home appuser
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]