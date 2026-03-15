FROM python:3.12-slim

RUN groupadd -r cgc && useradd -r -g cgc cgc

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir "typer[all]>=0.9.0" "neo4j>=5.15.0" || true

USER cgc

EXPOSE 9003

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.socket(socket.AF_INET, socket.SOCK_STREAM)" || exit 1

# CGC_PLUGIN_XDEBUG_ENABLED must be set to 'true' at runtime
CMD ["python", "-m", "cgc_plugin_xdebug.dbgp_server"]
