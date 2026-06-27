"""Arena Chiardiluna — arena cinema storica dell'Oltrarno (giu → set).

L'arena estiva del Chiardiluna (via Monte Oliveto), una proiezione a sera.
La biglietteria gira su 18tickets, che rende il programma in HTML lato server:
ogni film è un blocco `.movie` con titolo, data ("DD/MM/YYYY"), orario e lingua.

Fonte STAGIONALE: d'inverno l'arena è chiusa e il sito non ha programma
(gestito in scripts/health_check.py per non generare falsi allarmi).
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Arena Chiardiluna"
CATEGORY = "Cinema"
VENUE = "Arena Chiardiluna, Firenze"
PROGRAM_URL = "https://chiardilunafirenze.18tickets.it/"

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
_VOS_RE = re.compile(r"original|sottotitol", re.IGNORECASE)


def fetch() -> list[Event]:
    try:
        resp = http_get(PROGRAM_URL, timeout=20)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    events: list[Event] = []
    seen: set[tuple] = set()

    for movie in soup.select(".movie"):
        title_el = movie.select_one(".movie__title")
        if title_el is None:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue
        # Titoli tutti maiuscoli sul sito: li rendo più leggibili.
        if title.isupper():
            title = title.title()

        sched = movie.select_one(".schedule-section-show, .occupations")
        sched_text = sched.get_text(" ", strip=True) if sched else ""
        dm = _DATE_RE.search(sched_text)
        if dm is None:
            continue
        day, month, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        tm = _TIME_RE.search(sched_text)
        hour, minute = (int(tm.group(1)), int(tm.group(2))) if tm else (21, 30)

        if _VOS_RE.search(movie.get_text(" ", strip=True)):
            title = f"{title} (VOS)"

        try:
            start = datetime(year, month, day, hour, minute, tzinfo=ROME)
        except ValueError:
            continue

        key = (title, start)
        if key in seen:
            continue
        seen.add(key)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=PROGRAM_URL,
            venue=VENUE,
            category=CATEGORY,
        ))

    events.sort(key=lambda e: e.start)
    return events
