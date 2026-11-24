"""Per-host token-bucket rate limiter, Retry-After parser, and robots.txt helper."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from scrapingstore.config import get_settings

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


def retry_delay(attempt: int, header: Optional[str], *, backoff: Optional[float] = None) -> float:
    """Compute bounded retry delay, honoring Retry-After headers when present."""
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    base = get_settings().retry_backoff if backoff is None else backoff
    return float(min(30.0, base * 2 ** (attempt - 1)))


def check_robots_txt(
    url: str, *, user_agent: Optional[str] = None, timeout: float = 5.0
) -> Tuple[bool, Optional[float], str]:
    """Fetch robots.txt for url's host; returns (allowed, crawl_delay, note)."""
    ua = user_agent or get_settings().user_agent
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return True, None, "non-http scheme"
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        resp = requests.get(robots_url, headers={"User-Agent": ua}, timeout=timeout)
        if resp.status_code == 404:
            return True, None, "no robots.txt (404)"
        if resp.status_code >= 400:
            return True, None, f"robots.txt HTTP {resp.status_code}"
        rp.parse(resp.text.splitlines())
        allowed = rp.can_fetch(ua, url)
        delay = rp.crawl_delay(ua)
        crawl_delay = float(delay) if delay is not None else None
        return allowed, crawl_delay, "robots.txt parsed"
    except Exception as exc:
        return True, None, f"robots.txt unreachable ({type(exc).__name__})"


class HostRateLimiter:
    """Per-host sliding-window spacing limiter (sync & async safe)."""

    def __init__(self, min_interval: float = 1.0):
        self.min_interval = max(0.0, min_interval)
        self._next_allowed: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _reserve_wait(self, host: str) -> float:
        if self.min_interval <= 0:
            return 0.0
        now = time.monotonic()
        with self._lock:
            scheduled = max(now, self._next_allowed.get(host, now))
            self._next_allowed[host] = scheduled + self.min_interval
            return max(0.0, scheduled - now)

    def wait_sync(self, url: str, remaining: float) -> None:
        host = urlsplit(url).netloc.lower()
        wait = self._reserve_wait(host)
        if wait > 0:
            time.sleep(min(wait, max(0.0, remaining)))

    async def wait_async(self, url: str, remaining: float) -> None:
        host = urlsplit(url).netloc.lower()
        wait = self._reserve_wait(host)
        if wait > 0:
            await asyncio.sleep(min(wait, max(0.0, remaining)))
