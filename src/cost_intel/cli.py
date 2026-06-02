"""Cost Intelligence CLI — AI spending tracker with cost-quality correlation."""

import typer
from rich.console import Console

from cost_intel import __version__

app = typer.Typer(help="Cost Intelligence — AI spending tracker")
console = Console()


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"cost-intel {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True
    ),
) -> None:
    """Cost Intelligence — AI spending tracker with cost-quality correlation."""
    if ctx.invoked_subcommand is None:
        console.print("[bold]cost-intel[/bold] — AI spending tracker")
        console.print("Run [bold]cost-intel --help[/bold] for commands.")
