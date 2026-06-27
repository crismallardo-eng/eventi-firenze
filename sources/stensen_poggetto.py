"""Esterno Notte al Poggetto — arena cinema estiva della FLOG (giu → set).

Arena all'aperto della FLOG al Poggetto (Rifredi), film a bordo piscina, con
programmazione curata dalla Fondazione Stensen. Il programma è un articolo su
stensen.org con la stessa struttura della Manifattura: usa il parser condiviso
sources.stensen_arena.

Fonte STAGIONALE: fuori stagione l'articolo dell'anno può non esistere ancora.
"""
from __future__ import annotations

from sources.base import Event
from sources.arena_program import fetch_program

SOURCE_NAME = "Esterno Notte Poggetto"
CATEGORY = "Cinema"
VENUE = "Arena FLOG, Poggetto, Firenze"
PROGRAM_URL = "https://stensen.org/attivita/flog-arena-estiva-2026/"


def fetch() -> list[Event]:
    return fetch_program(PROGRAM_URL, SOURCE_NAME, VENUE)
