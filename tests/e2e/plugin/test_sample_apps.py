"""E2E test wrapping samples/smoke-all.sh.

Validates the full pipeline: index code → run instrumented apps → generate
OTEL spans → query cross-layer graph.

Requires Docker Compose and a running sample stack. Skipped automatically if
Docker is not available or the sample containers are not running.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SAMPLES_DIR = Path(__file__).resolve().parents[3] / "samples"
SMOKE_SCRIPT = SAMPLES_DIR / "smoke-all.sh"


def _docker_available() -> bool:
    """Check if Docker CLI is available and the daemon is responsive."""
    docker = shutil.which("docker")
    if not docker:
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


def _samples_running() -> bool:
    """Check if the sample app containers are running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--status", "running", "-q"],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
            timeout=10,
        )
        # At least 3 containers should be running (the 3 sample apps)
        running = [line for line in result.stdout.strip().splitlines() if line]
        return len(running) >= 3
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.mark.skipif(
    not _docker_available(),
    reason="Docker not available",
)
@pytest.mark.skipif(
    not _samples_running(),
    reason="Sample app containers not running (run: cd samples/ && docker compose up -d)",
)
class TestSampleApps:
    """End-to-end validation of CGC sample applications via smoke-all.sh."""

    def test_smoke_script_passes(self):
        """Run smoke-all.sh and assert it exits successfully.

        The smoke script runs 7 assertions against the Neo4j graph:
        - service_count >= 3
        - span_orders > 0
        - static_functions > 0
        - static_classes > 0
        - cross_service > 0
        - trace_links > 0
        - correlates_to == 0 (WARN, not FAIL — known FQN gap)

        Exit code 0 means all assertions passed (WARNs are OK).
        Exit code 1 means at least one assertion FAILed.
        """
        result = subprocess.run(
            ["bash", str(SMOKE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
            timeout=300,  # 5 minutes max
        )

        # Print output for debugging on failure
        if result.returncode != 0:
            print("=== STDOUT ===")
            print(result.stdout)
            print("=== STDERR ===")
            print(result.stderr)

        assert result.returncode == 0, (
            f"smoke-all.sh failed (exit code {result.returncode})\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_smoke_script_no_fail_lines(self):
        """Verify the smoke output contains no FAIL lines."""
        result = subprocess.run(
            ["bash", str(SMOKE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=SAMPLES_DIR,
            timeout=300,
        )

        fail_lines = [
            line for line in result.stdout.splitlines()
            if "FAIL:" in line
        ]

        assert not fail_lines, (
            f"Smoke script reported failures:\n" +
            "\n".join(fail_lines)
        )
