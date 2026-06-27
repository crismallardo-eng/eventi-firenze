"""Estate Fiesolana — Teatro Romano di Fiesole (giugno → settembre).

Lo storico festival estivo (79ª edizione nel 2026) al Teatro Romano di Fiesole:
musica, teatro classico, danza e incontri, spalmati su tutta l'estate.

Fonte STATICA curata a mano: il programma è pubblicato come cartellone (non
come calendario strutturato facilmente scrapabile). Le date sono inserite a
mano a inizio stagione; ogni voce è (mese, giorno, ora, minuto, titolo,
categoria). Quando esce il cartellone dell'edizione successiva si aggiorna
UPCOMING e si cambia EDITION_YEAR.

Gestita come fonte stagionale in scripts/health_check.py (fuori stagione la
lista è vuota e non deve generare falsi allarmi).
"""
from __future__ import annotations

from datetime import datetime

from sources.base import Event, ROME

SOURCE_NAME = "Estate Fiesolana"
CATEGORY = "Concerti"  # default; ogni voce porta la sua categoria
VENUE = "Teatro Romano, Fiesole"
URL = "https://www.bitconcerti.it/estate-fiesolana-2026.html"
EDITION_YEAR = 2026

# (mese, giorno, ora, minuto, titolo, categoria)
UPCOMING: list[tuple[int, int, int, int, str, str]] = [
    (6, 9, 20, 30, "Kairòs", "Concerti"),
    (6, 10, 20, 30, "Kairòs", "Concerti"),
    (6, 17, 21, 15, "Motus Danza – @Solo", "Teatro"),
    (6, 19, 21, 15, "Francesca Mannocchi e Rodrigo D'Erasmo", "Concerti"),
    (6, 21, 21, 15, "Festa della Musica", "Concerti"),
    (6, 22, 21, 30, "Jazz Ensemble Cherubini", "Concerti"),
    (6, 23, 21, 15, "I Persiani di Eschilo", "Teatro"),
    (6, 25, 21, 15, "Il Mediterraneo in barca – Mino Manni", "Teatro"),
    (6, 26, 21, 15, "Cristiano De André", "Concerti"),
    (6, 28, 21, 15, "A new Sketches of Spain", "Concerti"),
    (6, 29, 21, 15, "E lasciatemi divertire – Maria Cassi", "Teatro"),
    (6, 30, 21, 30, "Fatoumata Diawara", "Concerti"),
    (7, 1, 21, 30, "Ensemble Scuola di Musica di Fiesole", "Concerti"),
    (7, 3, 21, 30, "Raphael Gualazzi", "Concerti"),
    (7, 5, 21, 15, "The Pilgrims Gospel Choir", "Concerti"),
    (7, 7, 21, 15, "Marilyn oltre il sorriso – Lyric Dance Company", "Teatro"),
    (7, 8, 21, 15, "Irene Grandi", "Concerti"),
    (7, 9, 21, 15, "Robinson – Roberto Alinghieri", "Teatro"),
    (7, 10, 21, 15, "Automobili e altre storie – Omaggio a Dalla e Roversi", "Concerti"),
    (7, 13, 21, 15, "Massimo Gramellini", "Teatro"),
    (7, 14, 21, 30, "Yellowjackets", "Concerti"),
    (7, 16, 21, 15, "Daniela Lucangeli", "Teatro"),
    (7, 17, 21, 30, "Ginevra Di Marco e Nada", "Concerti"),
    (7, 20, 21, 15, "Prometeo da Eschilo", "Teatro"),
    (7, 21, 21, 15, "Orchestra della Toscana", "Concerti"),
    (7, 22, 21, 15, "Le fatiche di Ercole – Alessandro Riccio", "Teatro"),
    (7, 23, 19, 15, "Oceano Okeanos – Simone Regazzoni", "Teatro"),
    (7, 23, 21, 15, "La palestra di Platone – Simone Regazzoni", "Teatro"),
    (7, 26, 21, 15, "Joan Thiele", "Concerti"),
    (7, 27, 21, 30, "Bobo Rondelli e Nico Gori Swing Tentet", "Concerti"),
    (7, 28, 21, 15, "Jannacci e Dintorni", "Concerti"),
    (7, 29, 21, 15, "Xavier Rudd", "Concerti"),
    (7, 30, 21, 15, "Ecuba – Arianna Scommegna", "Teatro"),
    (8, 3, 21, 15, "La vie en rose / Bolero – Balletto di Milano", "Teatro"),
    (8, 6, 21, 15, "La linea d'ombra – Pietro Grossi", "Teatro"),
    (9, 6, 21, 0, "Osvaldo Poli", "Teatro"),
    (9, 8, 21, 0, "Alla scoperta di Morricone", "Concerti"),
    (9, 9, 21, 0, "Massimo Recalcati", "Teatro"),
    (9, 11, 21, 0, "Voglio vederti danzare – Omaggio a Franco Battiato", "Concerti"),
]


def fetch() -> list[Event]:
    out: list[Event] = []
    for month, day, hh, mm, title, category in UPCOMING:
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
            category=category,
        ))
    return out
