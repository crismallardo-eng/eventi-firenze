"""Flore Music Festival — concerti dalla pagina programma annuale.

La pagina /concerti-flore-festival-2026/ elenca tutti i concerti del festival
come card con: data ("05 Giugno"), ora ("20:30"), venue ("Chiesa di X, Firenze"),
titolo e link alla pagina dedicata. L'anno è hard-codato nell'URL della pagina
e va aggiornato manualmente ogni edizione (es. quando esce il programma 2027,
cambiare LIST_URL e FESTIVAL_YEAR).
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get, new_session
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Flore Music Festival"
CATEGORY = "Concerti"
BASE_URL = "https://www.floremusicfestival.it"
FESTIVAL_YEAR = 2026
LIST_URL = f"{BASE_URL}/concerti-flore-festival-{FESTIVAL_YEAR}/"

_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|"
    r"luglio|agosto|settembre|ottobre|novembre|dicembre)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_VENUE_HINT_RE = re.compile(
    r"^(Chiesa|Fondazione|Teatro|Palazzo|Museo|Villa|Auditorium|Sala|Basilica|Cattedrale)\b",
    re.IGNORECASE,
)


def _pick_detail_url(card) -> str | None:
    """Pick the most plausible internal link to the event detail page."""
    for a in card.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue
        low = href.lower()
        if any(s in low for s in (
            "eventbrite", "facebook", "twitter", "linkedin",
            "instagram", "whatsapp", "mailto:", "tel:",
        )):
            continue
        full = urljoin(BASE_URL, href)
        if "floremusicfestival.it" not in full:
            continue
        # Skip the list page itself (cards may contain a "back to list" link).
        if full.rstrip("/") == LIST_URL.rstrip("/"):
            continue
        return full
    return None


def _pick_title(card) -> str | None:
    for tag in ("h2", "h3", "h4", "h1"):
        el = card.find(tag)
        if el:
            t = el.get_text(" ", strip=True)
            if len(t) > 3:
                return t
    return None


def _pick_venue(card) -> str | None:
    """Heuristic: a short line that looks like an address ending in 'Firenze'."""
    # 1. Lines starting with a venue keyword (Chiesa, Fondazione, ...)
    for s in card.stripped_strings:
        if _VENUE_HINT_RE.match(s) and 5 < len(s) < 150:
            return s
    # 2. Any short line ending with ", Firenze"
    for s in card.stripped_strings:
        if s.endswith(", Firenze") and 5 < len(s) < 150:
            return s
    return None


def _pick_description(card, title: str, venue: str | None) -> str | None:
    """A paragraph that is neither the title nor the venue, of reasonable length."""
    for p in card.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t or t == title or (venue and t == venue):
            continue
        if 30 <= len(t) <= 400 and "Firenze" not in t[-15:]:
            if len(t) > 280:
                t = t[:277] + "…"
            return t
    return None


def fetch() -> list[Event]:
    session = new_session()
    response = http_get(LIST_URL, session=session)
    soup = BeautifulSoup(response.text, "html.parser")

    # Candidate cards: <article> first; if the theme uses divs, fall back to
    # common card class names used by Elementor / WP event themes.
    cards = list(soup.find_all("article"))
    if not cards:
        cards = list(soup.select(
            "[class*='event-card'], [class*='event-item'], [class*='ec-card'], "
            "[class*='post-item'], [class*='elementor-post'], [class*='tribe-events']"
        ))

    events: list[Event] = []
    seen: set[str] = set()

    for card in cards:
        text = card.get_text(" ", strip=True)
        date_m = _DATE_RE.search(text)
        if not date_m:
            continue
        day = int(date_m.group(1))
        month = ITALIAN_MONTHS.get(date_m.group(2).lower())
        if not month:
            continue

        hour, minute = 0, 0
        tm = _TIME_RE.search(text)
        if tm:
            h, mi = int(tm.group(1)), int(tm.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                hour, minute = h, mi

        try:
            start = datetime(FESTIVAL_YEAR, month, day, hour, minute, tzinfo=ROME)
        except ValueError:
            continue

        title = _pick_title(card)
        if not title:
            continue

        url = _pick_detail_url(card) or LIST_URL
        # De-dup by url+date (same concert can appear in multiple sections).
        key = f"{url}|{start.isoformat()}"
        if key in seen:
            continue
        seen.add(key)

        venue = _pick_venue(card)
        description = _pick_description(card, title, venue)

        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue=venue,
            description=description,
        ))

    return events
