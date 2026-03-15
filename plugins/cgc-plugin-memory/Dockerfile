FROM python:3.12-slim

RUN groupadd -r cgc && useradd -r -g cgc cgc

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir "typer[all]>=0.9.0" "neo4j>=5.15.0" || true

USER cgc

EXPOSE 8766

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import cgc_plugin_memory; print('ok')" || exit 1

CMD ["python", "-m", "cgc_plugin_memory.server"]
