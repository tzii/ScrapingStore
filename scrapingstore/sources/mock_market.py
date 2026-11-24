"""Deterministic simulated market for offline demos, failure injection, and testing."""

from __future__ import annotations

import html as html_lib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from scrapingstore.sources.oxylabs import OxylabsAdapter
from scrapingstore.sources.results import PageResult, ScrapeRunResult

_FRANCHISES: List[Tuple[str, str, float]] = [
    ("Super Mario", "Platformer", 59.99),
    ("Legend of Zelda", "Adventure", 64.99),
    ("Mega Man", "Action", 39.99),
    ("Final Fantasy", "Role-Playing", 69.99),
    ("Metroid Prime", "Action", 54.99),
    ("Persona", "Role-Playing", 59.99),
    ("Hollow Knight", "Indie", 19.99),
    ("Starfield Odyssey", "Sci-Fi", 74.99),
    ("Gran Turismo", "Racing", 69.99),
    ("Civilization", "Strategy", 49.99),
    ("Stardew Valley", "Simulation", 14.99),
    ("Elden Ring", "Role-Playing", 69.99),
]

_SUBTITLES = [
    "Deluxe Edition",
    "Collector's Cut",
    "Remastered",
    "Origins",
    "Chronicles",
    "Tactics",
    "Director's Cut",
    "Anniversary",
    "Zero",
    "Rebirth",
]


@dataclass
class MockSku:
    sku_id: int
    name: str
    genre: str
    price: float
    in_stock: bool
    rating: float
    listed: bool = True


