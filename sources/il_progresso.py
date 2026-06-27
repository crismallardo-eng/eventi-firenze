"""Circolo Il Progresso — eventi via l'endpoint AJAX di EventON.

Il sito (WordPress + EventON) ha lo stesso identico meccanismo di Arci Firenze.
In passato si usava il REST /wp-json/wp/v2/ajde_events, che però ordina per
data di PUBBLICAZIONE: restituiva solo eventi già passati. Ora si interroga il
calendario EventON (mese corrente + successivo) tramite il parser condiviso
sources.eventon_calendar.
"""
from __future__ import annotations

from sources.base import Event
from sources.eventon_calendar import fetch_calendar

SOURCE_NAME = "Circolo Il Progresso"
CATEGORY = "Circoli"
BASE_URL = "https://www.circoloilprogresso.it"
PAGE_URL = f"{BASE_URL}/eventi/"
AJAX_URL = f"{BASE_URL}/?evo-ajax=eventon_get_events"
VENUE = "Circolo Il Progresso"


def fetch() -> list[Event]:
    return fetch_calendar(PAGE_URL, AJAX_URL, SOURCE_NAME, CATEGORY, default_venue=VENUE)
