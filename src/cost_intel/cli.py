"""Cost Intelligence CLI — AI spending tracker with cost-quality correlation."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cost_intel import __version__
from cost_intel.duration import parse_window

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


# --- record command ---


@app.command()
def record(
    model: str = typer.Option(
        ..., "--model", "-m", help="Model ID (e.g., openai/gpt-4o)"
    ),
    input_tokens: int = typer.Option(..., "--input-tokens", "-i", help="Input tokens"),
    output_tokens: int = typer.Option(
        ..., "--output-tokens", "-o", help="Output tokens"
    ),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Human label"),
    cache_read_tokens: int = typer.Option(
        0, "--cache-read-tokens", help="Cache read tokens"
    ),
    cache_write_tokens: int = typer.Option(
        0, "--cache-write-tokens", help="Cache write tokens"
    ),
    latency_ms: Optional[int] = typer.Option(None, "--latency-ms", help="Latency ms"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider name"),
    run_type: str = typer.Option("api_call", "--run-type", help="Run type"),
) -> None:
    """Record a cost run."""
    from cost_intel.record import record_run

    run_id = record_run(
        model_id=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        label=label,
        run_type=run_type,
        provider=provider,
        latency_ms=latency_ms,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    console.print(f"[green]✓[/green] Recorded run [bold]{run_id}[/bold]")


# --- report command ---


@app.command()
def report(
    by_model: bool = typer.Option(False, "--by-model", help="Group by model"),
    by_label: bool = typer.Option(False, "--by-label", help="Group by label"),
    by_day: bool = typer.Option(False, "--by-day", help="Group by day"),
    last: Optional[str] = typer.Option(
        None, "--last", "-l", help="Time window (e.g., 7d, 30d, 1w)"
    ),
) -> None:
    """Show cost report."""
    from cost_intel.report import (
        report_by_day,
        report_by_label,
        report_by_model,
        report_summary,
    )

    days = parse_window(last) if last else None

    # Show summary first
    summary = report_summary(days=days)
    console.print(f"\n[bold]Cost Report[/bold] (last {last or 'all time'})")
    console.print(
        f"  Runs: [bold]{summary.get('total_runs', 0)}[/bold]  "
        f"Cost: [bold]${summary.get('total_cost', 0):.4f}[/bold]  "
        f"Avg: [bold]${summary.get('avg_cost_per_run', 0):.4f}[/bold]"
    )

    if by_model:
        data = report_by_model(days=days)
        table = Table(title="By Model")
        table.add_column("Model", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        table.add_column("Avg Cost", justify="right")
        for row in data:
            table.add_row(
                row["model_id"],
                str(row["run_count"]),
                f"${row['total_cost']:.4f}",
                f"${row['avg_cost']:.4f}",
            )
        console.print(table)

    if by_label:
        data = report_by_label(days=days)
        table = Table(title="By Label")
        table.add_column("Label", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        for row in data:
            table.add_row(
                row["label"] or "(none)",
                str(row["run_count"]),
                f"${row['total_cost']:.4f}",
            )
        console.print(table)

    if by_day:
        data = report_by_day(days=days)
        table = Table(title="By Day")
        table.add_column("Date", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        for row in data:
            table.add_row(
                row["date"],
                str(row["run_count"]),
                f"${row['total_cost']:.4f}",
            )
        console.print(table)


# --- trends command ---


@app.command()
def trends(
    last: str = typer.Option("30d", "--last", "-l", help="Time window"),
) -> None:
    """Show daily spending trends."""
    from cost_intel.report import report_by_day

    days = parse_window(last)
    data = report_by_day(days=days)

    table = Table(title=f"Daily Trends (last {last})")
    table.add_column("Date", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Total Cost", justify="right")
    table.add_column("Avg Cost", justify="right")
    for row in data:
        table.add_row(
            row["date"],
            str(row["run_count"]),
            f"${row['total_cost']:.4f}",
            f"${row['avg_cost']:.4f}",
        )
    console.print(table)


# --- export command ---


@app.command()
def export(
    fmt: str = typer.Option(
        "json", "--format", "-f", help="Output format: json or csv"
    ),
    last: Optional[str] = typer.Option(None, "--last", "-l", help="Time window"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Export cost data as JSON or CSV."""
    from cost_intel.report import report_by_day

    days = parse_window(last) if last else None
    data = report_by_day(days=days)

    if fmt == "json":
        content = json.dumps(data, indent=2)
    elif fmt == "csv":
        lines = ["date,run_count,total_cost,avg_cost"]
        for row in data:
            lines.append(
                f"{row['date']},{row['run_count']},"
                f"{row['total_cost']},{row['avg_cost']}"
            )
        content = "\n".join(lines) + "\n"
    else:
        console.print(f"[red]Unknown format: {fmt}[/red]")
        raise typer.Exit(1)

    if output:
        output.write_text(content)
        console.print(f"[green]✓[/green] Exported to {output}")
    else:
        console.print(content)


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


# --- estimate command ---
# --- estimate command ---


@app.command()
def estimate(
    text: str = typer.Argument(..., help="Text to estimate tokens for"),
    model: str = typer.Option(
        "gpt-4", "--model", "-m", help="Model name (e.g., gpt-4, gpt-4o)"
    ),
) -> None:
    """Estimate token count and cost for a given text."""
    from cost_intel.estimate import estimate_cost

    result = estimate_cost(text, model=model)
    console.print(
        f"Tokens: [bold]{result['input_tokens']}[/bold]  "
        f"Est. cost: [bold]${result['estimated_cost']:.6f}[/bold]"
    )


# --- ingest-api-responses command ---


@app.command(name="ingest-api-responses")
def ingest_api_responses(
    file: Path = typer.Argument(..., help="Path to JSONL file"),
    format: str = typer.Option("openrouter", "--format", "-f", help="Provider format"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Run label"),
) -> None:
    """Ingest cost runs from a JSONL file of API responses."""
    from cost_intel.ingest import ingest_jsonl

    count = ingest_jsonl(str(file), format=format, label=label)
    console.print(f"[green]✓[/green] Ingested [bold]{count}[/bold] runs from {file}")


budget_app = typer.Typer(help="Budget management")


@budget_app.command("set")
def budget_set(
    monthly: float = typer.Option(..., "--monthly", help="Monthly budget in USD"),
    alert_threshold: int = typer.Option(
        80, "--alert-threshold", help="Alert at % of budget"
    ),
) -> None:
    """Set monthly budget and alert threshold."""
    from cost_intel.budget import set_budget

    set_budget(monthly=monthly, alert_threshold=alert_threshold)
    console.print(
        f"[green]✓[/green] Budget set: ${monthly}/mo, alert at {alert_threshold}%"
    )


@budget_app.command("status")
def budget_status() -> None:
    """Show current budget status."""
    from cost_intel.budget import get_budget_status

    status = get_budget_status()
    if not status["budget_set"]:
        console.print("[yellow]No budget set[/yellow]")
        console.print(
            "Run [bold]cost-intel budget set --monthly 500[/bold] to set one."
        )
        return

    console.print(
        f"[bold]Budget:[/bold] ${status['monthly']:.2f}/mo  "
        f"[bold]Spent:[/bold] ${status['spent']:.2f}  "
        f"[bold]Remaining:[/bold] ${status['remaining']:.2f}  "
        f"[bold]Used:[/bold] {status['percent_used']:.1f}%"
    )
    if status["percent_used"] >= status["alert_threshold"]:
        console.print(f"[red]⚠ Over {status['alert_threshold']}% threshold![/red]")


app.add_typer(budget_app, name="budget")
