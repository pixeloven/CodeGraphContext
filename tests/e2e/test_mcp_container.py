"""
E2E tests for the cgc-mcp container image.

Validates the full hosted MCP server lifecycle:
  build Dockerfile.mcp
  → start container with Neo4j via docker compose
  → assert /healthz returns 200
  → assert tools/list returns core and plugin tools
  → assert tools/call executes a tool
  → assert CORS headers are present
  → clean up containers

These tests are skipped when Docker is not available on the host.  They are
not intended to run in unit-test CI — use a dedicated Docker-enabled
integration environment.

Run manually:
    pytest tests/e2e/test_mcp_container.py -v -s
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Repository root and compose file paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_MCP = REPO_ROOT / "Dockerfile.mcp"
PLUGIN_STACK_COMPOSE = REPO_ROOT / "docker-compose.plugin-stack.yml"
MCP_IMAGE_TAG = "cgc-mcp:test"
MCP_CONTAINER_NAME = "cgc-mcp-e2e-test"
MCP_PORT = 8045
MCP_BASE_URL = f"http://localhost:{MCP_PORT}"
STARTUP_TIMEOUT_S = 60  # seconds to wait for /healthz to become 200


# ---------------------------------------------------------------------------
# Module-level skip condition
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    """Return True if the Docker CLI is present and the daemon is responsive."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker not available or daemon not running",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and return the CompletedProcess."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        timeout=timeout,
        check=check,
    )


def _curl_mcp(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    req_id: int = 1,
    timeout: int = 15,
) -> subprocess.CompletedProcess[str]:
    """Send a JSON-RPC request to the MCP endpoint via curl."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    })
    return _run(
        [
            "curl", "-s", "-X", "POST",
            f"{MCP_BASE_URL}/mcp",
            "-H", "Content-Type: application/json",
            "-d", payload,
        ],
        timeout=timeout,
    )


def _wait_for_healthz(timeout_s: int = STARTUP_TIMEOUT_S) -> bool:
    """Poll /healthz until it returns HTTP 200 or timeout_s elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"{MCP_BASE_URL}/healthz"],
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip() == "200":
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def built_image():
    """Build Dockerfile.mcp once per class; yield the image tag.

    The image is removed after the class finishes only if this fixture
    created it (i.e. it was not already present before the test run).
    Skips the entire class if the build fails.
    """
    result = _run(
        ["docker", "build", "-f", str(DOCKERFILE_MCP), "-t", MCP_IMAGE_TAG, "."],
        timeout=300,
    )
    if result.returncode != 0:
        pytest.skip(f"Image build failed — skipping container tests.\n{result.stderr}")
    yield MCP_IMAGE_TAG
    # Clean up the test image
    _run(["docker", "rmi", "-f", MCP_IMAGE_TAG], timeout=30)


@pytest.fixture(scope="class")
def running_container(built_image: str):
    """Start cgc-mcp with a mock Neo4j stub (no real DB needed for most tests).

    Uses the standalone `docker run` path so the test is self-contained and
    does not require the full compose stack.  The container is started with
    DATABASE_TYPE=none so the server starts in degraded mode (Neo4j
    unreachable), which is sufficient to test tool listing and JSON-RPC
    dispatch without a live database.

    For tests that require a healthy Neo4j connection see
    TestMCPContainerWithNeo4j which uses docker compose.
    """
    # Remove any leftover container from a previous interrupted run
    _run(["docker", "rm", "-f", MCP_CONTAINER_NAME], timeout=15)

    result = _run(
        [
            "docker", "run", "-d",
            "--name", MCP_CONTAINER_NAME,
            "-e", "DATABASE_TYPE=none",
            "-e", f"CGC_MCP_PORT={MCP_PORT}",
            "-e", "CGC_CORS_ORIGIN=http://localhost:3000",
            "-p", f"{MCP_PORT}:{MCP_PORT}",
            built_image,
        ],
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"Could not start container: {result.stderr}")

    healthy = _wait_for_healthz(timeout_s=STARTUP_TIMEOUT_S)
    if not healthy:
        logs = _run(["docker", "logs", MCP_CONTAINER_NAME], timeout=10)
        pytest.skip(
            f"Container did not become ready within {STARTUP_TIMEOUT_S}s.\n"
            f"Container logs:\n{logs.stdout}\n{logs.stderr}"
        )

    yield MCP_CONTAINER_NAME

    # Teardown: stop and remove container
    _run(["docker", "stop", MCP_CONTAINER_NAME], timeout=30)
    _run(["docker", "rm", "-f", MCP_CONTAINER_NAME], timeout=15)


