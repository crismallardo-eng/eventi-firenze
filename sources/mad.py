"""MAD - Murate Art District — agenda via scraping HTML statico.

The /agenda/ page lists each exhibition / event as <article.menu-featured-post>
with title, an Italian date range "Dal X al Y", and link.
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import parse_italian_date

SOURCE_NAME = "MAD - Murate Art District"
CATEGORY = "Mostre"
URL = "https://www.murateartdistrict.it/agenda/"

# "Dal 23 aprile al 24 maggio 2026" or single "23 aprile 2026"
_RANGE_RE = re.compile(
    r"dal\s+(\d{1,2}\s+\w+(?:\s+\d{4})?)\s+al\s+(\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE,
)


def fetch() -> list[Event]:
    response = http_get(URL)
    soup = BeautifulSoup(response.text, "html.parser")
    today = datetime.now(tz=ROME).date()

    events: list[Event] = []
    seen_links = set()
    for article in soup.find_all("article", class_="menu-featured-post"):
        title_el = article.select_one("h1.title, h2.title, h3.title")
        if title_el is None:
            continue
        title = title_el.get_text(" ", strip=True)
        if not title:
            continue

        date_el = article.select_one("p.giorni")
        date_text = date_el.get_text(" ", strip=True) if date_el else ""

        link_el = article.select_one("a.std-link, a[href]")
        url = link_el.get("href", "").strip() if link_el else ""
        if not url or url in seen_links:
            continue

        # Parse date range; if it's a single date, fall back to a single-date parse.
        start_d = end_d = None
        m = _RANGE_RE.search(date_text)
        if m:
            # If start lacks year, copy it from end
            start_text = m.group(1)
            end_text = m.group(2)
            end_d = parse_italian_date(end_text)
            start_year = None
            if not re.search(r"\d{4}", start_text) and end_d:
                start_year = end_d.year
            start_d = parse_italian_date(start_text, default_year=start_year)
        else:
            start_d = parse_italian_date(date_text)

        if start_d is None:
            continue

        # Drop ended exhibitions
        if end_d and end_d < today:
            continue
        if not end_d and start_d < today:
            continue

        seen_links.add(url)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=datetime.combine(start_d, datetime.min.time(), tzinfo=ROME),
            end=datetime.combine(end_d, datetime.min.time(), tzinfo=ROME) if end_d else None,
            url=url,
            venue="MAD - Murate Art District",
        ))
    return events
