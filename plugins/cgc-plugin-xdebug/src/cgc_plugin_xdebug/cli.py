"""CLI command group contributed by the Xdebug plugin."""
from __future__ import annotations

import os
import threading
import typer
from typing import Optional

xdebug_app = typer.Typer(name="xdebug", help="Xdebug DBGp call-stack capture commands.")

_server_thread: threading.Thread | None = None


@xdebug_app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address"),
    port: int = typer.Option(9003, "--port", help="DBGp listen port"),
):
    """Start the Xdebug DBGp TCP listener (requires CGC_PLUGIN_XDEBUG_ENABLED=true)."""
    global _server_thread
    if os.environ.get("CGC_PLUGIN_XDEBUG_ENABLED", "").lower() != "true":
        typer.echo("CGC_PLUGIN_XDEBUG_ENABLED is not set to 'true' — refusing to start.", err=True)
        raise typer.Exit(1)

    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
    except Exception as e:
        typer.echo(f"Database unavailable: {e}", err=True)
        raise typer.Exit(1)

    from cgc_plugin_xdebug.neo4j_writer import XdebugWriter
    from cgc_plugin_xdebug.dbgp_server import DBGpServer

    writer = XdebugWriter(db)
    server = DBGpServer(writer, host=host, port=port)

    _server_thread = threading.Thread(target=server.listen, daemon=True, name="xdebug-dbgp")
    _server_thread.start()
    typer.echo(f"Xdebug DBGp listener started on {host}:{port}  (Ctrl-C to stop)")
    try:
        _server_thread.join()
    except KeyboardInterrupt:
        server.stop()
        typer.echo("\nXdebug listener stopped.")


@xdebug_app.command("status")
def status():
    """Show Xdebug listener configuration."""
    enabled = os.environ.get("CGC_PLUGIN_XDEBUG_ENABLED", "false")
    port = os.environ.get("XDEBUG_LISTEN_PORT", "9003")
    typer.echo(f"CGC_PLUGIN_XDEBUG_ENABLED: {enabled}")
    typer.echo(f"XDEBUG_LISTEN_PORT: {port}")
    if enabled.lower() != "true":
        typer.echo("Listener is NOT enabled.")
    else:
        typer.echo("Run 'cgc xdebug start' to start the listener.")


@xdebug_app.command("list-chains")
def list_chains(
    limit: int = typer.Option(20, "--limit", help="Maximum chains to display"),
):
    """List the most-observed call stack chains."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
        driver = db.get_driver()
        with driver.session() as session:
            rows = session.run(
                "MATCH (sf:StackFrame) WHERE sf.observation_count > 0 "
                "RETURN sf.fqn AS fqn, sf.observation_count AS count "
                "ORDER BY count DESC LIMIT $limit",
                limit=limit,
            ).data()
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not rows:
        typer.echo("No chains recorded.")
        return
    for row in rows:
        typer.echo(f"{row['count']:>6}x  {row['fqn']}")


def get_plugin_commands() -> tuple[str, typer.Typer]:
    """Entry point: return (command_name, typer_app)."""
    return ("xdebug", xdebug_app)
