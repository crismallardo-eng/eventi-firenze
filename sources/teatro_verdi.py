"""Teatro Verdi Firenze — cartellone spettacoli.

Sito WordPress: /programma/ elenca gli spettacoli, ogni dettaglio è su
/programma/{slug}/ e contiene tutte le date in formato italiano.

Detail page structure:
    h1                                        → titolo
    div.card-event_category                   → categoria (Pop-Rock-Jazz, Prosa, ...)
    div.event-dates-list_row.date-active
        span.date    "sabato 17 Ottobre"
        span.hour    "20:45"

L'anno NON è esplicito: viene dedotto come "anno corrente" se la data è
nei prossimi 11 mesi, "anno successivo" altrimenti (vedi italian_dates).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS, parse_italian_date

SOURCE_NAME = "Teatro Verdi"
CATEGORY = "Teatro"
BASE_URL = "https://www.teatroverdifirenze.it"
LIST_URL = f"{BASE_URL}/programma/"

PARALLEL_WORKERS = 6
REQUEST_TIMEOUT = 15

_HOUR_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _scrape_event(url: str) -> list[Event]:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    if not title:
        return []

    cat_el = soup.find(class_="card-event_category")
    sub_cat = cat_el.get_text(" ", strip=True) if cat_el else None

    # Le date dello show principale sono dentro div.date-hours-box.
    # Le card "event-dates-list" che stanno dentro div.card-event sono
    # invece spettacoli correlati ("altri eventi") e vanno ignorate.
    main_box = soup.find("div", class_="date-hours-box")
    if main_box is None:
        return []

    events: list[Event] = []
    for row in main_box.find_all("div", class_="event-dates-list_row"):
        if "date-active" not in row.get("class", []):
            continue
        date_span = row.find("span", class_="date")
        hour_span = row.find("span", class_="hour")
        if not (date_span and hour_span):
            continue

        # "sabato 17 Ottobre" → data
        d = parse_italian_date(date_span.get_text(" ", strip=True))
        if d is None:
            continue
        # "20:45" → ora
        hm = _HOUR_RE.search(hour_span.get_text())
        if not hm:
            continue
        try:
            t = time(int(hm.group(1)), int(hm.group(2)))
        except ValueError:
            continue

        start = datetime.combine(d, t, tzinfo=ROME)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue="Teatro Verdi",
            description=sub_cat,
            category=CATEGORY,
        ))
    return events


def fetch() -> list[Event]:
    try:
        resp = http_get(LIST_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    urls = sorted(set(re.findall(
        r'https://www\.teatroverdifirenze\.it/programma/[a-z0-9\-]+/',
        resp.text,
    )))
    if not urls:
        return []

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_scrape_event, u) for u in urls]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Dedup
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
