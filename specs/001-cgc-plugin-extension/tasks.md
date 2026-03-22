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

## Phase 7: User Story 5 — Sample Applications for End-to-End Plugin Validation (Priority: P5)

**Goal**: Three sample applications (PHP/Laravel, Python/FastAPI, TypeScript/Express) with
shared Docker Compose infrastructure and an automated smoke script that validates the full
pipeline: index code → run instrumented app → generate OTEL spans → query cross-layer graph.

**Independent Test**: `cd samples/ && docker compose up -d && bash smoke-all.sh` — all
assertions pass (correlates_to warns). Neo4j Browser shows Service, Span, Function, Class
nodes. `cgc otel list-services` returns `sample-php`, `sample-python`, `sample-ts-gateway`.

### Phase 7a: PHP/Laravel Sample App (T053-T056) — parallel with 7b, 7c

- [X] T053 [P] [US5] Create `samples/php-laravel/` directory structure: `app/Http/Controllers/`, `app/Services/`, `app/Repositories/`, `routes/`, `database/` — standard Laravel layout
- [X] T054 [P] [US5] Implement PHP controllers, services, repositories: `OrderController` (GET/POST `/api/orders`), `OrderService`, `OrderRepository` (SQLite), `HealthController` (`/health`) — cross-class call hierarchy producing meaningful call graph
- [X] T055 [P] [US5] Create `samples/php-laravel/Dockerfile` — PHP 8.3 + Composer, OTEL auto-instrumentation (`open-telemetry/opentelemetry-auto-laravel`), Xdebug extension configured for remote debugging, env: `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`, `OTEL_SERVICE_NAME=sample-php`
- [X] T056 [P] [US5] Create `samples/php-laravel/composer.json` + `samples/php-laravel/README.md` — dependencies, FQN format documentation (`Namespace\Class::method`), route table

### Phase 7b: Python/FastAPI Sample App (T057-T060) — parallel with 7a, 7c

- [X] T057 [P] [US5] Create `samples/python-fastapi/` directory structure: `app/`, `app/services/`, `app/repositories/` — Python package layout
- [X] T058 [P] [US5] Implement FastAPI app: `OrderRouter` (GET/POST `/api/orders`), `OrderService`, `OrderRepository` (SQLite via aiosqlite), `HealthRouter` (`/health`) — service/repository pattern with cross-module calls
- [X] T059 [P] [US5] Create `samples/python-fastapi/Dockerfile` — Python 3.12-slim, `opentelemetry-instrument` wrapping `uvicorn`, env: `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`, `OTEL_SERVICE_NAME=sample-python`
- [X] T060 [P] [US5] Create `samples/python-fastapi/requirements.txt` + `samples/python-fastapi/README.md` — dependencies, Python FQN format documentation (`module.Class.method` vs PHP `Namespace\Class::method`)

### Phase 7c: TypeScript/Express Gateway (T061-T063) — parallel with 7a, 7b

- [X] T061 [P] [US5] Create `samples/ts-express-gateway/` directory structure: `src/`, `src/routes/`, `src/services/` — TypeScript project layout
- [X] T062 [P] [US5] Implement Express gateway: `/api/dashboard` (aggregates from PHP + Python backends via HTTP), `/api/orders` (proxies to PHP backend), `/health` — W3C trace context propagation via `@opentelemetry/api`, CLIENT spans with `peer.service` attribute
- [X] T063 [P] [US5] Create `samples/ts-express-gateway/Dockerfile` (multi-stage: build TS → run Node), `package.json`, `tsconfig.json`, `samples/ts-express-gateway/README.md` — documents cross-service span generation and `CALLS_SERVICE` edge formation

### Phase 7d: Shared Infrastructure (T064-T068) — after 7a-7c

