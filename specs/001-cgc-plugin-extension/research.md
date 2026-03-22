# Research: CGC Plugin Extension System

**Feature**: 001-cgc-plugin-extension
**Date**: 2026-03-14
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## R-001: Plugin Discovery Mechanism

**Decision**: Use Python `importlib.metadata.entry_points()` (stdlib, Python 3.10+) with
two named groups: `cgc_cli_plugins` and `cgc_mcp_plugins`.

**Rationale**: Entry points are the Python ecosystem's standard plugin discovery contract.
They require zero runtime overhead beyond package installation — no config files, no
manual registration, no import scanning. Every tool in the Python ecosystem (pytest,
flask, flake8) uses this pattern. It is stdlib in Python 3.10+ (no extra dependency).

**How it works**:
- Plugin packages declare entry points in their own `pyproject.toml`
- `pip install` indexes entry point metadata into the environment
- CGC calls `entry_points(group="cgc_cli_plugins")` at startup to discover all installed
  plugins that contribute CLI commands
- CGC calls `entry_points(group="cgc_mcp_plugins")` to discover MCP tool contributors
- Each group resolves to a callable that CGC invokes to receive the plugin's registration

**Alternatives considered**:
- Filesystem scanning (explicit plugin dir) — more brittle, non-standard, breaks with
  virtual environments
- Config file listing plugins — requires manual edits (violates FR-002 "zero edits")
- Import path hooks — too low-level, fragile, hard to debug

---

## R-002: CLI Plugin Interface

**Decision**: Each CLI plugin entry point resolves to a function
`get_plugin_commands() -> Tuple[str, typer.Typer]` that returns a
`(command_group_name, typer_app_instance)` tuple. CGC calls
`app.add_typer(plugin_app, name=cmd_name)` for each loaded plugin.

**Rationale**: Typer's `add_typer()` is the idiomatic way to compose command groups. The
pattern requires the plugin to own its Typer app (clean separation), and CGC to own the
top-level `app` (clean host). Returning a tuple rather than a dict is simpler for the
common case (one command group per plugin) and is consistently typed.

**Startup sequence**:
```
CLI main.py imports → PluginRegistry discovers cgc_cli_plugins entries →
calls each get_plugin_commands() → app.add_typer() for each → Typer starts
```

**Alternatives considered**:
- Plugin directly calls `app.add_typer()` — creates bidirectional coupling; plugin
  imports core at registration time which can cause circular imports
- Plugin returns a Click group — Typer wraps Click but mixing levels is error-prone;
  Typer's add_typer is cleaner

---

## R-003: MCP Plugin Interface

**Decision**: Each MCP plugin entry point resolves to a function
`get_mcp_tools(server_context: dict) -> dict[str, ToolDefinition]` that returns a
mapping of tool name → tool definition dict (same schema as core `tool_definitions.py`).
CGC's `MCPServer._load_plugin_tools()` merges these into its tools manifest and routes
calls via a unified `handle_tool_call()` dispatcher.

**Server context passed to plugins** (minimal, read-only intent):
```python
{
    "db_manager": self.db_manager,   # shared database connection
    "version": "x.y.z",             # CGC core version string
}
```

**Rationale**: Plugins receive the `db_manager` so they can share the existing database
connection rather than opening independent connections (violating the constitution's
single-database principle). Passing only what is needed (not `self`) prevents plugins
from calling internal server methods they shouldn't access.

**Tool handler registration**: The plugin's `get_mcp_tools()` return value maps
tool names to JSON Schema definitions. The plugin ALSO registers handler callables
in a separate `get_mcp_handlers()` function (or combined in a single object). The
server stores handlers in `self.plugin_tool_handlers` dict and routes calls there
before checking built-in handlers.

**Alternatives considered**:
- Subclass MCPServer per plugin — couples plugin to server implementation; not viable
  for third-party plugins
- Plugin monkey-patches server — completely unsafe and untestable
- gRPC plugin protocol — overkill for in-process plugins; entry-points are sufficient

---

## R-004: Plugin Version Compatibility

**Decision**: Each plugin's `__init__.py` declares `PLUGIN_METADATA` dict with a
`cgc_version_constraint` key using PEP-440 version specifier syntax (e.g.
`">=0.3.0,<1.0"`). CGC's `PluginRegistry` validates this against the installed
`codegraphcontext` package version using `packaging.specifiers.SpecifierSet`.

**On mismatch**: plugin is skipped with a WARNING log; all compatible plugins still load;
no error is raised to the user unless zero plugins load.

**Rationale**: `packaging` is already an indirect dependency of pip and is present in
all virtual environments. PEP-440 specifiers are the Python standard for version
constraints. Soft-fail (warn, skip) rather than hard-fail ensures partial plugin
ecosystems remain usable.

**Alternatives considered**:
- Semver-only checking — PEP-440 is a superset and already the ecosystem standard
- No version checking — risks silent breakage when core APIs change

---

## R-005: Plugin Isolation (Error Containment)

**Decision**: Wrap each plugin load in a `try/except Exception` block. Use a
`PluginRegistry` class that catches `ImportError`, `AttributeError`, `TimeoutError`, and
generic `Exception` at each stage (import, metadata read, command/tool registration).
A broken plugin logs an error and sets `failed_plugins[name] = reason`; it NEVER
propagates an exception to the host process.

