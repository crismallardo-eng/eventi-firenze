"""Apriti Cinema — arena cinematografica gratuita in Piazza Pitti (giu → lug).

Arena all'aperto a ingresso libero in Piazza de' Pitti, a cura di Cinema La
Compagnia per l'Estate Fiorentina: una proiezione a sera, tutti i film in
versione originale sottotitolata. Il programma è un articolo su
cinemalacompagnia.it con la stessa struttura delle arene Stensen, quindi usa
il parser condiviso sources.arena_program (orario 21:45).

Fonte STAGIONALE: fuori stagione l'articolo del programma non esiste ancora.
"""
from __future__ import annotations

from datetime import time

from sources.base import Event
from sources.arena_program import fetch_program

SOURCE_NAME = "Apriti Cinema"
CATEGORY = "Cinema"
VENUE = "Piazza Pitti, Firenze"
PROGRAM_URL = "https://www.cinemalacompagnia.it/evento/apriti-cinema-2026-programma/"
SHOW_TIME = time(21, 45)


def fetch() -> list[Event]:
    return fetch_program(PROGRAM_URL, SOURCE_NAME, VENUE, show_time=SHOW_TIME)
