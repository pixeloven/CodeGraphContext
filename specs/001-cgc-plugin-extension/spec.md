# Feature Specification: CGC Plugin Extension System

**Feature Branch**: `001-cgc-plugin-extension`
**Created**: 2026-03-14
**Status**: Draft
**Input**: Based on research in `cgc-extended-spec.md` — extend CGC to support runtime
runtime intelligence layers via a plugin/addon pattern for CLI and MCP, with a
common CI/CD pipeline for Docker/K8s images.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plugin Extensibility Foundation (Priority: P1)

A CGC contributor or third-party developer wants to extend CGC with new capabilities
(new data sources, new MCP tools, new CLI commands) without modifying the core CGC
codebase. They build a self-contained addon package that declares its CLI commands and
MCP tools, publishes it separately, and CGC discovers and loads it automatically when
installed.

**Why this priority**: All other stories depend on a functioning plugin system. Without
the foundation, the runtime, and CI/CD stories cannot be independently developed
or released. This is the architectural backbone that makes the project composable.

**Independent Test**: Install CGC core alone and verify it starts correctly. Then install
a minimal stub plugin; verify CGC discovers the plugin, the plugin's CLI command appears
in `cgc --help`, and its MCP tool appears in the MCP tool listing — without any changes
to core CGC code.

**Acceptance Scenarios**:

1. **Given** CGC core is installed without any plugins, **When** a user runs the CGC
   CLI, **Then** only built-in core commands appear and no plugin-related errors occur.
2. **Given** a plugin package is installed in the same environment, **When** CGC starts,
   **Then** the plugin's CLI commands and MCP tools are automatically available alongside
   core capabilities.
3. **Given** a plugin is installed, **When** the plugin is uninstalled, **Then** CGC
   starts cleanly without the plugin's commands or tools and without crashing.
4. **Given** two plugins are installed simultaneously, **When** CGC starts, **Then**
   both plugins' commands and tools are available with no naming conflicts for distinct
   plugins.
5. **Given** a plugin declares an incompatible version constraint, **When** CGC loads
   plugins, **Then** the incompatible plugin is skipped with a clear warning stating the
   version mismatch, and all compatible plugins still load.

---

### User Story 2 - Runtime Intelligence via OTEL Plugin (Priority: P2)

A backend developer running a PHP/Laravel application wants to understand what code
actually executes at runtime, not just what the static graph shows. They enable the
OTEL plugin, point their application's telemetry at the CGC OTEL endpoint, and can then
ask their AI assistant questions that combine runtime call data with static code
structure — for example, "which methods were called in the last hour that have no test
coverage" or "show the full execution path for a POST /api/orders request."

**Why this priority**: The OTEL plugin is the highest-value runtime layer. It is
non-invasive (standard OTEL instrumentation already used in many projects), production-
safe, and delivers cross-layer queries immediately once spans flow into the graph.

**Independent Test**: Start CGC with the OTEL plugin enabled. Send a sample trace (or
synthetic span payload) to the plugin's ingestion endpoint. Verify that the graph now
contains runtime nodes linked to static code nodes from a pre-indexed repository, and
that a cross-layer query returns meaningful results.

**Acceptance Scenarios**:

1. **Given** the OTEL plugin is enabled and a repository is indexed, **When** a
   telemetry-instrumented application sends request traces, **Then** runtime call data
   appears in the graph within 10 seconds of the request completing.
2. **Given** runtime nodes exist in the graph, **When** an AI assistant queries
   "which methods ran during request X", **Then** the MCP tool returns a linked result
   showing both the runtime call chain and the corresponding static code nodes.
3. **Given** a cross-service call occurs (service A calls service B), **When** spans
   from both services are received, **Then** the graph contains an edge connecting the
   two services and the call is queryable as a single path.
4. **Given** health-check or noise spans are received, **When** ingestion runs, **Then**
   noise spans are filtered out and do not pollute the graph.
