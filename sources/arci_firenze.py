"""Arci Firenze — eventi dai circoli ARCI fiorentini (Vie Nuove, Quinto Basso, ecc.).

Arci Firenze federa decine di circoli che pubblicano i loro eventi sul portale
centralizzato arcifirenze.it. Il sito gira su WordPress + EventON, identico a
Circolo Il Progresso ma con catalogo più ampio.

Approccio:
  1. /wp-json/wp/v2/ajde_events?per_page=50&orderby=date&order=desc
     → 100 eventi più recentemente pubblicati (2 pagine)
  2. Per ciascuno, fetch della pagina di dettaglio e parsing del JSON-LD Event
     emesso da EventON (startDate, endDate, location, description)
  3. Filtro: tengo solo gli eventi con startDate >= oggi

Il `location.name` del JSON-LD identifica il singolo circolo: viene usato
come venue dell'Event, così l'utente vede "Brillante - Nuovo Teatro Lippi",
"Vie Nuove", "Quinto Basso", ecc.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from html import unescape

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Arci Firenze"
CATEGORY = "Circoli"
BASE_URL = "https://www.arcifirenze.it"
# Il sito ha spostato il front-end da /eventi/ a /agenda/ — probabilmente
# il post type WP e' cambiato di conseguenza. Provo i candidati piu'
# plausibili in ordine, il primo che ritorna >= 1 elemento vince.
LIST_API_CANDIDATES = [
    f"{BASE_URL}/wp-json/wp/v2/agenda",          # nuovo, matcha /agenda/
    f"{BASE_URL}/wp-json/wp/v2/ajde_events",     # vecchio EventON
    f"{BASE_URL}/wp-json/wp/v2/event",
    f"{BASE_URL}/wp-json/wp/v2/events",
    f"{BASE_URL}/wp-json/wp/v2/evento",
    f"{BASE_URL}/wp-json/wp/v2/eventi",
]
PAGES_TO_FETCH = 2
PER_PAGE = 50
PARALLEL_WORKERS = 8
REQUEST_TIMEOUT = 10

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html_str: str) -> str:
    return unescape(_TAG_RE.sub(" ", html_str)).strip()


def _parse_iso_date(text: str) -> datetime | None:
    """EventON emette date tipo '2026-5-10T21:30+2:00' (mese/timezone non zero-padded).

    Il tzoffset del sito è inaffidabile (+01:00 anche d'estate quando dovrebbe
    essere +02:00). Lo ignoriamo e ri-applichiamo Europe/Rome: le date sono
    sempre ora locale italiana.
    """
    if not text:
        return None
    try:
        dt = dateparser.parse(text)
    except (ValueError, TypeError):
        return None
    if dt is None:
        return None
    return dt.replace(tzinfo=None).replace(tzinfo=ROME)


def _extract_event_jsonld(html_text: str) -> dict | None:
    soup = BeautifulSoup(html_text, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        body = script.string or script.get_text() or ""
        if "Event" not in body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if isinstance(c, dict) and c.get("@type") == "Event":
                return c
    return None


def _extract_venue(jsonld: dict) -> str | None:
    loc = jsonld.get("location")
    if isinstance(loc, dict):
        name = loc.get("name")
        if isinstance(name, str) and name.strip():
            return unescape(name.strip())
    elif isinstance(loc, list) and loc:
        first = loc[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str) and name.strip():
                return unescape(name.strip())
    return None


def _event_from_link(link: str, fallback_title: str, today: datetime) -> Event | None:
    try:
        response = http_get(link, timeout=REQUEST_TIMEOUT)
    except Exception:
        return None

    jsonld = _extract_event_jsonld(response.text)
    if not jsonld:
        return None

    start = _parse_iso_date(jsonld.get("startDate", ""))
    if start is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=ROME)
    # Filtro lato scraper: scarta eventi passati (la list_api ritorna anche
    # eventi recentemente pubblicati la cui data è già passata).
    if start < today:
        return None

    end = _parse_iso_date(jsonld.get("endDate", ""))
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=ROME)
    # Alcuni eventi hanno endDate < startDate (bug del CMS): lo ignoro.
    if end and end < start:
        end = None

    title = unescape(jsonld.get("name") or fallback_title)
    description = _strip_html(jsonld.get("description", ""))
    if description and len(description) > 280:
        description = description[:277] + "…"

    venue = _extract_venue(jsonld)

    return Event(
        source=SOURCE_NAME,
        title=title,
        start=start,
        end=end,
        url=link,
        venue=venue,
        description=description,
        category=CATEGORY,
    )


def _fetch_links_from(list_api: str) -> list[tuple[str, str]]:
    """Prova un singolo endpoint REST. Ritorna lista link/titolo, lista
    vuota se l'endpoint risponde male o ha 0 elementi."""
    out: list[tuple[str, str]] = []
    for page in range(1, PAGES_TO_FETCH + 1):
        url = f"{list_api}?per_page={PER_PAGE}&orderby=date&order=desc&page={page}"
        try:
            resp = http_get(url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT)
        except Exception:
            return out
        try:
            items = resp.json()
        except Exception:
            return out
        if not isinstance(items, list) or not items:
            return out
        for item in items:
            link = item.get("link", "")
            title = (item.get("title") or {}).get("rendered", "") or ""
            if link:
                out.append((link, _strip_html(title)))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME)
    # Prova gli endpoint candidati nell'ordine: il primo che torna
    # qualcosa vince.
    links_titles: list[tuple[str, str]] = []
    tried = []
    for endpoint in LIST_API_CANDIDATES:
        links_titles = _fetch_links_from(endpoint)
        tried.append((endpoint, len(links_titles)))
        if links_titles:
            break

    if not links_titles:
        # Nessuno dei candidati ha ritornato eventi: segnalo errore con
        # i tentativi cosi' si capisce dove stiamo
        summary = ", ".join(f"{u.rsplit('/', 1)[-1]}={n}" for u, n in tried)
        raise RuntimeError(
            f"Nessun endpoint REST ha ritornato eventi. Tentativi: {summary}. "
            "Probabilmente il post type ha cambiato nome — verifica "
            "https://www.arcifirenze.it/wp-json/wp/v2/types nel browser."
        )

    # Scarica le pagine di dettaglio in parallelo.
    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [
            ex.submit(_event_from_link, link, title, today)
            for link, title in links_titles
        ]
        for fut in as_completed(futures):
            try:
                ev = fut.result()
            except Exception:
                continue
            if ev is not None:
                events.append(ev)

    # Dedup
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
