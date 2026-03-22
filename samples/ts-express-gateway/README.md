# CGC Sample: TypeScript/Express Gateway

An API gateway that proxies and aggregates requests to the PHP and Python
sample backends, exercising OTEL cross-service tracing.

## Routes

| Method | Path              | Description                                      |
|--------|-------------------|--------------------------------------------------|
| GET    | `/api/dashboard`  | Aggregates data from both PHP and Python backends |
| GET    | `/api/orders`     | Proxies to PHP backend                           |
| POST   | `/api/orders`     | Proxies to PHP backend                           |
| GET    | `/health`         | Liveness check                                   |

## Cross-service tracing

The gateway makes outbound HTTP calls to the PHP backend
(`http://sample-php:8080`) and the Python backend (`http://sample-python:8081`).
OTEL auto-instrumentation wraps these calls with **CLIENT spans** that carry
`peer.service` attributes. The CGC OTEL receiver converts these into
`CALLS_SERVICE` edges in the code graph.

**W3C trace context propagation** ensures that distributed traces are linked
end-to-end across all three services (gateway, PHP, Python).

## Running

This application is designed to run as part of the CGC sample Docker Compose
stack. See `samples/README.md` for the full walkthrough.

```bash
# Standalone (development)
npm install
npm run dev

# Docker
docker build -t cgc-sample-ts-gateway .
docker run -p 8082:8082 cgc-sample-ts-gateway
```
