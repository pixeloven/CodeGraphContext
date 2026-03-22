"""CLI command group contributed by the OTEL plugin."""
from __future__ import annotations

import os
import typer
from typing import Optional

otel_app = typer.Typer(name="otel", help="OpenTelemetry span commands.")


@otel_app.command("query-spans")
def query_spans(
    route: Optional[str] = typer.Option(None, "--route", help="Filter by HTTP route"),
    service: Optional[str] = typer.Option(None, "--service", help="Filter by service name"),
    limit: int = typer.Option(20, "--limit", help="Maximum results"),
):
    """Query spans stored in the graph, optionally filtered by route or service."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
    except Exception as e:
        typer.echo(f"Database unavailable: {e}", err=True)
        raise typer.Exit(1)

    where_clauses = []
    params: dict = {"limit": limit}
    if route:
        where_clauses.append("sp.http_route = $route")
        params["route"] = route
    if service:
        where_clauses.append("sp.service_name = $service")
        params["service"] = service

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    cypher = f"MATCH (sp:Span) {where} RETURN sp.span_id, sp.name, sp.service_name, sp.duration_ms ORDER BY sp.start_time_ns DESC LIMIT $limit"

    try:
        driver = db.get_driver()
        with driver.session() as session:
            result = session.run(cypher, **params)
            rows = result.data()
    except Exception as e:
        typer.echo(f"Query failed: {e}", err=True)
        raise typer.Exit(1)

    if not rows:
        typer.echo("No spans found.")
        return
    for row in rows:
        typer.echo(f"[{row.get('sp.service_name')}] {row.get('sp.name')} — {row.get('sp.duration_ms', '?')}ms  id={row.get('sp.span_id')}")


@otel_app.command("list-services")
def list_services():
    """List all services observed in the span graph."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
        driver = db.get_driver()
        with driver.session() as session:
            rows = session.run("MATCH (s:Service) RETURN s.name ORDER BY s.name").data()
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not rows:
        typer.echo("No services found.")
        return
    for row in rows:
        typer.echo(row["s.name"])


@otel_app.command("status")
def status():
    """Show whether the OTEL receiver process is configured."""
    port = os.environ.get("OTEL_RECEIVER_PORT", "5317")
    typer.echo(f"OTEL receiver port: {port}")
    typer.echo("Run 'python -m cgc_plugin_otel.receiver' to start the gRPC receiver.")


def get_plugin_commands() -> tuple[str, typer.Typer]:
    """Entry point: return (command_name, typer_app)."""
    return ("otel", otel_app)
