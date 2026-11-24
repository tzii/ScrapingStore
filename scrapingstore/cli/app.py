"""ScrapingStore command line: collect product pages, save each run, build the report."""

from __future__ import annotations

import json
import os
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from scrapingstore import __version__
from scrapingstore.analytics.comparison import compare_observations, format_diff_summary
from scrapingstore.cli.server import serve_report
from scrapingstore.cli.tui import run_tui
from scrapingstore.config import get_settings
from scrapingstore.io_utils import atomic_write_text
from scrapingstore.ledger.database import HISTORY_VERSION, DatabaseManager
from scrapingstore.logger import get_logger, setup_logger
from scrapingstore.quality.gates import evaluate_quality_gate
from scrapingstore.quality.smells import detect_smells
from scrapingstore.report.generator import generate_dashboard
from scrapingstore.report.snapshot import ReportSnapshot
from scrapingstore.sources.base import SourceAdapter
from scrapingstore.sources.mock_market import MockMarket
from scrapingstore.sources.oxylabs import OxylabsAdapter
from scrapingstore.sources.recipe import JsonLdAdapter, RecipeAdapter
from scrapingstore.sources.results import PageResult, ScrapeRunResult, clean_products
from scrapingstore.transport.archive import reparse_run
from scrapingstore.transport.browser import BrowserScraper
from scrapingstore.transport.collector import AutoScraper, BaseScraper
from scrapingstore.transport.http import StaticScraper
from scrapingstore.transport.rate_limit import check_robots_txt

app = typer.Typer(
    help="ScrapingStore: track product prices and stock across repeated collections.",
    invoke_without_command=True,
)
logger = get_logger("scrapingstore.cli")
console = Console()


class ScraperType(str, Enum):
    auto = "auto"
    static = "static"
    browser = "browser"


class SourceKind(str, Enum):
    oxylabs = "oxylabs"
    jsonld = "jsonld"
    mock = "mock"


def _resolve_adapter(
    source: SourceKind = SourceKind.oxylabs, recipe: Optional[Path] = None
) -> SourceAdapter:
    if recipe is not None:
        return RecipeAdapter.from_toml(recipe)
    if source == SourceKind.jsonld:
        return JsonLdAdapter()
    return OxylabsAdapter()


def _create_scraper(
    scraper_type: ScraperType,
    delay: float,
    *,
    base_url: Optional[str] = None,
    adapter: Optional[SourceAdapter] = None,
    on_page=None,
) -> BaseScraper:
    url = base_url or get_settings().base_url
    if scraper_type == ScraperType.static:
        return StaticScraper(base_url=url, delay=delay, adapter=adapter, on_page=on_page)
    if scraper_type == ScraperType.browser:
        return BrowserScraper(base_url=url, delay=delay, adapter=adapter, on_page=on_page)
    return AutoScraper(base_url=url, delay=delay, adapter=adapter, on_page=on_page)


def _diagnose_errors(run: ScrapeRunResult) -> list[str]:
    hints: list[str] = []
    all_errors = list(run.errors) + [
        err for page in run.pages for err in page.errors
    ]
    joined = " ".join(all_errors).lower()
    if "executable doesn't exist" in joined or "setup_or_browser_error" in run.stop_reason:
        hints.append("Chromium missing? Run: playwright install chromium (or use --type static)")
    if "http 403" in joined or "http 401" in joined:
        hints.append("Access denied (401/403). Check robots.txt and USER_AGENT in .env.")
    if "http 429" in joined:
        hints.append("Rate limited (HTTP 429). Increase --delay and verify Crawl-delay via `scrapingstore doctor`.")
    if "layout_unrecognized" in joined:
        hints.append("No product cards matched. Try --type browser or run `scrapingstore doctor --probe`.")
    if run.degraded_reasons:
        hints.append("Quality gate flagged parser drift: " + "; ".join(run.degraded_reasons))
    return hints