5. **Given** the OTEL plugin is disabled or not installed, **When** CGC starts, **Then**
   no OTEL-related commands or tools appear and the core graph is unaffected.

---

### User Story 3 - Development Traces via Xdebug Plugin (Priority: P3)

A PHP developer debugging a complex feature wants method-level execution traces that
capture exactly which concrete class implementations ran (not just the interface), which
is information OTEL spans don't always provide. They enable the Xdebug listener plugin
in their development environment and selectively trigger traces for specific requests.
The resulting call-chain graph is linked back to CGC's static code nodes so they can
navigate from "what ran" to "where it's defined."

**Why this priority**: This plugin is development/staging-only and requires Xdebug on
the target application, limiting its audience. It delivers deep, precise traces but is
not needed in production. It depends on the plugin foundation (P1) but is independent
of the OTEL plugin (P2).

**Independent Test**: Start CGC with the Xdebug plugin enabled in development mode.
Trigger an Xdebug connection from a PHP process. Verify that stack frame nodes appear
in the graph linked to the corresponding static method nodes from a pre-indexed
repository.

**Acceptance Scenarios**:

1. **Given** the Xdebug plugin is enabled and a repository is indexed, **When** a PHP
   process triggers an Xdebug trace, **Then** the full call stack appears in the graph
   as linked frame nodes within 5 seconds of the trace completing.
2. **Given** the same call chain occurs repeatedly, **When** ingestion processes the
   repeated traces, **Then** the graph contains deduplicated nodes (no duplicate chains)
   and the repetition count is reflected rather than duplicated structure.
3. **Given** a frame resolves to a method that CGC has indexed, **When** the graph is
   queried, **Then** the frame node is linked to the corresponding static method node,
   enabling navigation from runtime execution to source definition.
4. **Given** the Xdebug plugin is not installed, **When** CGC starts, **Then** no
   Xdebug-related commands or tools appear and no port is opened.

---

### User Story 4 - Automated Container Builds via Common CI/CD Pipeline (Priority: P4)

A maintainer releasing a new version of CGC or any plugin wants every service that
exposes an MCP endpoint to automatically build a versioned, production-ready container
image and publish it to a container registry. The build pipeline is shared across all
services (CGC core, OTEL plugin, Xdebug plugin), so adding a new plugin
service requires minimal CI configuration changes. The resulting images are compatible
with both Docker Compose and Kubernetes deployment patterns.

**Why this priority**: The CI/CD pipeline enables reliable, reproducible deployment of
the plugin ecosystem. It is independent of the plugin system itself and can be delivered
after the plugins are working locally. It is foundational for anyone wanting to run
CGC-X in a self-hosted or homelab environment.

**Independent Test**: Trigger the pipeline for a single service (CGC core or the OTEL
plugin). Verify that a tagged container image is built, passes a health-check smoke
test, and is published to the target registry with the correct version tag. Then verify
that the same pipeline configuration can build a second service with only a service
name change.

**Acceptance Scenarios**:

1. **Given** a version tag is pushed to the repository, **When** the pipeline runs,
   **Then** container images for all enabled plugin services are built and published with
   that version tag and a `latest` tag.
2. **Given** a plugin service container is started from its published image, **When** a
   health check is performed, **Then** the service responds correctly within 30 seconds.
3. **Given** a new plugin service directory follows the shared conventions, **When** it
   is added to the pipeline configuration, **Then** it builds and publishes alongside
   existing services without changes to shared pipeline logic.
4. **Given** a build failure occurs in one service, **When** the pipeline runs, **Then**
   only that service's build fails; other services complete successfully and their images
   are published.
5. **Given** published images, **When** a Kubernetes manifest referencing those images
   is applied to a cluster, **Then** the services start successfully and connect to their
   configured graph database.

---

### Edge Cases

