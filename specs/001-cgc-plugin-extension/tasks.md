---

description: "Task list for CGC Plugin Extension System"
---

# Tasks: CGC Plugin Extension System

**Input**: Design documents from `specs/001-cgc-plugin-extension/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Tests**: Included — required by Constitution Principle III (Testing Pyramid, NON-NEGOTIABLE).
Tests MUST be written and observed to FAIL before the corresponding implementation task.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths included in every task description

## Path Conventions

- Core CGC: `src/codegraphcontext/`
- Plugin packages: `plugins/cgc-plugin-<name>/src/cgc_plugin_<name>/`
- Tests: `tests/unit/plugin/`, `tests/integration/plugin/`, `tests/e2e/plugin/`
- CI/CD: `.github/workflows/`, `.github/services.json`
- Deployment: `docker-compose.yml`, `docker-compose.dev.yml`, `k8s/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize all plugin package scaffolding and root configuration before any
story work begins.

- [X] T001 Create `plugins/` directory tree: `plugins/cgc-plugin-otel/src/cgc_plugin_otel/`, `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/`, `plugins/cgc-plugin-stub/src/cgc_plugin_stub/` with empty `__init__.py` placeholders
- [X] T002 [P] Write `plugins/cgc-plugin-otel/pyproject.toml` — package name `cgc-plugin-otel`, entry-points groups `cgc_cli_plugins` and `cgc_mcp_plugins`, deps: `grpcio>=1.57.0`, `opentelemetry-proto>=0.43b0`, `opentelemetry-sdk>=1.20.0`, `typer[all]>=0.9.0`, `neo4j>=5.15.0`
- [X] T003 [P] Write `plugins/cgc-plugin-xdebug/pyproject.toml` — package name `cgc-plugin-xdebug`, entry-points groups `cgc_cli_plugins` and `cgc_mcp_plugins`, deps: `typer[all]>=0.9.0`, `neo4j>=5.15.0` (stdlib-only implementation)
- [X] T005 [P] Write `plugins/cgc-plugin-stub/pyproject.toml` — package name `cgc-plugin-stub`, entry-points groups `cgc_cli_plugins` and `cgc_mcp_plugins`, dep: `typer[all]>=0.9.0` only (minimal test fixture)
- [X] T006 Add `packaging>=23.0` dependency and optional extras `[otel]`, `[xdebug]`, `[all]` to root `pyproject.toml`, each extra pointing at its corresponding plugin package in `plugins/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented.
The `PluginRegistry` class, graph schema migration, and test infrastructure are shared by all stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

> **NOTE: Write tests FIRST (T008), ensure they FAIL before implementing T007**

- [X] T007 [P] Add plugin schema constraints and indexes to `config/neo4j/init.cypher` — `UNIQUE` constraints for Service.name, Trace.trace_id, Span.span_id, StackFrame.frame_id; indexes on Span.trace_id, Span.class_name, Span.http_route, StackFrame.fqn (per data-model.md)
- [X] T008 Write `tests/unit/plugin/test_plugin_registry.py` — unit tests (all entry points mocked) covering: discovers plugins from both entry-point groups, validates PLUGIN_METADATA required fields, skips plugin with incompatible cgc_version_constraint, skips plugin with conflicting name (second plugin), catches ImportError without crashing host, catches exception in get_plugin_commands() without crashing host, reports loaded/failed counts correctly. **Run and confirm FAILING before T009.**
- [X] T009 Implement `src/codegraphcontext/plugin_registry.py` — `PluginRegistry` class with: `discover_cli_plugins()` (reads `cgc_cli_plugins` group), `discover_mcp_plugins()` (reads `cgc_mcp_plugins` group), `_validate_metadata()` (checks required fields + cgc_version_constraint via `packaging.specifiers.SpecifierSet`), `_safe_load()` (try/except + SIGALRM 5s timeout on Unix), `_safe_call()` (try/except wrapper for get_plugin_commands/get_mcp_tools/get_mcp_handlers), `loaded_plugins: dict`, `failed_plugins: dict`, startup summary log line
- [X] T010 Update `tests/run_tests.sh` to include `tests/unit/plugin/` and `tests/integration/plugin/` in the `fast` suite alongside existing unit + integration paths

**Checkpoint**: PluginRegistry unit tests pass. Schema migration ready. Fast suite covers plugin tests.

---

## Phase 3: User Story 1 — Plugin Extensibility Foundation (Priority: P1) 🎯 MVP

**Goal**: CGC discovers and loads installed plugins automatically; CLI and MCP both surface
plugin-contributed commands and tools; broken plugins never crash the host process.

**Independent Test**: `pip install -e plugins/cgc-plugin-stub` → `cgc --help` shows `stub`
command group → `cgc stub hello` works → MCP tool `stub_hello` appears in tools/list →
`pip uninstall cgc-plugin-stub` → CGC restarts cleanly with no stub artifacts.

> **NOTE: Write integration tests (T011) FIRST, ensure they FAIL before T012–T015**

- [X] T011 Write `tests/integration/plugin/test_plugin_load.py` — integration tests using the stub plugin (installed as editable in conftest fixture): stub CLI command appears in `app.registered_commands` after registry runs; stub MCP tool name appears in server.tools dict; second incompatible-version stub is skipped with warning; two conflicting-name stubs load only first; registry reports correct counts. **Run and confirm FAILING before T012.**
- [X] T012 [P] [US1] Implement `plugins/cgc-plugin-stub/src/cgc_plugin_stub/__init__.py` — `PLUGIN_METADATA` dict: name `cgc-plugin-stub`, version `0.1.0`, cgc_version_constraint `>=0.1.0`, description `Stub plugin for testing`
- [X] T013 [P] [US1] Implement `plugins/cgc-plugin-stub/src/cgc_plugin_stub/cli.py` — `get_plugin_commands()` returning `("stub", stub_app)` where `stub_app` has one command `hello` that echoes "Hello from stub plugin"
- [X] T014 [P] [US1] Implement `plugins/cgc-plugin-stub/src/cgc_plugin_stub/mcp_tools.py` — `get_mcp_tools()` returning one tool `stub_hello` with inputSchema `{name: string}`; `get_mcp_handlers()` returning handler that returns `{"greeting": f"Hello {name}"}`
- [X] T015 [US1] Modify `src/codegraphcontext/cli/main.py` — add `_load_plugin_cli_commands(registry: PluginRegistry)` function that calls `app.add_typer()` for each entry in `registry.loaded_plugins`; call at module startup after core command registration; add `cgc plugin list` sub-command showing loaded/failed plugins with name, version, tool count
- [X] T016 [US1] Modify `src/codegraphcontext/server.py` — instantiate `PluginRegistry` in `MCPServer.__init__()`, call `_load_plugin_tools()` that merges plugin tool definitions into `self.tools` dict (with conflict check), store plugin handlers in `self.plugin_tool_handlers: dict`, update `handle_tool_call()` to check `self.plugin_tool_handlers` before built-in handler map

**Checkpoint**: `pip install -e plugins/cgc-plugin-stub && cgc plugin list` shows stub; MCP tools/list includes `stub_hello`; uninstall leaves CGC clean.

---

## Phase 4: User Story 2 — Runtime Intelligence via OTEL Plugin (Priority: P2)

**Goal**: OTEL plugin receives telemetry spans, writes Service/Trace/Span nodes to the
graph, correlates spans to static Method nodes, and exposes MCP tools for runtime queries.

**Independent Test**: With a pre-indexed PHP repository, send a synthetic OTLP span payload
to the OTEL plugin endpoint. Query `MATCH (s:Span) RETURN count(s)` → non-zero.
Query `MATCH (s:Span)-[:CORRELATES_TO]->(m:Method) RETURN s.name, m.fqn LIMIT 5` → returns linked results.

> **NOTE: Write unit tests (T017) FIRST, ensure they FAIL before T018–T022**

- [X] T017 Write `tests/unit/plugin/test_otel_processor.py` — unit tests (mocked db_manager, no gRPC): `extract_php_context()` parses code.namespace+code.function into fqn; `extract_php_context()` handles missing attributes gracefully (returns None fqn); `is_cross_service_span()` returns True for CLIENT kind spans with peer.service set; `should_filter_span()` returns True for health-check routes matching config; `build_span_dict()` computes duration_ms correctly from ns timestamps. **Run and confirm FAILING before T018.**
- [X] T018 [P] [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/__init__.py` — `PLUGIN_METADATA` dict: name `cgc-plugin-otel`, version `0.1.0`, cgc_version_constraint `>=0.1.0`
- [X] T019 [P] [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/cli.py` — `get_plugin_commands()` returning `("otel", otel_app)` with commands: `query-spans --route TEXT --limit INT`, `list-services`, `status` (shows whether receiver is running)
- [X] T020 [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/span_processor.py` — `extract_php_context(span_attrs: dict) -> dict` (parses code.namespace, code.function, http.route, http.method, db.statement, db.system into typed dict); `build_fqn(namespace, function) -> str | None`; `is_cross_service_span(span_kind, span_attrs) -> bool`; `should_filter_span(span_attrs, filter_routes: list[str]) -> bool` (configurable noise filter)
- [X] T021 [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/neo4j_writer.py` — `AsyncOtelWriter` class: async `write_batch(spans: list[dict])` using `asyncio.Queue(maxsize=10000)` and periodic flush (batch size 100, timeout 5s); MERGE queries for Service, Trace, Span nodes; CHILD_OF (parent_span_id), PART_OF (trace), ORIGINATED_FROM (service), CALLS_SERVICE (CLIENT kind), CORRELATES_TO (fqn match against existing Method nodes); dead-letter queue with `asyncio.Queue(maxsize=100000)` for Neo4j unavailability; `_background_retry_task()` coroutine
- [X] T022 [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/receiver.py` — `OTLPSpanReceiver` class implementing `TraceServiceServicer` (grpcio + opentelemetry-proto); `Export()` method queues spans for batch processing; `main()` starts gRPC server on `OTEL_RECEIVER_PORT` (default 5317) + launches `process_span_batch()` background task; graceful shutdown on SIGTERM
- [X] T023 [P] [US2] Implement `plugins/cgc-plugin-otel/src/cgc_plugin_otel/mcp_tools.py` — `get_mcp_tools()` returning: `otel_query_spans` (args: http_route, service, limit), `otel_list_services` (no args), `otel_cross_layer_query` (args: query_type enum: `never_observed|cross_service_calls|recent_executions`); `get_mcp_handlers()` with corresponding Cypher-backed handlers using `server_context["db_manager"]`
- [X] T024 [US2] Create `config/otel-collector/config.yaml` — OTLP gRPC+HTTP receivers (ports 4317, 4318); batch processor (timeout 5s, send_batch_size 512); filter processor dropping spans where `http.route` matches `/health`, `/metrics`, `/ping`; OTLP exporter forwarding to `otel-processor:5317` (insecure TLS)
- [X] T025 [US2] Add OTEL services to `docker-compose.yml` — `otel-collector` service (image: `otel/opentelemetry-collector-contrib:latest`, ports 4317-4318, depends on otel-processor); `cgc-otel-processor` service (build: `plugins/cgc-plugin-otel`, env: NEO4J_URI/USERNAME/PASSWORD/LISTEN_PORT/LOG_LEVEL, depends on neo4j healthcheck, Traefik labels)
- [X] T026 [US2] Write `tests/integration/plugin/test_otel_integration.py` — with real Neo4j fixture (or mock db_manager): call `write_batch()` with synthetic span dicts; assert Service node created with correct name; assert Span node created with correct span_id; assert CHILD_OF relationship created for parent_span_id; assert CORRELATES_TO created when fqn matches pre-existing Method node; assert filtered spans (health route) produce zero graph nodes

**Checkpoint**: OTEL plugin loads, gRPC receiver accepts a synthetic span, Service+Span nodes appear in graph with CORRELATES_TO link to static Method.

---

## Phase 5: User Story 3 — Development Traces via Xdebug Plugin (Priority: P3)

**Goal**: Xdebug plugin runs a TCP DBGp listener, captures PHP call stacks, deduplicates
chains, writes StackFrame nodes to the graph, and links frames to static Method nodes.

**Independent Test**: With a pre-indexed PHP repository, simulate a DBGp TCP connection
sending a synthetic stack_get XML response. Verify StackFrame nodes appear in the graph
with CALLED_BY chain relationships and RESOLVES_TO links to Method nodes.

> **NOTE: Write unit tests (T027) FIRST, ensure they FAIL before T028–T031**

- [X] T027 Write `tests/unit/plugin/test_xdebug_parser.py` — unit tests (no TCP): `parse_stack_xml(xml_str) -> list[dict]` returns correct frame list from sample DBGp XML; `compute_chain_hash(frames) -> str` returns same hash for identical frame lists and different hash for different lists; `build_frame_id(class_name, method_name, file_path, line) -> str` returns deterministic unique string; dedup check returns True for hash in LRU cache and False for new hash. **Run and confirm FAILING before T028.**
- [X] T028 [P] [US3] Implement `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/__init__.py` — `PLUGIN_METADATA` dict: name `cgc-plugin-xdebug`, version `0.1.0`, cgc_version_constraint `>=0.1.0`; note in description that this is dev/staging only
- [X] T029 [P] [US3] Implement `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/cli.py` — `get_plugin_commands()` returning `("xdebug", xdebug_app)` with commands: `start` (starts listener, requires `CGC_PLUGIN_XDEBUG_ENABLED=true`), `stop`, `status`, `list-chains --limit INT`
- [X] T030 [US3] Implement `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/dbgp_server.py` — `DBGpServer` class: `listen(host, port)` opens TCP socket with `SO_REUSEADDR`; `handle_connection(conn)` reads DBGp init packet, sends `run` command, loops: sends `stack_get -i {seq}`, parses XML response via `parse_stack_xml()`, calls `neo4j_writer.write_chain()`, sends `run`; `parse_stack_xml(xml: str) -> list[dict]` using `xml.etree.ElementTree`; server only starts when env var `CGC_PLUGIN_XDEBUG_ENABLED=true`
- [X] T031 [US3] Implement `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/neo4j_writer.py` — `XdebugWriter` class: `lru_cache: dict[str, int]` (hash → observation_count, max `DEDUP_CACHE_SIZE=10000`); `write_chain(frames: list[dict], db_manager)`: computes chain_hash, checks LRU — if seen, increments observation_count on existing StackFrame and returns; else MERGEs StackFrame nodes for each frame, creates CALLED_BY chain from depth ordering, attempts RESOLVES_TO match against `Method {fqn: $fqn}` for each frame
- [X] T032 [P] [US3] Implement `plugins/cgc-plugin-xdebug/src/cgc_plugin_xdebug/mcp_tools.py` — `get_mcp_tools()` returning: `xdebug_list_chains` (args: limit, min_observations), `xdebug_query_chain` (args: class_name, method_name); `get_mcp_handlers()` with Cypher-backed handlers
- [X] T033 [US3] Add `xdebug-listener` service to `docker-compose.dev.yml` — build: `plugins/cgc-plugin-xdebug`, env: NEO4J_URI/USERNAME/PASSWORD/LISTEN_HOST/LISTEN_PORT=9003/DEDUP_CACHE_SIZE/LOG_LEVEL=DEBUG/CGC_PLUGIN_XDEBUG_ENABLED=true, ports: `9003:9003`, depends on neo4j healthcheck

**Checkpoint**: Xdebug plugin loads with `CGC_PLUGIN_XDEBUG_ENABLED=true`, synthetic DBGp XML input produces StackFrame nodes with CALLED_BY chain and RESOLVES_TO Method links.

---

## Phase 6: User Story 4 — Automated Container Builds via Common CI/CD Pipeline (Priority: P4)

**Goal**: GitHub Actions matrix pipeline builds, smoke tests, and publishes versioned Docker
images for all plugin services. Adding a new service requires only editing `.github/services.json`.

**Independent Test**: Push a test tag; verify GitHub Actions builds all services in parallel;
verify each image's smoke test passes; verify images are tagged with semver + `latest`;
verify a failure in one service does not cancel other builds.

- [X] T039 [P] [US5] Create `plugins/cgc-plugin-otel/Dockerfile` — `FROM python:3.12-slim`, non-root `USER cgc`, `COPY` and `pip install --no-cache-dir`, `EXPOSE 5317`, `HEALTHCHECK --interval=30s --timeout=10s CMD python -c "import grpc; print('ok')"`, `CMD ["python", "-m", "cgc_plugin_otel.receiver"]`; no `ENV` with secret values
- [X] T040 [P] [US5] Create `plugins/cgc-plugin-xdebug/Dockerfile` — `FROM python:3.12-slim`, non-root user, `EXPOSE 9003`, `HEALTHCHECK CMD python -c "import socket; socket.socket()"`, `CMD ["python", "-m", "cgc_plugin_xdebug.dbgp_server"]`; requires `CGC_PLUGIN_XDEBUG_ENABLED=true` at runtime
- [X] T042 [US5] Create `.github/services.json` — JSON array with entries for: `cgc-core` (path: `.`, dockerfile: `Dockerfile`, health_check: `version`), `cgc-plugin-otel` (path: `plugins/cgc-plugin-otel`, health_check: `grpc_ping`), `cgc-plugin-xdebug` (path: `plugins/cgc-plugin-xdebug`, health_check: `tcp_connect`) per `contracts/cicd-pipeline.md` schema
- [X] T043 [US5] Create `.github/workflows/docker-publish.yml` — `setup` job reads `.github/services.json` and outputs matrix; `build-images` job with `strategy: {matrix: ${{ fromJson(...) }}, fail-fast: false}`: checkout, `docker/setup-buildx-action@v3`, `docker/login-action@v3` (GHCR, skipped on PR), `docker/metadata-action@v5` (semver+latest tags), `docker/build-push-action@v5` with `push: false` + `outputs: type=docker` for smoke test, smoke test per `health_check` type, then `docker/build-push-action@v5` with `push: true` if not PR and smoke test passed; `build-summary` job reports overall status
- [X] T044 [P] [US5] Create `.github/workflows/test-plugins.yml` — GitHub Actions workflow triggered on PR: matrix over plugin directories, runs `pip install -e . -e plugins/${{ matrix.plugin }}` then `pytest tests/unit/plugin/ tests/integration/plugin/ -v` per plugin; fail-fast: false
- [X] T045 [P] [US5] Create `k8s/cgc-plugin-otel/deployment.yaml` — standard `Deployment` (replicas: 1, image ref from registry, env from ConfigMap `cgc-config` for NEO4J_URI/USERNAME + Secret `cgc-secrets` for NEO4J_PASSWORD, readinessProbe via exec checking grpc import, no hostNetwork)
- [X] T046 [P] [US5] Create `k8s/cgc-plugin-otel/service.yaml` — `ClusterIP` Service exposing port 5317 (gRPC receiver) and 4318 (HTTP, forwarded from collector)
**Checkpoint**: Triggering the workflow on a test tag builds all services in parallel; one intentional Dockerfile error only fails that service's job; remaining images publish to registry with correct semver tags.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: E2E validation, cross-layer queries documentation, and developer experience
improvements that span multiple user stories.

- [X] T048 Write `tests/e2e/plugin/test_plugin_lifecycle.py` — full user journey E2E test: install stub plugin editable → cgc starts with stub command → cgc plugin list shows stub → stub MCP tool appears in tools/list → call stub_hello via MCP → uninstall stub → cgc restarts cleanly; also: install otel plugin → start receiver → call write_batch with synthetic spans → cross-layer Cypher query returns results; run with `./tests/run_tests.sh e2e`
- [X] T049 [P] Create `docs/plugins/cross-layer-queries.md` — 5 canonical cross-layer Cypher queries validating SC-005: (1) execution path for route, (2) recent methods with no spec, (3) cross-service call chains, (4) specs describing recently-active code, (5) static code never observed at runtime; include expected result schema for each
- [X] T050 [P] Create `docs/plugins/authoring-guide.md` — minimal plugin authoring guide referencing `contracts/plugin-interface.md` and `plugins/cgc-plugin-stub/` as the worked example; covers: package scaffold, PLUGIN_METADATA, CLI contract, MCP contract, testing, publishing to PyPI
- [X] T051 [P] Update root `CLAUDE.md` agent context with new plugin directories, plugin entry-point groups (`cgc_cli_plugins`, `cgc_mcp_plugins`), and the `plugins/` layout — run `.specify/scripts/bash/update-agent-context.sh claude`
- [X] T052 Run full `quickstart.md` validation: install all three plugins editable, execute every command in `specs/001-cgc-plugin-extension/quickstart.md` end-to-end, verify all succeed; update quickstart if any step is incorrect

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T002-T005 in parallel
- **Foundational (Phase 2)**: Depends on Setup (T001 for dirs, T006 for root pyproject)
  - T007 (schema) and T010 (test runner) are independent of each other — run in parallel
  - T008 (unit tests) must be written before T009 (PluginRegistry implementation)
- **US1 (Phase 3)**: Depends on Foundational (T009 PluginRegistry complete)
  - T011 (integration tests) written before T012-T016
  - T012, T013, T014 (stub plugin files) independent of each other — run in parallel
  - T015 and T016 (core modifications) can run in parallel once T009 is done
- **US2 (Phase 4)**: Depends on US1 complete (plugin loading infrastructure)
  - T017 (unit tests) before T018-T023
  - T018, T019 (metadata + CLI) independent — parallel
  - T020 → T021 → T022 (processor → writer → receiver — sequential)
  - T023 (MCP tools) independent of T020-T022 — can run in parallel with T021
  - T024 (OTel Collector config), T025 (docker-compose) independent — parallel after T022
- **US3 (Phase 5)**: Depends on US1 complete; independent of US2
  - T027 (unit tests) before T028-T032
  - T028, T029 (metadata + CLI) parallel
  - T030 → T031 (dbgp_server → neo4j_writer — sequential; writer depends on parsed frames)
  - T032 (MCP tools) independent — parallel with T031
- **US4 (Phase 6)**: Depends on US2 + US3 complete (Dockerfiles need working services)
  - T039, T040 (Dockerfiles) parallel
  - T042 (services.json) before T043 (workflow)
  - T044 (test workflow) parallel with T043
  - T045, T046 (K8s manifests) parallel, independent of T043-T044
- **Polish (Final Phase)**: Depends on all user stories complete
  - T049, T050, T051 all parallel
  - T052 (quickstart validation) last — sequentially after T048-T051

### User Story Dependencies

- **US1 (P1)**: No story dependencies — first to implement
- **US2 (P2)**: Depends on US1 complete
- **US3 (P3)**: Depends on US1 complete — independent of US2
- **US4 (P4)**: Depends on US2 + US3 complete (container services need working implementations)

### Within Each User Story

- Unit/integration tests MUST be written and FAIL before corresponding implementation
- `__init__.py` (metadata) before CLI and MCP modules
- CLI and MCP modules can be written in parallel
- Core logic (processor, writer, server) before MCP handlers that use it
- Docker/compose additions after core implementation is working

---

## Parallel Execution Examples

### Phase 1 (Setup)
```
Parallel: T002, T003, T005 — three plugin pyproject.toml files, different paths
Then: T001 (dirs), T006 (root pyproject)
```

### Phase 2 (Foundational)
```
Parallel: T007 (schema migration), T010 (test runner update)
Sequential: T008 (write unit tests) → T009 (implement PluginRegistry)
```

### US2 (OTEL Plugin)
```
Write + fail: T017
Parallel: T018, T019 (metadata + CLI)
Sequential: T020 → T021 → T022 (processor → writer → receiver)
Parallel with T021: T023 (MCP tools — uses db_manager directly, not receiver)
Parallel: T024, T025 (config + docker-compose)
Then: T026 (integration tests)
```

### US4 (CI/CD)
```
Parallel: T039, T040 (two Dockerfiles)
Sequential: T042 → T043 (services.json must exist before workflow reads it)
Parallel: T044, T045, T046 (test workflow + K8s manifests)
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001–T006)
2. Complete Phase 2: Foundational (T007–T010)
3. Complete Phase 3: US1 Plugin Foundation (T011–T016)
4. **STOP and VALIDATE**: `cgc plugin list` works; stub plugin loads; MCP tools list includes stub; broken plugin doesn't crash CGC
5. Deploy/demo: plugin system is usable by third-party authors

### Incremental Delivery

1. Setup + Foundational → PluginRegistry ready
2. US1 → Plugin system works → **demo: install any plugin**
3. US2 → Runtime intelligence → **demo: "show what ran during this request"**
4. US3 → Dev traces → **demo: "show concrete implementations that ran"**
5. US4 → CI/CD → **demo: `git tag v0.1.0` builds all images automatically**

### Parallel Team Strategy

With 2 developers after US1 is complete:
- Developer A: US2 (OTEL Plugin)
- Developer B: US3 (Xdebug Plugin)

Both complete independently, then US4 (CI/CD) begins.

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in the same phase
- `[US?]` maps each task to its user story for traceability and independent delivery
- Tests MUST be written and FAIL before implementation — this is NON-NEGOTIABLE per Constitution Principle III
- Each phase has a named Checkpoint — validate before moving to the next phase
- Verify `./tests/run_tests.sh fast` passes after completing each phase
- Plugin name prefix convention for MCP tools: `<pluginname>_<toolname>` (e.g., `otel_query_spans`)
- No credentials in Dockerfiles or docker-compose.yml — all via environment variables
- Xdebug plugin: requires `CGC_PLUGIN_XDEBUG_ENABLED=true` at runtime; absent = no TCP port opened