def _generate_pipeline_dashboard(
    db: DatabaseManager,
    dashboard_path: Optional[str] = None,
    run_id: Optional[str] = None,
    *,
    history_runs: int = 12,
) -> str:
    """Write the HTML report for the catalog (with run history) or for one saved run."""
    if run_id is None:
        products, run = db.get_catalog_snapshot()
        history = db.get_multi_run_history(limit=history_runs)
        snapshot = ReportSnapshot.from_products(products, run=run, history=history)
    else:
        resolved = db.resolve_run_id(run_id)
        snapshot = ReportSnapshot.from_products(
            db.get_run_products(resolved),
            run=db.get_run(resolved),
            scope=f"Collection run {resolved}",
            collection_label="Selected collection",
        )
    destination = dashboard_path or str(get_settings().dashboard_html_path)
    return generate_dashboard(snapshot, output_path=destination)


def _persist_collection(
    db: DatabaseManager,
    run: ScrapeRunResult,
    *,
    data_dir: Optional[Path] = None,
    archive_html: bool = True,
) -> None:
    products = clean_products(run.products, warnings=run.errors)
    for product in products:
        product.last_run_id = run.run_id

    # Quality gate check against prior complete runs
    prior = db.list_runs(limit=10)
    gate = evaluate_quality_gate(products, prior_runs=prior)
    run.quality_gate = gate
    if not gate["passed"]:
        run.degraded_reasons.extend(gate["reasons"])

    persistence_error = None
    try:
        run.accepted_products = len(products)
        manifest = {**run.manifest(), "history_version": HISTORY_VERSION}
        db.save_collection(
            products,
            manifest,
            raw_pages=run.raw_pages if archive_html else None,
        )
    except Exception as exc:
        persistence_error = exc
        run.accepted_products = 0
        run.errors.append(f"persistence_error: {exc}")

    manifest = run.manifest()
    if persistence_error is None:
        manifest["history_version"] = HISTORY_VERSION
    base_dir = data_dir or get_settings().data_dir
    destination = base_dir / "runs" / f"{run.run_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, indent=2, ensure_ascii=False)
    if not destination.exists():
        atomic_write_text(destination, serialized)
    elif destination.read_text(encoding="utf-8") != serialized:
        attempt_path = destination.with_name(f"{run.run_id}.attempt-{uuid4()}.json")
        atomic_write_text(attempt_path, serialized)
        destination = attempt_path

    typer.echo(f"Run manifest: {destination}")
    if persistence_error is not None:
        typer.echo("Persistence failed; see the run manifest.")
        raise typer.Exit(code=1)


def _publish_collection(
    db: DatabaseManager,
    run: ScrapeRunResult,
    export: bool,
    dashboard: bool,
    allow_partial: bool,
) -> None:
    typer.echo(
        f"Collection {run.status} ({run.short_id}): {len(run.pages)} pages attempted; "
        f"{run.accepted_products} products saved. Stop: {run.stop_reason}."
    )
    for hint in _diagnose_errors(run):
        typer.echo(f"Hint: {hint}")

    publish = run.status in ("complete", "empty") or (
        run.status in ("partial", "degraded") and allow_partial
    )
    if publish:
        if export:
            db.export_for_powerbi()
        if dashboard:
            _generate_pipeline_dashboard(db)
    elif export or dashboard:
        typer.echo(
            "Automatic publication skipped. Partial/degraded runs require --allow-partial."
        )
    if run.status == "partial":
        raise typer.Exit(code=2)
    if run.status == "degraded":
        raise typer.Exit(code=3)
    if run.status == "cancelled":
        raise typer.Exit(code=130)
    if run.status == "failed":
        raise typer.Exit(code=1)


@app.callback()
def setup(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Emit structured JSON logs"),
):
    """Global setup for logging and help."""
    setup_logger("DEBUG" if verbose else "INFO", json_logs=json_logs)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
