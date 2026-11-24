"""Universal Schema.org JSON-LD adapter and declarative TOML/dict Recipe adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapingstore import PARSER_VERSION
from scrapingstore.ledger.models import Product
from scrapingstore.sources.base import (
    availability_signal,
    default_page_url,
    extract_image_url,
    parse_price,
)
from scrapingstore.sources.results import PageResult


def _iter_jsonld_products(obj: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    if isinstance(obj, list):
        for item in obj:
            found.extend(_iter_jsonld_products(item))
    elif isinstance(obj, dict):
        kind = obj.get("@type")
        types = kind if isinstance(kind, list) else [kind]
        if "Product" in types:
            found.append(obj)
        if "ItemList" in types:
            for elem in obj.get("itemListElement", []):
                if isinstance(elem, dict) and "item" in elem:
                    found.extend(_iter_jsonld_products(elem["item"]))
                else:
                    found.extend(_iter_jsonld_products(elem))
        if "@graph" in obj:
            found.extend(_iter_jsonld_products(obj["@graph"]))
    return found


class JsonLdAdapter:
    """Extract structured Schema.org Product/Offer JSON-LD from real e-commerce pages."""

    name = "jsonld"
    ready_selector = "script[type='application/ld+json']"
    empty_text = "No products"

    def page_url(self, base_url: str, number: int) -> str:
        return default_page_url(base_url, number)

    def parse_page(
        self, content: Union[str, bytes], url: str, number: int
    ) -> PageResult:
        raw_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
        soup = BeautifulSoup(raw_bytes.decode("utf-8", errors="replace"), "html.parser")
        scripts = soup.select("script[type='application/ld+json']")
        result = PageResult(number, url)
        result.set_raw_html(raw_bytes)

        items: List[Dict[str, Any]] = []
        for tag in scripts:
            text = tag.string or tag.get_text()
            if not text.strip():
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            items.extend(_iter_jsonld_products(data))

        if not items:
            result.status = "failed"
            result.errors.append(
                "layout_unrecognized: no Schema.org Product JSON-LD found"
            )
            return result

        for idx, item in enumerate(items):
            try:
                name = str(item.get("name") or "").strip()
                if not name:
                    raise ValueError("missing product name in JSON-LD")
                offers = item.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                offers = offers if isinstance(offers, dict) else {}
                raw_price = offers.get("price")
                currency = str(offers.get("priceCurrency") or "EUR").upper()
                parsed_price = parse_price(
                    f"{raw_price} {currency}" if raw_price is not None else None,
                    allow_currencies=("EUR", "USD", "GBP"),
                )
                avail_raw = str(offers.get("availability") or "")
                avail, reason = availability_signal(avail_raw)
                img = item.get("image")
                if isinstance(img, list):
                    img = img[0] if img else None
                if isinstance(img, dict):
                    img = img.get("url")
                sku = item.get("sku") or item.get("productID") or item.get("mpn")
                prod_url = item.get("url")
                if prod_url:
                    prod_url = urljoin(url, str(prod_url))
                rating_obj = item.get("aggregateRating") or {}
                rating = None
                if isinstance(rating_obj, dict) and rating_obj.get("ratingValue") is not None:
                    try:
                        rating = float(rating_obj["ratingValue"])
                    except (TypeError, ValueError):
                        rating = None
                category = item.get("category")
                result.products.append(
                    Product(
                        name=name,
                        price=parsed_price.value,
                        price_raw=parsed_price.raw,
                        price_status=parsed_price.status,
                        currency=parsed_price.currency,
                        availability=avail,
                        availability_raw=avail_raw or None,
                        availability_reason=reason,
                        source_url=url,
                        source_id=str(sku) if sku else None,
                        product_url=str(prod_url) if prod_url else None,
                        image_url=urljoin(url, str(img)) if img else None,
                        category=str(category) if category else None,
                        rating=rating,
                        parser_version=PARSER_VERSION,
                    )
                )
            except (ValueError, TypeError) as exc:
                result.errors.append(f"jsonld[{idx}]: {exc}")
                result.rejected_cards += 1

        next_link = soup.select_one("a[rel~='next']")
        result.source_end = bool(
            next_link is None or next_link.get("aria-disabled") == "true"
        )
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


@dataclass
class RecipeAdapter:
    """Declarative CSS-selector adapter loaded from a TOML file or dict."""

    name: str
    card_selector: str
    title_selector: str
    price_selector: str
    availability_selector: Optional[str] = None
    link_selector: Optional[str] = None
    category_selector: Optional[str] = None
    id_attr: Optional[str] = None
    next_selector: str = "a[rel~='next']"
    empty_text: str = "No products"
    page_param: str = "page"
    currencies: tuple[str, ...] = ("EUR", "USD", "GBP")

    @property
    def ready_selector(self) -> str:
        return self.card_selector

    @classmethod
    def from_dict(cls, spec: Dict[str, Any]) -> "RecipeAdapter":
        currencies = tuple(spec.get("currencies", ("EUR", "USD", "GBP")))
        return cls(
            name=str(spec.get("name", "custom-recipe")),
            card_selector=str(spec["card_selector"]),
            title_selector=str(spec["title_selector"]),
            price_selector=str(spec["price_selector"]),
            availability_selector=spec.get("availability_selector"),
            link_selector=spec.get("link_selector"),
            category_selector=spec.get("category_selector"),
            id_attr=spec.get("id_attr"),
            next_selector=str(spec.get("next_selector", "a[rel~='next']")),
            empty_text=str(spec.get("empty_text", "No products")),
            page_param=str(spec.get("page_param", "page")),
            currencies=currencies,
        )

    @classmethod
    def from_toml(cls, path: Path | str) -> "RecipeAdapter":
        import tomllib

        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        section = data.get("recipe", data)
        return cls.from_dict(section)

    def page_url(self, base_url: str, number: int) -> str:
        return default_page_url(base_url, number)

    def parse_page(
        self, content: Union[str, bytes], url: str, number: int
    ) -> PageResult:
        raw_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
        soup = BeautifulSoup(raw_bytes.decode("utf-8", errors="replace"), "html.parser")
        cards = soup.select(self.card_selector)
        next_link = soup.select_one(self.next_selector)
        end = bool(next_link and next_link.get("aria-disabled") == "true")
        empty = self.empty_text in soup.get_text(" ", strip=True)
        result = PageResult(number, url, source_end=end or (not cards and empty))
        result.set_raw_html(raw_bytes)
        if not cards:
            result.status = "empty" if empty else "failed"
            if not empty:
                result.errors.append(
                    f"layout_unrecognized: selector {self.card_selector!r} matched 0 cards"
                )
            return result

        for idx, card in enumerate(cards):
            try:
                title_el = card.select_one(self.title_selector)
                if title_el is None or not title_el.get_text(strip=True):
                    raise ValueError("missing product title")
                price_el = card.select_one(self.price_selector)
                price = parse_price(
                    price_el.get_text(" ", strip=True) if price_el else None,
                    allow_currencies=self.currencies,
                )
                avail_raw = ""
                if self.availability_selector:
                    avail_el = card.select_one(self.availability_selector)
                    if avail_el:
                        avail_raw = avail_el.get_text(" ", strip=True)
                avail, reason = availability_signal(avail_raw)
                prod_url = None
                if self.link_selector:
                    link_el = card.select_one(self.link_selector)
                    if link_el and link_el.get("href"):
                        prod_url = urljoin(url, str(link_el["href"]))
                source_id = (
                    str(card.get(self.id_attr))
                    if self.id_attr and card.get(self.id_attr)
                    else None
                )
                category = None
                if self.category_selector:
                    cat_el = card.select_one(self.category_selector)
                    if cat_el:
                        category = cat_el.get_text(" ", strip=True) or None
                result.products.append(
                    Product(
                        name=title_el.get_text(" ", strip=True),
                        price=price.value,
                        price_raw=price.raw,
                        price_status=price.status,
                        currency=price.currency,
                        availability=avail,
                        availability_raw=avail_raw or None,
                        availability_reason=reason,
                        source_url=url,
                        source_id=source_id,
                        product_url=prod_url,
                        image_url=extract_image_url(card, url),
                        category=category,
                        parser_version=PARSER_VERSION,
                    )
                )
            except (ValueError, TypeError) as exc:
                result.errors.append(f"card {idx + 1}: {exc}")
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
