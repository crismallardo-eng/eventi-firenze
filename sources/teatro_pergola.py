"""Fondazione Teatro della Toscana — Teatro della Pergola + Nuovo Rifredi.

Il sito espone le card eventi via JavaScript, ma il sitemap.xml elenca
tutti gli URL dei singoli spettacoli; per ciascuno scarichiamo la
pagina di dettaglio e leggiamo titolo, luogo e date.

Sitemap:  https://www.teatrodellatoscana.it/sitemap.xml
URL evento: /it/evento/{spettacolo|evento}/{slug}

Struttura pagina dettaglio:
    h1.strip__title1                       → titolo
    div.event__location / event__banner__location → teatro
    div.event__dates > div.event__date     → singole date
        formato: "DD mes YYYY HH:MM" (es. "23 mag 2026 21:00")

Vengono inclusi solo gli eventi al Teatro della Pergola e al Nuovo
Rifredi Scena Aperta (entrambi a Firenze); il Teatro Era (Pontedera)
viene scartato.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Teatro della Pergola"
CATEGORY = "Teatro"
BASE_URL = "https://www.teatrodellatoscana.it"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

PARALLEL_WORKERS = 8
REQUEST_TIMEOUT = 12

# Venue ammessi (case-insensitive substring match)
ALLOWED_VENUES = ("pergola", "rifredi")

# "23 mag 2026 21:00" — può ripetersi più volte nel testo concatenato di event__dates
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)\s+(\d{4})\s+(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)


def _parse_dates_block(text: str) -> list[datetime]:
    """Estrae tutti i datetime da un blocco 'DD mes YYYY HH:MM ...'."""
    out: list[datetime] = []
    for d, mname, y, h, m in _DATE_RE.findall(text):
        month = ITALIAN_MONTHS.get(mname.lower())
        if month is None:
            continue
        try:
            out.append(datetime(int(y), month, int(d), int(h), int(m), tzinfo=ROME))
        except ValueError:
            continue
    return out


def _scrape_event(url: str) -> list[Event]:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.find("h1", class_="strip__title1")
    title = h1.get_text(" ", strip=True) if h1 else None
    if not title:
        return []

    # Cerca il luogo
    venue_el = (soup.find("div", class_="event__location")
                or soup.find("div", class_="event__banner__location"))
    venue = venue_el.get_text(" ", strip=True) if venue_el else ""

    venue_lower = venue.lower()
    if not any(v in venue_lower for v in ALLOWED_VENUES):
        return []

    dates_el = soup.find("div", class_="event__dates")
    if dates_el is None:
        return []
    starts = _parse_dates_block(dates_el.get_text(" ", strip=True))
    if not starts:
        return []

    return [
        Event(
            source=SOURCE_NAME,
            title=title,
            start=st,
            url=url,
            venue=venue or None,
            category=CATEGORY,
        )
        for st in starts
    ]


def fetch() -> list[Event]:
    # Sitemap → URL eventi
    try:
        resp = http_get(SITEMAP_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []
    event_urls = re.findall(
        r"<loc>([^<]+/it/evento/[a-z]+/[a-z0-9\-]+)</loc>", resp.text
    )
    if not event_urls:
        return []

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_scrape_event, u) for u in event_urls]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Dedup per (titolo, start, venue)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