@app.command("collect", hidden=True)
def scrape(
    scraper_type: ScraperType = typer.Option(
        ScraperType.auto,
        "--type",
        help="Transport: auto (HTTP then browser fallback), static, or browser",
    ),
    source: SourceKind = typer.Option(
        SourceKind.oxylabs,
        "--source",
        help="Source adapter: oxylabs, jsonld, or mock",
    ),
    recipe: Optional[Path] = typer.Option(
        None,
        "--recipe",
        help="Path to a declarative TOML store recipe",
    ),
    url: Optional[str] = typer.Option(
        None, "--url", help="Override target base URL"
    ),
    pages: Optional[int] = typer.Option(10, min=1, help="Max pages to scrape"),
    all_pages: bool = typer.Option(False, "--all", help="Scrape all available pages"),
    delay: float = typer.Option(
        1.0, min=0.0, help="Per-host spacing delay in seconds"
    ),
    export: bool = typer.Option(True, help="Export to Power BI CSV after scraping"),
    dashboard: bool = typer.Option(True, help="Build the HTML report after scraping"),
    allow_partial: bool = typer.Option(
        False, help="Publish partial or degraded runs with warnings"
    ),
    archive_html: bool = typer.Option(
        True, help="Keep the raw HTML of each page so the run can be reparsed later"
    ),
    json_progress: bool = typer.Option(
        False, "--json-progress", help="Stream per-page progress as NDJSON to stdout"
    ),
    page_budget: int = typer.Option(
        200, min=1, help="Hard page budget, including --all"
    ),
    run_timeout: float = typer.Option(1800, min=1, help="Run deadline in seconds"),
):
    """Collect product pages, check the result, save the run and build the report."""
    max_pages = None if all_pages else pages
    settings = get_settings()
    target_url = url or settings.base_url
    db = DatabaseManager()
    scraper = None
    run = ScrapeRunResult(target_url, max_pages, scraper_type.value)

    try:
        db.init_db()
        if source == SourceKind.mock:
            market = MockMarket()
            run = market.collect_epoch(0)
        else:
            adapter = _resolve_adapter(source, recipe)
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}p"),
                TimeElapsedColumn(),
                transient=True,
                disable=json_progress,
            )
            task_id = progress.add_task(
                f"Collecting ({scraper_type.value}/{adapter.name})...",
                total=max_pages,
            )

            def on_page(page: PageResult, active_run: ScrapeRunResult) -> None:
                if json_progress:
                    typer.echo(
                        json.dumps(
                            {
                                "event": "page",
                                "run_id": active_run.short_id,
                                "page": page.number,
                                "status": page.status,
                                "products": len(page.products),
                                "elapsed_ms": page.elapsed_ms,
                            }
                        )
                    )
                else:
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"Page {page.number} [{page.status}] · {len(active_run.products)} SKUs",
                    )

            try:
                scraper = _create_scraper(
                    scraper_type,
                    delay,
                    base_url=target_url,
                    adapter=adapter,
                    on_page=on_page,
                )
                scraper.page_budget = page_budget
                scraper.run_timeout = run_timeout
                with progress:
                    run = scraper.scrape(max_pages=max_pages)
            except KeyboardInterrupt:
                run = (scraper.last_run if scraper else None) or run
                run.errors.append("Collection cancelled by user")
                run.finish("cancelled")
            except Exception as exc:
                run = (scraper.last_run if scraper else None) or run
                run.errors.append(f"{type(exc).__name__}: {exc}")
                run.finish("collector_error")

        _persist_collection(db, run, archive_html=archive_html)
        _publish_collection(db, run, export, dashboard, allow_partial)
    finally:
        try:
            if scraper:
                scraper.close()
        finally:
            db.close()


@app.command()
def demo(
    epochs: int = typer.Option(5, min=2, max=5, help="Number of simulated epochs (2-5)"),
    docs: bool = typer.Option(
        False, "--docs", help="Write the report to docs/ instead of data/"
    ),
    open_browser: bool = typer.Option(
        False, "--open", help="Open the report in your browser"
    ),
):
    """Collect a simulated store several times and build its report (no network needed)."""
    settings = get_settings()
    demo_db_path = settings.data_dir / "demo_market.db"
    if demo_db_path.exists():
        demo_db_path.unlink()
    db = DatabaseManager(f"sqlite:///{demo_db_path}")
    try:
        db.init_db()
        market = MockMarket(seed=42, sku_count=96, per_page=24)
        for ep in range(epochs):
            run = market.collect_epoch(ep)
            _persist_collection(db, run, archive_html=True)
            console.print(
                f"Epoch {ep + 1}/{epochs}  [cyan]{run.short_id}[/cyan]  "
                f"status=[bold]{run.status}[/bold]  "
                f"products={run.accepted_products}"
                + (
                    f"  [yellow](gate: {'; '.join(run.degraded_reasons)})[/yellow]"
                    if run.degraded_reasons
                    else ""
                )
            )
        dash_path = str(settings.docs_dashboard_html_path) if docs else None
        out_dash = _generate_pipeline_dashboard(db, dash_path, history_runs=epochs)
        console.print(f"[green]Report ready:[/green] {out_dash}")
        if open_browser:
            webbrowser.open(Path(out_dash).resolve().as_uri())
    finally:
        db.close()


