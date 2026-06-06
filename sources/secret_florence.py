"""Secret Florence — rassegna estiva multidisciplinare (musica, cinema, danza,
performing arts) in luoghi inediti di Firenze.

Sito WordPress + Elementor. La pagina /programma-{anno}/ elenca gli eventi
come sequenza di heading (.elementor-heading-title) in quest'ordine:

    h4  "9 giugno"                          → data
    h3  "LO SCHERMO DELL'ARTE / CINEMA"     → curatore / disciplina
    h4  "Cinema La Compagnia"               → luogo
    h4  "▸ H 21:00"                         → orario (può essere multiplo)

Non c'è un markup semantico per-evento, quindi si cammina la sequenza di
heading e si raggruppa: ogni h4-data apre un nuovo evento.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Secret Florence"
CATEGORY = "Concerti"  # default; sovrascritto per-evento dalla disciplina
BASE_URL = "https://www.secretflorence.it"
REQUEST_TIMEOUT = 15

# Disciplina (parte dopo "/" nel titolo h3) → categoria del nostro feed.
_DISCIPLINE_CAT = {
    "CINEMA": "Cinema",
    "MUSICA": "Concerti",
    "DANZA": "Teatro",
    "PERFORMING ARTS": "Teatro",
    "PERFOMING ARTS": "Teatro",
}

_DATE_RE = re.compile(
    r"^\s*(\d{1,2})\s+(" + "|".join(ITALIAN_MONTHS.keys()) + r")\s*$", re.IGNORECASE
)
_TIME_RE = re.compile(r"(\d{1,2})[.:](\d{2})")
_YEAR_RE = re.compile(r"(20\d\d)")


def _infer_year(soup: BeautifulSoup, today: date) -> int:
    h1 = soup.find("h1", class_="elementor-heading-title")
    if h1:
        m = _YEAR_RE.search(h1.get_text())
        if m:
            return int(m.group(1))
    return today.year


def _emit(cur: dict, year: int) -> Event | None:
    if not cur.get("date") or not cur.get("title"):
        return None
    day, month = cur["date"]
    t = cur.get("time") or time(0, 0)
    try:
        start = datetime(year, month, day, t.hour, t.minute, tzinfo=ROME)
    except ValueError:
        return None
    return Event(
        source=SOURCE_NAME,
        title=cur["title"],
        start=start,
        url=cur.get("url") or f"{BASE_URL}/programma-{year}/",
        venue=cur.get("venue"),
        description=cur.get("discipline"),
        category=cur.get("category") or CATEGORY,
    )


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    # Prova l'anno corrente, poi quello successivo (a fine anno il programma
    # nuovo può uscire prima che cambi l'anno solare).
    soup = None
    page_url = None
    for year_try in (today.year, today.year + 1):
        url = f"{BASE_URL}/programma-{year_try}/"
        try:
            resp = http_get(url, timeout=REQUEST_TIMEOUT)
        except Exception:
            continue
        cand = BeautifulSoup(resp.text, "html.parser")
        # Valida che la pagina contenga davvero un programma con date.
        heads = cand.find_all(class_="elementor-heading-title")
        if any(_DATE_RE.match(h.get_text(" ", strip=True)) for h in heads):
            soup = cand
            page_url = url
            break
    if soup is None:
        return []

    year = _infer_year(soup, today)
    heads = soup.find_all(class_="elementor-heading-title")

    events: list[Event] = []
    cur: dict = {}
    for h in heads:
        text = h.get_text(" ", strip=True)
        if not text:
            continue
        tag = h.name

        m_date = _DATE_RE.match(text)
        if m_date:
            # Nuova data: emetti l'evento precedente e ricomincia.
            ev = _emit(cur, year)
            if ev:
                events.append(ev)
            month = ITALIAN_MONTHS.get(m_date.group(2).lower())
            cur = {"date": (int(m_date.group(1)), month), "url": page_url}
            continue

        if not cur.get("date"):
            continue  # heading prima del primo evento (titoli pagina, range)

        if tag == "h3":
            # Titolo + disciplina ("LO SCHERMO DELL'ARTE / CINEMA").
            if cur.get("title"):
                continue
            if text.upper() in ("PROGRAMMA",):
                continue
            parts = [p.strip() for p in text.split("/")]
            cur["title"] = parts[0].title() if parts[0].isupper() else parts[0]
            if len(parts) > 1:
                disc = parts[-1].strip().upper()
                cur["discipline"] = parts[-1].strip().title()
                cur["category"] = _DISCIPLINE_CAT.get(disc)
            continue

        # h4 non-data: o l'orario (▸ H ...) o il luogo.
        if "▸" in text or text.upper().startswith("H ") or _TIME_RE.search(text):
            if cur.get("time") is None:
                mt = _TIME_RE.search(text)
                if mt:
                    try:
                        cur["time"] = time(int(mt.group(1)), int(mt.group(2)))
                    except ValueError:
                        pass
            # se non c'è orario ma c'è il luogo già, ignora
            if not cur.get("venue") and "▸" not in text and not text.upper().startswith("H "):
                cur["venue"] = text
        else:
            if not cur.get("venue"):
                cur["venue"] = text

    ev = _emit(cur, year)
    if ev:
        events.append(ev)

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
