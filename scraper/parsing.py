"""Shared source adapter. Parse dedicated signals; preserve uncertainty."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Optional, Tuple, Union
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from models import Product
from scraper.results import PageResult, PARSER_VERSION

CARD_SELECTOR = "div.product-card"
EMPTY_TEXT = "Sorry there are no products in the list."
READY_SELECTOR = CARD_SELECTOR + ", [data-empty='true']"


@dataclass(frozen=True)
class ParsedPrice:
    value: Optional[float]
    raw: Optional[str]
    status: str


def parse_price(raw: Optional[str]) -> ParsedPrice:
    """EUR contract: 2 decimals; grouped thousands; no negatives or multiple amounts."""
    if not raw or not raw.strip():
        return ParsedPrice(None, raw, "missing")
    text = raw.strip().replace("\u00a0", " ").replace("\u202f", " ")
    if any(mark in text for mark in ("-", "−", "+")):
        return ParsedPrice(None, raw, "invalid")
    if text.count("€") > 1 or len(re.findall(r"\bEUR\b", text)) > 1:
        return ParsedPrice(None, raw, "ambiguous")
    text = re.sub(r"^(?:€|EUR)\s*|\s*(?:€|EUR)$", "", text).strip()
    patterns = (
        r"\d+(?:[.,]\d{2})?",
        r"\d{1,3}(?:\.\d{3})+,\d{2}",
        r"\d{1,3}(?:,\d{3})+\.\d{2}",
        r"\d{1,3}(?: \d{3})+(?:[.,]\d{2})?",
    )
    if not any(re.fullmatch(pattern, text) for pattern in patterns):
        return ParsedPrice(None, raw, "unsupported")
    text = text.replace(" ", "")
    if "," in text and "." in text:
        decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal_mark == "," else ",", "")
    try:
        value = float(Decimal(text.replace(",", ".")))
    except (InvalidOperation, OverflowError):
        return ParsedPrice(None, raw, "invalid")
    from math import isfinite

    return (
        ParsedPrice(value, raw, "known")
        if isfinite(value)
        else ParsedPrice(None, raw, "invalid")
    )


def availability_signal(text: str) -> Tuple[str, Optional[str]]:
    lower = text.casefold()
    negative = bool(
        re.search(r"\b(not in stock|out of stock|unavailable|sold out)\b", lower)
    )
    remaining = re.sub(r"not in stock|out of stock", "", lower)
    positive = bool(re.search(r"\bin stock\b|\badd to basket\b", remaining))
    if positive and negative:
        return "Unknown", "conflicting availability signals"
    if negative:
        return "Out of Stock", None
    if positive:
        return "In Stock", None
    return "Unknown", "no explicit availability signal"


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
            # Native numeric IDs are part of the observed sandbox URL contract.
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
    image = card.select_one("img[src]")
    return Product(
        name=title.get_text(" ", strip=True),
        price=price.value,
        price_raw=price.raw,
        price_status=price.status,
        availability=availability,
        availability_raw=raw_availability or None,
        availability_reason=reason,
        source_url=listing_url,
        source_id=str(source_id) if source_id else None,
        product_url=product_url,
        image_url=str(image["src"]) if image else None,
        parser_version=PARSER_VERSION,
    )


def parse_page(content: Union[str, bytes], url: str, number: int) -> PageResult:
    soup = BeautifulSoup(
        content.decode("utf-8") if isinstance(content, bytes) else content,
        "html.parser",
    )
    cards = soup.select(CARD_SELECTOR)
    next_link = soup.select_one("a[rel~='next']")
    end = bool(next_link and next_link.get("aria-disabled") == "true")
    empty = bool(soup.select_one("[data-empty='true']")) or EMPTY_TEXT in soup.get_text(
        " ", strip=True
    )
    result = PageResult(number, url, source_end=end or (not cards and empty))
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
