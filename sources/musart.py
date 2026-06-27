"""Musart Festival — grandi concerti estivi (giugno → luglio).

L'XI edizione (2026) si tiene nel Parco Mediceo di Pratolino (Vaglia, pochi km
a nord di Firenze), dopo gli anni in Piazza Santissima Annunziata. Pochi grandi
concerti, lineup annunciata in anticipo.

Fonte STATICA: la lineup è nota e fissa; si aggiorna UPCOMING e EDITION_YEAR
a ogni edizione. Gestita come stagionale in scripts/health_check.py.
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Musart Festival"
CATEGORY = "Concerti"
VENUE = "Parco Mediceo di Pratolino, Vaglia"
URL = "https://musartfestival.com/"
EDITION_YEAR = 2026

# (mese, giorno, ora, minuto, titolo)
UPCOMING: list[tuple[int, int, int, int, str]] = [
    (6, 28, 20, 30, "Ben Harper & The Innocent Criminals"),
    (7, 4, 21, 0, "Mannarino"),
    (7, 11, 21, 15, "Alfa"),
    (7, 21, 21, 15, "Elio e Le Storie Tese"),
    (7, 24, 21, 15, "Luca Carboni"),
    (7, 25, 21, 15, "Carmina Burana – Orchestra e Coro del Maggio Musicale"),
    (7, 26, 4, 45, "Vittorio Nocenzi – concerto all'alba"),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for month, day, hh, mm, title in UPCOMING:
        try:
            start = datetime(EDITION_YEAR, month, day, hh, mm, tzinfo=ROME)
        except ValueError:
            continue
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=URL,
            venue=VENUE,
            category=CATEGORY,
        ))
    return out
