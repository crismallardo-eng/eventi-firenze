"""Lumen — Laboratorio Urbano Mensola (via del Guarlone, Firenze).

Lumen è uno spazio culturale del quartiere Mensola. La sua programmazione
2026 ricade dentro la rassegna "Urban Pulse" dell'Estate Fiorentina ma
non viene esposta come calendario strutturato:

  • lumen.fi.it/programma → descrizioni generiche per giorno della settimana
  • il programma mensile è un'immagine grafica (non OCR-abile)
  • i singoli concerti sono annunciati via Instagram/Facebook (no API)

L'unica fonte testuale ricca è l'articolo del Comune sul progetto:
  https://cultura.comune.fi.it/dalle-redazioni/urban-pulse
che elenca i nomi degli artisti con le date. Questi sono ricopiati a
mano qui sotto; quando il calendario viene aggiornato (es. l'articolo
estende le date d'autunno) basta aggiornare ``UPCOMING``.
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Lumen"
CATEGORY = "Concerti"
VENUE = "Lumen, via del Guarlone, Firenze"
BASE_URL = "https://lumen.fi.it"
# Pagina del Comune da cui sono stati estratti gli eventi (uso come URL
# di riferimento per ogni evento).
SOURCE_PAGE = "https://cultura.comune.fi.it/dalle-redazioni/urban-pulse"


# Lista degli eventi estratti dall'articolo "Urban Pulse" (Comune di Firenze,
# pubblicato il 3 giugno 2026). Formato:
#   (start_datetime, title, description)
# L'orario è 21:00 per i concerti serali per i quali non è specificata l'ora
# nella fonte (convenzione interna). 18:00 è invece esplicito per LAN.
UPCOMING: list[tuple[datetime, str, str | None]] = [
    (
        datetime(2026, 6, 5, 18, 0, tzinfo=ROME),
        "LAN — Esa's Afro-Synth Band (Live)",
        "Local Alliance Network · Giorno 1. Esa Williams presenta l'album "
        "Dala What We Must, progetto transcontinentale; a seguire dancefloor "
        "con i dj di Introspettiva, Autentica e Dissidanza.",
    ),
    (
        datetime(2026, 6, 6, 18, 0, tzinfo=ROME),
        "LAN — Mc Yallah & Debmaster (Live) + talk Esa Williams",
        "Local Alliance Network · Giorno 2. Talk e proiezione documentario di "
        "Esa Williams, poi live di Mc Yallah (UG/KE) con Debmaster, infine "
        "clubbing con Introspettiva, Autentica e Dissidanza.",
    ),
    (
        datetime(2026, 6, 7, 21, 0, tzinfo=ROME),
        "Francesco Farfa con Eteria",
        "Icona del clubbing italiano in dj set con il collettivo Eteria.",
    ),
    (
        datetime(2026, 6, 12, 21, 0, tzinfo=ROME),
        "Super Jet Kinoko (Osaka)",
        "Garage psichedelico giapponese da Osaka.",
    ),
    (
        datetime(2026, 6, 19, 21, 0, tzinfo=ROME),
        "Dengue Dengue Dengue + Isidora",
        "Duo elettronico peruviano insieme al collettivo fiorentino Isidora.",
    ),
    (
        datetime(2026, 6, 20, 21, 0, tzinfo=ROME),
        "Lattex con Fabrizio Mammarella",
        "Notte Lattex con ospite Fabrizio Mammarella (Periodica Records).",
    ),
    (
        datetime(2026, 6, 21, 21, 0, tzinfo=ROME),
        "Saturnia",
        "Serata curata dal collettivo Saturnia.",
    ),
    (
        datetime(2026, 7, 1, 21, 0, tzinfo=ROME),
        "Bassolino",
        "Concerto del produttore napoletano Dario Bassolino.",
    ),
    (
        datetime(2026, 7, 3, 21, 0, tzinfo=ROME),
        "Numa Crew",
        "Notte curata dalla Numa Crew, sound system fiorentino di lunga data.",
    ),
    (
        datetime(2026, 7, 5, 21, 0, tzinfo=ROME),
        "Francesco Farfa con Eteria",
        "Seconda data della rassegna Eteria con Francesco Farfa.",
    ),
    (
        datetime(2026, 7, 11, 21, 0, tzinfo=ROME),
        "Lattex",
        "Seconda notte Lattex della stagione.",
    ),
    (
        datetime(2026, 7, 12, 21, 0, tzinfo=ROME),
        "Cisco (Modena City Ramblers)",
        "Concerto di Cisco Bellotti, storica voce dei Modena City Ramblers.",
    ),
    (
        datetime(2026, 8, 28, 19, 0, tzinfo=ROME),
        "Lasciati Fiorire Festival — giorno 1",
        "Prima giornata del festival Lasciati Fiorire (28-30 agosto).",
    ),
    (
        datetime(2026, 8, 29, 19, 0, tzinfo=ROME),
        "Lasciati Fiorire Festival — giorno 2",
        "Seconda giornata del festival Lasciati Fiorire.",
    ),
    (
        datetime(2026, 8, 30, 19, 0, tzinfo=ROME),
        "Lasciati Fiorire Festival — giorno 3",
        "Terza giornata del festival Lasciati Fiorire.",
    ),
    (
        datetime(2026, 8, 31, 19, 0, tzinfo=ROME),
        "Copula Mundi — apertura",
        "Apertura del festival Copula Mundi (31 agosto – 6 settembre).",
    ),
    (
        datetime(2026, 9, 6, 19, 0, tzinfo=ROME),
        "Copula Mundi — chiusura",
        "Ultima giornata del festival Copula Mundi.",
    ),
    (
        datetime(2026, 9, 27, 21, 0, tzinfo=ROME),
        "Francesco Farfa con Eteria",
        "Terza data della rassegna Eteria (chiusura stagione).",
    ),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for start, title, description in UPCOMING:
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=SOURCE_PAGE,
            venue=VENUE,
            description=description,
            category=CATEGORY,
        ))
    return out
