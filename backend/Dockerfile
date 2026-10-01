FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY backend/ /app/

EXPOSE 8000

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]