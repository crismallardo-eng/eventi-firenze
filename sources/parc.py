"""PARC Firenze — calendario eventi via scraping della pagina categoria."""
from __future__ import annotations

from bs4 import BeautifulSoup

from sources.base import Event, http_get
from sources.italian_dates import parse_italian_datetime

SOURCE_NAME = "PARC Firenze"
CATEGORY = "Concerti"
URL = "https://parcfirenze.net/category/calendario/"


def fetch() -> list[Event]:
    response = http_get(URL)
    soup = BeautifulSoup(response.text, "html.parser")

    events: list[Event] = []
    for article in soup.find_all("article"):
        # PARC tags upcoming events with "prossimamente" in the class list.
        # Past articles still appear, so we filter on this.
        article_classes = article.get("class") or []
        if "prossimamente" not in article_classes:
            continue

        title_link = article.select_one("h2.entry-title a")
        if title_link is None:
            continue
        # Title can have <br> separating artist / project; use space-separated text.
        title = title_link.get_text(" ", strip=True)
        url = title_link.get("href", "").strip()

        date_span = article.select_one("span.entry-date")
        if date_span is None:
            continue
        date_text = date_span.get_text(" ", strip=True)
        start = parse_italian_datetime(date_text)
        if start is None:
            continue

        summary_p = article.select_one("div.entry-summary p")
        description = summary_p.get_text(" ", strip=True) if summary_p else None

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue="PARC, Firenze",
            description=description,
        ))

    return events
