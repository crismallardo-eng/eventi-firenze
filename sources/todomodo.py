"""Todo Modo — libreria internazionale indipendente di Firenze (via dei Fossi).

Source manuale: Todo Modo pubblica gli eventi via newsletter settimanale
("Piccolo Sabato") ma sul sito Shopify compaiono solo le prime 3-4 edizioni
dell'anno, poi smettono di pubblicarle. Quindi non c'è un endpoint web
affidabile da cui scrappare.

Ogni settimana copio a mano gli eventi datati dalla newsletter ricevuta
via email. Quando questi eventi passano lo scraper restituisce
automaticamente lista vuota (run.py filtra per data >= oggi). Aggiornare
i contenuti di ``UPCOMING`` quando arriva la newsletter nuova.

Fonte: newsletter del 1 giugno 2026 ("Anno V Numero XX").
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Todo Modo"
CATEGORY = "Altro"
VENUE = "Todo Modo, Firenze"
BASE_URL = "https://todomodo.org"


# Lista degli eventi datati estratti dall'ultima newsletter.
# Formato: (start_datetime, title, description, venue_override).
UPCOMING: list[tuple[datetime, str, str | None, str | None]] = [
    (
        datetime(2026, 6, 4, 19, 0, tzinfo=ROME),
        "Edison Square Garden — MaidireMAIKE",
        "Prima serata del mini festival nel festival con MaidireMAIKE, "
        "beatmaker e produttore di chill & type beats della crew Florence "
        "Lo-Fi Sunset. Al Bar Crodino rinfrescanti ghiacciati e un alcolico.",
        "Bar Crodino, Piazza Edison",
    ),
    (
        datetime(2026, 6, 6, 11, 0, tzinfo=ROME),
        "Il Caffè — prima lezione (Andrea Batacchi)",
        "Primo dei quattro incontri sul mondo del caffè (specialty, moka, "
        "filtro, degustazione) tenuti dal campione italiano Andrea Batacchi. "
        "Su prenotazione: caffe@todomodo.org. Al Bar Crodino caffè.",
        "Bar Crodino, Piazza Edison",
    ),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for start, title, description, venue in UPCOMING:
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=BASE_URL,
            venue=venue or VENUE,
            description=description,
            category=CATEGORY,
        ))
    return out