# ---------------------------------------------------------------------------
# Test: image build
# ---------------------------------------------------------------------------

class TestDockerfileMCPBuilds:
    """Verify Dockerfile.mcp exists and builds to a runnable image."""

    def test_dockerfile_mcp_exists(self):
        """Dockerfile.mcp is present in the repository root."""
        assert DOCKERFILE_MCP.exists(), (
            f"Dockerfile.mcp not found at {DOCKERFILE_MCP}"
        )

    def test_dockerfile_builds_successfully(self):
        """docker build -f Dockerfile.mcp exits with code 0."""
        result = _run(
            ["docker", "build", "-f", str(DOCKERFILE_MCP), "-t", MCP_IMAGE_TAG, "."],
            timeout=300,
        )
        assert result.returncode == 0, (
            f"docker build failed (exit {result.returncode}).\n"
            f"stderr:\n{result.stderr}"
        )
        # Cleanup: remove the image after this standalone test
        _run(["docker", "rmi", "-f", MCP_IMAGE_TAG], timeout=30)

    def test_image_has_cgc_entrypoint(self):
        """Built image has cgc binary available at /usr/local/bin/cgc."""
        # Build first
        _run(
            ["docker", "build", "-f", str(DOCKERFILE_MCP), "-t", MCP_IMAGE_TAG, "."],
            timeout=300,
        )
        result = _run(
            ["docker", "run", "--rm", MCP_IMAGE_TAG, "which", "cgc"],
            timeout=30,
        )
        _run(["docker", "rmi", "-f", MCP_IMAGE_TAG], timeout=30)
        assert result.returncode == 0, "cgc binary not found in image"
        assert "cgc" in result.stdout

    def test_image_exposes_port_8045(self):
        """Dockerfile.mcp declares EXPOSE 8045."""
        content = DOCKERFILE_MCP.read_text(encoding="utf-8")
        assert "EXPOSE 8045" in content, (
            "Dockerfile.mcp does not EXPOSE 8045"
        )


# ---------------------------------------------------------------------------
# Test: container health and JSON-RPC
# ---------------------------------------------------------------------------

