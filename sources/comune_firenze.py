"""Comune di Firenze — eventi via scraping della pagina Drupal con paginazione.

Cards expose date split into <span class="card-year">, "card-date", "card-month".
Time of day is only on the detail page, so we keep date-only here (renders as
"all day" in the output, which is fine for civic events that often span hours).
"""
from __future__ import annotations

from datetime import datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS, parse_italian_date_range

SOURCE_NAME = "Comune di Firenze"
CATEGORY = "Civici"
BASE_URL = "https://www.comune.firenze.it"
LIST_URL = f"{BASE_URL}/vivere-il-comune/eventi"

# Drupal lists are paginated 0-indexed; we walk a small number of pages, which
# already covers the next ~3 months of events.
MAX_PAGES = 5


def _parse_card(card) -> Event | None:
    title_link = card.select_one("h3.card-title a")
    if title_link is None:
        return None
    title = title_link.get_text(strip=True)
    href = title_link.get("href", "").strip()
    if not href:
        return None
    url = urljoin(BASE_URL, href)

    year_span = card.select_one("span.card-year")
    date_span = card.select_one("span.card-date")
    month_span = card.select_one("span.card-month")
    if not (year_span and date_span and month_span):
        return None
    try:
        year = int(year_span.get_text(strip=True))
        day = int(date_span.get_text(strip=True))
    except ValueError:
        return None
    month_text = month_span.get_text(strip=True).lower().rstrip(".")
    month = ITALIAN_MONTHS.get(month_text)
    if month is None:
        return None

    try:
        start = datetime(year, month, day, tzinfo=ROME)
    except ValueError:
        return None

    category_el = card.select_one("span.category")
    tags = [category_el.get_text(strip=True)] if category_el else []

    desc_el = card.select_one("div.field--name-field-descrizione-breve")
    description = desc_el.get_text(" ", strip=True) if desc_el else None

    # Evento "spalmato" su più giorni ("dal X al Y"): imposta la fine così
    # resta visibile per tutto l'arco e non solo il giorno d'inizio.
    end: datetime | None = None
    _, e_range = parse_italian_date_range(
        f"{title}. {description or ''}", default_year=year
    )
    if e_range is not None:
        end_dt = datetime.combine(e_range, time(23, 59), tzinfo=ROME)
        if end_dt > start:
            end = end_dt

    if description and len(description) > 280:
        description = description[:277] + "…"

    return Event(
        source=SOURCE_NAME,
        title=title,
        start=start,
        end=end,
        url=url,
        description=description,
        tags=tags,
    )


def fetch() -> list[Event]:
    events: list[Event] = []
    seen_urls: set[str] = set()

    for page in range(MAX_PAGES):
        url = LIST_URL if page == 0 else f"{LIST_URL}?page={page}"
        try:
            response = http_get(url)
        except Exception:
            break

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("div.card-wrapper")
        if not cards:
            break

        page_events = 0
        for card in cards:
            event = _parse_card(card)
            if event is None:
                continue
            if event.url in seen_urls:
                continue
            seen_urls.add(event.url)
            events.append(event)
            page_events += 1

        # If a page returned nothing new, no point in continuing.
        if page_events == 0:
            break

    return events
