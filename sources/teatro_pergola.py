"""Fondazione Teatro della Toscana — Teatro della Pergola + Nuovo Rifredi.

I permalink degli spettacoli si raccolgono dalle pagine di cartellone;
per ciascuno si scarica la pagina di dettaglio e si leggono titolo,
luogo e date.

Cartellone: /spettacoli/ e /it/in-programma
URL evento: /it/evento/{spettacolo|evento|mostra}/{slug}

NB: il sitemap.xml NON è più utilizzabile — è diventato un indice di
sotto-sitemap, e sitemap-eventi-it.xml elenca URL della vecchia
struttura a un solo segmento (/it/evento/<slug>) che oggi non
risolvono più. Era questa la causa della fonte a zero eventi.

Struttura pagina dettaglio:
    h1.strip__title1                       → titolo
    div.event__location / event__banner__location → teatro
    div.event__dates > div.event__date     → singole date
        formato: "DD mes YYYY HH:MM" (es. "23 mag 2026 21:00")

Vengono inclusi solo gli eventi al Teatro della Pergola e al Nuovo
Rifredi Scena Aperta (entrambi a Firenze); il Teatro Era (Pontedera)
viene scartato.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Teatro della Pergola"
CATEGORY = "Teatro"
BASE_URL = "https://www.teatrodellatoscana.it"
# Pagine di cartellone da cui raccogliere i permalink degli spettacoli.
LISTING_URLS = (
    f"{BASE_URL}/spettacoli/",
    f"{BASE_URL}/it/in-programma",
)
# Permalink spettacolo: /it/evento/{spettacolo|evento|mostra}/<slug>
_EVENT_URL_RE = re.compile(
    rf"^{re.escape(BASE_URL)}/it/evento/[a-z]+/[a-z0-9\-]+/?$"
)

# Presentazioni, reading e incontri (spesso a ingresso libero) NON entrano in
# cartellone: il teatro li pubblica come notizie. La data reale sta nella
# prosa ("mercoledì 9 settembre, ore 18:30 in Saloncino 'Paolo Poli'"),
# mentre l'unica data strutturata è quella di pubblicazione. Le pagine di
# dettaglio delle notizie sono costruite via JavaScript e risultano vuote:
# il testo utile c'è solo nell'elenco.
NEWS_URL = f"{BASE_URL}/news/"
_MONTHS_ALT = "|".join(m for m in ITALIAN_MONTHS if len(m) > 3)
# Riga della data di pubblicazione nell'elenco: "31 agosto" seguita da "2026".
_NEWS_PUB_RE = re.compile(rf"^(\d{{1,2}})\s+({_MONTHS_ALT})$", re.IGNORECASE)
_NEWS_YEAR_RE = re.compile(r"^(20\d{2})$")
# Data dell'evento dentro il testo: "9 settembre", "26 settembre".
_PROSE_DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTHS_ALT})\b", re.IGNORECASE)
# Orario: "ore 18:30", "ore 18.30", "alle 18". La presenza di un orario è ciò
# che distingue un evento vero da un avviso (bandi, sconti, lavori edilizi).
_PROSE_TIME_RE = re.compile(r"\b(?:ore|alle)\s+(\d{1,2})(?:[:.](\d{2}))?\b", re.IGNORECASE)
_NEWS_END = "continua a leggere"
# Un orario può essere una SCADENZA e non l'inizio di un evento: "la richiesta
# dovrà pervenire entro e non oltre le ore 23:59 del 10 settembre". Se prima
# dell'orario compaiono queste parole, il blocco non è un appuntamento.
_DEADLINE_RE = re.compile(
    r"(?:entro|non oltre|scadenz|termine ultimo|pervenire|dovrà pervenire)",
    re.IGNORECASE,
)
# Quanto testo guardare prima dell'orario per riconoscere una scadenza.
_DEADLINE_LOOKBEHIND = 80
# Comunicazioni amministrative: non sono eventi a cui si partecipa.
_NOT_AN_EVENT_RE = re.compile(
    r"\b(avviso|bando|selezione|concorso|graduatoria|sponsor|"
    r"manifestazione di interesse|abbonamenti)\b",
    re.IGNORECASE,
)
# Sale citate nel testo delle notizie. Il Teatro Era è a Pontedera: escluso.
_NEWS_VENUES = (
    ("saloncino", "Saloncino 'Paolo Poli' - Teatro della Pergola"),
    ("pergola", "Teatro della Pergola"),
    ("rifredi", "Nuovo Rifredi Scena Aperta"),
)

PARALLEL_WORKERS = 8
REQUEST_TIMEOUT = 12

# Venue ammessi (case-insensitive substring match)
ALLOWED_VENUES = ("pergola", "rifredi")

# "23 mag 2026 21:00" — può ripetersi più volte nel testo concatenato di event__dates
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)\s+(\d{4})\s+(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)


def _parse_dates_block(text: str) -> list[datetime]:
    """Estrae tutti i datetime da un blocco 'DD mes YYYY HH:MM ...'."""
    out: list[datetime] = []
    for d, mname, y, h, m in _DATE_RE.findall(text):
        month = ITALIAN_MONTHS.get(mname.lower())
        if month is None:
            continue
        try:
            out.append(datetime(int(y), month, int(d), int(h), int(m), tzinfo=ROME))
        except ValueError:
            continue
    return out


def _scrape_event(url: str) -> list[Event]:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Titolo: la classe dedicata se c'è, altrimenti il primo h1 utile —
    # così un restyling del tema non azzera di nuovo la fonte.
    h1 = soup.find("h1", class_="strip__title1") or soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    if not title:
        return []

    # Cerca il luogo
    venue_el = (soup.find("div", class_="event__location")
                or soup.find("div", class_="event__banner__location"))
    venue = venue_el.get_text(" ", strip=True) if venue_el else ""

    venue_lower = venue.lower()
    if not any(v in venue_lower for v in ALLOWED_VENUES):
        return []

    dates_el = soup.find("div", class_="event__dates")
    if dates_el is None:
        return []
    starts = _parse_dates_block(dates_el.get_text(" ", strip=True))
    if not starts:
        return []

    return [
        Event(
            source=SOURCE_NAME,
            title=title,
            start=st,
            url=url,
            venue=venue or None,
            category=CATEGORY,
        )
        for st in starts
    ]


def _event_urls_from_listing() -> list[str]:
    """URL degli spettacoli in cartellone, dalle pagine di programmazione.

    Non si usa più il sitemap: è diventato un indice di sotto-sitemap e
    quello degli eventi elenca URL della vecchia struttura (un solo
    segmento, es. /it/evento/odissea-di-omero) che oggi non risolvono.
    Le pagine di cartellone invece portano i permalink correnti nella
    forma /it/evento/{spettacolo|evento|mostra}/<slug>.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for page in LISTING_URLS:
        try:
            resp = http_get(page, timeout=REQUEST_TIMEOUT)
        except Exception:  # noqa: BLE001
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            full = urljoin(BASE_URL, a["href"].split("?")[0].split("#")[0])
            if not _EVENT_URL_RE.match(full) or full in seen:
                continue
            seen.add(full)
            urls.append(full)
    return urls