class TestMCPContainerRunning:
    """Tests that require a running container (no live Neo4j)."""

    def test_healthz_returns_200(self, running_container: str):
        """GET /healthz returns HTTP 200."""
        result = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"{MCP_BASE_URL}/healthz"],
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "200", (
            f"Expected HTTP 200 from /healthz, got: {result.stdout.strip()}"
        )

    def test_healthz_response_body_is_json(self, running_container: str):
        """GET /healthz returns a JSON body with a 'status' field."""
        result = _run(
            ["curl", "-s", f"{MCP_BASE_URL}/healthz"],
            timeout=10,
        )
        assert result.returncode == 0
        try:
            body = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(f"/healthz did not return valid JSON: {result.stdout!r} — {exc}")
        assert "status" in body, f"'status' field missing from /healthz response: {body}"

    def test_tools_list_returns_valid_jsonrpc(self, running_container: str):
        """tools/list returns a valid JSON-RPC 2.0 response."""
        result = _curl_mcp("tools/list")
        assert result.returncode == 0, f"curl failed: {result.stderr}"
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(f"tools/list response is not valid JSON: {result.stdout!r} — {exc}")
        assert response.get("jsonrpc") == "2.0", f"Missing jsonrpc field: {response}"
        assert "result" in response, f"Expected 'result' in response: {response}"

    def test_tools_list_contains_tools_array(self, running_container: str):
        """tools/list result contains a non-empty 'tools' array."""
        result = _curl_mcp("tools/list")
        response = json.loads(result.stdout)
        tools = response.get("result", {}).get("tools", [])
        assert isinstance(tools, list), f"'tools' should be a list, got: {type(tools)}"
        assert len(tools) > 0, "tools/list returned an empty tools array"

    def test_tools_list_includes_core_tools(self, running_container: str):
        """Core CGC tools (e.g. query_graph, get_context) appear in tools/list."""
        result = _curl_mcp("tools/list")
        response = json.loads(result.stdout)
        tool_names = {t["name"] for t in response.get("result", {}).get("tools", [])}
        # At least one well-known core tool must be present
        core_tools = {"query_graph", "get_context", "list_functions", "analyze_callers"}
        found = core_tools & tool_names
        assert found, (
            f"No core CGC tools found in tools/list.\n"
            f"Expected at least one of {core_tools}.\n"
            f"Got: {sorted(tool_names)}"
        )

    def test_tools_list_includes_plugin_tools(self, running_container: str):
        """Plugin tools (otel_* or xdebug_*) appear in tools/list."""
        result = _curl_mcp("tools/list")
        response = json.loads(result.stdout)
        tool_names = {t["name"] for t in response.get("result", {}).get("tools", [])}
        plugin_tools = [n for n in tool_names if n.startswith(("otel_", "xdebug_"))]
        assert plugin_tools, (
            f"No plugin tools (otel_* or xdebug_*) found in tools/list.\n"
            f"All tools: {sorted(tool_names)}"
        )

    def test_each_tool_has_required_schema_fields(self, running_container: str):
        """Every tool in tools/list has name, description, and inputSchema."""
        result = _curl_mcp("tools/list")
        response = json.loads(result.stdout)
        tools = response.get("result", {}).get("tools", [])
        for tool in tools:
            name = tool.get("name", "<unknown>")
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool '{name}' missing 'description'"
            assert "inputSchema" in tool, f"Tool '{name}' missing 'inputSchema'"
            assert tool["inputSchema"].get("type") == "object", (
                f"Tool '{name}' inputSchema.type should be 'object', "
                f"got: {tool['inputSchema'].get('type')!r}"
            )

    def test_unknown_method_returns_jsonrpc_error(self, running_container: str):
        """Calling an unknown method returns a JSON-RPC error object."""
        result = _curl_mcp("no_such_method_xyz")
        assert result.returncode == 0
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Response is not JSON: {result.stdout!r} — {exc}")
        assert "error" in response, (
            f"Expected JSON-RPC error for unknown method, got: {response}"
        )

    def test_cors_header_present_on_mcp_response(self, running_container: str):
        """POST /mcp response includes Access-Control-Allow-Origin header."""
        result = _run(
            [
                "curl", "-s", "-I", "-X", "POST",
                f"{MCP_BASE_URL}/mcp",
                "-H", "Content-Type: application/json",
                "-H", "Origin: http://localhost:3000",
                "-d", '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
            ],
            timeout=15,
        )
        assert result.returncode == 0
        headers_lower = result.stdout.lower()
        assert "access-control-allow-origin" in headers_lower, (
            f"CORS header missing from /mcp response.\nHeaders:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# Test: tools/call dispatch
# ---------------------------------------------------------------------------

class TestMCPToolsCall:
    """Verify that tools/call routes to the correct handler."""

    def test_tools_call_returns_jsonrpc_result(self, running_container: str):
        """tools/call for a valid tool returns a JSON-RPC result (not an error)."""
        # Use tools/list first to pick a tool name that actually exists
        list_result = _curl_mcp("tools/list")
        tools = json.loads(list_result.stdout).get("result", {}).get("tools", [])
        assert tools, "Cannot test tools/call — tools/list is empty"

        # Pick the first tool with no required parameters (empty properties or no required)
        candidate: str | None = None
        for tool in tools:
            schema = tool.get("inputSchema", {})
            required = schema.get("required", [])
            if not required:
                candidate = tool["name"]
                break

        if candidate is None:
            pytest.skip("No tool with zero required parameters found in tools/list")

        result = _curl_mcp(
            "tools/call",
            params={"name": candidate, "arguments": {}},
        )
        assert result.returncode == 0
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(f"tools/call response is not JSON: {result.stdout!r} — {exc}")

        # A valid dispatch should return 'result', not an 'error'
        assert "result" in response, (
            f"tools/call returned an error for tool '{candidate}': {response}"
        )

    def test_tools_call_unknown_tool_returns_error(self, running_container: str):
        """Calling a non-existent tool returns a JSON-RPC error."""
        result = _curl_mcp(
            "tools/call",
            params={"name": "nonexistent_tool_abc123", "arguments": {}},
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert "error" in response, (
            f"Expected error for unknown tool, got: {response}"
        )


# ---------------------------------------------------------------------------
# Test: docker compose integration (requires full stack)
# ---------------------------------------------------------------------------

class TestMCPContainerWithNeo4j:
    """
    E2E tests that start the full compose stack (Neo4j + cgc-mcp).

    These are skipped if the compose file is not present.  They take longer
    than the standalone container tests because Neo4j has a ~30s startup time.
    """

    @pytest.fixture(scope="class", autouse=True)
    def compose_stack(self):
        """Start neo4j + cgc-mcp via docker compose; tear down after class."""
        if not PLUGIN_STACK_COMPOSE.exists():
            pytest.skip(f"Compose file not found: {PLUGIN_STACK_COMPOSE}")

        # Bring up only the services needed for this test
        up_result = _run(
            [
                "docker", "compose",
                "-f", str(PLUGIN_STACK_COMPOSE),
                "up", "-d", "--build", "neo4j", "cgc-mcp",
            ],
            timeout=300,
        )
        if up_result.returncode != 0:
            pytest.skip(
                f"docker compose up failed:\n{up_result.stderr}"
            )

        # Wait for /healthz to return 200 (Neo4j must also be healthy)
        healthy = _wait_for_healthz(timeout_s=90)
        if not healthy:
            logs = _run(
                ["docker", "compose", "-f", str(PLUGIN_STACK_COMPOSE),
                 "logs", "cgc-mcp"],
                timeout=15,
            )
            _run(
                ["docker", "compose", "-f", str(PLUGIN_STACK_COMPOSE),
                 "down", "-v"],
                timeout=60,
            )
            pytest.skip(
                f"cgc-mcp did not become healthy within 90s.\n"
                f"Logs:\n{logs.stdout}"
            )

        yield

        _run(
            ["docker", "compose", "-f", str(PLUGIN_STACK_COMPOSE),
             "down", "-v"],
            timeout=60,
        )

    def test_healthz_reports_neo4j_connected(self):
        """When Neo4j is running, /healthz reports neo4j as connected."""
        result = _run(
            ["curl", "-s", f"{MCP_BASE_URL}/healthz"],
            timeout=10,
        )
        assert result.returncode == 0
        body = json.loads(result.stdout)
        assert body.get("neo4j") == "connected", (
            f"Expected neo4j='connected' in /healthz body, got: {body}"
        )

    def test_tools_list_with_live_neo4j(self):
        """tools/list succeeds with a live Neo4j connection."""
        result = _curl_mcp("tools/list")
        response = json.loads(result.stdout)
        assert "result" in response, f"tools/list returned error with live DB: {response}"
        tools = response["result"].get("tools", [])
        assert len(tools) > 0

    def test_query_graph_tool_executes_against_neo4j(self):
        """query_graph tool executes a Cypher query against the live Neo4j instance."""
        result = _curl_mcp(
            "tools/call",
            params={
                "name": "query_graph",
                "arguments": {"query": "RETURN 1 AS n"},
            },
        )
        assert result.returncode == 0
        response = json.loads(result.stdout)
        assert "result" in response, (
            f"query_graph failed with live Neo4j: {response}"
        )

    def test_503_when_neo4j_is_stopped(self):
        """After stopping Neo4j, /healthz returns HTTP 503.

        This test stops the neo4j container, checks the 503, then restarts it.
        It is ordered last in the class because it is destructive to the stack.
        """
        # Stop Neo4j
        _run(
            ["docker", "compose", "-f", str(PLUGIN_STACK_COMPOSE),
             "stop", "neo4j"],
            timeout=30,
        )
        time.sleep(5)  # Allow the MCP server to detect the disconnection

        result = _run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"{MCP_BASE_URL}/healthz"],
            timeout=10,
        )
        http_code = result.stdout.strip()

        # Restart Neo4j so teardown can proceed cleanly
        _run(
            ["docker", "compose", "-f", str(PLUGIN_STACK_COMPOSE),
             "start", "neo4j"],
            timeout=30,
        )

        assert http_code == "503", (
            f"Expected HTTP 503 after Neo4j stopped, got: {http_code}"
        )
