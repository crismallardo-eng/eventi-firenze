"""Firenze Jazz Festival — festival jazz diffuso (settembre).

La 10ª edizione (2026) si tiene a settembre in oltre 10 location tra Oltrarno
e ville storiche, a cura di Musicus Concentus. Jazz, elettronica, world music,
reggae, hip hop.

Fonte STATICA: il Main Stage (11-13 settembre) è confermato col programma
per serata. Il cartellone completo "diffuso" (19 concerti in 10+ location,
con orari e sedi) viene annunciato il 9 luglio 2026: a quel punto si potranno
arricchire le voci (orari/sedi) e aggiungere i concerti minori. Gli orari qui
sotto sono provvisori (default serale) finché non escono quelli ufficiali.

Nota: il festival è organizzato da Musicus Concentus (sources.musicus_concentus);
quando quel sito ripubblicherà gli eventi, parte del cartellone potrebbe
arrivare anche da lì. Tenere d'occhio possibili duplicati.

Stagionale in scripts/health_check.py.
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Firenze Jazz Festival"
CATEGORY = "Concerti"
VENUE = "Firenze (varie sedi)"
URL = "https://www.firenzejazzfestival.it/"
EDITION_YEAR = 2026

# (mese, giorno, ora, minuto, titolo, luogo_opzionale)
# Main Stage confermato dal sito ufficiale; orari provvisori (default serale).
UPCOMING: list[tuple[int, int, int, int, str, str | None]] = [
    (9, 11, 21, 0, "Alborosie & Shengen Clan", None),
    (9, 11, 22, 30, "DJ Gruff – O tutto o niente", None),
    (9, 12, 21, 0, "Casino Royale – Sempre più Vicini Reloaded", None),
    (9, 12, 22, 0, "Altea", None),
    (9, 12, 22, 30, "Pellegrino – Dance Rituals", None),
    (9, 13, 21, 0, "C'mon Tigre – Lumina", None),
    (9, 13, 21, 30, "Teho Teardo & Blixa Bargeld", None),
    (9, 13, 22, 0, "Meraz", None),
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
            venue=venue or VENUE,
            category=CATEGORY,
        ))
    return out
