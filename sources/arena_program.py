"""Parser condiviso per i programmi delle arene cinema estive fiorentine.

Diverse arene pubblicano il programma come articolo redazionale con la stessa
struttura testuale regolare (Stensen Manifattura, Esterno Notte al Poggetto,
Apriti Cinema della Compagnia):

    Martedì 23 giugno            ← intestazione giorno (weekday + giorno + mese)
    [Original sound / Versione originale / v.o.]  ← marker lingua originale
    Il Dio dell'amore            ← titolo film
    di Francesco Lagi (Italia 2026, 100')   ← riga "ancora" con anno e durata

Ogni film è ancorato da una riga che contiene "…AAAA…, NN'" (anno + durata in
minuti), con o senza parentesi. Il titolo è la riga sopra. Si emette UN evento
per serata (il film di durata maggiore), così l'arena compare come un
appuntamento giornaliero e non come decine di righe. I film in lingua originale
prendono il suffisso "(VOS)".
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

CATEGORY = "Cinema"
DEFAULT_SHOW_TIME = time(21, 30)

_WEEKDAYS = r"(?:luned[ìi]|marted[ìi]|mercoled[ìi]|gioved[ìi]|venerd[ìi]|sabato|domenica)"
# Nota: il primo del mese è spesso scritto "1°" (es. "Mercoledì 1° luglio"):
# l'indicatore ordinale "°"/"º" dopo il giorno è opzionale.
_DATE_RE = re.compile(
    rf"^{_WEEKDAYS}\s+(\d{{1,2}})[°º]?\s+(giugno|luglio|agosto|settembre)\b",
    re.IGNORECASE,
)
_MONTHS = {"giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9}
# Riga "ancora" del film: contiene un anno (AAAA) seguito, nella stessa riga,
# da una durata in minuti (NN'). Copre sia il formato Stensen "(Italia 2026,
# 100')" sia quello della Compagnia "di Billy Wilder, Usa 1959, 120'". Escluse
# le righe-rubrica e i recap che NON hanno la coppia anno+durata. Cattura i min.
# Riga "ancora" del film, due forme:
#  1) un anno (AAAA) seguito da una durata in minuti: "(Italia 2026, 100')",
#     "Usa 1959, 120'" o, per refuso del sito, "(Kor 2025, 139)" senza apostrofo;
#  2) una riga "di <regista> …, NN'" SENZA anno (capita su Apriti, es.
#     "di Caroline Vignal, Francia, 95'").
_FILM_RE = re.compile(
    r"(?:19|20)\d{2}[^()\n]*?(\d{1,3})\s*['’′)]"
    r"|^di\s.*?(\d{1,3})\s*['’′]"
)
_YEAR_RE = re.compile(r"(?:settembre|agosto|luglio)\s+(20\d{2})")
# Lingua originale: "Original sound" (Manifattura), "Versione originale"
# (Poggetto), "v.o." (Apriti Cinema, tutti in versione originale sottotitolata).
_VOS_RE = re.compile(r"original sound|versione original|v\.o\.", re.IGNORECASE)


def _edition_year(full_text: str, today: datetime) -> int:
    m = _YEAR_RE.search(full_text)
    if m:
        return int(m.group(1))
    return today.year if today.month <= 9 else today.year + 1


def _content_lines(soup: BeautifulSoup) -> list[str]:
    body = soup.select_one("main") or soup.select_one("article") or soup
    raw = body.get_text("\n", strip=True)
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


def fetch_program(
    url: str,
    source_name: str,
    venue: str,
    show_time: time = DEFAULT_SHOW_TIME,
) -> list[Event]:
    today = datetime.now(tz=ROME)
    try:
        resp = http_get(url, timeout=20)
    except Exception:
        return []

    lines = _content_lines(BeautifulSoup(resp.text, "html.parser"))
    if not lines:
        return []
    year = _edition_year(" ".join(lines[:60]), today)

    by_date: dict[tuple[int, int], dict] = {}
    cur_key: tuple[int, int] | None = None

    for i, line in enumerate(lines):
        # Fine del programma: segue un recap "Ospiti …:" / "I nostri ospiti
        # sono …" che ripete i titoli (con anno+durata) fuori data — senza
        # questo stop verrebbero attribuiti all'ultima serata.
        low = line.lower()
        if "i nostri ospiti sono" in low or (
            low.startswith("ospiti in") and line.rstrip().endswith(":")
        ):
            break

        dm = _DATE_RE.match(line)
        if dm:
            month = _MONTHS[dm.group(2).lower()]
            cur_key = (month, int(dm.group(1)))
            by_date.setdefault(cur_key, {"vos": False, "films": []})
            continue
        if cur_key is None:
            continue
        if _VOS_RE.search(line):
            by_date[cur_key]["vos"] = True
            # niente continue: in alcune arene (Apriti) il marker "v.o." sta
            # sulla STESSA riga del film, che va comunque registrato sotto.
        fm = _FILM_RE.search(line)
        if fm and i > 0:
            duration = int(fm.group(1) or fm.group(2))
            title = lines[i - 1].strip(" –-+").strip()
            # Se la riga sopra è quella del regista ("di Tizio" su riga a sé,
            # con anno+durata sulla riga ancora successiva), il vero titolo è
            # una riga più su.
            tl = title.lower()
            if (tl == "di" or tl.startswith("di ")) and i >= 2:
                title = lines[i - 2].strip(" –-+").strip()
            if title:
                by_date[cur_key]["films"].append((title, duration))

    events: list[Event] = []
    for (month, day), info in by_date.items():
        if not info["films"]:
            continue
        title, duration = max(info["films"], key=lambda f: f[1])
        if info["vos"]:
            title = f"{title} (VOS)"
        try:
            start = datetime.combine(
                datetime(year, month, day).date(), show_time, tzinfo=ROME
            )
        except ValueError:
            continue
        end = start + timedelta(minutes=duration) if duration else None
        events.append(Event(
            source=source_name,
            title=title,
            start=start,
            end=end,
            url=url,
            venue=venue,
            category=CATEGORY,
        ))

    events.sort(key=lambda e: e.start)
    return events
