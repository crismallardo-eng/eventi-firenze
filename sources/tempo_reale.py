"""Tempo Reale — centro per la musica contemporanea (Villa Strozzi, Firenze).

Strategia: la home espone link alle rassegne in corso, in particolare
"Suoni e Musica di Ricerca a Firenze | <stagione>". Quella pagina
contiene il calendario stagionale dei concerti in formato testuale:

    "Domenica 17 maggio, Frittelli Arte Contemporanea, ore 20.30 e ore 21.30
     ELLIOTT SHARP | SOLO + STRATEGIES FOR IMPROVISATION"

Estraiamo: data + venue + orario + titolo da ogni blocco prosa.
Skip degli eventi fuori Firenze (in rare occasioni la rassegna li include).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Tempo Reale"
CATEGORY = "Concerti"
BASE_URL = "https://temporeale.it"
HOME_URL = f"{BASE_URL}/"

REQUEST_TIMEOUT = 15

# "Lunedì 8 giugno" / "Domenica 17 maggio 2026" / "Venerdì 5 giugno"
_WEEKDAYS = (
    r"luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|sabato|domenica"
)
_MONTHS_ALT = "|".join(sorted(ITALIAN_MONTHS.keys(), key=len, reverse=True))
_DATE_HEADER_RE = re.compile(
    rf"({_WEEKDAYS})\s+(\d{{1,2}})\s+({_MONTHS_ALT})(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"ore\s+(\d{1,2})[.:](\d{2})|ore\s+(\d{1,2})\b", re.IGNORECASE)

OUT_OF_FLORENCE = re.compile(
    r"\b(cracovia|torino|bologna|ravenna|roma|milano|pistoia|pisa|venezia|"
    r"berlin|paris|london|wien|new\s+york|tokyo|madrid)\b",
    re.IGNORECASE,
)


def _find_rassegna_urls(home_html: str) -> list[str]:
    soup = BeautifulSoup(home_html, "html.parser")
    urls = set()
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if "/rassegne/suoni-e-musica-di-ricerca-a-firenze" in h.lower():
            urls.add(h)
    return sorted(urls)


def _infer_year(today: date, day: int, month: int) -> int:
    candidate = date(today.year, month, day)
    if (today - candidate).days > 30:
        return today.year + 1
    return today.year


def _parse_rassegna(url: str) -> list[Event]:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    content_el = soup.find(class_=re.compile(r"entry-content|post-content"))
    if content_el is None:
        return []
    text = content_el.get_text(" ", strip=True)

    today = datetime.now(tz=ROME).date()

    # Trova tutti i bookmark "Weekday D mese (Y)?" e fai segmenti tra uno e l'altro
    matches = list(_DATE_HEADER_RE.finditer(text))
    events: list[Event] = []
    for i, m in enumerate(matches):
        day = int(m.group(2))
        month_name = m.group(3).lower()
        month = ITALIAN_MONTHS.get(month_name)
        if month is None:
            continue
        year = int(m.group(4)) if m.group(4) else _infer_year(today, day, month)
        try:
            d = date(year, month, day)
        except ValueError:
            continue

        # Blocco di testo: da fine match a inizio successivo (o fine testo)
        start_offset = m.end()
        end_offset = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start_offset:end_offset]

        # Salta blocchi fuori Firenze
        if OUT_OF_FLORENCE.search(chunk):
            continue

        # Estrai PRIMA ora (se ce ne sono due, "ore 20.30 e ore 21.30",
        # prendiamo la prima — l'altra è dello stesso evento o di un evento
        # successivo strettamente connesso).
        tmatch = _TIME_RE.search(chunk)
        t: time | None = None
        if tmatch:
            h = int(tmatch.group(1) or tmatch.group(3))
            mm = int(tmatch.group(2) or 0)
            try:
                t = time(h, mm)
            except ValueError:
                t = None

        # Estrai titolo: prima riga in MAIUSCOLO dopo la data/venue/ora.
        # Pattern tipico: ", VENUE, ore HH.MM TITOLO IN CAPS..."
        # Cerco una sequenza di parole in maiuscolo separate da spazi.
        title_match = re.search(
            r"[A-ZÀ-Ý][A-ZÀ-Ý0-9' \-–|/&,.]{8,}",
            chunk,
        )
        if not title_match:
            continue
        title = title_match.group(0).strip(" -–,")
        # Pulisce code: tronca a 100 char e taglia su spazio
        if len(title) > 100:
            title = title[:100].rsplit(" ", 1)[0]
        # Rimuove eventuale lettera singola finale (leftover dell'inizio della
        # descrizione successiva, es. "...DEI DISCHI L" ← "Letture...").
        title = re.sub(r"\s+[A-Z]$", "", title).rstrip(" ,-–|")

        # Venue: testo prima della parola "ore" (se presente), altrimenti
        # prima del titolo.
        venue: str | None = None
        venue_end = tmatch.start() if tmatch else title_match.start()
        venue_chunk = chunk[:venue_end].strip(" ,")
        if venue_chunk:
            # Prendi solo il primo segmento ragionevole (fino a virgola/newline)
            v = re.split(r"\s*,\s*", venue_chunk)[0].strip()
            if 3 <= len(v) <= 80:
                venue = v

        start = datetime.combine(d, t or time(0, 0), tzinfo=ROME)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue=venue or "Tempo Reale, Firenze",
            category=CATEGORY,
        ))
    return events


def fetch() -> list[Event]:
    try:
        resp = http_get(HOME_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []
    rassegna_urls = _find_rassegna_urls(resp.text)

    events: list[Event] = []
    for url in rassegna_urls:
        events.extend(_parse_rassegna(url))

    # Dedup per (titolo, inizio)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
