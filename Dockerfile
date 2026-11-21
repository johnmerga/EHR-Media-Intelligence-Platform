FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so source changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the embedding model into the image: no download at startup, no network needed.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EHR_EMBEDDING_MODEL=${EMBEDDING_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"
ENV HF_HUB_OFFLINE=1

COPY src ./src
RUN uv sync --frozen --no-dev

# Ship the committed data and build the vector index, so the API starts ready to serve.
COPY data ./data
RUN ehr index

RUN useradd --create-home --uid 1000 app && chown -R app:app /app/data
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "ehr_platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
