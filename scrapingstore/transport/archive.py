"""Archive transport: replay content-addressed raw HTML blobs for time-travel reparsing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from scrapingstore import PARSER_VERSION
from scrapingstore.io_utils import as_utc
from scrapingstore.ledger.database import HISTORY_VERSION, DatabaseManager
from scrapingstore.ledger.models import Product
from scrapingstore.sources.base import SourceAdapter
from scrapingstore.sources.oxylabs import OxylabsAdapter
from scrapingstore.sources.results import PageResult, ScrapeRunResult, clean_products


class ArchiveTransport:
    """Replays stored RawPageBlob HTML through a given SourceAdapter without network access."""

    def __init__(self, db: DatabaseManager, adapter: Optional[SourceAdapter] = None):
        self.db = db
        self.adapter: SourceAdapter = adapter or OxylabsAdapter()

    def replay(self, run_id: str) -> ScrapeRunResult:
        manifest = self.db.get_run(run_id)
        if manifest is None:
            raise ValueError(f"Collection run {run_id!r} was not found")
        page_records = self.db.get_run_pages(run_id)
        if not page_records:
            raise ValueError(
                f"Collection run {run_id!r} has no archived page records to reparse"
            )

        started_raw = str(manifest["started_at"])
        if started_raw.endswith("Z"):
            started_raw = started_raw[:-1] + "+00:00"
        original_started = as_utc(datetime.fromisoformat(started_raw))

        replayed = ScrapeRunResult(
            source_url=str(manifest.get("source_url", "")),
            requested_pages=manifest.get("scope", {}).get("requested_pages"),
            scraper_type="archive_reparse",
            source_name=str(manifest.get("source_name", getattr(self.adapter, "name", "oxylabs"))),
            started_at=original_started,
            configuration={
                "reparsed_from": run_id,
                "parser_version": PARSER_VERSION,
                "adapter": getattr(self.adapter, "name", "oxylabs"),
            },
        )

        blobs_found = 0
        for rec in page_records:
            if rec.outside_scope:
                continue
            raw_bytes = self.db.get_raw_blob(rec.raw_blob_sha256) if rec.raw_blob_sha256 else None
            if raw_bytes is None:
                page = PageResult(
                    rec.page_number,
                    rec.url,
                    status="failed",
                    errors=["raw_blob_missing: raw HTML was not archived for this page"],
                )
            else:
                blobs_found += 1
                page = self.adapter.parse_page(raw_bytes, rec.url, rec.page_number)
                page.http_status = rec.http_status
                page.attempts = 1
                page.elapsed_ms = 0.0
                for prod in page.products:
                    prod.scraped_at = original_started
            replayed.pages.append(page)

        if blobs_found == 0:
            raise ValueError(
                f"Collection run {run_id!r} has no archived raw HTML blobs to reparse"
            )

        replayed.finish(str(manifest.get("stop_reason", "source_end")))
        return replayed


def _has_real_image(p: Product) -> bool:
    return bool(p.image_url and not p.image_url.strip().lower().startswith("data:"))


def reparse_run(
    db: DatabaseManager,
    run_ref: str,
    *,
    adapter: Optional[SourceAdapter] = None,
    apply: bool = False,
) -> Dict[str, Any]:
    """Replay archived HTML for run_ref and compute a Parser Diff before optional commit."""
    run_id = db.resolve_run_id(run_ref)
    original_products = db.get_run_products(run_id)
    transport = ArchiveTransport(db, adapter=adapter)
    replayed = transport.replay(run_id)
    new_products = clean_products(replayed.products, warnings=replayed.errors)

    old_by_key = {p.source_key: p for p in original_products}
    new_by_key = {p.source_key: p for p in new_products}

    images_recovered = 0
    categories_recovered = 0
    prices_recovered = 0
    prices_changed = 0
    availability_changed = 0

    for key, new_p in new_by_key.items():
        old_p = old_by_key.get(key)
        if old_p is None:
            continue
        if not _has_real_image(old_p) and _has_real_image(new_p):
            images_recovered += 1
        if not old_p.category and new_p.category:
            categories_recovered += 1
        if old_p.price is None and new_p.price is not None:
            prices_recovered += 1
        elif old_p.price != new_p.price:
            prices_changed += 1
        if old_p.availability != new_p.availability:
            availability_changed += 1

    committed_run_id: Optional[str] = None
    if apply:
        replayed.run_id = str(uuid4())
        for prod in new_products:
            prod.last_run_id = replayed.run_id
        replayed.accepted_products = len(new_products)
        manifest = {**replayed.manifest(), "history_version": HISTORY_VERSION}
        db.save_collection(new_products, manifest, raw_pages=replayed.raw_pages)
        committed_run_id = replayed.run_id

    return {
        "source_run_id": run_id,
        "parser_version": PARSER_VERSION,
        "pages_replayed": len(replayed.pages),
        "original_products": len(original_products),
        "reparsed_products": len(new_products),
        "parser_diff": {
            "images_recovered": images_recovered,
            "categories_recovered": categories_recovered,
            "prices_recovered": prices_recovered,
            "prices_changed": prices_changed,
            "availability_changed": availability_changed,
        },
        "applied": apply,
        "new_run_id": committed_run_id,
    }
