"""Biblioteche comunali fiorentine — eventi via scraping per giorno.

The Drupal page at /eventi-biblioteche/YYYY-MM-DD exposes the schedule for
a single day. We walk a 30-day window from today and fetch each day in
parallel. This covers all comune libraries (Oblate, BiblioteCaNova, Thouar,
Mario Luzi, Villa Bandini, Palagio di Parte Guelfa, etc.).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get, new_session

SOURCE_NAME = "Biblioteche Comunali"
CATEGORY = "Biblioteche"
BASE_URL = "https://cultura.comune.fi.it"
DAY_URL = f"{BASE_URL}/eventi-biblioteche/{{date}}"

DAYS_AHEAD = 30
# Lower parallelism: hitting a Drupal site behind a WAF with many
# concurrent connections from the same IP increases 403s. 3 is gentle
# enough to avoid rate-limit triggers and still fast.
PARALLEL_WORKERS = 3

_TIME_RE = re.compile(r"(\d{1,2})\s*:\s*(\d{2})")


def _parse_time(text: str) -> time | None:
    m = _TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def _events_for_day(
    d: date,
    *,
    session=None,
    raise_on_error: bool = False,
) -> list[Event]:
    url = DAY_URL.format(date=d.isoformat())
    # Set Referer to the site root so each per-day request looks like
    # navigation from the previous page (anti-bot friendlier).
    headers = {"Referer": BASE_URL + "/"}
    try:
        response = http_get(url, session=session, headers=headers)
    except Exception:
        if raise_on_error:
            raise
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    out: list[Event] = []
    for item in soup.select("div.timeline-item"):
        title_link = item.select_one("div.timeline-event-title a")
        if title_link is None:
            continue
        title = title_link.get_text(" ", strip=True)
        href = title_link.get("href", "").strip()
        if not href:
            continue
        event_url = urljoin(BASE_URL, href)

        # Hour/minute span: "Ore: 09 :00" (with weird whitespace from layout).
        time_el = item.select_one("div.timeline-event")
        t = _parse_time(time_el.get_text(" ", strip=True)) if time_el else None
        start = datetime.combine(d, t or time(0, 0), tzinfo=ROME)

        venue_el = item.select_one("div.timeline-event-location a")
        venue = venue_el.get_text(strip=True) if venue_el else None

        desc_el = item.select_one("div.timeline-event-attendee")
        description = desc_el.get_text(" ", strip=True) if desc_el else None
        if description and len(description) > 280:
            description = description[:277] + "…"

        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=event_url,
            venue=venue,
            description=description,
        ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    # A shared Session keeps cookies (PHPSESSID, WAF challenge tokens,
    # etc.) across requests — needed because the day pages reject
    # cold-start clients.
    session = new_session()
    # Warm the session with a hit to the site root so cookies are set
    # before we start hitting deeper URLs.
    try:
        http_get(BASE_URL + "/", session=session)
    except Exception:
        # Continue anyway: the per-day fetch will surface the real error.
        pass

    # Probe today synchronously so a site-wide failure (403/5xx/timeout)
    # surfaces as an error on the page instead of silently dropping all
    # library events.
    events: list[Event] = list(
        _events_for_day(today, session=session, raise_on_error=True)
    )

    remaining = [today + timedelta(days=i) for i in range(1, DAYS_AHEAD)]
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = {ex.submit(_events_for_day, d, session=session): d for d in remaining}
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue
    return events
