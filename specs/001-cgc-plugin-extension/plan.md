# Implementation Plan: CGC Plugin Extension System

**Branch**: `001-cgc-plugin-extension` | **Date**: 2026-03-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-cgc-plugin-extension/spec.md`

## Summary

Extend CodeGraphContext with a Python entry-points plugin system that allows independently
installable packages to contribute CLI commands (Typer) and MCP tools without modifying
CGC core. Two first-party plugins ship with the extension: an OTEL span processor (runtime
intelligence) and an Xdebug DBGp listener (dev-time stack traces). A shared GitHub Actions
matrix CI/CD pipeline builds and publishes versioned Docker images for each plugin service.
All plugin data flows into the existing Neo4j/FalkorDB graph, enabling cross-layer queries
across static code and runtime execution.

## Technical Context

**Language/Version**: Python 3.10+ (constitutional constraint)
**Primary Dependencies**:
- Plugin system: `importlib.metadata` (stdlib), `packaging>=23.0` (version constraint checking)
- OTEL plugin: `grpcio>=1.57.0`, `opentelemetry-proto>=0.43b0`, `opentelemetry-sdk>=1.20.0`
- Xdebug plugin: stdlib only (`socket`, `xml.etree.ElementTree`, `hashlib`)
- All plugins: `typer[all]>=0.9.0`, `neo4j>=5.15.0` (shared with core)

**Storage**: Neo4j (production) / FalkorDB (default) — same shared instance as CGC core;
new additive node labels and relationships per `data-model.md`

**Testing**: pytest + pytest-asyncio; existing `tests/run_tests.sh` extended with
`tests/unit/plugin/`, `tests/integration/plugin/`, `tests/e2e/plugin/`

**Target Platform**: Linux server (Docker containers); Kubernetes compatible (no host
networking, env-var-only config)

**Project Type**: Python library + CLI extensions + containerised microservices

**Performance Goals**:
- CGC startup with all plugins: ≤ 15 seconds
- Span data queryable within 10 seconds of request completion under normal load
- Plugin load failure: ≤ 5-second timeout per plugin (SIGALRM)

**Constraints**:
- Plugin failures MUST NOT crash CGC core (strict isolation)
- No credentials baked into container images
- `./tests/run_tests.sh fast` MUST pass after each phase
- Xdebug plugin MUST default to disabled (security: TCP listener)

**Scale/Scope**: 2 plugin packages, 1 shared CI/CD pipeline, 4 container services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| **I. Graph-First Architecture** | ✅ PASS | All plugin output (spans, stack frames) writes to the graph as typed nodes + relationships per `data-model.md`. No flat data structures. Graph schema is the output target for both plugins. |
| **II. Dual Interface — CLI + MCP** | ✅ PASS | Each plugin MUST contribute both CLI commands AND MCP tools (per plugin interface contract). The plugin contract enforces parity by design. |
| **III. Testing Pyramid** | ✅ PASS | Plugin packages include `tests/unit/` and `tests/integration/`. `./tests/run_tests.sh fast` is extended to cover plugin directories. E2E tests cover the full plugin lifecycle. Tests written and observed to FAIL before implementation (Red-Green-Refactor). |
| **IV. Multi-Language Parser Parity** | ✅ PASS | No new language parsers introduced. Runtime nodes carry `source` property (`"runtime_otel"`, `"runtime_xdebug"`) that distinguish origin layers without breaking existing cross-language queries. |
| **V. Simplicity** | ⚠️ JUSTIFIED | Plugin registry is an abstraction. Justified because: (a) the feature requires extensibility without forking core — a non-negotiable requirement; (b) `importlib.metadata` entry-points is Python stdlib — minimal abstraction; (c) without a registry, adding each plugin would require modifying `server.py` and `cli/main.py` permanently, producing a worse monolith. See Complexity Tracking below. |

*Post-Phase 1 re-check*: ✅ Design satisfies all five principles. No new violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/001-cgc-plugin-extension/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── plugin-interface.md   # Plugin author contract
│   └── cicd-pipeline.md      # CI/CD service registration contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
# Core CGC modifications (existing package)
src/codegraphcontext/
├── plugin_registry.py          # NEW: PluginRegistry class, isolation wrappers
├── cli/
│   └── main.py                 # MODIFIED: call load_plugin_cli_commands() at startup
└── server.py                   # MODIFIED: call _load_plugin_tools() in __init__

# New plugin packages
plugins/
├── cgc-plugin-otel/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/cgc_plugin_otel/
│       ├── __init__.py         # PLUGIN_METADATA
│       ├── cli.py              # get_plugin_commands() → ("otel", typer.Typer)
│       ├── mcp_tools.py        # get_mcp_tools(), get_mcp_handlers()
│       ├── receiver.py         # gRPC OTLP receiver (grpcio + opentelemetry-proto)
│       ├── span_processor.py   # PHP attribute extraction + correlation logic
│       └── neo4j_writer.py     # Async batch writer with dead-letter queue
│
└── cgc-plugin-xdebug/
    ├── pyproject.toml
    ├── Dockerfile
    └── src/cgc_plugin_xdebug/
        ├── __init__.py         # PLUGIN_METADATA
        ├── cli.py              # get_plugin_commands() → ("xdebug", typer.Typer)
        ├── mcp_tools.py        # get_mcp_tools(), get_mcp_handlers()
        ├── dbgp_server.py      # TCP DBGp listener + XML stack frame parser
        └── neo4j_writer.py     # Frame upsert + CALLED_BY chain + deduplication

# Tests (additions to existing structure)
tests/
├── unit/
│   └── plugin/
│       ├── test_plugin_registry.py    # PluginRegistry unit tests (mocked)
│       ├── test_otel_processor.py     # Span extraction logic
│       └── test_xdebug_parser.py      # DBGp XML parsing + deduplication
├── integration/
│   └── plugin/
│       ├── test_plugin_load.py        # Plugin discovery + load integration
│       └── test_otel_integration.py   # OTLP receive → graph write
└── e2e/
    └── plugin/
        └── test_plugin_lifecycle.py   # Full install/use/uninstall user journey

# CI/CD
.github/
├── services.json                      # NEW: service list for Docker matrix
└── workflows/
    ├── docker-publish.yml             # MODIFIED: matrix over services.json
    └── test-plugins.yml               # NEW: per-plugin fast test suite

# Deployment
docker-compose.yml                     # MODIFIED: add otel services
docker-compose.dev.yml                 # MODIFIED: add xdebug service
config/
├── otel-collector/
│   └── config.yaml                    # NEW: OTel Collector pipeline config
└── neo4j/
    └── init.cypher                    # MODIFIED: add plugin schema constraints

k8s/
└── cgc-plugin-otel/
    ├── deployment.yaml
    └── service.yaml
```

