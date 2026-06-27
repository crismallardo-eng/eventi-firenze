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

CATEGORY_EXTRA = "Incontri"  # talk e presentazioni hanno orario proprio (pre-film)
# Talk con orario esplicito: "Talk ore 19.30 con il regista X".
_TALK_RE = re.compile(r"talk\s+ore\s+(\d{1,2})[.:](\d{2})\s*(.*)", re.IGNORECASE)
# Orario di un evento collaterale pre-film: "Alle 18.30", "Ore 18:30".
_ALLE_RE = re.compile(r"\b(?:alle|ore)\s+(\d{1,2})[.:](\d{2})", re.IGNORECASE)
# Credito editoriale di un libro: parentetica che termina con solo l'anno
# ("(Nottetempo 2026)"). NON combacia coi crediti film "(… 2025, 131')" perché
# lì l'anno non è subito prima della parentesi di chiusura.
_BOOK_CREDIT_RE = re.compile(r"\([^()]*(?:19|20)\d{2}\)")


def _edition_year(full_text: str, today: datetime) -> int:
    m = _YEAR_RE.search(full_text)
    if m:
        return int(m.group(1))
    return today.year if today.month <= 9 else today.year + 1


def _content_lines(soup: BeautifulSoup) -> list[str]:
    body = soup.select_one("main") or soup.select_one("article") or soup
    raw = body.get_text("\n", strip=True)
    return [ln.strip() for ln in raw.split("\n") if ln.strip()]


def _blocks(lines: list[str]) -> list[tuple[tuple[int, int], list[str]]]:
    """Spezza le righe in blocchi-serata (una data → le sue righe), fermandosi
    al recap finale che ripete i titoli fuori data."""
    out: list[tuple[tuple[int, int], list[str]]] = []
    key: tuple[int, int] | None = None
    block: list[str] = []
    for line in lines:
        low = line.lower()
        if "i nostri ospiti sono" in low or (
            low.startswith("ospiti in") and line.rstrip().endswith(":")
        ):
            break
        dm = _DATE_RE.match(line)
        if dm:
            if key is not None:
                out.append((key, block))
            key = (_MONTHS[dm.group(2).lower()], int(dm.group(1)))
            block = []
            continue
        if key is not None:
            block.append(line)
    if key is not None:
        out.append((key, block))
    return out


def _main_film(block: list[str]) -> tuple[str, int, bool] | None:
    """Il film principale della serata (durata maggiore) + flag lingua originale."""
    films: list[tuple[str, int]] = []
    vos = False
    for i, line in enumerate(block):
        if _VOS_RE.search(line):
            vos = True
        fm = _FILM_RE.search(line)
        if fm and i > 0:
            duration = int(fm.group(1) or fm.group(2))
            title = block[i - 1].strip(" –-+").strip()
            tl = title.lower()
            if (tl == "di" or tl.startswith("di ")) and i >= 2:
                title = block[i - 2].strip(" –-+").strip()
            if title:
                films.append((title, duration))
    if not films:
        return None
    title, duration = max(films, key=lambda f: f[1])
    return title, duration, vos


def _extra_events(block: list[str]) -> list[tuple[time, str]]:
    """Eventi collaterali con orario PROPRIO: talk e presentazioni di libri.

    Gli "Evento speciale" senza orario dedicato (es. "Che c'è night", "Sound of
    cinema") sono solo qualificatori del film e non vengono emessi a parte.
    """
    extras: list[tuple[time, str]] = []

    # Talk col regista ("Talk ore 19.30 con …")
    for line in block:
        m = _TALK_RE.search(line)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            rest = m.group(3).strip(" –-:").strip()
            extras.append((time(hh, mm), f"Talk {rest}".strip()))

    # Presentazione libro con orario pre-film: il titolo è la riga sopra il
    # credito editoriale "(Editore AAAA)". Richiediamo che nel blocco compaia
    # "libro" per non scambiare trame o note con un credito editoriale.
    has_libro = "libro" in " ".join(block).lower()
    for j, line in enumerate(block):
        if (
            has_libro and j > 0
            and _BOOK_CREDIT_RE.search(line) and not _FILM_RE.search(line)
        ):
            book = block[j - 1].strip(" \"“”–-+").strip()
            tmatch = next(
                ((int(a), int(b)) for ln in block
                 for a, b in _ALLE_RE.findall(ln) if int(a) < 20),
                (18, 30),
            )
            if len(book) > 4:
                extras.append((time(*tmatch), f"Presentazione: {book}"))
            break

    return extras


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

    events: list[Event] = []
    for (month, day), block in _blocks(lines):
        try:
            day_date = datetime(year, month, day).date()
        except ValueError:
            continue

        film = _main_film(block)
        if film is not None:
            title, duration, vos = film
            if vos:
                title = f"{title} (VOS)"
            start = datetime.combine(day_date, show_time, tzinfo=ROME)
            events.append(Event(
                source=source_name,
                title=title,
                start=start,
                end=start + timedelta(minutes=duration) if duration else None,
                url=url,
                venue=venue,
                category=CATEGORY,
            ))

        for show_t, extra_title in _extra_events(block):
            events.append(Event(
                source=source_name,
                title=extra_title,
                start=datetime.combine(day_date, show_t, tzinfo=ROME),
                url=url,
                venue=venue,
                category=CATEGORY_EXTRA,
            ))

    events.sort(key=lambda e: e.start)
    return events
