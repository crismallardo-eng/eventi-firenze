"""Cinema non su MYmovies — via firenzealcinema.info.

Tre cinema fiorentini assenti da MYmovies vengono qui coperti:
  • Original Sound (id=25) — cinema interamente dedicato al VO
  • Cabiria        (id=2)  — piccola sala d'essai
  • Grotta         (id=6)  — cinema di quartiere a Sesto Fiorentino

Original Sound (id=25) è interamente VO: incluso tutto.
Cabiria e Grotta seguono la stessa logica del vecchio scraper:
solo i titoli con tag (VOS) / (VO) nel nome.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta

import requests
from bs4 import BeautifulSoup

from sources.base import DEFAULT_HEADERS, Event, ROME

SOURCE_NAME = "Cinema (altri)"
CATEGORY = "Cinema"
BASE_URL = "https://firenzealcinema.info/2013/"

CINEMAS: dict[int, str] = {
    25: "Original Sound",
    2:  "Cabiria",
    6:  "Grotta, Sesto Fiorentino",
}

DAYS_AHEAD = 7
PARALLEL_WORKERS = 7   # una richiesta per giorno in parallelo per cinema
REQUEST_TIMEOUT = 4    # risponde in ~1s quando è up; fallisce subito altrimenti

_TIME_RE = re.compile(r"\b(\d{1,2}),(\d{2})\b")  # formato "20,15" del sito
_VO_TAG_RE = re.compile(r"\((?:VOS?|V\.?O\.?S?\.?)\)", re.IGNORECASE)
ALWAYS_VO_IDS = {25}  # Original Sound: tutto in VO per definizione


def _format_dmy(d: date) -> str:
    return d.strftime("%d%m%Y")


def _events_for_cinema_day(cinema_id: int, cinema_name: str, d: date) -> list[Event]:
    url = f"{BASE_URL}?pag=orari&tipo=cine&day={_format_dmy(d)}&id={cinema_id}"
    try:
        # Nessun retry: il sito risponde subito o non risponde affatto.
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[Event] = []
    for row in soup.select("tr.show"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        title_link = cells[1].find("a", href=True)
        if title_link is None:
            continue
        span = title_link.find("span")
        title = (span.get_text(" ", strip=True)
                 if span else title_link.get_text(" ", strip=True))
        if not title:
            continue

        # Filtra per lingua: Original Sound sempre OK, gli altri solo se VOS
        if cinema_id not in ALWAYS_VO_IDS and not _VO_TAG_RE.search(title):
            continue

        href = title_link.get("href", "").strip()
        film_url = (BASE_URL.rstrip("/") + "/" + href.lstrip("/")
                    if href else BASE_URL)

        for h, m in _TIME_RE.findall(cells[2].get_text(" ", strip=True)):
            try:
                t = time(int(h), int(m))
            except ValueError:
                continue
            start = datetime.combine(d, t, tzinfo=ROME)
            out.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=film_url,
                venue=f"Cinema {cinema_name}",
                category=CATEGORY,
            ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]
    jobs = [(cid, name, d) for cid, name in CINEMAS.items() for d in days]

    events: list[Event] = []
    # Parallelismo per cinema (7 worker = 7 giorni in parallelo per volta),
    # timeout corto: se il sito è down ogni job fallisce in ~4s.
    # Worst case: ceil(21/7) × 4s = ~12s totali.
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_events_for_cinema_day, cid, name, d) for cid, name, d in jobs]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue
    return events
