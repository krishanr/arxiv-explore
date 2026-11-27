FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Install only the app's runtime dependencies (not the pipeline/dev groups).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project

COPY app.py analytics.py ./
COPY pipeline/__init__.py pipeline/jsonl.py pipeline/
COPY assets/ assets/
COPY data/ data/

# Run as an unprivileged user; the app only needs to read the files above (owned by root, world-readable).
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8080
CMD ["gunicorn", "app:server", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4"]
