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
    days: Optional[int] = typer.Option(
        None, "--days", "-d", help="Window size in days (overrides --last)"
    ),
    metric: str = typer.Option(
        "spending", "--metric", "-m", help="Metric: spending (default) or cpqp"
    ),
) -> None:
    """Show spending trends or week-over-week CPQP trend."""
    from cost_intel.report import report_by_day
    from cost_intel.trends import get_cpqp_trend

    window_days = days if days is not None else parse_window(last)

    if metric == "cpqp":
        trend = get_cpqp_trend(window_days=window_days)
        table = Table(title=f"CPQP Trend (window={window_days}d)")
        table.add_column("Window", style="cyan")
        table.add_column("Avg CPQP", justify="right")
        table.add_row("This window", f"${trend['this_window']:.4f}")
        table.add_row("Prior window", f"${trend['prior_window']:.4f}")
        ratio = trend["ratio"]
        if ratio > 1:
            ratio_str = f"[red]↑ {ratio:.2f}[/red] (degrading)"
        elif 0 < ratio < 1:
            ratio_str = f"[green]↓ {ratio:.2f}[/green] (improving)"
        else:
            ratio_str = f"{ratio:.2f}"
        table.add_row("Ratio", ratio_str)
        console.print(table)
        return

    data = report_by_day(days=window_days)
    table = Table(title=f"Daily Trends (last {window_days}d)")
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


# --- cpqp command ---


def _render_cpqp_row(table: Table, r: dict) -> None:
    """Render a CPQP row with color-coded rating."""
    rating = r.get("rating") or "N/A"
    rating_style = {
        "A": "green",
        "B": "bright_green",
        "C": "yellow",
        "D": "red",
        "F": "bold red",
        "N/A": "dim",
    }.get(rating, "")
    table.add_row(
        (r.get("run_id") or "")[:8],
        r.get("label") or "",
        r.get("model_id") or "",
        f"${r['total_cost']:.4f}" if r.get("total_cost") is not None else "N/A",
        f"{r['combined_score']:.2f}" if r.get("combined_score") is not None else "N/A",
        f"${r['cpqp']:.4f}" if r.get("cpqp") is not None else "N/A",
        f"[{rating_style}]{rating}[/{rating_style}]" if rating_style else rating,
    )


