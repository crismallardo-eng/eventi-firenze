"""Rassegne/festival estivi fiorentini "spalmati" su più giorni.

I portali del Comune (comune.firenze.it, cultura.comune.fi.it) annunciano questi
festival con UNA sola voce ("dal X al Y…") rimandando al sito ufficiale per il
programma. Qui trascriviamo il calendario completo giorno-per-giorno con orari,
così ogni singolo appuntamento compare nella sua data e non solo il primo giorno.

Fonte STATICA: i programmi sono fissi per la stagione. Si aggiorna UPCOMING e
EDITION_YEAR a ogni edizione. Stagionale in scripts/health_check.py.

Festival inclusi (2026):
  • Glass Sound Festival (il-trillo.com) — musica diffusa, 28/6–27/7
  • Cinema nel Chiostro (Sant'Orsola) — arena cinema, 29/6–6/9
  • Estate a San Salvi (Chille de la Balanza) — teatro, luglio
  • Ultracorpi Festival — performance/drag (solo date future)
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Rassegne estive"
CATEGORY = "Concerti"  # default; ogni voce porta la sua categoria
EDITION_YEAR = 2026

# (mese, giorno, ora, minuto, titolo, categoria, luogo, url)
_GLASS = "https://www.il-trillo.com/glass-sound-festival/"
_SANSALVI = "https://chille.it/"
_CHIOSTRO = "https://cultura.comune.fi.it/dalle-redazioni/cinema-nel-chiostro-5"
_ULTRA = "https://cultura.comune.fi.it/dalle-redazioni/ultracorpi-festival-2026"

UPCOMING: list[tuple[int, int, int, int, str, str, str, str]] = [
    # --- Glass Sound Festival (musica) ---
    (6, 28, 19, 30, "Glass Sound: Bassamusica", "Concerti", "Giardino dell'Orticoltura, Firenze", _GLASS),
    (6, 29, 21, 0, "Glass Sound: Nervi", "Concerti", "Ultravox, Firenze", _GLASS),
    (6, 30, 18, 0, "Glass Sound: Orchestra da Camera Il Trillo", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 2, 19, 0, "Glass Sound: Duo Giovannardi e Mellone", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 5, 19, 30, "Glass Sound: Orlando Cialli Middle-Eastern Trio", "Concerti", "Giardino dell'Orticoltura, Firenze", _GLASS),
    (7, 6, 17, 30, "Glass Sound: St. Helen's Girls School Choir", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 8, 17, 30, "Glass Sound: Duo Euterpe", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 9, 21, 0, "Glass Sound: Massimo Poggio & Quartetto d'archi Il Trillo", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 13, 21, 0, "Glass Sound: Stefano Cocco Cantini Trio", "Concerti", "Ultravox, Firenze", _GLASS),
    (7, 14, 17, 30, "Glass Sound: Arie d'opera – Ni Zhou", "Concerti", "Palazzo Medici Riccardi, Firenze", _GLASS),
    (7, 15, 19, 30, "Glass Sound: Petz Are Cool", "Concerti", "Area Pettini Burresi, Firenze", _GLASS),
    (7, 27, 19, 0, "Glass Sound: Engelholm Marching Band", "Concerti", "Giardino dell'Orticoltura, Firenze", _GLASS),

    # --- Cinema nel Chiostro (Sant'Orsola) — orario 21:30 ---
    (6, 30, 21, 30, "Sorry, Baby", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 3, 21, 30, "Persepolis", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 7, 21, 30, "La mia famiglia a Taipei", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 9, 21, 30, "Hamnet (VOS)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 10, 21, 30, "The Sea", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 14, 21, 30, "Antartica – Quasi una fiaba", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 16, 21, 30, "The Drama (VOS)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 17, 21, 30, "La torta del presidente", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 19, 21, 30, "Bianca (omaggio a Nanni Moretti)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 21, 21, 30, "Nino", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 23, 21, 30, "No Other Choice (VOS)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 24, 21, 30, "Divine Comedy", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 26, 21, 30, "La messa è finita (omaggio a Nanni Moretti)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 30, 21, 30, "I colori del tempo (VOS)", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),
    (7, 31, 21, 30, "Disunited Nations", "Cinema", "Chiostro di Sant'Orsola, Firenze", _CHIOSTRO),

    # --- Estate a San Salvi (Chille de la Balanza) — teatro ---
    (7, 3, 21, 0, "Visioni da Don Chisciotte", "Teatro", "San Salvi, Firenze", _SANSALVI),
    (7, 8, 21, 30, "Ecuba. La guerra sulle madri", "Teatro", "San Salvi, Firenze", _SANSALVI),
    (7, 14, 21, 30, "La Locandiera, lo Chef e gli altri", "Teatro", "San Salvi, Firenze", _SANSALVI),
    (7, 15, 21, 30, "La Locandiera, lo Chef e gli altri", "Teatro", "San Salvi, Firenze", _SANSALVI),
    (7, 16, 21, 30, "La Locandiera, lo Chef e gli altri", "Teatro", "San Salvi, Firenze", _SANSALVI),
    (7, 23, 21, 30, "Studio su Edipo", "Teatro", "San Salvi, Firenze", _SANSALVI),

    # --- Ultracorpi Festival (solo serate future) ---
    (6, 28, 21, 0, "Ultracorpi: Be Your Drag – apertura pubblica", "Teatro", "Circolo Vie Nuove, Firenze", _ULTRA),
    (7, 2, 21, 0, "Ultracorpi: A Drag Is Born", "Teatro", "Firenze", _ULTRA),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for month, day, hh, mm, title, category, venue, url in UPCOMING:
        try:
            start = datetime(EDITION_YEAR, month, day, hh, mm, tzinfo=ROME)
        except ValueError:
            continue
        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=url,
            venue=venue,
            category=category,
        ))
    return out
