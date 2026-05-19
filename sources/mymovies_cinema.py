"""MYmovies.it — film di produzione italiana nei cinema fiorentini.

Categoria dedicata "Film italiani" per consentire un filtro separato
rispetto alle proiezioni VOS (gestite da sources.firenze_al_cinema).

Filtro: include solo film con almeno una nazionalità "Italia" nel campo
nazionalità di MYmovies (link href con country=italia nel testo lancio).
Non include i film stranieri in versione originale: quelli arrivano da
firenze_al_cinema con il tag (VOS) nel titolo.

URL pattern:
    Firenze:           https://www.mymovies.it/cinema/firenze/{id}/?giorno=DD-MM-YYYY
    Sesto Fiorentino:  https://www.mymovies.it/cinema/firenze/sestofiorentino/{id}/?giorno=DD-MM-YYYY

Card film (una per film, dentro div.mm-row):
    div.mm-white > div.schedine-titolo > a            → titolo + URL film
    div.mm-white > div.schedine-lancio                → trama + link nazionalità
    div.mm-white > div.mm-light-grey > div.orari-dettaglio
        div.stonda3 span.mm-weight-700                → orario HH:MM
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Cinema Firenze"
CATEGORY = "Film italiani"
BASE_URL = "https://www.mymovies.it"

# Mappa cinema → (path_segment, nome_visibile).
# Firenze ha il path "firenze/{id}", Sesto Fiorentino "firenze/sestofiorentino/{id}".
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


def _is_italian_production(lancio_el) -> bool:
    """True se la card ha un link 'country=italia' fra le nazionalità."""
    return bool(lancio_el and lancio_el.find('a', href=_ITALIA_RE))


def _events_for_cinema_day(cinema_id: int, path_seg: str, cinema_name: str, d: date) -> list[Event]:
    giorno = d.strftime('%d-%m-%Y')
    url = f"{BASE_URL}/cinema/{path_seg}/{cinema_id}/?giorno={giorno}"
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
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
            continue  # duplicati mobile/desktop

        # Risali al div.mm-white che contiene tutto il blocco film
        container = title_div
        while container and not (
            container.name == 'div' and 'mm-white' in container.get('class', [])
        ):
            container = container.parent
        if container is None:
            continue

        lancio_el = container.find('div', class_='schedine-lancio')
        if not _is_italian_production(lancio_el):
            continue

        orari_el = container.find('div', class_='orari-dettaglio')
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
                category=CATEGORY,
            ))
    return out


def fetch() -> list[Event]:
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
            ex.submit(_events_for_cinema_day, cid, path_seg, name, d)
            for cid, path_seg, name, d in jobs
        ]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Dedup finale per (titolo, inizio, venue)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
