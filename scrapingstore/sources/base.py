"""SourceAdapter protocol and shared evidence-preserving parsing primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import TYPE_CHECKING, Optional, Protocol, Tuple, Union
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import Tag

if TYPE_CHECKING:
    from scrapingstore.sources.results import PageResult


@dataclass(frozen=True)
class ParsedPrice:
    value: Optional[float]
    raw: Optional[str]
    status: str
    currency: str = "EUR"


class SourceAdapter(Protocol):
    """Contract implemented by every site adapter (Oxylabs, JSON-LD, Recipe, Mock)."""

    name: str
    empty_text: str

    @property
    def ready_selector(self) -> str: ...

    def page_url(self, base_url: str, number: int) -> str: ...

    def parse_page(
        self, content: Union[str, bytes], url: str, number: int
    ) -> "PageResult": ...


def default_page_url(base_url: str, number: int) -> str:
    """Append or replace ?page=N for pages > 1, preserving existing query params."""
    parts = urlsplit(base_url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"]
    if number > 1:
        query.append(("page", str(number)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def parse_price(raw: Optional[str], *, allow_currencies: Tuple[str, ...] = ("EUR",)) -> ParsedPrice:
    """Parse prices strictly without inventing values or silently accepting ambiguities.

    EUR contract: 2 decimals; grouped thousands; no negatives or multiple amounts.
    """
    if not raw or not raw.strip():
        return ParsedPrice(None, raw, "missing")
    text = raw.strip().replace("\u00a0", " ").replace("\u202f", " ")
    if any(mark in text for mark in ("-", "\u2212", "+")):
        return ParsedPrice(None, raw, "invalid")

    # Detect currency
    currency = "EUR"
    symbol_map = {"€": "EUR", "$": "USD", "£": "GBP"}
    detected: list[str] = []
    for sym, code in symbol_map.items():
        if sym in text:
            if text.count(sym) > 1:
                return ParsedPrice(None, raw, "ambiguous")
            detected.append(code)
    for code in ("EUR", "USD", "GBP"):
        matches = re.findall(rf"\b{code}\b", text)
        if len(matches) > 1:
            return ParsedPrice(None, raw, "ambiguous")
        if matches and code not in detected:
            detected.append(code)

    if len(detected) > 1:
        return ParsedPrice(None, raw, "ambiguous")
    if detected:
        currency = detected[0]
        if currency not in allow_currencies:
            return ParsedPrice(None, raw, "unsupported", currency=currency)

    text = re.sub(
        r"^(?:€|\$|£|EUR|USD|GBP)\s*|\s*(?:€|\$|£|EUR|USD|GBP)$", "", text
    ).strip()

    patterns = (
        r"\d+(?:[.,]\d{2})?",
        r"\d{1,3}(?:\.\d{3})+,\d{2}",
        r"\d{1,3}(?:,\d{3})+\.\d{2}",
        r"\d{1,3}(?: \d{3})+(?:[.,]\d{2})?",
    )
    if not any(re.fullmatch(pattern, text) for pattern in patterns):
        return ParsedPrice(None, raw, "unsupported", currency=currency)

    text = text.replace(" ", "")
    if "," in text and "." in text:
        decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal_mark == "," else ",", "")

    try:
        value = float(Decimal(text.replace(",", ".")))
    except (InvalidOperation, OverflowError):
        return ParsedPrice(None, raw, "invalid", currency=currency)

    return (
        ParsedPrice(value, raw, "known", currency=currency)
        if isfinite(value)
        else ParsedPrice(None, raw, "invalid", currency=currency)
    )


def availability_signal(text: str) -> Tuple[str, Optional[str]]:
    """Classify availability text while flagging contradictions explicitly."""
    lower = text.casefold()
    negative = bool(
        re.search(
            r"\b(not in stock|out of stock|unavailable|sold out|outofstock)\b", lower
        )
    )
    remaining = re.sub(r"not in stock|out of stock|outofstock", "", lower)
    positive = bool(
        re.search(r"\bin stock\b|\binstock\b|\badd to (basket|cart)\b", remaining)
    )
    if positive and negative:
        return "Unknown", "conflicting availability signals"
    if negative:
        return "Out of Stock", None
    if positive:
        return "In Stock", None
    return "Unknown", "no explicit availability signal"


def _is_placeholder_image(url: str) -> bool:
    low = url.strip().lower()
    if not low:
        return True
    if low.startswith("data:"):
        return True
    if any(
        token in low
        for token in ("placeholder", "blank.gif", "spacer.gif", "1x1.", "transparent.gif")
    ):
        return True
    return False


def _best_from_srcset(srcset: str) -> Optional[str]:
    candidates = [part.strip().split()[0] for part in srcset.split(",") if part.strip()]
    for url in reversed(candidates):
        if not _is_placeholder_image(url):
            return url
    return None


def extract_image_url(
    card: Tag, listing_url: str, *, resolve_relative: bool = True
) -> Optional[str]:
    """Extract a real image URL, checking lazy-load attrs and rejecting data: placeholders."""
    img = card.select_one("img")
    if img is None:
        return None

    candidates: list[str] = []
    for attr in ("data-src", "data-lazy-src", "data-original", "data-srcset", "srcset", "src"):
        val = img.get(attr)
        if not val:
            continue
        raw = str(val).strip()
        if attr in ("srcset", "data-srcset"):
            picked = _best_from_srcset(raw)
            if picked:
                candidates.append(picked)
        else:
            candidates.append(raw)

    for candidate in candidates:
        if _is_placeholder_image(candidate):
            continue
        if resolve_relative and listing_url:
            parts = urlsplit(candidate)
            if not parts.scheme and candidate.startswith("/"):
                return urljoin(listing_url, candidate)
        return candidate
    return None


_GENRE_OVERRIDES = {
    "role-playing": "Role-Playing",
    "rpg": "RPG",
    "fps": "FPS",
    "mmo": "MMO",
    "real-time-strategy": "Real-Time Strategy",
    "turn-based-strategy": "Turn-Based Strategy",
    "point-and-click": "Point & Click",
    "hack-and-slash": "Hack & Slash",
    "beat-em-up": "Beat 'Em Up",
    "sci-fi": "Sci-Fi",
}


def infer_genre_from_image_url(image_url: Optional[str]) -> Optional[str]:
    """Derive a clean category/genre from semantic asset paths like /assets/action.svg."""
    if not image_url or image_url.startswith("data:"):
        return None
    path = urlsplit(image_url).path
    match = re.search(r"/assets/([a-z0-9_-]+)\.svg$", path, re.IGNORECASE)
    if not match:
        return None
    slug = match.group(1).lower().replace("_", "-")
    if slug in ("placeholder", "default", "logo", "icon"):
        return None
    if slug in _GENRE_OVERRIDES:
        return _GENRE_OVERRIDES[slug]
    return " ".join(part.capitalize() for part in slug.split("-") if part)
