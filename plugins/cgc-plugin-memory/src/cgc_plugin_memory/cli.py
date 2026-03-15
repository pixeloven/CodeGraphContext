"""CLI command group contributed by the Memory plugin."""
from __future__ import annotations

import typer
from typing import Optional

memory_app = typer.Typer(name="memory", help="Project knowledge memory commands.")


@memory_app.command("store")
def store(
    entity_type: str = typer.Option(..., "--type", help="Knowledge type (spec, decision, note, …)"),
    name: str = typer.Option(..., "--name", help="Short descriptive name"),
    content: str = typer.Option(..., "--content", help="Full content / body text"),
    links_to: Optional[str] = typer.Option(None, "--links-to", help="FQN of code node to link via DESCRIBES"),
):
    """Store a knowledge entity in the graph."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
    except Exception as e:
        typer.echo(f"Database unavailable: {e}", err=True)
        raise typer.Exit(1)

    from cgc_plugin_memory.mcp_tools import _make_store_handler
    result = _make_store_handler(db)(entity_type=entity_type, name=name, content=content, links_to=links_to)
    typer.echo(f"Stored memory {result['memory_id']}")


@memory_app.command("search")
def search(
    query: str = typer.Argument(..., help="Search terms"),
    limit: int = typer.Option(10, "--limit"),
):
    """Full-text search across stored memories."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
    except Exception as e:
        typer.echo(f"Database unavailable: {e}", err=True)
        raise typer.Exit(1)

    from cgc_plugin_memory.mcp_tools import _make_search_handler
    result = _make_search_handler(db)(query=query, limit=limit)
    if not result["results"]:
        typer.echo("No results found.")
        return
    for row in result["results"]:
        typer.echo(f"[{row.get('entity_type')}] {row.get('name')}  (score: {row.get('score', '?'):.3f})")
        typer.echo(f"  {str(row.get('content',''))[:120]}")


@memory_app.command("undocumented")
def undocumented(
    node_type: str = typer.Option("Class", "--type", help="Class or Method"),
    limit: int = typer.Option(20, "--limit"),
):
    """List code nodes that have no linked Memory (no documentation/spec)."""
    try:
        from codegraphcontext.core import get_database_manager
        db = get_database_manager()
    except Exception as e:
        typer.echo(f"Database unavailable: {e}", err=True)
        raise typer.Exit(1)

    from cgc_plugin_memory.mcp_tools import _make_undocumented_handler
    result = _make_undocumented_handler(db)(node_type=node_type, limit=limit)
    if not result["nodes"]:
        typer.echo(f"All {node_type} nodes are documented.")
        return
    typer.echo(f"Undocumented {node_type} nodes:")
    for row in result["nodes"]:
        typer.echo(f"  {row.get('fqn')}")


@memory_app.command("status")
def status():
    """Show Memory plugin status."""
    typer.echo("Memory plugin is active.")
    typer.echo("Use 'cgc memory store' to add knowledge entities.")
    typer.echo("Use 'cgc memory undocumented' to find unspecced code.")


def get_plugin_commands() -> tuple[str, typer.Typer]:
    """Entry point: return (command_name, typer_app)."""
    return ("memory", memory_app)
