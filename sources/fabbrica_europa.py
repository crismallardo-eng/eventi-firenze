"""Fabbrica Europa — festival internazionale delle arti performative a Firenze.

Festival autunnale (settembre–ottobre) alla Stazione Leopolda e altre sedi
fiorentine: danza, teatro, musica, performance.

Struttura del sito (verificata dai dati del primo run reale): ogni spettacolo
ha una pagina dedicata sotto /events/<slug>/, es.
    /events/motus-frankenstein-history-of-hate/
    /events/rabih-abou-khalil/
Le pagine di edizioni passate stanno invece sotto /fabbrica-europa-<anno>/ o
/festival-fabbrica-europa-<anno>/ e NON vanno raccolte.

Il sito non è ispezionabile dall'ambiente di build (bloccato dal proxy egress),
quindi la data non si legge da un selettore CSS noto ma cercando una data
italiana nel contesto del link o nella pagina di dettaglio.

L'anno è nell'URL: quando esce l'edizione 2027 cambiare FESTIVAL_YEAR/LIST_URL.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get, new_session
from sources.italian_dates import parse_italian_datetime

SOURCE_NAME = "Fabbrica Europa"
CATEGORY = "Teatro"
BASE_URL = "https://fabbricaeuropa.net"
FESTIVAL_YEAR = 2026
LIST_URL = f"{BASE_URL}/fabbrica-europa-{FESTIVAL_YEAR}/"

# Solo le pagine spettacolo: /events/<slug>/ con slug non vuoto. Questo
# esclude da solo l'indice /events/, le pagine delle edizioni passate
# (/fabbrica-europa-2021/, /festival-fabbrica-europa-2025/), social, asset.
_EVENT_PATH_RE = re.compile(r"^/events/[^/]+/?$")
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    r"agosto|settembre|ottobre|novembre|dicembre)\b",
    re.IGNORECASE,
)


def _is_detail_link(href: str) -> bool:
    """True solo per le pagine dei singoli spettacoli: /events/<slug>/."""
    full = urljoin(BASE_URL, href)
    if not full.startswith(BASE_URL):
        return False
    path = full[len(BASE_URL):].split("?")[0].split("#")[0]
    return bool(_EVENT_PATH_RE.match(path))


def _date_near(node) -> datetime | None:
    """Cerca una data italiana nel testo dell'antenato più vicino."""
    cur = node
    for _ in range(4):  # risali max 4 livelli
        if cur is None:
            break
        text = cur.get_text(" ", strip=True)
        if _DATE_RE.search(text):
            dt = parse_italian_datetime(text, default_year=FESTIVAL_YEAR)
            if dt is not None:
                return dt
        cur = cur.parent
    return None


def fetch() -> list[Event]:
    session = new_session()
    resp = http_get(LIST_URL, session=session)
    soup = BeautifulSoup(resp.text, "html.parser")

    events: list[Event] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _is_detail_link(href):
            continue
        title = a.get_text(" ", strip=True)
        if len(title) < 4:
            continue
        full = urljoin(BASE_URL, href)
        if full in seen:
            continue

        # Prima prova a trovare la data vicino al link nella pagina programma.
        start = _date_near(a)

        # Se non c'è, apri la pagina di dettaglio e cerca lì.
        if start is None:
            try:
                d = http_get(full, session=session)
                dsoup = BeautifulSoup(d.text, "html.parser")
                body = dsoup.get_text(" ", strip=True)
                start = parse_italian_datetime(body, default_year=FESTIVAL_YEAR)
            except Exception:
                start = None
        if start is None:
            continue

        seen.add(full)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=full,
            venue="Stazione Leopolda, Firenze",
            category=CATEGORY,
        ))

    return events
