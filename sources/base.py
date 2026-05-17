"""Shared building blocks for event sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

ROME = ZoneInfo("Europe/Rome")

# A realistic User-Agent helps with sites that block default Python clients.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
}

DEFAULT_TIMEOUT = 20


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


def http_get(url: str, **kwargs) -> requests.Response:
    """GET helper with browser-like headers, sane timeout, and one retry.

    The retry covers the case where a server (e.g. PARC) drops the first
    connection before responding — a single immediate retry tends to succeed.
    """
    headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            continue
    raise last_exc if last_exc else requests.ConnectionError("unknown error")
