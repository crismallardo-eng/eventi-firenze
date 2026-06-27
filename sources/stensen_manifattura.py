"""Stensen — arena cinema estiva in Manifattura Tabacchi (giu → set).

Una proiezione a sera all'aperto in Manifattura Tabacchi (B3 Motel Garden,
via Marie Curie). Il programma è un articolo redazionale su stensen.org,
aggiornato in due "tempi". Parsing e logica nel modulo condiviso
sources.stensen_arena.

Fonte STAGIONALE: fuori stagione l'articolo dell'anno può non esistere ancora
(gestito in scripts/health_check.py per non generare falsi allarmi).
"""
from __future__ import annotations

from sources.base import Event
from sources.arena_program import fetch_program

SOURCE_NAME = "Stensen Manifattura"
CATEGORY = "Cinema"
VENUE = "Manifattura Tabacchi, Firenze"
PROGRAM_URL = (
    "https://stensen.org/attivita/"
    "non-solo-cinema-in-manifattura-2026-il-programma/"
)


def fetch() -> list[Event]:
    return fetch_program(PROGRAM_URL, SOURCE_NAME, VENUE)
