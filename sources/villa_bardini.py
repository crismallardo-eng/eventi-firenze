"""Villa Bardini — eventi via feed RSS WordPress.

The feed includes recent posts (mostly events but occasionally also news/recap
items). Dates are inside the content prose. Many entries omit the year; we use
the post's pubDate year as the inference fallback.
"""
from __future__ import annotations

from datetime import datetime

import feedparser
from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import parse_italian_datetime

SOURCE_NAME = "Villa Bardini"
CATEGORY = "Mostre"
FEED_URL = "https://www.villabardini.it/feed/"


def _content_text(entry) -> str:
    if entry.get("content"):
        html_text = entry.content[0].get("value", "")
    else:
        html_text = entry.get("summary", "")
    return BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)


def fetch() -> list[Event]:
    response = http_get(FEED_URL)
    parsed = feedparser.parse(response.content)

    events: list[Event] = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        text = _content_text(entry)

        # Use pubDate year as a hint when the body's date omits the year.
        default_year = None
        if entry.get("published_parsed"):
            default_year = entry.published_parsed.tm_year

        # Search title first (often "Twilight In The Round 16 settembre"),
        # then the content body.
        start = parse_italian_datetime(title, default_year=default_year)
        if start is None:
            start = parse_italian_datetime(text, default_year=default_year)
        if start is None:
            continue

        # Short description: first sentence of the cleaned body.
        description = text.split(".")[0][:280] if text else None

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue="Villa Bardini",
            description=description,
        ))

    return events