def _news_blocks(lines: list[str]):
    """Spezza il testo dell'elenco notizie in blocchi (titolo, corpo, anno).

    Ogni notizia comincia con la data di pubblicazione su due righe
    ("31 agosto" / "2026"), poi il titolo, poi il testo fino a
    "Continua a leggere".
    """
    i = 0
    while i < len(lines) - 2:
        if _NEWS_PUB_RE.match(lines[i]) and _NEWS_YEAR_RE.match(lines[i + 1]):
            year = int(lines[i + 1])
            title = lines[i + 2].strip()
            body: list[str] = []
            j = i + 3
            while j < len(lines) and lines[j].strip().lower() != _NEWS_END:
                # una nuova notizia comincia: chiudi il blocco corrente
                if (_NEWS_PUB_RE.match(lines[j]) and j + 1 < len(lines)
                        and _NEWS_YEAR_RE.match(lines[j + 1])):
                    break
                body.append(lines[j])
                j += 1
            if title:
                yield title, " ".join(body), year
            i = j
        else:
            i += 1


def _events_from_news(today) -> list[Event]:
    """Eventi ricavati dalle notizie: presentazioni, reading, incontri."""
    try:
        resp = http_get(NEWS_URL, timeout=REQUEST_TIMEOUT)
    except Exception:  # noqa: BLE001
        return []  # le notizie sono un extra: se mancano restano gli spettacoli

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]

    out: list[Event] = []
    for title, body, pub_year in _news_blocks(lines):
        # Comunicazioni amministrative (bandi, selezioni, promozioni sugli
        # abbonamenti): hanno date e talvolta orari, ma non sono appuntamenti.
        if _NOT_AN_EVENT_RE.search(title):
            continue

        # Senza orario è un avviso (lavori, comunicati), non un evento a cui
        # si può andare. E l'orario dev'essere un inizio, non una scadenza.
        tmatch = None
        for cand in _PROSE_TIME_RE.finditer(body):
            before = body[max(0, cand.start() - _DEADLINE_LOOKBEHIND):cand.start()]
            if _DEADLINE_RE.search(before):
                continue
            tmatch = cand
            break
        if tmatch is None:
            continue
        dmatch = _PROSE_DATE_RE.search(body)
        if dmatch is None:
            continue
        month = ITALIAN_MONTHS.get(dmatch.group(2).lower())
        if month is None:
            continue
        hour = int(tmatch.group(1))
        minute = int(tmatch.group(2) or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            continue

        # L'anno non è scritto: uso quello di pubblicazione, e passo al
        # successivo se la data risulterebbe già passata (notizia di
        # dicembre su un evento di gennaio).
        year = pub_year
        try:
            start = datetime(year, month, int(dmatch.group(1)), hour, minute, tzinfo=ROME)
        except ValueError:
            continue
        if start.date() < today:
            try:
                start = start.replace(year=year + 1)
            except ValueError:
                continue
        if start.date() < today:
            continue

        haystack = f"{title} {body}".lower()
        venue = next((v for key, v in _NEWS_VENUES if key in haystack), None)
        if venue is None:
            continue  # sede non riconosciuta (o Teatro Era, fuori Firenze)

        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            url=NEWS_URL,
            venue=venue,
            description=body[:277] + "…" if len(body) > 280 else body,
            category=CATEGORY,
        ))
    return out


def fetch() -> list[Event]:
    event_urls = _event_urls_from_listing()
    if not event_urls:
        raise RuntimeError(
            "Nessun link spettacolo trovato nelle pagine di cartellone "
            f"({', '.join(LISTING_URLS)}): struttura del sito cambiata."
        )

    events: list[Event] = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [ex.submit(_scrape_event, u) for u in event_urls]
        for fut in as_completed(futures):
            try:
                events.extend(fut.result())
            except Exception:
                continue

    # Presentazioni e incontri pubblicati come notizie anziché in cartellone.
    events.extend(_events_from_news(datetime.now(tz=ROME).date()))

    # Dedup per (titolo, start, venue)
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start, e.venue)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
