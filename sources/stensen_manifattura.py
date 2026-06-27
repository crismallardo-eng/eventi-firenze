"""Stensen — arena cinema estiva in Manifattura Tabacchi.

La Fondazione Stensen gestisce d'estate un'arena cinematografica all'aperto
in Manifattura Tabacchi (B3 Motel Garden, via Marie Curie, Firenze): una
proiezione a sera, fine giugno → inizio settembre. Il programma è pubblicato
come UN articolo su stensen.org (testo redazionale, non un calendario
strutturato), aggiornato in due "tempi" (giugno-luglio, poi agosto-settembre).

PARSING dell'articolo — la struttura del testo è regolare:
    Martedì 23 giugno            ← intestazione giorno (weekday + giorno + mese)
    [Original sound]             ← marker opzionale: proiezione in lingua orig.
    Il Dio dell'amore            ← titolo film
    di Francesco Lagi (Italia 2026, 100')   ← riga "ancora": regista (Paese AAAA, durata')

Ogni film è ancorato dalla riga "di … (… AAAA, NN')". Il titolo è la riga
subito sopra. Le proiezioni si raggruppano per serata: si emette UN evento
per sera (il film principale = quello di durata maggiore), così l'arena
compare come un appuntamento giornaliero e non come decine di righe.

Orario: 21:30 (default arena). I film in "Original sound" prendono il suffisso
"(VOS)" nel titolo, come le altre fonti cinema.

Fonte STAGIONALE: fuori stagione l'articolo dell'anno può non esistere ancora
(gestito in scripts/health_check.py per non generare falsi allarmi).
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Stensen Manifattura"
CATEGORY = "Cinema"
VENUE = "Manifattura Tabacchi, Firenze"
PROGRAM_URL = (
    "https://stensen.org/attivita/"
    "non-solo-cinema-in-manifattura-2026-il-programma/"
)
SHOW_TIME = time(21, 30)  # orario standard dell'arena

_MONTHS = {"giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9}
_WEEKDAYS = r"(?:luned[ìi]|marted[ìi]|mercoled[ìi]|gioved[ìi]|venerd[ìi]|sabato|domenica)"
_DATE_RE = re.compile(
    rf"^{_WEEKDAYS}\s+(\d{{1,2}})\s+(giugno|luglio|agosto|settembre)\b",
    re.IGNORECASE,
)
# Riga "ancora" del film: un parentetico con (Paese AAAA, durata'). È la firma
# affidabile di un film, ovunque nella riga ("di Tizio (…)" oppure "4K di
# Tizio (…)"). Esclude di proposito le righe del recap "Ospiti" in fondo, che
# ripetono i titoli senza il parentetico. Cattura la durata in minuti.
_FILM_RE = re.compile(
    r"\((?:[^()]*?)(?:19|20)\d{2}[^()]*?(\d{1,3})\s*['’′]\s*\)"
)
_YEAR_RE = re.compile(r"settembre\s+(20\d{2})")
_VOS_RE = re.compile(r"original sound", re.IGNORECASE)


def _edition_year(full_text: str, today: datetime) -> int:
    m = _YEAR_RE.search(full_text)
    if m:
        return int(m.group(1))
    # Fallback: l'arena è estiva; se siamo già a fine anno punta all'anno dopo.
    return today.year if today.month <= 9 else today.year + 1


def _content_lines(soup: BeautifulSoup) -> list[str]:
    body = soup.select_one("main") or soup.select_one("article") or soup
    raw = body.get_text("\n", strip=True)
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME)
    try:
        resp = http_get(PROGRAM_URL, timeout=20)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    lines = _content_lines(soup)
    if not lines:
        return []
    year = _edition_year(" ".join(lines[:30]), today)

    # 1) Raccogli i film con la loro serata. Per ogni serata può esserci più
    #    di un film (cortometraggio + lungometraggio): teniamo il principale.
    by_date: dict[tuple[int, int], dict] = {}
    cur_key: tuple[int, int] | None = None
    cur_vos = False

    for i, line in enumerate(lines):
        # Fine del programma giornaliero: segue il recap "Ospiti in
        # Manifattura:" che ripete i titoli (con parentetico) fuori data —
        # senza questo stop verrebbero attribuiti all'ultima serata.
        low = line.lower()
        if "i nostri ospiti sono" in low or (
            low.startswith("ospiti in manifattura") and line.rstrip().endswith(":")
        ):
            break

        dm = _DATE_RE.match(line)
        if dm:
            day = int(dm.group(1))
            month = _MONTHS[dm.group(2).lower()]
            cur_key = (month, day)
            cur_vos = False
            by_date.setdefault(cur_key, {"vos": False, "films": []})
            continue
        if cur_key is None:
            continue
        if _VOS_RE.search(line):
            cur_vos = True
            by_date[cur_key]["vos"] = True
            continue
        fm = _FILM_RE.search(line)
        if fm and i > 0:
            title = lines[i - 1].strip(" –-+").strip()
            if not title:
                continue
            duration = int(fm.group(1))
            by_date[cur_key]["films"].append((title, duration))

    # 2) Un evento per serata = film di durata maggiore (il "principale").
    events: list[Event] = []
    for (month, day), info in by_date.items():
        films = info["films"]
        if not films:
            continue
        title, duration = max(films, key=lambda f: f[1])
        if info["vos"]:
            title = f"{title} (VOS)"
        try:
            start = datetime.combine(
                datetime(year, month, day).date(), SHOW_TIME, tzinfo=ROME
            )
        except ValueError:
            continue
        end = start + timedelta(minutes=duration) if duration else None
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            end=end,
            url=PROGRAM_URL,
            venue=VENUE,
            category=CATEGORY,
        ))

    events.sort(key=lambda e: e.start)
    return events
