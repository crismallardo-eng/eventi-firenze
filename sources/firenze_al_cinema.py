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


def fetch() -> list[Event]:
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

    # Deduplicate (some films can show under multiple cinemas at the same time
    # in the same showroom — keep one entry per (title, start, venue) combo).
    seen = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)

    # Integro SEMPRE i VOS da MYmovies sopra a quelli di firenzealcinema.info.
    # firenzealcinema.info include solo i film con (VOS) esplicitamente nel
    # titolo; molti cinema (es. La Compagnia) non lo taggano, ma su MYmovies
    # quegli stessi film hanno l'etichetta strutturata "Versione originale
    # con sottotitoli". Dedupplico con normalizzazione case-insensitive sul
    # titolo e venue (i due siti usano formati leggermente diversi).
    def _norm_title(t: str) -> str:
        return (t or "").lower().strip()
    def _norm_venue(v: str | None) -> str:
        if not v: return ""
        s = v.lower().strip()
        if s.startswith("cinema "):
            s = s[len("cinema "):]
        return s
    seen_keys = {(_norm_title(e.title), e.start, _norm_venue(e.venue)) for e in unique}
    try:
        from sources.mymovies_cinema import fetch_vos
        mymovies_vos = fetch_vos()
    except Exception:
        mymovies_vos = []
    for ev in mymovies_vos:
        key = (_norm_title(ev.title), ev.start, _norm_venue(ev.venue))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(ev)

    # Fallback storico: se davvero nessuna delle due fonti ha restituito
    # nulla (entrambi i siti down), esci con lista vuota.
    if not unique:
        try:
            from sources.mymovies_cinema import fetch_vos
            return fetch_vos()
        except Exception:
            return []

    return unique
