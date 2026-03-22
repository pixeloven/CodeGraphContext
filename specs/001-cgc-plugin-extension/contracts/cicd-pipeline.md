# Contract: CI/CD Pipeline for Plugin Service Images

**Version**: 1.0.0
**Feature**: 001-cgc-plugin-extension
**Audience**: CGC maintainers and plugin authors contributing container services

---

## 1. Pipeline Triggers

The shared Docker build pipeline (`docker-publish.yml`) runs on:

| Trigger | Behavior |
|---|---|
| Push to `main` branch | Build all service images; push with `latest` tag |
| Push of a semver tag (`v*`) | Build all images; push with version tags + `latest` |
| Pull request to `main` | Build all images; smoke test; do NOT push |
| Manual dispatch | Build all images; push with `latest` |

---

## 2. Service Registry

All container services are declared in `.github/services.json`. This is the only file
that MUST be edited to add or remove a service from the pipeline.

**Schema**:
```json
[
    {
        "name": "cgc-core",
        "path": ".",
        "dockerfile": "Dockerfile",
        "health_check": "version"
    },
    {
        "name": "cgc-plugin-otel",
        "path": "plugins/cgc-plugin-otel",
        "dockerfile": "plugins/cgc-plugin-otel/Dockerfile",
        "health_check": "grpc_ping"
    },
]
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Image name (used as registry path segment) |
| `path` | string | Docker build context path (relative to repo root) |
| `dockerfile` | string | Path to Dockerfile (relative to repo root) |
| `health_check` | string | Smoke test type: `"version"`, `"grpc_ping"`, `"http_health"` |

---

## 3. Image Tagging Convention

All images are published to the configured registry under:
`<registry>/<org>/<service-name>:<tag>`

Tags produced per build:

| Event | Tags |
|---|---|
| Tag `v1.2.3` pushed | `1.2.3`, `1.2`, `1`, `latest` |
| Push to `main` | `latest`, `main-<sha7>` |
| Push to other branch | `<branch-name>-<sha7>` |
| Pull request | `pr-<number>` (not pushed) |

---

## 4. Smoke Test Types

Each service MUST declare a `health_check` type. The pipeline runs the corresponding
test against the locally-built image before pushing.

| Type | Test command | Pass condition |
|---|---|---|
| `version` | `docker run --rm <image> --version` | Exit code 0 |
| `grpc_ping` | `docker run --rm <image> python -c "import grpc; print('ok')"` | Exit code 0 |
| `http_health` | Start container, `curl -f http://localhost:<port>/health` | HTTP 200 |

A build that fails its smoke test MUST NOT be pushed to the registry.
Other services' builds continue regardless (`fail-fast: false`).

---

## 5. Dockerfile Requirements

Every service Dockerfile MUST:

1. Use a minimal base image (e.g. `python:3.12-slim`, NOT `python:3.12`)
2. Run as a non-root user (final `USER` instruction MUST NOT be root)
3. Include a `HEALTHCHECK` instruction that CGC's health_check type can exercise
4. Accept all configuration via environment variables (no credentials in `ENV`)
5. Produce a reproducible build (pin dependency versions)

**Example `HEALTHCHECK`** for a Python service:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1
```

---

## 6. Kubernetes Compatibility Requirements

Published images MUST be deployable via standard Kubernetes `Deployment` + `Service`
manifests with no special configuration:

- No `hostNetwork: true` required
- No `privileged: true` required
- All config via environment variables (compatible with `ConfigMap` + `Secret`)
- Readiness and liveness probes derivable from `HEALTHCHECK`
- No persistent volume required for stateless plugin services
  (Neo4j connection details passed via env vars)

Reference K8s manifests are provided in `k8s/<service-name>/` for each service.

---

## 7. Adding a New Service

To add a new plugin service to the pipeline:

1. Add the service entry to `.github/services.json`
2. Ensure the plugin directory has a `Dockerfile` satisfying §5
3. The pipeline automatically picks up the new service on the next run

No other workflow changes are required.

---

## 8. Registry Configuration

The target registry is configured via repository secrets/variables:

| Secret/Variable | Description | Example |
|---|---|---|
| `REGISTRY` | Registry hostname | `ghcr.io` |
| `REGISTRY_USERNAME` | Login username (or use `${{ github.actor }}`) | `myorg` |
| `REGISTRY_PASSWORD` | Login password / token | (GitHub token for GHCR) |

For GHCR (GitHub Container Registry), `REGISTRY_PASSWORD` is `${{ secrets.GITHUB_TOKEN }}`
and no additional secret configuration is required.