- [X] T064 [US5] Create `samples/KNOWN-LIMITATIONS.md` — documents FQN correlation gap: OTEL writer matches `(m:Method {fqn: sp.fqn})` but CGC creates `Function` nodes without `fqn` property; explains that `CORRELATES_TO` and `RESOLVES_TO` edges will not form; references graph_builder.py:379; states this is a known limitation, not a bug; references future FQN story
- [X] T065 [US5] Create `samples/docker-compose.yml` — uses `include` to extend `docker-compose.plugin-stack.yml` from project root; adds 3 app services (`sample-php`, `sample-python`, `sample-ts-gateway`); depends_on otel-collector healthcheck; shared network
- [X] T066 [US5] Create `samples/smoke-all.sh` — 6-phase automated validation: (1) wait for services healthy, (2) index sample code via `cgc index`, (3) generate traffic (curl to all routes), (4) wait for span ingestion (poll with timeout), (5) assert via Cypher queries (service_count>=3, span_orders>0, static_functions>0, static_classes>0, cross_service>0, trace_links>0, correlates_to==0 as WARN), (6) summary with pass/warn/fail counts
- [X] T067 [US5] Create `samples/README.md` — full walkthrough: prerequisites, architecture diagram (ASCII), `docker compose up` instructions, smoke script usage, Neo4j Browser exploration guide, per-app route tables, link to KNOWN-LIMITATIONS.md
- [X] T068 [US5] Write `tests/e2e/plugin/test_sample_apps.py` — E2E test wrapping smoke-all.sh: `subprocess.run(["bash", "samples/smoke-all.sh"])`, asserts exit code 0, parses output for FAIL lines; skipped if Docker not available (`pytest.mark.skipif`)

**Checkpoint**: `cd samples/ && docker compose up -d` starts all services; `bash smoke-all.sh` passes all assertions (correlates_to warns); Neo4j Browser shows populated graph.

---

## Phase 8: User Story 6 — Hosted MCP Server Container Image (Priority: P6)

**Goal**: The CGC MCP server supports plain JSON-RPC HTTP transport natively (no
supergateway/Node.js), with CORS and health checks. No application-level auth —
authentication deferred to reverse proxy or network controls. A dedicated Docker
image runs it as a long-running service deployable to Docker, Docker Swarm, and
Kubernetes. Single-process async via uvicorn default asyncio event loop.

**Independent Test**: `docker compose up -d cgc-mcp neo4j` → wait for healthy →
`curl -X POST http://localhost:8045/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`
returns JSON with all core + plugin tools.

### Phase 8a: HTTP Transport (T069-T073) — sequential

> **NOTE: Write tests (T069) FIRST, ensure they FAIL before T070-T072**

- [X] T069 [US6] Write `tests/unit/test_http_transport.py` — unit tests (no network): HTTP handler parses MCP JSON-RPC from request body and returns JSON-RPC response; `/healthz` returns 200 with `{"status":"ok","tools":N}` when DB connected; `/healthz` returns 503 with `{"status":"unhealthy"}` when DB unreachable; CORS preflight returns correct headers; unknown routes return 404. **Run and confirm FAILING before T070.**
- [X] T070 [US6] Add `--transport` option to `cgc mcp start` in `src/codegraphcontext/cli/main.py` — accepts `stdio` (default, existing behavior) or `http`; when `http`, reads `CGC_MCP_PORT` (default 8045) from env; launches HTTP server instead of stdio loop
- [X] T071 [US6] Implement `src/codegraphcontext/http_transport.py` — `HTTPTransport` class using uvicorn + starlette (already a dependency): `POST /mcp` route that deserializes JSON-RPC, calls `MCPServer.handle_request()`, returns JSON-RPC response; `GET /healthz` route that returns `{"status":"ok","tools":N}` (HTTP 200) when DB connected or `{"status":"unhealthy"}` (HTTP 503) when DB unreachable; CORS middleware with configurable origin via `CGC_CORS_ORIGIN` (default `*`); single-process async (uvicorn default asyncio event loop, no workers)
- [X] T072 [US6] Refactor `src/codegraphcontext/server.py` — extract request routing from the stdin loop into a `handle_request(method, params, request_id)` method that both the stdio loop and HTTP transport can call; existing stdio behavior unchanged
- [X] T073 [US6] Write `tests/integration/test_http_transport_integration.py` — start HTTP transport on a random port, send MCP requests via `httpx`, verify: `initialize` returns capabilities, `tools/list` includes core + plugin tools, `tools/call` with `stub_hello` returns greeting, `/healthz` returns 200 when DB connected, `/healthz` returns 503 when DB unreachable

### Phase 8b: Container Image (T074-T077) — after 8a

