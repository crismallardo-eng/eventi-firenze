"""Fabbrica Europa — festival internazionale delle arti performative a Firenze.

Festival autunnale (settembre–ottobre): danza, teatro, musica, performance in
diverse sedi cittadine (Teatro Cantiere Florida, Teatro Puccini, Teatro della
Pergola, Stazione Leopolda, ...).

STRUTTURA DEL SITO (verificata scaricando le pagine dal runner CI, vedi
scripts/dump_page.py — il dominio è irraggiungibile dall'ambiente di sviluppo).

La pagina /fabbrica-europa-2026/ elenca i link ai singoli spettacoli, che
vivono sotto /events/<slug>/. Le edizioni passate stanno invece sotto
/fabbrica-europa-<anno>/ e non vanno raccolte.

Ogni pagina spettacolo espone, in righe di testo consecutive:

    Motus                                  <- artista/compagnia
    FRANKENSTEIN (HISTORY OF HATE)         <- titolo dello spettacolo
    30 Settembre 2026 21:00                <- data e ora di inizio
    Teatro Cantiere Florida di Firenze | IT <- sede
    nell'ambito del festival Fabbrica Europa 2026

Il parsing si aggancia alla riga data+ora (formato rigido e inequivocabile) e
legge le righe adiacenti: titolo e artista sopra, sede sotto. Questo evita sia
gli orari fittizi a mezzanotte sia una sede hard-coded uguale per tutti.

L'anno è nell'URL: per l'edizione 2027 cambiare FESTIVAL_YEAR.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get, new_session
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Fabbrica Europa"
CATEGORY = "Teatro"
BASE_URL = "https://fabbricaeuropa.net"
FESTIVAL_YEAR = 2026
LIST_URL = f"{BASE_URL}/fabbrica-europa-{FESTIVAL_YEAR}/"

PARALLEL_WORKERS = 6
REQUEST_TIMEOUT = 20

# Solo i permalink degli spettacoli: /events/<slug>/. Esclude da sé l'indice
# /events/ e le pagine archivio delle edizioni passate.
_EVENT_PATH_RE = re.compile(r"^/events/[^/]+/?$")

# "30 Settembre 2026 21:00" — riga compatta con data e ora.
_DATETIME_LINE_RE = re.compile(
    r"^(\d{1,2})\s+([A-Za-zàèéìòù]+)\s+(\d{4})\s+(\d{1,2}):(\d{2})$"
)
# La sede è seguita dal codice paese: "Teatro Puccini di Firenze | IT".
_COUNTRY_SUFFIX_RE = re.compile(r"\s*\|\s*[A-Z]{2}\s*$")

# Voci del menu di navigazione, da non scambiare per nomi di artisti.
_NAV_WORDS = {
    "eng", "ita", "home", "festival", "fondazione", "progetti", "produzioni",
    "calendario", "news", "contatti", "sostienici", "newsletter",
    "privacy policy",
}


def _is_nav(line: str) -> bool:
    low = line.strip().lower()
    return (
        low in _NAV_WORDS
        or low.startswith("festival 2")
        or low.startswith("archivio festival")
    )


def _detail_links(soup) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(BASE_URL, a["href"].strip())
        if not full.startswith(BASE_URL):
            continue
        path = full[len(BASE_URL):].split("?")[0].split("#")[0]
        if not _EVENT_PATH_RE.match(path):
            continue
        full = BASE_URL + path
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def _event_from_page(url: str, session) -> Event | None:
    try:
        resp = http_get(url, session=session, timeout=REQUEST_TIMEOUT)
    except Exception:  # noqa: BLE001
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]

    for i, line in enumerate(lines):
        m = _DATETIME_LINE_RE.match(line.strip())
        if not m:
            continue
        day, month_name, year, hour, minute = m.groups()
        month = ITALIAN_MONTHS.get(month_name.lower())
        if month is None:
            continue
        try:
            start = datetime(
                int(year), month, int(day), int(hour), int(minute), tzinfo=ROME
            )
        except ValueError:
            continue

        # Titolo: riga sopra la data. Artista/compagnia: quella ancora sopra,
        # se non è una voce di menu.
        title = lines[i - 1].strip() if i >= 1 else ""
        if not title or _is_nav(title):
            return None
        artist = lines[i - 2].strip() if i >= 2 else ""
        if artist and not _is_nav(artist) and artist.lower() != title.lower():
            title = f"{artist} — {title}"

        # Sede: riga sotto la data, senza il suffisso "| IT".
        venue = None
        if i + 1 < len(lines):
            candidate = _COUNTRY_SUFFIX_RE.sub("", lines[i + 1].strip())
            if candidate and not _is_nav(candidate) and len(candidate) < 120:
                venue = candidate

        # Descrizione: prima riga di prosa dopo l'intestazione.
        description = None
        for later in lines[i + 2: i + 8]:
            t = later.strip()
            if len(t) > 80 and not t.lower().startswith("nell"):
                description = t[:277] + "…" if len(t) > 280 else t
                break

        return Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue=venue,
            description=description,
            category=CATEGORY,
        )
    return None


def fetch() -> list[Event]:
    session = new_session()
    resp = http_get(LIST_URL, session=session, timeout=REQUEST_TIMEOUT)
    links = _detail_links(BeautifulSoup(resp.text, "html.parser"))
    if not links:
        raise RuntimeError(
            f"Nessun link /events/<slug>/ trovato su {LIST_URL} — "
            "la pagina programma ha probabilmente cambiato struttura."
        )

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_event_from_page, u, session) for u in links]
        for fut in as_completed(futures):
            try:
                ev = fut.result()
            except Exception:  # noqa: BLE001
                continue
            if ev is not None:
                events.append(ev)
    return events
