"""Shared building blocks for event sources."""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

ROME = ZoneInfo("Europe/Rome")

# A realistic User-Agent + the Sec-Fetch / Accept-* triad helps with sites
# (Drupal/Cloudflare etc.) that 403 default Python clients.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="126", "Not.A/Brand";v="24", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

DEFAULT_TIMEOUT = 20

# HTTP statuses worth retrying: anti-bot/WAF often returns 403, rate limit
# 429, and gateway errors 5xx are transient.
_RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}
# Backoff between retries (seconds). Total wall time: ~7s before giving up.
_RETRY_BACKOFF = (0, 2, 5)


@dataclass
class Event:
    source: str
    title: str
    start: datetime
    url: str
    end: Optional[datetime] = None
    venue: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    category: str = "Altro"

    def sort_key(self) -> datetime:
        # Make naive datetimes sortable alongside aware ones.
        if self.start.tzinfo is None:
            return self.start.replace(tzinfo=ROME)
        return self.start


def http_get(
    url: str,
    *,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> requests.Response:
    """GET helper with browser-like headers, retries on transient/403 errors.

    Pass `session` to reuse cookies across calls — required for sites that
    issue a cookie on the first page view and then expect it on subsequent
    requests (typical of Drupal sites behind a WAF).
    """
    headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    getter = session.get if session is not None else requests.get

    last_exc: Exception | None = None
    last_resp: Optional[requests.Response] = None
    for backoff in _RETRY_BACKOFF:
        if backoff:
            _time.sleep(backoff)
        try:
            response = getter(url, headers=headers, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            last_resp = None
            continue
        if response.status_code in _RETRYABLE_STATUSES:
            last_resp = response
            last_exc = None
            continue
        response.raise_for_status()
        return response

    if last_resp is not None:
        # Surface the HTTPError so the caller sees the actual status.
        last_resp.raise_for_status()
        return last_resp  # pragma: no cover (raise_for_status will raise)
    raise last_exc if last_exc else requests.ConnectionError("unknown error")


def new_session() -> requests.Session:
    """Build a Session pre-loaded with browser headers for cookie reuse."""
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s
