"""Fondazione Teatro della Toscana — Teatro della Pergola + Nuovo Rifredi.

I permalink degli spettacoli si raccolgono dalle pagine di cartellone;
per ciascuno si scarica la pagina di dettaglio e si leggono titolo,
luogo e date.

Cartellone: /spettacoli/ e /it/in-programma
URL evento: /it/evento/{spettacolo|evento|mostra}/{slug}

NB: il sitemap.xml NON è più utilizzabile — è diventato un indice di
sotto-sitemap, e sitemap-eventi-it.xml elenca URL della vecchia
struttura a un solo segmento (/it/evento/<slug>) che oggi non
risolvono più. Era questa la causa della fonte a zero eventi.

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
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Teatro della Pergola"
CATEGORY = "Teatro"
BASE_URL = "https://www.teatrodellatoscana.it"
# Pagine di cartellone da cui raccogliere i permalink degli spettacoli.
LISTING_URLS = (
    f"{BASE_URL}/spettacoli/",
    f"{BASE_URL}/it/in-programma",
)
# Permalink spettacolo: /it/evento/{spettacolo|evento|mostra}/<slug>
_EVENT_URL_RE = re.compile(
    rf"^{re.escape(BASE_URL)}/it/evento/[a-z]+/[a-z0-9\-]+/?$"
)

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

    # Titolo: la classe dedicata se c'è, altrimenti il primo h1 utile —
    # così un restyling del tema non azzera di nuovo la fonte.
    h1 = soup.find("h1", class_="strip__title1") or soup.find("h1")
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


def _event_urls_from_listing() -> list[str]:
    """URL degli spettacoli in cartellone, dalle pagine di programmazione.

    Non si usa più il sitemap: è diventato un indice di sotto-sitemap e
    quello degli eventi elenca URL della vecchia struttura (un solo
    segmento, es. /it/evento/odissea-di-omero) che oggi non risolvono.
    Le pagine di cartellone invece portano i permalink correnti nella
    forma /it/evento/{spettacolo|evento|mostra}/<slug>.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for page in LISTING_URLS:
        try:
            resp = http_get(page, timeout=REQUEST_TIMEOUT)
        except Exception:  # noqa: BLE001
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            full = urljoin(BASE_URL, a["href"].split("?")[0].split("#")[0])
            if not _EVENT_URL_RE.match(full) or full in seen:
                continue
            seen.add(full)
            urls.append(full)
    return urls


def fetch() -> list[Event]:
    event_urls = _event_urls_from_listing()
    if not event_urls:
        raise RuntimeError(
            "Nessun link spettacolo trovato nelle pagine di cartellone "
            f"({', '.join(LISTING_URLS)}): struttura del sito cambiata."
        )

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