class MockMarket:
    """Seeded multi-epoch simulated storefront exercising every resilience path.

    Epochs:
      0 (Day -28): Clean baseline catalog (96 SKUs across 4 pages, 2 high outliers)
      1 (Day -21): Normal market week — price drops/rises, restocks, stockouts
      2 (Day -14): Transient HTTP 429 + Retry-After on page 3 (recovers cleanly) + new drops
      3 (Day -7):  Deliberate selector drift (45% prices missing -> triggers DEGRADED gate!)
      4 (Today):   Recovery + new titles + sustained absence (delisting candidates)
    """

    def __init__(self, *, seed: int = 42, sku_count: int = 96, per_page: int = 24):
        self.seed = seed
        self.sku_count = sku_count
        self.per_page = per_page
        self.base_url = "https://mock.scrapingstore.local/products"
        self.adapter = OxylabsAdapter()
        self._catalog: List[MockSku] = self._build_initial_catalog()

    def _build_initial_catalog(self) -> List[MockSku]:
        rng = random.Random(self.seed)
        skus: List[MockSku] = []
        for idx in range(1, self.sku_count + 1):
            franchise, genre, base = _FRANCHISES[(idx - 1) % len(_FRANCHISES)]
            subtitle = _SUBTITLES[((idx - 1) // len(_FRANCHISES)) % len(_SUBTITLES)]
            tier_offset = rng.choice([-15, -10, -5, 0, 5, 10, 15, 20])
            price = max(9.99, round(base + tier_offset, 2))
            if idx == 1:
                price = 489.99  # High-price collector outlier
            elif idx == 2:
                price = 779.99  # Ultra-rare hardware bundle outlier
            skus.append(
                MockSku(
                    sku_id=1000 + idx,
                    name=f"{franchise}: {subtitle}"
                    + (f" Vol. {idx // 40 + 1}" if idx > 80 else ""),
                    genre=genre,
                    price=price,
                    in_stock=rng.random() < 0.74,
                    rating=round(rng.uniform(3.4, 5.0), 1),
                )
            )
        return skus

    def _evolve_epoch(self, epoch: int) -> None:
        rng = random.Random(self.seed + epoch * 1009)
        if epoch == 0:
            return
        for sku in self._catalog:
            if not sku.listed:
                continue
            # Realistic price movement (~18% move each week)
            roll = rng.random()
            if roll < 0.11:
                sku.price = max(9.99, round(sku.price - rng.choice([3.0, 5.0, 10.0]), 2))
            elif roll < 0.17:
                sku.price = round(sku.price + rng.choice([2.0, 5.0]), 2)
            # Realistic stock transitions
            if sku.in_stock and rng.random() < 0.14:
                sku.in_stock = False
            elif not sku.in_stock and rng.random() < 0.35:
                sku.in_stock = True

        # Delist 3 items starting epoch 2 so confidence-graded delisting fires by epoch 4
        if epoch == 2:
            for sku in self._catalog[-3:]:
                sku.listed = False
        # Introduce 4 new releases in epoch 4
        if epoch == 4:
            next_id = max(s.sku_id for s in self._catalog) + 1
            for offset, (title, genre, price) in enumerate(
                [
                    ("Super Mario: Galaxy Echoes", "Platformer", 69.99),
                    ("Hollow Knight: Silksong", "Indie", 29.99),
                    ("Final Fantasy: Nova Tactics", "Role-Playing", 79.99),
                    ("Metroid Prime: Beyond", "Action", 64.99),
                ]
            ):
                self._catalog.append(
                    MockSku(
                        sku_id=next_id + offset,
                        name=title,
                        genre=genre,
                        price=price,
                        in_stock=True,
                        rating=4.9,
                    )
                )

    def _render_page_html(
        self,
        skus: List[MockSku],
        page_num: int,
        is_last: bool,
        *,
        drift_prices: bool = False,
        lazy_images: bool = False,
    ) -> bytes:
        cards: List[str] = []
        for idx, sku in enumerate(skus):
            genre_slug = sku.genre.lower().replace(" ", "-")
            img_path = f"/assets/{genre_slug}.svg"
            if lazy_images and idx >= 4 and idx % 2 == 0:
                img_tag = (
                    '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" '
                    f'data-src="{img_path}" alt="{html_lib.escape(sku.name)}">'
                )
            else:
                img_tag = f'<img src="{img_path}" alt="{html_lib.escape(sku.name)}">'
            if drift_prices and idx % 2 == 0:
                price_html = '<span class="broken-price-selector">TBD</span>'
            else:
                price_str = f"{sku.price:.2f}".replace(".", ",") + " €"
                price_html = f'<div class="price-wrapper">{price_str}</div>'
            stock_text = "In Stock" if sku.in_stock else "Out of Stock"
            cards.append(
                f'<div class="product-card" data-product-id="{sku.sku_id}" data-rating="{sku.rating}">'
                f'<a class="card-header" href="/products/{sku.sku_id}">'
                f"<h4>{html_lib.escape(sku.name)}</h4></a>"
                f"{img_tag}"
                f"{price_html}"
                f'<span class="availability">{stock_text}</span>'
                f"</div>"
            )
        next_attr = ' aria-disabled="true"' if is_last else ""
        next_html = f'<a rel="next" href="?page={page_num + 1}"{next_attr}>Next</a>'
        doc = (
            "<!DOCTYPE html><html><head><title>Mock Market (Simulated)</title></head>"
            f"<body><main>{''.join(cards)}</main><nav>{next_html}</nav></body></html>"
        )
        return doc.encode("utf-8")

    def collect_epoch(
        self,
        epoch: int,
        *,
        anchor_time: Optional[datetime] = None,
    ) -> ScrapeRunResult:
        """Collect one full deterministic epoch with realistic telemetry and HTML blobs."""
        if epoch > 0:
            self._evolve_epoch(epoch)
        now = anchor_time or datetime.now(timezone.utc)
        run_time = now - timedelta(days=(4 - epoch) * 7)
        run = ScrapeRunResult(
            source_url=self.base_url,
            requested_pages=None,
            scraper_type="mock",
            source_name="mock_market",
            started_at=run_time,
            configuration={
                "simulated": True,
                "seed": self.seed,
                "epoch": epoch,
                "delay": 0.0,
            },
        )
        active_skus = [sku for sku in self._catalog if sku.listed]
        chunks = [
            active_skus[i : i + self.per_page]
            for i in range(0, len(active_skus), self.per_page)
        ]
        drift_prices = epoch == 3
        lazy_images = epoch == 0

        for page_idx, chunk in enumerate(chunks, start=1):
            is_last = page_idx == len(chunks)
            url = self.adapter.page_url(self.base_url, page_idx)
            raw_html = self._render_page_html(
                chunk,
                page_idx,
                is_last,
                drift_prices=drift_prices,
                lazy_images=lazy_images,
            )
            page: PageResult = self.adapter.parse_page(raw_html, url, page_idx)
            page.http_status = 200
            page.attempts = 2 if (epoch == 2 and page_idx == 3) else 1
            page.elapsed_ms = round(35.0 + page_idx * 12.5 + (180.0 if epoch == 2 and page_idx == 3 else 0.0), 2)
            for prod in page.products:
                prod.scraped_at = run_time
                prod.last_run_id = run.run_id
            run.pages.append(page)

        run.finish("source_end")
        run.finished_at = run_time + timedelta(seconds=2)
        return run


class MockMarketAdapter(OxylabsAdapter):
    """Adapter alias identifying the deterministic simulated store."""

    name = "mock_market"
