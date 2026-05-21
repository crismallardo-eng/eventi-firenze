"""Estate Fiorentina — cartellone unico estivo del Comune di Firenze.

WordPress + plugin "Modern Events Calendar" (MEC). Gli eventi sono
indicizzati in più sitemap (mec-events-sitemap*.xml) e ogni pagina
dettaglio espone i metadati Schema.org/Event in JSON-LD.

Strategia:
  1. Scarica tutti i mec-events-sitemap*.xml referenziati nell'indice
  2. Per ogni URL evento, parsa il JSON-LD type=Event
  3. Tieni gli eventi con startDate >= oggi
  4. Estrae titolo dall'<h1> e orario/luogo dalla description del JSON-LD
     (formato tipico: "DD Mese · h HH:MM  <Luogo>  <Sottotitolo>")
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Estate Fiorentina"
CATEGORY = "Estate Fiorentina"
BASE_URL = "https://estatefiorentina.it"
SITEMAP_INDEX = f"{BASE_URL}/sitemap_index.xml"

PARALLEL_WORKERS = 10
REQUEST_TIMEOUT = 12
# Solo sitemap aggiornati negli ultimi N giorni: l'Estate Fiorentina
# pubblica il calendario a maggio/giugno; sitemap stagionali più vecchi
# contengono eventi ormai passati e non vale la pena scaricarli.
SITEMAP_FRESHNESS_DAYS = 75
# Eventi per sitemap recente (i più nuovi sono in fondo alla sitemap).
MAX_EVENTS_PER_SITEMAP = 100

_TIME_DESC_RE = re.compile(r"\bh\s*(\d{1,2})[:.]?(\d{2})?", re.IGNORECASE)


def _list_event_urls() -> list[str]:
    try:
        resp = http_get(SITEMAP_INDEX, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    # Estrae (url_sitemap, lastmod_iso) per ogni mec-events-sitemap
    sm_re = re.compile(
        r"<sitemap>\s*<loc>([^<]+mec-events-sitemap\d*\.xml)</loc>"
        r"\s*<lastmod>([^<]+)</lastmod>",
        re.DOTALL,
    )
    today = datetime.now(tz=ROME).date()
    fresh_sitemaps: list[str] = []
    for sm_url, lastmod in sm_re.findall(resp.text):
        try:
            lm_date = datetime.fromisoformat(lastmod.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if (today - lm_date).days <= SITEMAP_FRESHNESS_DAYS:
            fresh_sitemaps.append(sm_url)

    event_urls: list[str] = []
    seen: set[str] = set()
    for sm_url in fresh_sitemaps:
        try:
            sm_resp = http_get(sm_url, timeout=REQUEST_TIMEOUT)
        except Exception:
            continue
        urls = re.findall(r"<loc>([^<]+/events/[^<]+)</loc>", sm_resp.text)
        # Ultimi in sitemap = più recenti
        for u in reversed(urls[-MAX_EVENTS_PER_SITEMAP:] if len(urls) > MAX_EVENTS_PER_SITEMAP else urls):
            if u not in seen:
                seen.add(u)
                event_urls.append(u)
    return event_urls


def _scrape_event(url: str, today: date) -> Event | None:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    # Cerca lo script JSON-LD di tipo Event
    event_data = None
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Event":
            event_data = data
            break
    if event_data is None:
        return None

    start_str = event_data.get("startDate")
    if not start_str:
        return None
    try:
        # "2025-09-20" o "2025-09-20T19:00"
        if "T" in start_str:
            d = datetime.fromisoformat(start_str).date()
        else:
            d = date.fromisoformat(start_str)
    except ValueError:
        return None

    # Tieni solo eventi futuri (oggi compreso)
    if d < today:
        return None

    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    if not title:
        title = event_data.get("name") or ""
    if not title:
        return None

    # Orario e luogo dalla description del JSON-LD
    description = event_data.get("description") or ""
    t: time | None = None
    m = _TIME_DESC_RE.search(description)
    if m:
        try:
            t = time(int(m.group(1)), int(m.group(2) or 0))
        except ValueError:
            t = None

    # Luogo: provo location.name, altrimenti euristica sulla description
    venue: str | None = None
    loc = event_data.get("location")
    if isinstance(loc, dict):
        venue = loc.get("name") or None
    if not venue:
        # Cerca tra l'orario e fino al primo gruppo lungo di spazi/punti
        if m:
            tail = description[m.end():].strip()
            # Il pattern comune è "h 19:00  Parco di San Donato  Sottotitolo"
            parts = re.split(r"\s{2,}|·", tail)
            for p in parts:
                p = p.strip()
                if 4 <= len(p) <= 80 and not re.match(r"^[a-zà-ý]", p):
                    venue = p
                    break

    start = datetime.combine(d, t or time(0, 0), tzinfo=ROME)
    return Event(
        source=SOURCE_NAME,
        title=title,
        start=start,
        url=url,
        venue=venue,
        category=CATEGORY,
    )


def fetch() -> list[Event]:
    urls = _list_event_urls()
    if not urls:
        return []

    today = datetime.now(tz=ROME).date()
    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_scrape_event, u, today) for u in urls]
        for fut in as_completed(futures):
            try:
                ev = fut.result()
            except Exception:
                continue
            if ev is not None:
                events.append(ev)

    # Dedup per (titolo, inizio)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
