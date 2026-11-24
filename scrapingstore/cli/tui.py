"""Interactive Rich terminal shell over the saved data (`scrapingstore tui`)."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scrapingstore import __version__
from scrapingstore.analytics.comparison import compare_observations, format_diff_summary
from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.quality.smells import detect_smells


def run_tui(db: DatabaseManager, *, console: Console | None = None) -> None:
    """Run an interactive keyboard-driven Rich query shell over the SQLite ledger."""
    con = console or Console()
    products, latest = db.get_catalog_snapshot()
    runs = db.list_runs(limit=20)
    con.print(
        Panel.fit(
            f"[bold cyan]ScrapingStore TUI v{__version__}[/bold cyan]\n"
            f"Catalog: [bold]{len(products)}[/bold] products · "
            f"Archived runs: [bold]{len(runs)}[/bold] · "
            f"Latest: [bold]{latest['status'] if latest else 'none'}[/bold]\n"
            "Commands: [green]find <q>[/green], [green]top [N][/green], "
            "[green]runs[/green], [green]diff[/green], [green]smells[/green], "
            "[green]blame <sku>[/green], [green]help[/green], [green]quit[/green]",
            border_style="cyan",
        )
    )

    while True:
        try:
            raw = con.input("[bold green]scrapingstore>[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("q", "quit", "exit"):
            break
        if cmd == "help":
            con.print(
                "Commands: find <query> | top [N] | runs | diff | smells | blame <sku> | quit"
            )
            continue
        if cmd == "runs":
            tbl = Table(title="Saved Collection Runs")
            tbl.add_column("Short ID", style="cyan")
            tbl.add_column("Status")
            tbl.add_column("Started (UTC)")
            tbl.add_column("Products", justify="right")
            tbl.add_column("Stop Reason")
            for r in db.list_runs(limit=15):
                tbl.add_row(
                    str(r.get("short_id") or r["run_id"][:8]),
                    str(r.get("status")),
                    str(r.get("started_at", ""))[:19],
                    str(r.get("products_accepted", 0)),
                    str(r.get("stop_reason", "")),
                )
            con.print(tbl)
            continue
        if cmd == "smells":
            cur, _ = db.get_catalog_snapshot()
            smells = detect_smells(cur)
            if not smells:
                con.print("[green]No structural data smells detected.[/green]")
            for s in smells:
                color = "red" if s.severity == "error" else ("yellow" if s.severity == "warn" else "cyan")
                con.print(f"[{color}][{s.severity.upper()}][/{color}] [bold]{s.title}[/bold] ({s.metric}) — {s.detail}")
            continue
        if cmd == "top":
            n = int(args[0]) if args and args[0].isdigit() else 10
            cur, _ = db.get_catalog_snapshot()
            priced = sorted(
                [p for p in cur if p.price is not None], key=lambda p: -(p.price or 0.0)
            )[:n]
            tbl = Table(title=f"Top {n} Highest Priced")
            tbl.add_column("#", justify="right")
            tbl.add_column("Product")
            tbl.add_column("Price", justify="right", style="yellow")
            tbl.add_column("Stock")
            tbl.add_column("Genre")
            for i, p in enumerate(priced, 1):
                tbl.add_row(
                    str(i),
                    p.name,
                    f"€{p.price:.2f}" if p.price is not None else "—",
                    p.availability,
                    p.category or "—",
                )
            con.print(tbl)
            continue
        if cmd == "find":
            needle = " ".join(args).lower()
            cur, _ = db.get_catalog_snapshot()
            hits = [
                p for p in cur if needle in p.name.lower() or needle in (p.category or "").lower()
            ]
            tbl = Table(title=f"Matches for {needle!r} ({len(hits)})")
            tbl.add_column("Product")
            tbl.add_column("Price", justify="right")
            tbl.add_column("Stock")
            tbl.add_column("Genre")
            for p in hits[:20]:
                tbl.add_row(
                    p.name,
                    f"€{p.price:.2f}" if p.price is not None else "Unavailable",
                    p.availability,
                    p.category or "—",
                )
            con.print(tbl)
            continue
        if cmd == "diff":
            try:
                old_id = db.resolve_run_id("@prev")
                new_id = db.resolve_run_id("@latest")
                diff = compare_observations(
                    db.get_run(old_id) or {},
                    db.get_run(new_id) or {},
                    db.get_run_products(old_id),
                    db.get_run_products(new_id),
                )
                con.print(format_diff_summary(diff))
            except ValueError as exc:
                con.print(f"[red]{exc}[/red]")
            continue
        if cmd == "blame" and args:
            try:
                info = db.blame_product(" ".join(args))
                tbl = Table(title=f"Blame: {info['name']} ({info['source_key']})")
                tbl.add_column("Field", style="cyan")
                tbl.add_column("Current Value")
                tbl.add_column("Changed In Run")
                tbl.add_column("Observed (UTC)")
                for f_name, f_info in info["fields"].items():
                    tbl.add_row(
                        f_name,
                        str(f_info["value"]),
                        str(f_info["short_id"]),
                        str(f_info["observed_at"])[:19],
                    )
                con.print(tbl)
            except ValueError as exc:
                con.print(f"[red]{exc}[/red]")
            continue
        con.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
