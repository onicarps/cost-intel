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


# --- refresh-pricing command ---


@app.command(name="refresh-pricing")
def refresh_pricing_cmd() -> None:
    """Refresh model pricing from OpenRouter API."""
    from cost_intel.pricing import refresh_all_pricing

    count = refresh_all_pricing()
    console.print(f"[green]✓[/green] Refreshed pricing for [bold]{count}[/bold] models")


# --- pricing sub-app ---

pricing_app = typer.Typer(help="Model pricing management")


@pricing_app.command("set")
def pricing_set(
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
    input_price: float = typer.Option(
        ..., "--input-price", help="Input price per 1K tokens"
    ),
    output_price: float = typer.Option(
        ..., "--output-price", help="Output price per 1K tokens"
    ),
) -> None:
    """Set manual pricing for a private/enterprise model."""
    from cost_intel.pricing import set_manual_pricing

    provider = model.split("/")[0] if "/" in model else "custom"
    set_manual_pricing(model, provider, input_price, output_price)
    console.print(
        f"[green]✓[/green] Pricing set for {model}: "
        f"${input_price}/1K in, ${output_price}/1K out"
    )


@pricing_app.command("show")
def pricing_show(
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
) -> None:
    """Show current pricing for a model."""
    from cost_intel.pricing import get_pricing

    p = get_pricing(model)
    if p:
        console.print(
            f"{model}: ${p['input_price_per_1k_tokens']}/1K in, "
            f"${p['output_price_per_1k_tokens']}/1K out "
            f"(effective {p['effective_date']}, source: {p['source']})"
        )
    else:
        console.print(f"[yellow]No pricing found for {model}[/yellow]")


app.add_typer(pricing_app, name="pricing")
