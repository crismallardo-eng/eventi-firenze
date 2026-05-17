"""Palazzo Strozzi — mostre via WP REST + scraping data range dalla pagina.

The REST endpoint /wp-json/wp/v2/mostra returns the list, but the date range
isn't in the API response (acf is empty). Each exhibition page contains the
range as Italian prose: "dal 22 maggio 2026<br>al 23 agosto 2026".
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import unescape

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import parse_italian_date

SOURCE_NAME = "Palazzo Strozzi"
CATEGORY = "Mostre"
LIST_API = "https://www.palazzostrozzi.org/wp-json/wp/v2/mostra?per_page=10"
PARALLEL_WORKERS = 6
REQUEST_TIMEOUT = 12

# Match phrases like "dal 22 maggio 2026 al 23 agosto 2026" with arbitrary
# whitespace / <br> tags between the two dates.
_RANGE_RE = re.compile(
    r"dal\s+(\d{1,2}\s+\w+\s+\d{4}).{0,40}?al\s+(\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE | re.DOTALL,
)


def _extract_range(html_text: str) -> tuple | None:
    # Strip tags first so "dal 22 maggio 2026<br>al 23 agosto 2026" becomes
    # "dal 22 maggio 2026 al 23 agosto 2026".
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = _RANGE_RE.search(text)
    if not m:
        return None
    start = parse_italian_date(m.group(1))
    end = parse_italian_date(m.group(2))
    if start is None:
        return None
    return start, end


def _event_for_item(item: dict) -> Event | None:
    title = unescape((item.get("title") or {}).get("rendered", "")).strip()
    link = item.get("link", "").strip()
    if not title or not link:
        return None

    try:
        page = http_get(link, timeout=REQUEST_TIMEOUT)
    except Exception:
        return None

    rng = _extract_range(page.text)
    if rng is None:
        return None
    start_d, end_d = rng
    today = datetime.now(tz=ROME).date()

    if end_d and end_d < today:
        return None

    return Event(
        source=SOURCE_NAME,
        title=title,
        start=datetime.combine(start_d, datetime.min.time(), tzinfo=ROME),
        end=datetime.combine(end_d, datetime.min.time(), tzinfo=ROME) if end_d else None,
        url=link,
        venue="Palazzo Strozzi",
    )


def fetch() -> list[Event]:
    response = http_get(LIST_API, headers={"Accept": "application/json"})
    items = response.json()

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_event_for_item, item) for item in items]
        for fut in as_completed(futures):
            try:
                ev = fut.result()
                if ev is not None:
                    events.append(ev)
            except Exception:
                continue
    return events
