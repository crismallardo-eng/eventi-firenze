"""MYmovies.it — film nei cinema fiorentini.

Espone due fetch:
  • fetch()      → film di produzione italiana, categoria "Film italiani"
  • fetch_vos()  → film con "Versione originale con sottotitoli", categoria
                   "Cinema". Usato come fallback da sources.firenze_al_cinema
                   quando il sito firenzealcinema.info non risponde.

URL pattern:
    Firenze:          https://www.mymovies.it/cinema/firenze/{id}/?giorno=DD-MM-YYYY
    Sesto Fiorentino: https://www.mymovies.it/cinema/firenze/sestofiorentino/{id}/?giorno=DD-MM-YYYY

Card film (una per film, dentro div.mm-row):
    div.mm-white > div.schedine-titolo > a            → titolo + URL film
    div.mm-white > div.schedine-lancio                → trama + link nazionalità
    div.mm-white > div.mm-light-grey > div.orari-dettaglio
        div.mm-medium                                 → etichetta versione
        div.stonda3 span.mm-weight-700                → orario HH:MM
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from typing import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Cinema Firenze"
CATEGORY = "Film italiani"
BASE_URL = "https://www.mymovies.it"

# Mappa cinema → (path_segment, nome_visibile).
# Firenze ha path "firenze/{id}", Sesto Fiorentino "firenze/sestofiorentino/{id}".
CINEMAS: dict[int, tuple[str, str]] = {
    22449: ("firenze",                  "La Compagnia"),
    4976:  ("firenze",                  "Fiorella"),
    5045:  ("firenze",                  "Spazio Alfieri"),
    5042:  ("firenze",                  "Astra"),
    5036:  ("firenze",                  "Adriano"),
    5048:  ("firenze",                  "Fiamma"),
    5053:  ("firenze",                  "Marconi"),
    5049:  ("firenze",                  "Portico"),
    5050:  ("firenze",                  "Principe"),
    5039:  ("firenze",                  "Giunti Odeon"),
    6208:  ("firenze",                  "Castello"),
    4853:  ("firenze/sestofiorentino",  "Grotta, Sesto Fiorentino"),
}

DAYS_AHEAD = 7
PARALLEL_WORKERS = 6
REQUEST_TIMEOUT = 20

_TIME_RE = re.compile(r'\b(\d{1,2}):(\d{2})\b')
_ITALIA_RE = re.compile(r'country=italia', re.I)
_ORIGINALE_RE = re.compile(r'version[ei]\s+original[ei]', re.I)


# Predicato: (lancio_el, orari_el) → bool
FilterFn = Callable[[object, object], bool]


def _is_italian_production(lancio_el, _orari_el) -> bool:
    return bool(lancio_el and lancio_el.find('a', href=_ITALIA_RE))


def _is_vos(_lancio_el, orari_el) -> bool:
    if orari_el is None:
        return False
    label = orari_el.find('div', class_='mm-medium')
    return bool(label and _ORIGINALE_RE.search(label.get_text()))


# Cache module-level delle pagine MYmovies parsate: serve perché fetch()
# (Film italiani) e fetch_vos() (Cinema VOS) iterano sugli STESSI cinema/giorni
# applicando filtri diversi. Senza cache colpiamo la rete due volte e sforiamo
# il timeout di 90s per source in run.py.
_PAGE_CACHE: dict[tuple, BeautifulSoup | None] = {}
_CACHE_LOCK = None  # niente lock: dict.setdefault è atomic sotto GIL


def _get_page_soup(cinema_id: int, path_seg: str, d: date) -> BeautifulSoup | None:
    key = (cinema_id, path_seg, d.isoformat())
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    giorno = d.strftime('%d-%m-%Y')
    url = f"{BASE_URL}/cinema/{path_seg}/{cinema_id}/?giorno={giorno}"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception:
        soup = None
    _PAGE_CACHE[key] = soup
    return soup


def _events_for_cinema_day(
    cinema_id: int,
    path_seg: str,
    cinema_name: str,
    d: date,
    include: FilterFn,
    category: str,
) -> list[Event]:
    soup = _get_page_soup(cinema_id, path_seg, d)
    if soup is None:
        return []
    out: list[Event] = []
    seen_film_urls: set[str] = set()

    for title_div in soup.find_all('div', class_='schedine-titolo'):
        title_a = title_div.find('a', href=True)
        if not title_a:
            continue
        title = (title_a.get('title') or title_a.get_text(' ', strip=True)).strip()
        if not title:
            continue
        film_url = urljoin(BASE_URL, title_a['href'])
        if film_url in seen_film_urls:
            continue

        # Risali al div.mm-white che contiene tutto il blocco film
        container = title_div
        while container and not (
            container.name == 'div' and 'mm-white' in container.get('class', [])
        ):
            container = container.parent
        if container is None:
            continue

        lancio_el = container.find('div', class_='schedine-lancio')
        orari_el  = container.find('div', class_='orari-dettaglio')
        if not include(lancio_el, orari_el):
            continue

        if orari_el is None:
            continue
        times_found: list[time] = []
        for h, m in _TIME_RE.findall(orari_el.get_text(' ')):
            try:
                times_found.append(time(int(h), int(m)))
            except ValueError:
                continue
        if not times_found:
            continue

        seen_film_urls.add(film_url)
        for t in times_found:
            start = datetime.combine(d, t, tzinfo=ROME)
            out.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=film_url,
                venue=f"Cinema {cinema_name}",
                category=category,
            ))
    return out


def _fetch_with_filter(include: FilterFn, category: str) -> list[Event]:
    today = datetime.now(tz=ROME).date()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]
    jobs = [
        (cid, path_seg, name, d)
        for cid, (path_seg, name) in CINEMAS.items()
        for d in days
    ]

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [
            ex.submit(_events_for_cinema_day, cid, path_seg, name, d, include, category)
            for cid, path_seg, name, d in jobs
        ]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Dedup per (titolo, inizio, venue)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def fetch() -> list[Event]:
    """Film di produzione italiana — usato dalla pipeline come fonte primaria."""
    return _fetch_with_filter(_is_italian_production, CATEGORY)


def fetch_vos() -> list[Event]:
    """Film in versione originale con sottotitoli — fallback per firenze_al_cinema."""
    return _fetch_with_filter(_is_vos, "Cinema")
