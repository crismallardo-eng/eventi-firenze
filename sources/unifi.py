"""UniFi — eventi pubblici dell'Università (musei, Orto Botanico, conferenze).

Cards expose start / end dates in short Italian form ("15 Nov - 31 Mag")
without year. We handle three cases:
- Single date (start == end or end missing): use that date.
- Future range: use start date.
- Ongoing range (today is between start and end): place the event on today's
  date so the user sees "still open" exhibitions in the current view.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "UniFi"
CATEGORY = "Mostre"
BASE_URL = "https://www.unifi.it"
LIST_URL = f"{BASE_URL}/it/eventi"

_SHORT_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+([A-Za-zàèéìòù]+)\b"
)


def _parse_short(text: str, year: int) -> date | None:
    """Parse 'DD Mes' (Italian short month) with explicit year."""
    m = _SHORT_DATE_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = ITALIAN_MONTHS.get(m.group(2).lower().rstrip("."))
    if month is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_dates(
    inizio_text: str,
    fine_text: str,
    today: date,
) -> tuple[date | None, date | None]:
    """Pick year(s) so the resulting range is plausible and currently relevant."""
    if not inizio_text:
        return None, None
    if not fine_text:
        # Single-date event: prefer this year, roll to next year if too past.
        d = _parse_short(inizio_text, today.year)
        if d and (today - d).days > 10:
            d = _parse_short(inizio_text, today.year + 1)
        return d, None

    # Both dates: assume same year first
    inizio = _parse_short(inizio_text, today.year)
    fine = _parse_short(fine_text, today.year)
    if not (inizio and fine):
        return inizio, fine

    if fine < inizio:
        # Range crosses year boundary. Either inizio was last year or fine is next year.
        # Pick the option whose range covers "today" (current exhibit).
        inizio_last = _parse_short(inizio_text, today.year - 1)
        if inizio_last and inizio_last <= today <= fine:
            inizio = inizio_last
        else:
            fine_next = _parse_short(fine_text, today.year + 1)
            if fine_next:
                fine = fine_next

    # If both ended up in the past, try rolling forward (announced future exhibit).
    if fine < today - timedelta(days=10):
        next_inizio = _parse_short(inizio_text, today.year + 1)
        next_fine = _parse_short(fine_text, today.year + 1)
        if next_inizio and next_fine:
            inizio, fine = next_inizio, next_fine

    return inizio, fine


def fetch() -> list[Event]:
    response = http_get(LIST_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    today = datetime.now(tz=ROME).date()

    events: list[Event] = []
    for card in soup.select("div.evento-card"):
        title_link = card.select_one("div.evento-card__title a")
        if title_link is None:
            continue
        title = title_link.get_text(" ", strip=True)
        href = title_link.get("href", "").strip()
        if not href:
            continue
        url = urljoin(BASE_URL, href)

        inizio_el = card.select_one("div.evento-card__inizio")
        fine_el = card.select_one("div.evento-card__fine")
        inizio_text = inizio_el.get_text(" ", strip=True).rstrip("-").strip() if inizio_el else ""
        fine_text = fine_el.get_text(" ", strip=True) if fine_el else ""

        inizio, fine = _resolve_dates(inizio_text, fine_text, today)
        if inizio is None:
            continue

        # Drop events whose range has ended
        if fine and fine < today:
            continue

        venue_el = card.select_one("div.evento-card__luogo")
        venue = venue_el.get_text(" ", strip=True) if venue_el else None

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=datetime.combine(inizio, datetime.min.time(), tzinfo=ROME),
            end=datetime.combine(fine, datetime.min.time(), tzinfo=ROME) if fine else None,
            url=url,
            venue=venue,
        ))

    return events
