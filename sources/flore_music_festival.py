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


def _find_card(heading):
    """Risale dagli antenati di un heading fino a trovare la card:
    il primo container con data+ora+una sola heading dentro."""
    node = heading.parent
    while node is not None and node.name not in ("body", "html"):
        text = node.get_text(" ", strip=True)
        if _DATE_RE.search(text) and _TIME_RE.search(text):
            # Una sola heading dentro = è UNA card, non un wrapper di più card.
            if len(node.find_all(["h1", "h2", "h3", "h4"])) == 1:
                return node
            return None
        node = node.parent
    return None


def _parse_ewpe_card(card) -> Event | None:
    """Parser dedicato alle card del widget Elementor `ewpe-*` usato da Flore.

    Le card del programma hanno una struttura precisa che possiamo leggere
    senza euristiche, evitando di catturare sezioni laterali della pagina
    (es. la sezione 'biblioteche per bambini' che combacia con l'euristica
    data+ora ma non sono concerti del festival).

    Struttura:
        .ewpe-ev-day            "05"          giorno
        .ewpe-ev-mo             "Giu"         mese (italiano abbreviato)
        .ewpe-ev-yr             "20:30"       (sic) il widget mette qui l'orario
        .ewpe-event-title       "TITOLO | Artista"
        .ewpe-event-venue-details "Chiesa di X, Firenze"
        .ewpe-evt-category      "Concerti in Divenire 2026"
    """
    day_el = card.find(class_="ewpe-ev-day")
    mo_el = card.find(class_="ewpe-ev-mo")
    yr_el = card.find(class_="ewpe-ev-yr")
    title_el = card.find(class_="ewpe-event-title")
    venue_el = card.find(class_="ewpe-event-venue-details")
    cat_el = card.find(class_="ewpe-evt-category")
    if not (day_el and mo_el and title_el):
        return None

    try:
        day = int(day_el.get_text(strip=True))
    except ValueError:
        return None
    month_name = mo_el.get_text(strip=True).lower().rstrip(".")
    month = ITALIAN_MONTHS.get(month_name)
    if month is None:
        return None

    hour, minute = 20, 30
    if yr_el:
        tm = _TIME_RE.search(yr_el.get_text())
        if tm:
            h, m = int(tm.group(1)), int(tm.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59:
                hour, minute = h, m

    try:
        start = datetime(FESTIVAL_YEAR, month, day, hour, minute, tzinfo=ROME)
    except ValueError:
        return None

    title = title_el.get_text(" ", strip=True)
    if not title:
        return None
    venue = venue_el.get_text(" ", strip=True) if venue_el else None
    description = cat_el.get_text(" ", strip=True) if cat_el else None
    url = _pick_detail_url(card) or LIST_URL

    return Event(
        source=SOURCE_NAME,
        title=title,
        start=start,
        url=url,
        venue=venue,
        description=description,
    )


def fetch() -> list[Event]:
    session = new_session()
    response = http_get(LIST_URL, session=session)
    soup = BeautifulSoup(response.text, "html.parser")

    events: list[Event] = []
    seen_cards: set[int] = set()
    seen_keys: set[str] = set()

    # 1) Strada primaria: card Elementor con classi ewpe-* — selettori
    #    precisi che catturano SOLO i concerti del festival.
    for card in soup.find_all("div", class_="ewpe-inner-wrapper"):
        ev = _parse_ewpe_card(card)
        if ev is None:
            continue
        if id(card) in seen_cards:
            continue
        seen_cards.add(id(card))
        key = f"{ev.url}|{ev.start.isoformat()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        events.append(ev)

    if events:
        return events

    # 2) Fallback euristico: se il widget cambia struttura o si rompe,
    #    cerchiamo qualsiasi heading + container col pattern data+ora.
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        title = h.get_text(" ", strip=True)
        if len(title) < 4:
            continue
        card = _find_card(h)
        if card is None:
            continue
        if id(card) in seen_cards:
            continue
        seen_cards.add(id(card))

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
            hcand, mcand = int(tm.group(1)), int(tm.group(2))
            if 0 <= hcand <= 23 and 0 <= mcand <= 59:
                hour, minute = hcand, mcand

        try:
            start = datetime(FESTIVAL_YEAR, month, day, hour, minute, tzinfo=ROME)
        except ValueError:
            continue

        url = _pick_detail_url(card) or LIST_URL
        key = f"{url}|{start.isoformat()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

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