**Structure Decision**: Multi-package layout under `plugins/` with independent
`pyproject.toml` per plugin. This matches the research recommendation (R-010) and is the
standard Python ecosystem pattern for monorepo plugin families. Plugin packages are
installable independently (`pip install codegraphcontext[otel]`) or via optional extras
in the root `pyproject.toml`. Each plugin that exposes a container service has its own
`Dockerfile` in the plugin directory.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Plugin registry abstraction | Feature explicitly requires extensibility without forking core. Three current plugins + third-party extensibility require a clean registration boundary. | Hardcoding plugins in `server.py`/`main.py` defeats the extensibility requirement entirely. There is no simpler path to the stated goal. |
| gRPC server in OTEL plugin | OTLP protocol uses gRPC. The Python opentelemetry-sdk is tracer-side only and cannot act as a receiver. | Pure HTTP OTLP would require the same gRPC-level effort and provides less tooling ecosystem support. The OTel Collector (sidecar) already handles the edge; gRPC is the right interface for collector → processor. |
| Multiple new graph node types | Runtime layers produce genuinely different data (spans, frames). Reusing existing `Method`/`Class` nodes for runtime data would corrupt the static layer. | Cannot collapse runtime nodes into static nodes — they represent different semantic things (observed execution vs. declared code). The `source` property differentiates them without schema explosion. |
