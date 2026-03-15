"""CLI command group contributed by the stub plugin."""
import typer

stub_app = typer.Typer(name="stub", help="Stub plugin commands (for testing).")


@stub_app.command()
def hello():
    """Echo a greeting from the stub plugin."""
    typer.echo("Hello from stub plugin")


def get_plugin_commands() -> tuple[str, typer.Typer]:
    """Entry point: return (command_name, typer_app)."""
    return ("stub", stub_app)
