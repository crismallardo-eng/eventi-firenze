"""Firenze Rocks — grande festival rock estivo (Visarno Arena, Cascine).

Il sito firenzerocks.it pubblica date e lineup come IMMAGINI
(lineup-desktop.png), non come testo: niente da scrappare automaticamente.
Come Pistoia Blues, è una fonte "statica": inserisco a mano le date dei
concerti quando la lineup 2026 viene annunciata.

Quando escono date+artisti, aggiungere tuple a UPCOMING. Finché la lista è
vuota lo scraper restituisce 0 eventi (gestito come fonte stagionale in
scripts/health_check.py, così non genera falsi allarmi).
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Firenze Rocks"
CATEGORY = "Concerti"
VENUE = "Visarno Arena, Firenze"
BASE_URL = "https://www.firenzerocks.it"

# (start_datetime, titolo/headliner, descrizione_opzionale)
UPCOMING: list[tuple[datetime, str, str | None]] = [
    # Esempio (da riempire quando esce la lineup 2026):
    # (datetime(2026, 6, 12, 19, 0, tzinfo=ROME), "Headliner X", "con support A, B"),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for start, title, description in UPCOMING:
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=BASE_URL,
            venue=VENUE,
            description=description,
            category=CATEGORY,
        ))
    return out
