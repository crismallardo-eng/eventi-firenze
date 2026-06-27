"""Festival au Désert Firenze — world music sahariana/mediterranea (luglio).

Edizione fiorentina del festival nato in Mali, al Parco delle Cascine (spazi
PARC e Ultravox · Prato della Tinaia). Tre serate a luglio, ingresso libero,
a cura di Fabbrica Europa.

Fonte STATICA: poche date, lineup annunciata in anticipo (parte ancora da
confermare). Si aggiorna a ogni edizione. Stagionale in health_check.py.
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Festival au Désert"
CATEGORY = "Concerti"
URL = "https://fabbricaeuropa.net/festival-au-desert-2026/"
EDITION_YEAR = 2026

# (mese, giorno, ora, minuto, titolo, luogo)
UPCOMING: list[tuple[int, int, int, int, str, str]] = [
    (7, 3, 19, 0, "Ressacs, une histoire tuareg – proiezione", "PARC, Cascine, Firenze"),
    (7, 8, 21, 30, "Festival au Désert – serata (programma da confermare)", "Ultravox, Cascine, Firenze"),
    (7, 9, 21, 30, "Alessio Bondì · Kader Tarhanine · Savāna Funk", "Ultravox, Cascine, Firenze"),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for month, day, hh, mm, title, venue in UPCOMING:
        try:
            start = datetime(EDITION_YEAR, month, day, hh, mm, tzinfo=ROME)
        except ValueError:
            continue
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=URL,
            venue=venue,
            category=CATEGORY,
        ))
    return out
