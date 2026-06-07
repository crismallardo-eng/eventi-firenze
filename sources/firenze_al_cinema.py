"""Firenze al Cinema — schedule scraper, focused on original-language films.

Each cinema in the circuit has a daily schedule page. We walk all cinemas for
the next 8 days (their visible window) in parallel and emit one event per
showtime. We keep only screenings that are in original language: anything at
"Original Sound" (the dedicated VO cinema) or any title tagged "(VOS)" / "(VO)"
at the other cinemas.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sources.base import DEFAULT_HEADERS, Event, ROME

SOURCE_NAME = "Firenze al Cinema"
CATEGORY = "Cinema"
BASE_URL = "https://firenzealcinema.info/2013/"

CINEMAS = {
    1: "Adriano",
    2: "Cabiria",
    4: "Fiamma",
    6: "Grotta",
    7: "Marconi",
    8: "Portico",
    10: "Principe",
    23: "Fiorella",
    25: "Original Sound",
    26: "La Compagnia",
    29: "Astra",
}
ORIGINAL_LANGUAGE_CINEMA_IDS = {25}  # Original Sound = always VO

DAYS_AHEAD = 7
PARALLEL_WORKERS = 10
REQUEST_TIMEOUT = 5  # risponde in ~1s quando è up; fallisce subito altrimenti

_VO_TAG_RE = re.compile(r"\((?:VOS?|V\.?O\.?S?\.?)\)", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(\d{1,2}),(\d{2})\b")


def _is_original_language(title: str, cinema_id: int) -> bool:
    if cinema_id in ORIGINAL_LANGUAGE_CINEMA_IDS:
        return True
    return bool(_VO_TAG_RE.search(title))


def _format_dmy(d: date) -> str:
    return d.strftime("%d%m%Y")


def _parse_times(cell_text: str) -> list[time]:
    times: list[time] = []
    for h, m in _TIME_RE.findall(cell_text):
        try:
            t = time(int(h), int(m))
        except ValueError:
            continue
        if t not in times:
            times.append(t)
    return times


def _events_for_cinema_day(cinema_id: int, cinema_name: str, d: date) -> list[Event]:
    url = f"{BASE_URL}?pag=orari&tipo=cine&day={_format_dmy(d)}&id={cinema_id}"
    try:
        # Nessun retry: il sito risponde subito o non risponde affatto.
        # http_get riproverebbe raddoppiando il tempo di fallimento.
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    out: list[Event] = []
    for row in soup.select("tr.show"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        title_link = cells[1].find("a", href=True)
        if title_link is None:
            continue
        title_span = title_link.find("span")
        title = (title_span.get_text(" ", strip=True)
                 if title_span else title_link.get_text(" ", strip=True))
        if not title:
            continue

        if not _is_original_language(title, cinema_id):
            continue

        times = _parse_times(cells[2].get_text(" ", strip=True))
        if not times:
            continue

        href = title_link.get("href", "").strip()
        scheda_url = urljoin(BASE_URL, href) if href else BASE_URL

        for t in times:
            start = datetime.combine(d, t, tzinfo=ROME)
            out.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=scheda_url,
                venue=f"Cinema {cinema_name}",
            ))
    return out


# Cinema presenti SOLO su firenzealcinema.info e non su MYmovies. Per tutti
# gli altri MYmovies è la fonte primaria (vedi fetch()): teniamo questi da
# firenzealcinema solo per non perdere copertura. "Original Sound" è IL cinema
# in lingua originale, quindi è importante non perderlo.
FIRENZEALCINEMA_ONLY = {"cabiria", "original sound"}


def _norm_title(t: str) -> str:
    return (t or "").lower().strip()


def _norm_venue(v: str | None) -> str:
    if not v:
        return ""
    s = v.lower().strip()
    if s.startswith("cinema "):
        s = s[len("cinema "):]
    return s


def _fetch_firenzealcinema() -> list[Event]:
    """Scrape grezzo di firenzealcinema.info (tutti i cinema del circuito)."""
    today = datetime.now(tz=ROME).date()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]

    jobs = [(cid, name, d) for cid, name in CINEMAS.items() for d in days]
    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_events_for_cinema_day, cid, name, d) for cid, name, d in jobs]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Dedup interno per (titolo, inizio, venue).
    seen = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


def fetch() -> list[Event]:
    """VOS combinati: MYmovies primario, firenzealcinema solo per i suoi cinema esclusivi.

    Storia del bug: firenzealcinema.info è spesso down o risponde con dati
    parziali, e per i cinema in comune (es. Grotta) usava un nome diverso
    ("Cinema Grotta" vs "Cinema Grotta, Sesto Fiorentino") e a volte orari
    diversi da MYmovies. Mergiando le due fonti nascevano doppioni con orari
    fantasma. Soluzione: una sola fonte per ciascun cinema.
      • MYmovies → fonte primaria (strutturata, orari affidabili, copre quasi
        tutti i cinema).
      • firenzealcinema → solo per i cinema che MYmovies non ha
        (FIRENZEALCINEMA_ONLY: Original Sound, Cabiria).
      • Se MYmovies è giù → fallback completo su firenzealcinema.
    """
    try:
        from sources.mymovies_cinema import fetch_vos
        mymovies_vos = fetch_vos()
    except Exception:
        mymovies_vos = []

    firenze = _fetch_firenzealcinema()

    if mymovies_vos:
        # Da firenzealcinema teniamo SOLO i cinema che MYmovies non copre,
        # così evitiamo doppioni e conflitti di orario sui cinema in comune.
        extra = [e for e in firenze if _norm_venue(e.venue) in FIRENZEALCINEMA_ONLY]
        combined = mymovies_vos + extra
    else:
        # MYmovies non ha restituito nulla: ripiego su tutto firenzealcinema.
        combined = firenze

    # Dedup finale per (titolo, inizio, venue normalizzato).
    seen_keys: set[tuple] = set()
    unique: list[Event] = []
    for ev in combined:
        key = (_norm_title(ev.title), ev.start, _norm_venue(ev.venue))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(ev)

    return _mark_vos(unique)


def _mark_vos(events: list[Event]) -> list[Event]:
    """Garantisce che ogni film di questa categoria mostri la dicitura (VOS).

    I VOS presi da firenzealcinema.info a volte hanno già "(VOS)" nel titolo,
    quelli da MYmovies (etichetta strutturata) no. Normalizziamo: togliamo
    eventuali varianti "(VO)/(V.O.S.)/(VOS)" e aggiungiamo un "(VOS)" pulito
    in coda, così l'utente riconosce sempre i film in lingua originale.
    """
    for e in events:
        base = _VO_TAG_RE.sub("", e.title).strip().rstrip("-–").strip()
        e.title = f"{base} (VOS)"
    return events
