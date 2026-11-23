FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy FASTEMBED_CACHE_PATH=/models

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev \
 && uv run --no-sync python -c "from actrag.index import _model; _model()"

# the embedding model is baked in; never reach out to Hugging Face at runtime
ENV HF_HUB_OFFLINE=1
RUN useradd --create-home app && chown -R app /models
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["/app/.venv/bin/uvicorn", "actrag.api:app", "--host", "0.0.0.0", "--port", "8000"]
