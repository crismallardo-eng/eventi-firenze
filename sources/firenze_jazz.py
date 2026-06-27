"""Firenze Jazz Festival — festival jazz diffuso (settembre).

La 10ª edizione (2026) si tiene a settembre in oltre 10 location tra Oltrarno
e ville storiche, a cura di Musicus Concentus. Jazz, elettronica, world music,
reggae, hip hop.

Fonte STATICA scaffold: al momento della scrittura il cartellone completo non
è ancora uscito (annuncio previsto per il 9 luglio 2026). Sono confermati la
finestra del festival e i nomi del Main Stage, ma non tutte le date per
artista. Si riempie UPCOMING quando esce il programma ufficiale.

Nota: il festival è organizzato da Musicus Concentus (sources.musicus_concentus);
quando quel sito ripubblicherà gli eventi, parte del cartellone potrebbe
arrivare anche da lì. Tenere d'occhio possibili duplicati.

Stagionale in scripts/health_check.py (UPCOMING vuoto = nessun allarme).
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
# Main Stage confermato; date per-artista da completare col programma ufficiale.
UPCOMING: list[tuple[int, int, int, int, str, str | None]] = [
    (9, 11, 21, 0, "DJ Gruff – O tutto o niente", None),
    (9, 11, 21, 0, "Alborosie & Shengen Clan", None),
    # Da aggiungere col cartellone completo (9 luglio): Altea, Casino Royale,
    # C'mon Tigre, Meraz, Pellegrino, Teho Teardo & Blixa Bargeld, …
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
