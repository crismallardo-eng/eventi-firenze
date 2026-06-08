"""Circolo Il Progresso — eventi via WP REST + JSON-LD per pagina evento.

The /eventi/ page is rendered client-side by the EventON plugin, so direct
scraping returns nothing. We instead pull the event list from the standard
WordPress REST endpoint, then fetch each event page in parallel and extract
the schema.org Event JSON-LD which carries proper startDate/endDate.
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

SOURCE_NAME = "Circolo Il Progresso"
CATEGORY = "Circoli"
LIST_API = "https://www.circoloilprogresso.it/wp-json/wp/v2/ajde_events?per_page=30"
PARALLEL_WORKERS = 8
REQUEST_TIMEOUT = 10

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html_str: str) -> str:
    return unescape(_TAG_RE.sub(" ", html_str)).strip()


def _parse_iso_date(text: str) -> datetime | None:
    """EventON emits dates like '2026-5-22T20:30+1:00' (single-digit timezone).

    Bug noto: il sito emette il tzoffset come +01:00 fisso (CET) anche
    d'estate, quando l'ora locale italiana è +02:00 (CEST). Risultato: un
    evento che termina alle "23:00 +01:00" sul sito coincide con la
    mezzanotte ITA del giorno dopo, e finisce per restare visibile come
    "non passato" il giorno successivo. Ignoriamo il tzoffset emesso e
    re-applichiamo Europe/Rome — le date sono sempre ora locale italiana.

    `dateutil.parser` handles most variants; if it fails we fall back to None.
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
        # Could be a single Event or a list
        candidates = data if isinstance(data, list) else [data]
        for c in candidates:
            if isinstance(c, dict) and c.get("@type") == "Event":
                return c
    return None


def _event_from_link(link: str, fallback_title: str) -> Event | None:
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
    end = _parse_iso_date(jsonld.get("endDate", ""))
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=ROME)

    title = unescape(jsonld.get("name") or fallback_title)
    description = _strip_html(jsonld.get("description", ""))
    if description and len(description) > 280:
        description = description[:277] + "…"

    return Event(
        source=SOURCE_NAME,
        title=title,
        start=start,
        end=end,
        url=link,
        venue="Circolo Il Progresso",
        description=description,
    )


def fetch() -> list[Event]:
    response = http_get(LIST_API, headers={"Accept": "application/json"})
    items = response.json()

    links_titles = []
    for item in items:
        link = item.get("link", "")
        title = (item.get("title") or {}).get("rendered", "") or ""
        if link:
            links_titles.append((link, _strip_html(title)))

    if not links_titles:
        # REST API risponde 200 ma con lista vuota: lo segnalo per non
        # far sparire la fonte silenziosamente.
        raise RuntimeError(
            "REST API /ajde_events ha risposto OK ma con 0 eventi pubblicati. "
            "Verificare circoloilprogresso.it/eventi nel browser."
        )

    events: list[Event] = []
    failed_details = 0
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_event_from_link, link, title) for link, title in links_titles]
        for fut in as_completed(futures):
            try:
                ev = fut.result()
            except Exception:
                failed_details += 1
                continue
            if ev is not None:
                events.append(ev)
            else:
                failed_details += 1

    # Se ho la lista di eventi dalla REST API ma TUTTE le pagine di dettaglio
    # hanno fallito il parsing, e' un problema strutturale (es. JSON-LD
    # rimosso dal tema): lo segnalo invece di tornare [] in silenzio.
    if events == [] and failed_details == len(links_titles):
        raise RuntimeError(
            f"REST API ha ritornato {len(links_titles)} eventi ma nessuna "
            "pagina di dettaglio espone JSON-LD parsabile."
        )
    return events