- [X] T074 [P] [US6] Create `Dockerfile.mcp` — multi-stage build from existing `Dockerfile`, installs core + all plugins (`cgc-plugin-otel`, `cgc-plugin-xdebug`), `EXPOSE 8045`, `HEALTHCHECK` via `/healthz`, `CMD ["cgc", "mcp", "start", "--transport", "http"]`; non-root user, no embedded credentials
- [X] T075 [P] [US6] Add `cgc-mcp` service to `docker-compose.plugin-stack.yml` — build from `Dockerfile.mcp`, env: `DATABASE_TYPE`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `CGC_CORS_ORIGIN`, `CGC_MCP_PORT`; ports `8045:8045`; depends_on neo4j healthy; replaces existing `cgc-core` service (which restarts in a loop)
- [X] T076 [P] [US6] Create `k8s/cgc-mcp/deployment.yaml` — Deployment with readinessProbe on `/healthz`, env from ConfigMap + Secret, image ref from registry; `k8s/cgc-mcp/service.yaml` — ClusterIP exposing port 8045
- [X] T077 [US6] Add `cgc-mcp` to `.github/services.json` for CI/CD matrix build — path `./`, dockerfile `Dockerfile.mcp`, health_check `http_get`

### Phase 8c: Documentation and Testing (T078-T080) — after 8b

- [X] T078 [US6] Create `docs/deployment/MCP_SERVER_HOSTING.md` — deployment guide covering: Docker standalone, Docker Compose with Neo4j, Docker Swarm, Kubernetes; env var reference; client configuration (Claude Desktop, VS Code, Cursor, Claude Code) for remote HTTP MCP endpoint; reverse proxy auth and TLS recommendations
- [X] T079 [US6] Write `tests/e2e/test_mcp_container.py` — E2E test: build `Dockerfile.mcp`, start container with docker-compose, send MCP requests via curl/httpx, assert `tools/list` returns core + plugin tools, assert `tools/call` executes, assert `/healthz` 200; skipped if Docker not available
- [X] T080 [US6] Update `samples/docker-compose.yml` to include `cgc-mcp` service as an alternative to `cgc-core`, with documentation in `samples/README.md` showing how to connect AI clients to the hosted endpoint

**Checkpoint**: `docker compose up -d cgc-mcp neo4j` → `/healthz` returns 200 → `curl -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' http://localhost:8045/mcp` returns tool listing → same image deploys to K8s pod.

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
- **US5 (Phase 7)**: Depends on US2 + US4 complete (needs working OTEL plugin + Docker images)
  - Phase 7a (T053-T056), 7b (T057-T060), 7c (T061-T063) all parallel — three independent apps
  - Phase 7d (T064-T068) sequential after 7a-7c — shared infrastructure depends on all apps
  - T064 (KNOWN-LIMITATIONS) → T065 (docker-compose) → T066 (smoke script) → T067 (README) → T068 (E2E test)
- **US6 (Phase 8)**: Depends on US1 complete (plugin loading for tool listing); independent of US2-US5
  - Phase 8a (T069-T073) sequential — tests first, then transport, then server refactor
  - Phase 8b (T074-T077) after 8a — T074, T075, T076 parallel; T077 after T074
  - Phase 8c (T078-T080) after 8b — T078 parallel with T079; T080 last
- **Polish (Final Phase)**: Depends on all user stories complete
  - T049, T050, T051 all parallel
  - T052 (quickstart validation) last — sequentially after T048-T051

### User Story Dependencies

- **US1 (P1)**: No story dependencies — first to implement
- **US2 (P2)**: Depends on US1 complete
- **US3 (P3)**: Depends on US1 complete — independent of US2
- **US4 (P4)**: Depends on US2 + US3 complete (container services need working implementations)
- **US5 (P5)**: Depends on US2 + US4 complete (needs working OTEL plugin + Docker infrastructure)
- **US6 (P6)**: Depends on US1 complete (plugin loading); independent of US2-US5 (can be parallelized)

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

### US6 (Hosted MCP Server)
```
Sequential: T069 (write tests, confirm FAIL) → T070 → T071 → T072 → T073
Parallel: T074, T075, T076 (Dockerfile, docker-compose, K8s manifests)
Then: T077 (services.json update)
Parallel: T078, T079 (docs + E2E test)
Then: T080 (samples integration)
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
6. US5 → Sample apps → **demo: `docker compose up && bash smoke-all.sh` — full pipeline validated**
7. US6 → Hosted MCP → **demo: `curl -d '...' http://cgc-mcp:8045/mcp` — remote AI clients connect**

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
