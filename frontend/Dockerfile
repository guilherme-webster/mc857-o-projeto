FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app

RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates mesa-utils libgl1 libgl1-mesa-dri libglu1-mesa libegl1 \
    libx11-6 libxext6 libxrender1 libxi6 libxcursor1 libxrandr2 libxinerama1 \
    libxkbcommon-x11-0 libxxf86vm1 libfontconfig1 libasound2 libopenal1 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY frontend/ ./frontend/

CMD ["python", "-m", "frontend.arcade"]
