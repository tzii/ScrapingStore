"""Oxylabs Sandbox E-commerce source adapter with lazy-image & genre recovery."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Optional, Union
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from scrapingstore import PARSER_VERSION
from scrapingstore.ledger.models import Product
from scrapingstore.sources.base import (
    ParsedPrice,
    availability_signal,
    default_page_url,
    extract_image_url,
    infer_genre_from_image_url,
    parse_price,
)
from scrapingstore.sources.results import PageResult

CARD_SELECTOR = "div.product-card"
EMPTY_TEXT = "Sorry there are no products in the list."
READY_SELECTOR = CARD_SELECTOR + ", [data-empty='true']"


def extract_price(card: Tag) -> ParsedPrice:
    for selector in (
        "[data-current-price]",
        "[itemprop='price']",
        ".current-price",
        ".price-wrapper",
        ".price",
    ):
        elements = card.select(selector)
        if elements:
            if len(elements) != 1:
                return ParsedPrice(
                    None,
                    " | ".join(e.get_text(" ", strip=True) for e in elements),
                    "ambiguous",
                )
            element = elements[0]
            raw = (
                element.get("data-current-price")
                or element.get("content")
                or element.get_text(" ", strip=True)
            )
            return parse_price(str(raw))
    return ParsedPrice(None, None, "missing")


def _extract_category(card: Tag, image_url: Optional[str]) -> Optional[str]:
    if card.get("data-category"):
        raw = str(card.get("data-category")).strip()
        if raw:
            return raw
    cat_el = card.select_one("[data-category], .category, .genre, .category-wrapper")
    if cat_el:
        raw = str(cat_el.get("data-category") or cat_el.get_text(" ", strip=True)).strip()
        if raw:
            return raw
    return infer_genre_from_image_url(image_url)


def _extract_rating(card: Tag) -> Optional[float]:
    raw_attr = card.get("data-rating")
    raw: Optional[str] = str(raw_attr).strip() if raw_attr is not None else None
    if not raw:
        rating_el = card.select_one("[data-rating], [itemprop='ratingValue'], .rating-value")
        if rating_el:
            raw = str(
                rating_el.get("data-rating")
                or rating_el.get("content")
                or rating_el.get_text(" ", strip=True)
            ).strip()
    if raw:
        match = re.search(r"(\d+(?:\.\d+)?)", raw)
        if match:
            try:
                val = float(match.group(1))
                if 0.0 <= val <= 5.0:
                    return val
            except ValueError:
                pass
    return None


def parse_card(card: Tag, listing_url: str) -> Product:
    title = card.find("h4")
    if title is None or not title.get_text(strip=True):
        raise ValueError("missing product title")
    price = extract_price(card)
    link = card.select_one("a.card-header[href]") or title.find_parent("a", href=True)
    product_url = None
    source_id = card.get("data-product-id")
    if link and link.get("href"):
        parsed = urlsplit(urljoin(listing_url, str(link["href"])))
        if parsed.scheme in ("https", "http"):
            product_url = urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
            )
            native = re.fullmatch(r"/products/(\d+)", parsed.path)
            if native and not parsed.query:
                source_id = source_id or native.group(1)
            if parsed.query:
                source_id = None

    availability_element = card.select_one(
        "[data-availability], .availability, [itemprop='availability']"
    )
    if availability_element:
        raw_availability = str(
            availability_element.get("data-availability")
            or availability_element.get("content")
            or availability_element.get_text(" ", strip=True)
        )
    else:
        controls = card.select("button, a:not(.card-header)")
        raw_availability = " ".join(
            c.get_text(" ", strip=True)
            for c in controls
            if not c.has_attr("disabled") and c.get("aria-disabled") != "true"
        )
    availability, reason = availability_signal(raw_availability)
    image_url = extract_image_url(card, listing_url)
    category = _extract_category(card, image_url)
    rating = _extract_rating(card)

    return Product(
        name=title.get_text(" ", strip=True),
        price=price.value,
        price_raw=price.raw,
        price_status=price.status,
        currency=price.currency,
        availability=availability,
        availability_raw=raw_availability or None,
        availability_reason=reason,
        source_url=listing_url,
        source_id=str(source_id) if source_id else None,
        product_url=product_url,
        image_url=image_url,
        category=category,
        rating=rating,
        parser_version=PARSER_VERSION,
    )


def parse_page(content: Union[str, bytes], url: str, number: int) -> PageResult:
    raw_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
    soup = BeautifulSoup(raw_bytes.decode("utf-8", errors="replace"), "html.parser")
    cards = soup.select(CARD_SELECTOR)
    next_link = soup.select_one("a[rel~='next']")
    end = bool(next_link and next_link.get("aria-disabled") == "true")
    empty = bool(soup.select_one("[data-empty='true']")) or EMPTY_TEXT in soup.get_text(
        " ", strip=True
    )
    result = PageResult(number, url, source_end=end or (not cards and empty))
    result.set_raw_html(raw_bytes)
    if not cards:
        result.status = "empty" if empty else "failed"
        if not empty:
            result.errors.append(
                "layout_unrecognized: no product cards or confirmed empty state"
            )
        return result
    for index, card in enumerate(cards):
        try:
            result.products.append(parse_card(card, url))
        except (ValueError, TypeError) as exc:
            result.errors.append(f"card {index + 1}: {exc}")
            result.rejected_cards += 1
    result.status = (
        "partial"
        if result.errors and result.products
        else "failed" if result.errors else "success"
    )
    evidence = [
        (p.source_id, p.product_url, p.name, p.price_raw) for p in result.products
    ]
    if evidence:
        result.fingerprint = hashlib.sha256(
            json.dumps(evidence, sort_keys=True).encode()
        ).hexdigest()
    return result


class OxylabsAdapter:
    """Default adapter for Oxylabs Sandbox E-commerce."""

    name = "oxylabs"
    ready_selector = READY_SELECTOR
    empty_text = EMPTY_TEXT

    def page_url(self, base_url: str, number: int) -> str:
        return default_page_url(base_url, number)

    def parse_page(
        self, content: Union[str, bytes], url: str, number: int
    ) -> PageResult:
        return parse_page(content, url, number)
