"""Arci Firenze — eventi dai circoli ARCI fiorentini (Vie Nuove, Quinto Basso, ecc.).

Arci Firenze federa decine di circoli che pubblicano i loro eventi sul portale
centralizzato arcifirenze.it (WordPress + EventON, protetto da Wordfence).

Si usa il parser condiviso sources.eventon_calendar: interroga l'endpoint AJAX
di EventON (mese corrente + successivo) invece del REST /wp-json, che ordinava
per data di pubblicazione e restituiva solo eventi passati — oltre a far
scattare Wordfence con ~100 fetch in parallelo.
"""
from __future__ import annotations

from sources.base import Event
from sources.eventon_calendar import fetch_calendar

SOURCE_NAME = "Arci Firenze"
CATEGORY = "Circoli"
BASE_URL = "https://www.arcifirenze.it"
PAGE_URL = f"{BASE_URL}/agenda/"
AJAX_URL = f"{BASE_URL}/?evo-ajax=eventon_get_events"


def fetch() -> list[Event]:
    return fetch_calendar(PAGE_URL, AJAX_URL, SOURCE_NAME, CATEGORY)
