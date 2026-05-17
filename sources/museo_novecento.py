"""Museo Novecento — mostre via WP REST + ACF date fields.

The custom post type `mostre` exposes ACF fields with ISO dates:
    acf.data_inizio_mostra = "YYYY-MM-DD"
    acf.data_fine_mostra   = "YYYY-MM-DD"

For exhibits already running, we surface them with start = today so they
appear in the current view rather than at their original opening date.
"""
from __future__ import annotations

from datetime import date, datetime
from html import unescape

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Museo Novecento"
CATEGORY = "Mostre"
LIST_API = "https://www.museonovecento.it/wp-json/wp/v2/mostre?per_page=50"


def _parse_iso(text: str) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch() -> list[Event]:
    response = http_get(LIST_API, headers={"Accept": "application/json"})
    items = response.json()
    today = datetime.now(tz=ROME).date()

    events: list[Event] = []
    for item in items:
        title = unescape((item.get("title") or {}).get("rendered", "")).strip()
        link = item.get("link", "").strip()
        if not title or not link:
            continue

        acf = item.get("acf") or {}
        if not isinstance(acf, dict):
            continue
        start_d = _parse_iso(acf.get("data_inizio_mostra", ""))
        end_d = _parse_iso(acf.get("data_fine_mostra", ""))
        if start_d is None:
            continue

        # Drop exhibits that already ended
        if end_d and end_d < today:
            continue

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=datetime.combine(start_d, datetime.min.time(), tzinfo=ROME),
            end=datetime.combine(end_d, datetime.min.time(), tzinfo=ROME) if end_d else None,
            url=link,
            venue="Museo Novecento",
        ))
    return events
