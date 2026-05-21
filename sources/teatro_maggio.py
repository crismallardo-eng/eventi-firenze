"""Teatro del Maggio Musicale Fiorentino — calendario opera, concerti, balletto.

URL pattern:
    https://www.maggiofiorentino.com/calendario                — mese corrente
    https://www.maggiofiorentino.com/calendario/{YYYY}/{MM}    — mese specifico

Struttura card (10 eventi per pagina mese):
    <a class="block" href="/events/SLUG" aria-label="TITOLO alle HH:MM di Day, DD Month YYYY">
        <span style="color:..."><Concerti|Opera|Maggio aperto></span>
        <span class="font-bold">DD Month</span> Day-of-week
        <span class="font-bold">HH:MM</span> Venue
        <div class="event-excerpt">
            <h4>Compositore</h4>
            <h2>Titolo</h2>
            <p>...</p>
        </div>
    </a>

La data viene parsata dall'aria-label (formato inglese).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Teatro del Maggio"
CATEGORY = "Concerti"
BASE_URL = "https://www.maggiofiorentino.com"
MONTHS_AHEAD = 3  # mese corrente + 2 successivi

# Mapping mesi inglesi
ENG_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10,
    "November": 11, "December": 12,
}

# "alle HH:MM di DAY, DD Month YYYY"
_ARIA_RE = re.compile(
    r"alle\s+(\d{1,2}):(\d{2})\s+di\s+\w+,\s+(\d{1,2})\s+(\w+)\s+(\d{4})",
    re.IGNORECASE,
)


def _parse_aria_label(label: str) -> datetime | None:
    m = _ARIA_RE.search(label)
    if not m:
        return None
    hour, minute, day, month_name, year = m.groups()
    month = ENG_MONTHS.get(month_name.capitalize())
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), int(hour), int(minute), tzinfo=ROME)
    except ValueError:
        return None


def _events_for_month(year: int, month: int) -> list[Event]:
    url = f"{BASE_URL}/calendario/{year}/{month:02d}"
    try:
        resp = http_get(url, timeout=15)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[Event] = []
    for a in soup.find_all("a", class_="block"):
        if not a.find("div", class_="event-excerpt"):
            continue
        aria = a.get("aria-label", "")
        start = _parse_aria_label(aria)
        if start is None:
            continue

        href = a.get("href", "").strip()
        url_event = urljoin(BASE_URL, href) if href else BASE_URL

        excerpt = a.find("div", class_="event-excerpt")
        h2 = excerpt.find("h2") if excerpt else None
        title = h2.get_text(" ", strip=True) if h2 else None
        if not title:
            continue

        h4 = excerpt.find("h4") if excerpt else None
        composer = h4.get_text(" ", strip=True) if h4 else None

        # Venue: nello span "HH:MM <Venue>" sotto la data
        venue: str | None = None
        # cerca il primo div con font-size-small che contiene HH:MM e venue
        for d in a.find_all("div", class_="font-size-small"):
            text = d.get_text(" ", strip=True)
            mm = re.match(r"\d{1,2}:\d{2}\s+(.+)", text)
            if mm:
                venue = mm.group(1).strip()
                break

        # Categoria visiva (Concerti/Opera/Maggio aperto): la mostriamo come tag
        cat_span = a.find("span", class_="font-bold")
        # ma in realtà ci sono diversi font-bold. Cerco lo span colorato.
        tag_text: str | None = None
        colored = a.find("span", style=re.compile(r"color:"))
        if colored:
            tag_text = colored.get_text(strip=True) or None

        # Descrizione: compositore + tag opera/concerto se utile
        desc_parts = []
        if tag_text:
            desc_parts.append(tag_text)
        if composer:
            desc_parts.append(composer)
        description = " · ".join(desc_parts) if desc_parts else None

        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url_event,
            venue=venue or "Teatro del Maggio",
            description=description,
            category=CATEGORY,
        ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    events: list[Event] = []
    seen: set[tuple] = set()

    y, m = today.year, today.month
    for _ in range(MONTHS_AHEAD):
        for ev in _events_for_month(y, m):
            key = (ev.title, ev.start)
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)
        # avanza al mese successivo
        m += 1
        if m > 12:
            m = 1
            y += 1
    return events
