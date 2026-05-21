"""Pistoia Blues Festival — concerti estivi in Piazza del Duomo a Pistoia.

La pagina /biglietti/ espone tutte le date del festival con struttura HTML
pulita (article.show):

    <article class="show ...">
      <h3 class="date">
        <span class="dateDay">sabato</span>
        <span class="dateDaynum">4</span>
        <span class="dateMonth">luglio</span>
        <span class="dateY">2026</span>
      </h3>
      <div class="single-luogo">
        <p>Piazza del Duomo – Mainstage | ore <span class="orario">20.30</span></p>
      </div>
      <h2 class="entry-title programmaArtist">FANTASTIC NEGRITO<br/>ERIC STECKEL</h2>
      ...
    </article>
"""
from __future__ import annotations

import re
from datetime import datetime, time

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Pistoia Blues"
CATEGORY = "Concerti"
BASE_URL = "https://pistoiablues.com"
TICKETS_URL = f"{BASE_URL}/biglietti/"
REQUEST_TIMEOUT = 15

_TIME_RE = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")


def fetch() -> list[Event]:
    try:
        resp = http_get(TICKETS_URL, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[Event] = []
    for art in soup.find_all("article", class_="show"):
        # Data
        h3 = art.find("h3", class_="date")
        if not h3:
            continue
        day_el = h3.find("span", class_="dateDaynum")
        month_el = h3.find("span", class_="dateMonth")
        year_el = h3.find("span", class_="dateY")
        if not (day_el and month_el and year_el):
            continue
        try:
            day = int(day_el.get_text(strip=True))
            month = ITALIAN_MONTHS.get(month_el.get_text(strip=True).lower())
            year = int(year_el.get_text(strip=True))
        except ValueError:
            continue
        if month is None:
            continue

        # Orario
        orario_el = art.find("span", class_="orario")
        t: time | None = None
        if orario_el:
            m = _TIME_RE.search(orario_el.get_text())
            if m:
                try:
                    t = time(int(m.group(1)), int(m.group(2)))
                except ValueError:
                    t = None

        # Venue (testo prima di "| ore")
        venue: str | None = None
        luogo_el = art.find(class_="single-luogo")
        if luogo_el:
            venue_text = luogo_el.get_text(" ", strip=True)
            venue = re.split(r"\|\s*ore", venue_text)[0].strip() or None

        # Titolo: artisti separati da <br>. L'HTML del sito è a tratti
        # mal-formato (es. tag `</br>` di chiusura invalido) quindi usiamo
        # `separator=" + "` che concatena i text-node tra gli elementi.
        title_el = art.find("h2", class_="entry-title")
        if not title_el:
            continue
        title = title_el.get_text(separator=" + ", strip=True)
        # Compatta separatori multipli ed estremi
        title = re.sub(r"\s*\+\s*(?:\+\s*)+", " + ", title)
        title = re.sub(r"\s+", " ", title).strip(" +")
        if not title:
            continue

        try:
            start = datetime(year, month, day, tzinfo=ROME)
        except ValueError:
            continue
        if t:
            start = start.replace(hour=t.hour, minute=t.minute)

        # URL: la pagina dell'articolo (id="post-NNNN")
        # ma la pagina biglietti non linka al singolo show; uso TICKETS_URL.
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=TICKETS_URL,
            venue=venue or "Piazza del Duomo, Pistoia",
            category=CATEGORY,
        ))

    # Dedup
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in out:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