**Timeout**: On Unix, `signal.SIGALRM` with a 5-second timeout prevents hanging imports.
(Windows lacks SIGALRM — on Windows, timeout is skipped with a warning.)

**Startup summary**: After all plugins are processed, CGC logs:
```
CGC started with 19 built-in tools and 4 plugin tools (1 plugin failed).
  ✓ cgc-plugin-otel      4 tools
  ✗ cgc-plugin-xdebug    SKIPPED: missing dependency 'dbgp'
```

**Rationale**: The spec requires (FR-003) that plugin failures do not prevent CGC core
from starting. Isolation at the `PluginRegistry` boundary is the cleanest enforcement.

---

## R-006: OTEL Span Receiver Architecture

**Decision**: Deploy the standard OpenTelemetry Collector (`otel/opentelemetry-collector-contrib`)
as a sidecar. It receives OTLP from applications and forwards to the OTEL plugin service
via OTLP gRPC. The plugin service implements a Python gRPC server using `grpcio` +
`opentelemetry-proto` protobuf definitions.

**Rationale**: The Python `opentelemetry-sdk` is tracer-side only — it cannot act as an
OTLP gRPC receiver endpoint. Using the official OTel Collector as a sidecar provides
batching, retry, filtering, and sampling for free before spans reach the custom processor.
This is the established production pattern (used by Datadog, Honeycomb, Jaeger agents).

**Key packages**:
- `grpcio>=1.57.0` — gRPC server implementation
- `opentelemetry-proto>=0.43b0` — generated protobuf/gRPC classes
- `neo4j>=5.15.0` — async Python driver

**Write pattern**: Async batch writer using `asyncio.Queue` with configurable
`max_batch_size=100` and `max_wait_ms=5000`. MERGE on `(trace_id, span_id)` for
idempotency. Dead-letter queue for resilience when Neo4j is temporarily unavailable.

**Alternatives considered**:
- Pure Python OTLP HTTP receiver (no gRPC) — simpler but less efficient; OTel Collector
  already handles the gRPC ↔ HTTP translation if needed
- Direct OTLP from app → Python service — fragile; the Collector adds resilience

---

## R-007: Xdebug DBGp Listener

**Decision**: Implement a minimal TCP server using Python's stdlib `socket` and
`xml.etree.ElementTree` modules. No external DBGp library is required — the protocol
is XML over TCP and is simple enough to implement directly.

**Protocol flow**: PHP Xdebug connects → init packet received → `run` command sent →
on each breakpoint, send `stack_get` → parse XML response → upsert `StackFrame` nodes
and `CALLED_BY` edges → send `run` → repeat until connection closes.

**Deduplication**: Hash the call chain (`sha256(class::method|...) [:16]`) with an
LRU cache (size configurable, default 10,000). If hash seen recently, skip upsert.
This prevents the same execution path from creating duplicate graph structure.

**Dev-only deployment**: The Xdebug plugin starts its TCP listener only when enabled
(`CGC_PLUGIN_XDEBUG_ENABLED=true`). In production Docker Compose, the `xdebug` service
is absent from the default compose file; it exists only in `docker-compose.dev.yml`.

**Rationale**: Xdebug is a dev tool. Running a DBGp listener in production is a security
risk. The plugin MUST default to disabled and require explicit opt-in.

---

## R-008: CI/CD Pipeline Architecture

**Decision**: GitHub Actions matrix strategy with `fail-fast: false`. Services defined
in `.github/services.json` as a JSON array. Shared logic for checkout, Docker login,
version tag extraction, and metadata is in the matrix job — matrix jobs inherit shared
steps via `needs` dependencies from a `setup` job that outputs the services matrix.

**Tagging strategy**: `docker/metadata-action@v5` generates:
- Semver tags from git tags (`v1.2.3` → `1.2.3`, `1.2`, `1`)
- `latest` on default branch pushes
- Branch name tags for non-default branches

**Health check**: After `docker/build-push-action@v5` with `push: false` (local build),
load image and run a service-specific smoke test. Only push if smoke test passes.

**Adding a new service**: Add one JSON object to `.github/services.json`. Zero workflow
logic changes.

**Key action versions** (current as of research date):
- `docker/setup-buildx-action@v3`
- `docker/build-push-action@v5`
- `docker/login-action@v3`
- `docker/metadata-action@v5`

**Alternatives considered**:
- One workflow file per service — massive duplication, violates FR-030
- Reusable workflow (workflow_call) — more complex than needed; matrix is sufficient

---

## R-009: Monorepo Package Layout

**Decision**: Plugin packages live in `plugins/` subdirectory, each as an independently
installable Python package with its own `pyproject.toml`. Plugin services that run as
standalone containers (OTEL, Xdebug) also have a `Dockerfile` in their directory.

**Development installation**:
```bash
pip install -e .                             # CGC core
pip install -e plugins/cgc-plugin-otel
pip install -e plugins/cgc-plugin-xdebug
```

After this, `cgc --help` shows plugin commands automatically.

**Production installation** (users who want only specific plugins):
```bash
pip install codegraphcontext                 # Core only
pip install codegraphcontext[otel]           # Core + OTEL plugin (via extras)
pip install codegraphcontext[all]            # Core + all plugins
```

This is achieved by declaring plugins as optional extras in the root `pyproject.toml`.