def _cpqp_table(title: str) -> Table:
    table = Table(title=title)
    table.add_column("Run ID", style="cyan", max_width=12)
    table.add_column("Label", max_width=20)
    table.add_column("Model", max_width=25)
    table.add_column("Cost", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("CPQP", justify="right")
    table.add_column("Rating", justify="right")
    return table


@app.command()
def cpqp(
    waste_only: bool = typer.Option(
        False, "--waste-only", help="Show only D/F rated (inefficient) runs"
    ),
    last: Optional[str] = typer.Option(
        None, "--last", "-l", help="Time window (e.g., 7d, 30d, 12h)"
    ),
) -> None:
    """Show cost-per-quality-point (CPQP) report with percentile ratings."""
    from cost_intel.quality import get_all_cpqp, get_waste_runs

    days = parse_window(last) if last else None

    if waste_only:
        results = get_waste_runs(days=days)
        title = "Waste Runs (Rating D or F)"
    else:
        results = get_all_cpqp(days=days)
        title = "Cost-Per-Quality-Point (CPQP)"

    if last:
        title += f" — last {last}"

    if not results:
        console.print(f"[dim]No CPQP results to display for {title}.[/dim]")
        return

    table = _cpqp_table(title)
    for r in results:
        _render_cpqp_row(table, r)
    console.print(table)


@app.command()
def waste(
    last: Optional[str] = typer.Option(
        None, "--last", "-l", help="Time window (e.g., 7d, 30d)"
    ),
) -> None:
    """Show waste analysis — runs with D or F efficiency ratings."""
    from cost_intel.quality import get_waste_runs

    days = parse_window(last) if last else None
    waste_runs = get_waste_runs(days=days)

    try:
        from cost_intel.optimize import get_waste_index

        wi = get_waste_index(days=days)
        console.print(
            f"Waste Index: [bold]{wi['waste_index']:.1%}[/bold] "
            f"(${wi['waste_spend']:.4f} of ${wi['total_spend']:.4f})"
        )
    except ImportError:
        pass

    if not waste_runs:
        console.print("[green]No waste detected — all runs rated A/B/C.[/green]")
        return

    table = _cpqp_table("Waste Runs (Rating D or F)")
    for r in waste_runs:
        _render_cpqp_row(table, r)
    console.print(table)


# --- optimize command ---


@app.command()
def optimize(
    target_cpqp: Optional[float] = typer.Option(
        None, "--target-cpqp", help="Show runs exceeding this CPQP target"
    ),
    route: bool = typer.Option(
        False,
        "--suggest-model-routing",
        help="Suggest cheaper models for the same task",
    ),
    min_runs: int = typer.Option(
        1, "--min-runs", help="Minimum runs per model for routing suggestions"
    ),
) -> None:
    """Find optimization opportunities (model routing, target CPQP, waste)."""
    from cost_intel.optimize import (
        get_runs_above_target_cpqp,
        get_waste_index,
        suggest_model_routing,
    )

    if target_cpqp is not None:
        results = get_runs_above_target_cpqp(target_cpqp)
        table = Table(title=f"Runs Above Target CPQP (${target_cpqp:.4f})")
        table.add_column("Run ID", style="cyan", max_width=12)
        table.add_column("Label", max_width=20)
        table.add_column("Model", max_width=25)
        table.add_column("Cost", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("CPQP", justify="right")
        table.add_column("Rating", justify="right")
        for r in results:
            table.add_row(
                r["run_id"][:8],
                r["label"] or "",
                r["model_id"] or "",
                f"${r['total_cost']:.4f}" if r.get("total_cost") is not None else "N/A",
                f"{r['combined_score']:.2f}"
                if r["combined_score"] is not None
                else "N/A",
                f"${r['cpqp']:.4f}" if r["cpqp"] is not None else "N/A",
                r.get("rating") or "N/A",
            )
        console.print(table)
        console.print(f"[dim]{len(results)} run(s) exceed target CPQP[/dim]")
    elif route:
        results = suggest_model_routing(min_runs=min_runs)
        if not results:
            console.print("[yellow]No models meet --min-runs threshold.[/yellow]")
            return
        table = Table(title="Model Routing Suggestions")
        table.add_column("Model", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Avg Cost/Run", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        for r in results:
            table.add_row(
                r["model_id"],
                str(r["total_runs"]),
                f"${r['avg_cost_per_run']:.4f}",
                f"${r['min_cost']:.4f}",
                f"${r['max_cost']:.4f}",
            )
        console.print(table)
    else:
        wi = get_waste_index()
        table = Table(title="Waste Index")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Waste Index", f"{wi['waste_index']:.1%}")
        table.add_row("Total Spend", f"${wi['total_spend']:.4f}")
        table.add_row("Waste Spend", f"${wi['waste_spend']:.4f}")
        console.print(table)


# --- compare-models command ---


@app.command(name="compare-models")
def compare_cmd(
    label: Optional[str] = typer.Option(
        None, "--label", "-l", help="Filter by task label"
    ),
    models: Optional[str] = typer.Option(
        None, "--models", "-m", help="Comma-separated model IDs to compare"
    ),
) -> None:
    """Compare cost efficiency and CPQP across models."""
    from cost_intel.compare import compare_models

    model_list = [m.strip() for m in models.split(",")] if models else None
    results = compare_models(label=label, models=model_list)

    if not results:
        console.print(
            "[yellow]No results — filter returned empty. "
            "Check --label / --models values.[/yellow]"
        )
        return

    table = Table(title="Model Comparison")
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Total Cost", justify="right")
    table.add_column("Avg Cost/Run", justify="right")
    table.add_column("Avg CPQP", justify="right")
    table.add_column("Δ CPQP", justify="right")
    for r in results:
        delta = r.get("delta_cpqp")
        delta_str = f"{delta:+.4f}" if delta is not None else "N/A"
        table.add_row(
            r["model_id"],
            str(r["total_runs"]),
            f"${r['total_cost']:.4f}",
            f"${r['avg_cost_per_run']:.4f}",
            f"${r['avg_cpqp']:.4f}" if r.get("avg_cpqp") is not None else "N/A",
            delta_str,
        )
    console.print(table)


# --- import-scores command ---


@app.command(name="import-scores")
def import_scores_cmd(
    source: str = typer.Option(
        ..., "--source", "-s", help="Source: csv, eval-harness, braintrust"
    ),
    file: Optional[str] = typer.Option(
        None, "--file", "-f", help="CSV file path (for csv source)"
    ),
    db_path: Optional[str] = typer.Option(
        None, "--db-path", help="SQLite DB path (for eval-harness source)"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API key (for braintrust source)"
    ),
    project_id: Optional[str] = typer.Option(
        None, "--project-id", help="Project ID (for braintrust source)"
    ),
    experiment_id: Optional[str] = typer.Option(
        None, "--experiment-id", help="Experiment ID (for braintrust source)"
    ),
    mapping: Optional[str] = typer.Option(
        None,
        "--mapping",
        help='JSON column mapping, e.g. \'{"run_id":"id","score":"quality"}\'',
    ),
) -> None:
    """Import quality scores from an external source."""
    if source == "csv":
        if not file:
            console.print("[red]Error:[/red] --file is required for source 'csv'")
            raise typer.Exit(1)
        from cost_intel.quality import import_scores_csv

        mapping_dict = json.loads(mapping) if mapping else None
        count = import_scores_csv(file, source="csv", mapping=mapping_dict)
        console.print(
            f"[green]✓[/green] Imported [bold]{count}[/bold] scores from {file}"
        )
    elif source == "eval-harness":
        if not db_path:
            console.print(
                "[red]Error:[/red] --db-path is required for source 'eval-harness'"
            )
            raise typer.Exit(1)
        from cost_intel.adapters.eval_harness import import_from_db

        count = import_from_db(db_path)
        console.print(
            f"[green]✓[/green] Imported [bold]{count}[/bold] scores from Eval Harness"
        )
    elif source == "braintrust":
        if not api_key or not project_id:
            console.print(
                "[red]Error:[/red] --api-key and --project-id are required for "
                "source 'braintrust'"
            )
            raise typer.Exit(1)
        from cost_intel.adapters.braintrust import import_from_api

        count = import_from_api(
            api_key=api_key,
            project_id=project_id,
            experiment_id=experiment_id,
        )
        console.print(
            f"[green]✓[/green] Imported [bold]{count}[/bold] scores from Braintrust"
        )
    else:
        console.print(f"[red]Unknown source: {source}[/red]")
        raise typer.Exit(1)


# --- gate command ---


@app.command()
def gate(
    max_avg_cpqp: Optional[float] = typer.Option(
        None, "--max-avg-cpqp", help="Max average CPQP threshold"
    ),
    max_waste_index: Optional[float] = typer.Option(
        None, "--max-waste-index", help="Max waste index threshold (0.0-1.0)"
    ),
    budget_check: bool = typer.Option(
        False, "--budget-check", help="Check budget threshold"
    ),
    window: str = typer.Option(
        "7d", "--window", "-w", help="Window (e.g. 7d, 30d, 24h, 7)"
    ),
    fmt: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
) -> None:
    """CI/CD cost gate. Exits 0 if passed, 1 if failed."""
    from cost_intel.gate import check_gate

    window_days = parse_window(window)
    passed, msg = check_gate(
        max_avg_cpqp=max_avg_cpqp,
        max_waste_index=max_waste_index,
        budget_check=budget_check,
        window_days=window_days,
    )
    if fmt == "json":
        console.print(json.dumps({"passed": passed, "message": msg}))
    else:
        if passed:
            console.print(f"[green]✓[/green] {msg}")
        else:
            console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(code=0 if passed else 1)


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


# --- alert sub-app ---

alert_app = typer.Typer(help="Budget alert dispatch (Slack webhook + SMTP email)")


@alert_app.command("check")
def alert_check() -> None:
    """Check budget threshold and dispatch alerts when reached."""
    from cost_intel.alerts import check_and_alert

    result = check_and_alert()
    if not result["triggered"]:
        console.print("[green]✓[/green] Budget below alert threshold — no alert sent.")
        return

    if result["alert_sent"]:
        console.print("[yellow]⚠[/yellow] Budget alert triggered and dispatched.")
    else:
        console.print(
            "[red]⚠[/red] Budget alert triggered but no channel succeeded "
            "(check slack_webhook_url / smtp_host config)."
        )
    console.print(result["message"])


@alert_app.command("test")
def alert_test() -> None:
    """Show which alert channels are configured."""
    from cost_intel.config import load_config

    cfg = load_config()
    slack_url = cfg.get("slack_webhook_url", "") or ""
    smtp_host = cfg.get("smtp_host", "") or ""
    recipients = cfg.get("alert_recipients", []) or []

    table = Table(title="Alert Channels")
    table.add_column("Channel", style="cyan")
    table.add_column("Configured", justify="right")
    table.add_column("Details")
    table.add_row(
        "Slack",
        "[green]yes[/green]" if slack_url else "[red]no[/red]",
        "(webhook set)" if slack_url else "(set slack_webhook_url in config)",
    )
    table.add_row(
        "SMTP",
        "[green]yes[/green]" if smtp_host else "[red]no[/red]",
        smtp_host or "(set smtp_host in config)",
    )
    table.add_row(
        "Recipients",
        "[green]yes[/green]" if recipients else "[red]no[/red]",
        f"{len(recipients)} recipient(s)",
    )
    console.print(table)


app.add_typer(alert_app, name="alert")


# --- trace-cost command ---


@app.command(name="trace-cost")
def trace_cost_cmd(
    trace_id: str = typer.Argument(..., help="OpenTelemetry trace ID"),
) -> None:
    """Show cost breakdown by agent in a trace."""
    from cost_intel.otel import get_trace_cost

    data = get_trace_cost(trace_id)
    if not data["agents"]:
        console.print(f"[yellow]No spans found for trace {trace_id}[/yellow]")
        return

    table = Table(title=f"Trace Cost: {trace_id}")
    table.add_column("Agent", style="cyan")
    table.add_column("Model", max_width=25)
    table.add_column("Own Cost", justify="right")
    table.add_column("Rolled Up", justify="right")
    table.add_column("Input Tok", justify="right")
    table.add_column("Output Tok", justify="right")
    table.add_column("CPQP", justify="right")
    for agent in data["agents"]:
        indent = "  " * agent.get("depth", 0)
        cpqp = agent.get("cpqp")
        table.add_row(
            f"{indent}{agent['label'] or ''}",
            agent["model_id"] or "",
            f"${agent['own_cost']:.4f}",
            f"${agent['rolled_up_cost']:.4f}",
            str(agent["input_tokens"]),
            str(agent["output_tokens"]),
            f"${cpqp:.4f}" if cpqp is not None else "N/A",
        )
    console.print(table)
    console.print(
        f"Total: [bold]${data['total_cost']:.4f}[/bold] "
        f"across {data['total_runs']} span(s) "
        f"({data['total_input_tokens']} in / {data['total_output_tokens']} out)"
    )


@app.command(name="prompt-opt")
def prompt_opt_cmd(
    top_n: int = typer.Option(10, "--top-n"),
    threshold_tokens: int = typer.Option(3000, "--threshold-tokens"),
) -> None:
    """Analyze prompt patterns and suggest optimizations."""
    from rich.table import Table

    from cost_intel.prompt_opt import analyze_prompt_patterns, suggest_trimming

    console.print("[bold]Top Cost Patterns by Label Prefix[/bold]")
    patterns = analyze_prompt_patterns(top_n=top_n)
    table = Table()
    table.add_column("Prefix", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Avg Input Tok", justify="right")
    table.add_column("Total Cost", justify="right")
    for p in patterns:
        table.add_row(
            p["label_prefix"],
            str(p["total_runs"]),
            f"${p['avg_cost']:.4f}",
            str(int(p["avg_input_tokens"])),
            f"${p['total_cost']:.4f}",
        )
    console.print(table)

    console.print(
        f"\n[bold]Trimming Suggestions (>{threshold_tokens} avg input tokens)[/bold]"
    )
    suggestions = suggest_trimming(threshold_tokens=threshold_tokens)
    if not suggestions:
        console.print("[green]No patterns exceed the threshold.[/green]")
    else:
        for s in suggestions:
            console.print(f"  - {s['suggestion']}")


@app.command(name="guard")
def guard_cmd(
    threshold: Optional[float] = typer.Option(
        None,
        "--threshold",
        "-t",
        help="Override alert threshold (0.0-1.0, e.g. 0.8 for 80%)",
    ),
) -> None:
    """Budget enforcement guard. Returns non-zero exit if budget exceeded."""
    from cost_intel.guard import check_guard

    allowed, msg = check_guard(threshold_override=threshold)
    if allowed:
        console.print(f"[green]OK[/green] {msg}")
    else:
        console.print(f"[red]BLOCKED[/red] {msg}")
    raise typer.Exit(code=0 if allowed else 1)
