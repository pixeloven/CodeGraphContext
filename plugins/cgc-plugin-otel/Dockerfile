FROM python:3.12-slim

# Security: run as non-root
RUN groupadd -r cgc && useradd -r -g cgc cgc

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e . && \
    pip install --no-cache-dir grpcio>=1.57.0 "opentelemetry-proto>=0.43b0" "opentelemetry-sdk>=1.20.0" \
    "typer[all]>=0.9.0" "neo4j>=5.15.0" || true

USER cgc

EXPOSE 5317

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import grpc; print('ok')" || exit 1

CMD ["python", "-m", "cgc_plugin_otel.receiver"]
