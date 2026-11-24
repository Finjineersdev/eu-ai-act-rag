FROM python:3.12-slim@sha256:37fc60d303cb9294d3718b5b48998a0210bb1c73611c1399ef5eb7964c0536e5
LABEL org.opencontainers.image.source=https://github.com/Finjineersdev/eu-ai-act-rag
COPY --from=ghcr.io/astral-sh/uv:0.12.7@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy FASTEMBED_CACHE_PATH=/models

COPY pyproject.toml uv.lock README.md LICENSE ./
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