- What happens when a plugin depends on a specific graph schema version and the core has
  been upgraded with schema changes?
- How does CGC handle a plugin that registers a CLI command name or MCP tool name
  already used by another loaded plugin?
- What happens if the graph database is unavailable when a plugin attempts to write
  ingested data?
- How does the system behave when the OTEL plugin receives a very high volume of spans
  (burst traffic) that exceeds ingestion capacity?
- What happens when Xdebug sends stack frames for a file path that CGC has not indexed?
- How are sensitive values (database credentials, API keys) managed in container images
  so they are never baked into the image layer?

## Requirements *(mandatory)*

### Functional Requirements

**Plugin System Core**

- **FR-001**: CGC MUST provide a plugin registration interface that allows independently
  installable packages to declare CLI commands and MCP tools without modifying core code.
- **FR-002**: CGC MUST auto-discover installed plugins at startup and load them without
  requiring manual configuration file edits.
- **FR-003**: CGC MUST isolate plugin failures so that a broken or incompatible plugin
  does not prevent CGC core or other plugins from starting.
- **FR-004**: CGC MUST enforce plugin version compatibility checks and skip plugins that
  declare an unsupported version range, reporting a clear diagnostic message.
- **FR-005**: CGC MUST ensure plugin-registered CLI commands appear in the top-level
  help output, grouped under a visible "plugins" section or annotated as plugin-provided.
- **FR-006**: CGC MUST ensure plugin-registered MCP tools appear in the MCP tool listing
  alongside core tools with their plugin source identified in metadata.

**CLI Plugin Interface**

- **FR-007**: The plugin interface MUST define a standard contract for registering CLI
  command groups, including command name, arguments, options, and handler.
- **FR-008**: Plugins MUST be able to add new top-level CLI command groups without
  conflicting with core command names.

**MCP Plugin Interface**

- **FR-009**: The plugin interface MUST define a standard contract for registering MCP
  tools, including tool name, description, input schema, and handler function.
- **FR-010**: Plugins MUST be able to share the same graph database connection managed
  by CGC core rather than opening independent connections.

**OTEL Processor Plugin**

- **FR-011**: The OTEL plugin MUST expose an ingestion endpoint that accepts telemetry
  spans from a standard OpenTelemetry collector.
- **FR-012**: The OTEL plugin MUST extract structured runtime data from spans (service
  identity, code namespace, called function, HTTP route, database query) and write it
  to the graph as typed runtime nodes and relationships.
- **FR-013**: The OTEL plugin MUST attempt to correlate runtime nodes to existing static
  code nodes in the graph where the function identity can be resolved.
- **FR-014**: The OTEL plugin MUST detect and represent cross-service calls as graph
  edges between service nodes.
- **FR-015**: The OTEL plugin MUST support configurable span filtering to exclude
  high-noise spans (health checks, metrics polling) from graph storage.
- **FR-016**: The OTEL plugin MUST expose at least one MCP tool that enables querying
  the execution path for a specific request or route.

**Xdebug Listener Plugin**

- **FR-017**: The Xdebug plugin MUST expose a TCP listener that accepts DBGp protocol
  connections from Xdebug-enabled PHP processes.
- **FR-018**: The Xdebug plugin MUST capture the full call stack on each trace event
  and write stack frame nodes and call-chain relationships to the graph.
- **FR-019**: The Xdebug plugin MUST deduplicate identical call chains so repeated
  execution of the same path does not create redundant graph structure.
- **FR-020**: The Xdebug plugin MUST attempt to resolve stack frames to static method
  nodes already indexed by CGC core.
- **FR-021**: The Xdebug plugin MUST be configurable as a development/staging-only
  service, excluded from production deployments without changing core configuration.

**CI/CD Pipeline**

- **FR-026**: The pipeline MUST build a versioned container image for each plugin
  service when a version tag is pushed to the repository.
- **FR-027**: Container images MUST pass a basic health-check smoke test before being
  published to the registry.