@app.command()
@app.command("log", hidden=True)
def runs(
    limit: int = typer.Option(20, min=1, max=1000),
    plain: bool = typer.Option(False, "--plain", help="Plain script-friendly output"),
):
    """List saved collections, newest first."""
    db = DatabaseManager()
    try:
        db.init_db()
        manifests = db.list_runs(limit=limit)
        if not manifests:
            typer.echo("No saved collections.")
            return
        if plain or not console.is_terminal:
            for run in manifests:
                typer.echo(
                    f"{run['run_id']}  {run['status']}  "
                    f"{run.get('finished_at') or run['started_at']}  "
                    f"{run.get('products_accepted', 0)} products  "
                    f"{run.get('scope', {}).get('description', 'Scope not recorded')}  "
                    f"Stop: {run.get('stop_reason', 'Not recorded')}"
                )
            return

        tbl = Table(title="ScrapingStore Collection Log")
        tbl.add_column("Short ID", style="cyan")
        tbl.add_column("Status")
        tbl.add_column("Started (UTC)")
        tbl.add_column("Products", justify="right")
        tbl.add_column("Scope")
        tbl.add_column("Stop Reason")
        for run in manifests:
            st = str(run.get("status", "unknown"))
            color = (
                "green"
                if st == "complete"
                else ("yellow" if st in ("partial", "degraded") else "red")
            )
            tbl.add_row(
                str(run.get("short_id") or run["run_id"][:8]),
                f"[{color}]{st}[/{color}]",
                str(run.get("started_at", ""))[:19],
                str(run.get("products_accepted", 0)),
                str(run.get("scope", {}).get("description", "—")),
                str(run.get("stop_reason", "—")),
            )
        console.print(tbl)
    finally:
        db.close()


