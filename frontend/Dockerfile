FROM ghcr.io/astral-sh/uv:0.8.22 AS uv

FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install --no-install-recommends -y \
    ca-certificates \
    libasound2 \
    libegl1 \
    libfontconfig1 \
    libgl1 \
    libgl1-mesa-dri \
    libglu1-mesa \
    libopenal1 \
    libwayland-client0 \
    libx11-6 \
    libxcursor1 \
    libxext6 \
    libxi6 \
    libxinerama1 \
    libxkbcommon-x11-0 \
    libxrandr2 \
    libxrender1 \
    libxxf86vm1 \
    mesa-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY frontend/ ./frontend/

RUN useradd --create-home --uid 1000 arcade
USER arcade

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

CMD ["python", "-m", "frontend.arcade"]