- **FR-028**: The pipeline MUST publish images with both a specific version tag and a
  `latest` tag to the configured container registry.
- **FR-029**: A build failure in one service image MUST NOT prevent other service images
  from completing their build and publish steps.
- **FR-030**: The pipeline MUST support a shared build configuration so that adding a
  new plugin service requires only adding the service name to a list, not duplicating
  pipeline logic.
- **FR-031**: Container images MUST NOT embed sensitive credentials; all secrets MUST
  be provided at runtime via environment variables.
- **FR-032**: Each published image MUST include a container health-check definition that
  verifies the service is ready to accept connections.
- **FR-033**: Published images MUST be compatible with Kubernetes pod specifications
  (no host-mode networking requirements, configurable via environment variables only).

### Key Entities

- **Plugin**: A self-contained, independently installable package that contributes CLI
  commands and/or MCP tools to CGC. Has a declared name, version, compatibility range,
  and lists of registered commands and tools.
- **PluginRegistry**: The runtime component within CGC core that discovers, validates,
  and loads installed plugins. Tracks which plugins are active and resolves conflicts.
- **CLICommand**: A command or command group contributed by a plugin. Has a name,
  description, argument schema, and an executing handler.
- **MCPTool**: An MCP-protocol tool contributed by a plugin. Has a name, description,
  input schema, and a handler. Source plugin is identified in its metadata.
- **RuntimeNode**: A graph node produced by the OTEL or Xdebug plugin representing an
  observed execution event (span, stack frame). Carries a `source` property identifying
  its origin layer.
- **ContainerImage**: A versioned, publishable artifact for a plugin service. Produced
  by the CI/CD pipeline and tagged with the release version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can create a working plugin that adds a CLI command and an MCP
  tool to CGC in under 2 hours, using only the published plugin interface documentation
  and without reading CGC core source code.
- **SC-002**: Installing or uninstalling a plugin requires no changes to CGC core
  configuration files — zero manual edits.
- **SC-003**: CGC with all plugins enabled starts in under 15 seconds on standard
  developer hardware.
- **SC-004**: Runtime span data from an instrumented request appears in the graph within
  10 seconds of the request completing under normal load conditions.
- **SC-005**: An AI assistant using the combined graph (static + runtime) can
  answer cross-layer queries (e.g., "what code paths are never executed at runtime") that
  are impossible with static analysis alone — validated by documented canonical query
  examples that all return correct results.
- **SC-006**: The CI/CD pipeline builds and publishes all plugin service images in a
  single pipeline run triggered by a version tag — zero manual steps required after
  tagging.
- **SC-007**: Any published plugin service image passes its health check within 30
  seconds of container startup.
- **SC-008**: A new plugin service can be added to the CI/CD pipeline by a contributor
  who changes only the service list in pipeline configuration — no pipeline logic
  changes required.
- **SC-009**: Duplicate call-chain ingestion (the same execution path observed multiple
  times) does not increase graph node count — deduplication is 100% effective for
  identical chains.
- **SC-010**: All plugin service images run successfully in a Kubernetes environment
  using only standard Kubernetes primitives (Deployments, Services, ConfigMaps, Secrets).

## Assumptions

- The existing CGC codebase uses Python 3.10+ and the plugin interface will be
  implemented in Python using the standard entry-points discovery mechanism.
- The graph database (FalkorDB or Neo4j) is already running and accessible to all
  plugins via the connection managed by CGC core.
- Plugin authors are expected to be Python developers familiar with the CGC graph schema.
- The OTEL plugin is the primary runtime layer for production use; Xdebug is dev/staging
  only, consistent with the research document's stated intent.
- CI/CD pipeline targets GitHub Actions as the execution environment, consistent with
  the project's existing workflows.
- Container registry target is determined by project maintainers at implementation time
  (Docker Hub, GHCR, or self-hosted).