@app.command("inspect-run")
@app.command("show", hidden=True)
def inspect_run(
    run_id: str = typer.Argument("@latest", help="Run ID, short prefix, or @latest/@prev"),
    products: bool = typer.Option(
        False, "--products", help="Include the saved product observations."
    ),
):
    """Print a saved collection's page outcomes and evidence as JSON."""
    db = DatabaseManager()
    try:
        db.init_db()
        resolved = db.resolve_run_id(run_id)
        manifest = db.get_run(resolved)
        if manifest is None:
            raise ValueError(f"Collection run not found: {run_id}")
        payload: Dict[str, Any] = {"run": manifest}
        if products:
            payload["products"] = [
                product.model_dump(mode="json")
                for product in db.get_run_products(resolved)
            ]
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command("compare-runs")
def compare_runs(
    old: str = typer.Argument("@prev", help="Older run ID, prefix, or @prev"),
    new: str = typer.Argument("@latest", help="Newer run ID, prefix, or @latest"),
):
    """Compare OLD and NEW saved observations as JSON, in the supplied order."""
    db = DatabaseManager()
    try:
        db.init_db()
        old_id = db.resolve_run_id(old)
        new_id = db.resolve_run_id(new)
        old_products = db.get_run_products(old_id)
        new_products = db.get_run_products(new_id)
        payload = compare_observations(
            db.get_run(old_id) or {},
            db.get_run(new_id) or {},
            old_products,
            new_products,
        )
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def diff(
    old: str = typer.Argument("@prev", help="Baseline run (default: @prev)"),
    new: str = typer.Argument("@latest", help="Target run (default: @latest)"),
    as_json: bool = typer.Option(False, "--json", help="Emit raw JSON instead of table"),
):
    """Human-readable diff between two saved runs (defaults to @prev..@latest)."""
    db = DatabaseManager()
    try:
        db.init_db()
        old_id = db.resolve_run_id(old)
        new_id = db.resolve_run_id(new)
        payload = compare_observations(
            db.get_run(old_id) or {},
            db.get_run(new_id) or {},
            db.get_run_products(old_id),
            db.get_run_products(new_id),
        )
        if as_json:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            typer.echo(format_diff_summary(payload))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def blame(
    sku: str = typer.Argument(..., help="Product source_key or name substring"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
):
    """Git-blame style provenance: show which run last changed each field of a SKU."""
    db = DatabaseManager()
    try:
        db.init_db()
        info = db.blame_product(sku)
        if as_json:
            typer.echo(json.dumps(info, indent=2, ensure_ascii=False))
            return
        tbl = Table(title=f"Blame: {info['name']} ({info['source_key']})")
        tbl.add_column("Field", style="cyan")
        tbl.add_column("Current Value")
        tbl.add_column("Last Changed Run")
        tbl.add_column("Observed (UTC)")
        tbl.add_column("Parser")
        for field_name, entry in info["fields"].items():
            tbl.add_row(
                field_name,
                str(entry["value"]),
                str(entry["short_id"]),
                str(entry["observed_at"])[:19],
                str(entry["parser_version"]),
            )
        console.print(tbl)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def reparse(
    run_id: str = typer.Argument("@latest", help="Archived run ID or alias to reparse"),
    apply: bool = typer.Option(
        False, "--apply", help="Commit the reparsed observations as a new archived run"
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON parser diff"),
):
    """Time-travel re-parsing: replay archived raw HTML through the current parser."""
    db = DatabaseManager()
    try:
        db.init_db()
        result = reparse_run(db, run_id, apply=apply)
        if as_json:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
            return
        pd = result["parser_diff"]
        typer.echo(
            f"Reparse {result['source_run_id'][:8]} with parser v{result['parser_version']} "
            f"({result['pages_replayed']} archived pages):"
        )
        typer.echo(
            f"  +{pd['images_recovered']} real images recovered · "
            f"+{pd['categories_recovered']} genres recovered · "
            f"+{pd['prices_recovered']} prices recovered · "
            f"{pd['prices_changed']} price diffs"
        )
        if result["applied"]:
            typer.echo(f"Committed reparsed run: {result['new_run_id']}")
        else:
            typer.echo("Dry run only. Pass --apply to persist the reparsed run.")
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def smells(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Audit a specific run"),
    strict: bool = typer.Option(False, "--strict", help="Exit 2 if error-severity smells exist"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON smells report"),
):
    """Check the catalog or a saved run for data problems."""
    db = DatabaseManager()
    try:
        db.init_db()
        if run_id:
            products = db.get_run_products(db.resolve_run_id(run_id))
        else:
            products, _ = db.get_catalog_snapshot()
        found = detect_smells(products)
        if as_json:
            typer.echo(json.dumps([s.to_dict() for s in found], indent=2, ensure_ascii=False))
        elif not found:
            typer.echo("CLEAN: No structural data smells detected.")
        else:
            for s in found:
                typer.echo(f"[{s.severity.upper()}] {s.title} ({s.metric}): {s.detail}")
                typer.echo(f"  -> {s.remediation}")
        if strict and any(s.severity == "error" for s in found):
            raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def doctor(
    probe: bool = typer.Option(
        False, "--probe", help="Fetch page 1 & robots.txt to audit live selector hit rates"
    ),
):
    """Audit environment health, Chromium availability, DB schema, and source reachability."""
    settings = get_settings()
    checks = []
    checks.append(("Version", f"ScrapingStore v{__version__}", "OK"))
    checks.append(("Workspace", str(settings.project_dir), "OK"))
    checks.append(("User-Agent", settings.user_agent, "OK"))

    # Data dir write check
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        writable = os.access(settings.data_dir, os.W_OK)
        checks.append(("Data Dir", str(settings.data_dir), "OK" if writable else "FAIL"))
    except Exception as exc:
        checks.append(("Data Dir", str(exc), "FAIL"))

    # DB check
    db = DatabaseManager()
    try:
        db.init_db()
        prods, latest = db.get_catalog_snapshot()
        checks.append(
            (
                "SQLite Ledger",
                f"{len(prods)} products · latest={latest['status'] if latest else 'none'}",
                "OK",
            )
        )
    except Exception as exc:
        checks.append(("SQLite Ledger", str(exc), "FAIL"))
    finally:
        db.close()

    # Chromium check
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            exe = Path(pw.chromium.executable_path)
            checks.append(
                (
                    "Playwright Chromium",
                    str(exe) if exe.exists() else "Not installed (run: playwright install chromium)",
                    "OK" if exe.exists() else "WARN",
                )
            )
    except Exception as exc:
        checks.append(("Playwright Chromium", f"Unavailable ({type(exc).__name__})", "WARN"))

    if probe:
        allowed, crawl_delay, note = check_robots_txt(settings.base_url)
        checks.append(
            (
                "robots.txt",
                f"allowed={allowed}, crawl_delay={crawl_delay} ({note})",
                "OK" if allowed else "WARN",
            )
        )
        scraper = StaticScraper(base_url=settings.base_url, delay=0)
        try:
            res = scraper.scrape(max_pages=1)
            checks.append(
                (
                    "Page 1 Probe",
                    f"status={res.status}, products={len(res.products)}, stop={res.stop_reason}",
                    "OK" if res.status == "complete" else "WARN",
                )
            )
        finally:
            scraper.close()

    tbl = Table(title="ScrapingStore Doctor")
    tbl.add_column("Check", style="cyan")
    tbl.add_column("Details")
    tbl.add_column("State")
    for name, detail, state in checks:
        color = "green" if state == "OK" else ("yellow" if state == "WARN" else "red")
        tbl.add_row(name, detail, f"[{color}]{state}[/{color}]")
    console.print(tbl)


@app.command()
def export():
    """Export existing database data to Power BI CSV (UTF-8 BOM + formula guard)."""
    db = DatabaseManager()
    try:
        db.init_db()
        db.export_for_powerbi()
    finally:
        db.close()


@app.command("generate-report")
@app.command("report", hidden=True)
def generate_report(
    docs: bool = typer.Option(
        False,
        "--docs",
        help="Write GitHub Pages files to docs/ instead of data/.",
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id", help="Render observations saved by this run (or @latest/@prev)."
    ),
    history_runs: int = typer.Option(
        12, min=1, max=50, help="Number of recent runs to show in the report"
    ),
    open_browser: bool = typer.Option(
        False, "--open", help="Open the report in your browser"
    ),
):
    """Build the offline HTML report from saved data."""
    settings = get_settings()
    db = DatabaseManager()
    try:
        db.init_db()
        dashboard_path = str(settings.docs_dashboard_html_path) if docs else None
        out_dash = _generate_pipeline_dashboard(
            db, dashboard_path, run_id, history_runs=history_runs
        )
        if open_browser:
            webbrowser.open(Path(out_dash).resolve().as_uri())
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        db.close()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8765, min=1, max=65535, help="Port number"),
    open_browser: bool = typer.Option(False, "--open", help="Open browser automatically"),
):
    """Serve the report locally; each page load rebuilds it from saved data."""
    db = DatabaseManager()
    try:
        db.init_db()
        console.print(
            Panel.fit(
                f"Serving the ScrapingStore report at [bold cyan]http://{host}:{port}/[/bold cyan]\n"
                "Press Ctrl+C to stop.",
                border_style="cyan",
            )
        )
        serve_report(db, host=host, port=port, open_browser=open_browser)
    finally:
        db.close()


@app.command()
def tui():
    """Browse saved data in an interactive terminal shell."""
    db = DatabaseManager()
    try:
        db.init_db()
        run_tui(db, console=console)
    finally:
        db.close()


if __name__ == "__main__":
    app()
