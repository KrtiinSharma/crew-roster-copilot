# Backend image for Google Cloud Run (also runs anywhere: docker run -p 8080:8080).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first so code changes don't reinstall them
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# Run as an unprivileged user
RUN useradd -m -u 1000 user && chown -R user /app
USER user

EXPOSE 8080
CMD ["sh", "-c", "exec uv run --no-sync uvicorn crew_roster.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
