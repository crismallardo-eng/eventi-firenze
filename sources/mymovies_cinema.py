"""MYmovies.it — programmazione cinema Firenze: originali e film italiani.

Scrapa le pagine giornaliere per i prossimi DAYS_AHEAD giorni.
Include solo:
  • proiezioni con "Versione originale" (VO/VOS con sottotitoli)
  • film di produzione italiana (link country=italia nel testo lancio)

URL pattern:
    https://www.mymovies.it/cinema/firenze/{id}/?giorno=DD-MM-YYYY

Struttura card (una per film, dentro div.mm-row):
    div.mm-white > div.schedine-titolo > a   → titolo + URL film
    div.mm-white > div.schedine-lancio       → trama + link nazionalità
    div.mm-white > div.mm-light-grey > div.orari-dettaglio
        div.mm-medium                        → etichetta versione
        div.stonda3 span.mm-weight-700       → orario HH:MM
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get

SOURCE_NAME = "Cinema Firenze"
CATEGORY = "Cinema"
BASE_URL = "https://www.mymovies.it"

# ID MYmovies dei cinema fiorentini disponibili
CINEMAS: dict[int, str] = {
    22449: "La Compagnia",
    4976:  "Fiorella",
    5045:  "Spazio Alfieri",
    5042:  "Astra",
    5036:  "Adriano",
    5048:  "Fiamma",
    5053:  "Marconi",
    5049:  "Portico",
    5050:  "Principe",
    5039:  "Giunti Odeon",
    6208:  "Castello",
}

DAYS_AHEAD = 7
PARALLEL_WORKERS = 6
REQUEST_TIMEOUT = 20

_TIME_RE = re.compile(r'\b(\d{1,2}):(\d{2})\b')
_ITALIA_RE = re.compile(r'country=italia', re.I)
_ORIGINALE_RE = re.compile(r'version[ei]\s+original[ei]', re.I)


def _include_film(lancio_el, orari_el) -> bool:
    """True solo se la proiezione è in versione originale con sottotitoli."""
    if orari_el:
        label = orari_el.find('div', class_='mm-medium')
        if label and _ORIGINALE_RE.search(label.get_text()):
            return True
    return False


def _events_for_cinema_day(cinema_id: int, cinema_name: str, d: date) -> list[Event]:
    giorno = d.strftime('%d-%m-%Y')
    url = f"{BASE_URL}/cinema/firenze/{cinema_id}/?giorno={giorno}"
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
            continue  # salta duplicati mobile/desktop

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

        if not _include_film(lancio_el, orari_el):
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
                category=CATEGORY,
            ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]
    jobs = [(cid, name, d) for cid, name in CINEMAS.items() for d in days]

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [
            ex.submit(_events_for_cinema_day, cid, name, d)
            for cid, name, d in jobs
        ]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Deduplica finale per (titolo, inizio, venue)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
