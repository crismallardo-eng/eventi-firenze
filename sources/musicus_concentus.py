"""Musicus Concentus — events from their public iCal feed."""
from __future__ import annotations

from datetime import datetime, date, time

from icalendar import Calendar

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Musicus Concentus"
CATEGORY = "Concerti"
ICAL_URL = "https://www.musicusconcentus.com/events/?ical=1"


def _to_datetime(value) -> datetime:
    """Normalize an iCal DTSTART/DTEND into a tz-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=ROME)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tzinfo=ROME)
    raise TypeError(f"Unexpected DTSTART type: {type(value)!r}")


def fetch() -> list[Event]:
    response = http_get(ICAL_URL)
    cal = Calendar.from_ical(response.content)

    events: list[Event] = []
    for component in cal.walk("VEVENT"):
        title = str(component.get("SUMMARY") or "").strip()
        if not title:
            continue

        start_raw = component.get("DTSTART")
        if start_raw is None:
            continue
        start = _to_datetime(start_raw.dt)

        end = None
        end_raw = component.get("DTEND")
        if end_raw is not None:
            end = _to_datetime(end_raw.dt)

        url = str(component.get("URL") or "").strip()
        venue = str(component.get("LOCATION") or "").strip() or None
        description = str(component.get("DESCRIPTION") or "").strip() or None
        if description and len(description) > 280:
            description = description[:277] + "…"

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            end=end,
            url=url,
            venue=venue,
            description=description,
        ))

    return events
