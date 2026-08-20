"""Fabbrica Europa — festival internazionale delle arti performative a Firenze.

Festival primaverile (tipicamente maggio) alla Stazione Leopolda e altre sedi
fiorentine: danza, teatro, musica, performance.

NB: il sito NON è ispezionabile dall'ambiente di build (bloccato dal proxy
egress), quindi lo scraper usa un approccio EURISTICO generico anziché
selettori CSS precisi — lo stesso schema che ha funzionato per Flore:
  1. Scarica la pagina programma.
  2. Per ogni link interno che sembra puntare a uno spettacolo, cerca nel
     testo circostante (o nella pagina di dettaglio) una data italiana.
  3. Costruisce un Event con titolo = testo del link, data estratta.

L'anno è nell'URL: quando esce l'edizione 2027 cambiare FESTIVAL_YEAR/LIST_URL.
Se al primo run reale i selettori non intercettano nulla, va rifinito con uno
screenshot della struttura vera del sito.
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

# Un link di dettaglio spettacolo su WordPress ha di solito uno slug testuale
# sotto la home; escludiamo asset, social, categorie e pagine di servizio.
_SKIP_HREF = (
    "eventbrite", "facebook", "twitter", "linkedin", "instagram", "youtube",
    "whatsapp", "mailto:", "tel:", "wp-content", "wp-login", "/feed",
    "/category/", "/tag/", "/author/", ".jpg", ".png", ".pdf", "#",
)
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
    r"agosto|settembre|ottobre|novembre|dicembre)\b",
    re.IGNORECASE,
)


def _is_detail_link(href: str) -> bool:
    low = href.lower()
    if any(s in low for s in _SKIP_HREF):
        return False
    full = urljoin(BASE_URL, href)
    if BASE_URL not in full:
        return False
    if full.rstrip("/") == LIST_URL.rstrip("/"):
        return False
    # Deve avere uno slug non banale dopo il dominio.
    path = full.split(BASE_URL, 1)[-1].strip("/")
    return len(path) > 3


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
