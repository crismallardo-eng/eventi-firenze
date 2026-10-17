"""Teatro Puccini — cartellone della stagione (via delle Cascine, Firenze).

Teatro cittadino con una programmazione fitta: prosa, comico, musica,
incontri. Mancava del tutto fra le fonti: compariva solo come sede di eventi
altrui (per esempio i concerti di Fabbrica Europa).

STRUTTURA (verificata scaricando le pagine dal runner CI):
ogni scheda del cartellone ha un `div.date-container` con data e orario in
chiaro, e il link alla pagina dello spettacolo:

    Domenica 20 dicembre 2026, ore 21.00
    CHRISTMAS ROCK
    Stef Burns, Fede Poggipollini e Giuseppe Scarpato

La riga della data può contenere più repliche, con forme diverse:

    "Venerdì 23 e 30 ottobre e 6 novembre 2026, ore 21.30"   → 3 repliche
    "Da venerdì 16 a domenica 18 ottobre 2026"               → intervallo

Si raccolgono i giorni raggruppandoli per mese: per ogni nome di mese si
prendono i numeri che lo precedono (dopo il mese precedente), espandendo gli
intervalli introdotti da "a"/"al". L'anno è quello indicato accanto al mese,
o l'ultimo presente nella riga.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Teatro Puccini"
CATEGORY = "Teatro"
BASE_URL = "https://www.teatropuccini.it"
VENUE = "Teatro Puccini, Firenze"
REQUEST_TIMEOUT = 20

# Il cartellone è l'elenco completo; le altre sezioni sono suoi sottoinsiemi,
# ma si leggono comunque perché a volte ospitano voci che lì non compaiono.
LISTING_URLS = (
    f"{BASE_URL}/cartellone",
    f"{BASE_URL}/altri-eventi",
    f"{BASE_URL}/fuori-abbonamento",
    f"{BASE_URL}/visioni-autunno-fiorentino",
)

_MONTHS_ALT = "|".join(m for m in ITALIAN_MONTHS if len(m) > 3)
_MONTH_RE = re.compile(rf"\b({_MONTHS_ALT})\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
# "ore 21.00", "ore 21:00", "ore 21"
_TIME_RE = re.compile(r"\bore\s+(\d{1,2})(?:[.:](\d{2}))?", re.IGNORECASE)
_DAY_RE = re.compile(r"\b(\d{1,2})\b")
# "16 a domenica 18" / "16 al 18": intervallo di giorni, non due date isolate.
_RANGE_RE = re.compile(r"\b(\d{1,2})\s+al?\b[^\d]{0,15}(\d{1,2})\b", re.IGNORECASE)
# Permalink spettacolo: /slug/ sotto la radice (esclude le pagine di sezione).
_SECTION_SLUGS = {
    "cartellone", "altri-eventi", "fuori-abbonamento", "spettacoli",
    "visioni-autunno-fiorentino", "per-grandi-e-puccini", "laboratorio-puccini",
    "spettacoli-in-abbonamento", "spettacoli-passati", "stagione", "il-teatro",
    "biglietteria", "contatti", "amministrazione-trasparente", "acquista",
}
_EVENT_URL_RE = re.compile(rf"^{re.escape(BASE_URL)}/([a-z0-9\-]+)/?$")


def _days_by_month(text: str) -> list[tuple[int, int, int]]:
    """Da una riga di date ricava le terne (giorno, mese, anno).

    Per ogni nome di mese si guardano i numeri che lo precedono, a partire
    dalla fine del mese precedente: così "23 e 30 ottobre e 6 novembre 2026"
    dà (23,10) (30,10) (6,11).
    """
    fallback_year = None
    years = _YEAR_RE.findall(text)
    if years:
        fallback_year = int(years[-1])

    out: list[tuple[int, int, int]] = []
    cursor = 0
    for mm in _MONTH_RE.finditer(text):
        month = ITALIAN_MONTHS.get(mm.group(1).lower())
        segment = text[cursor:mm.start()]
        cursor = mm.end()
        if month is None:
            continue

        # L'anno scritto subito dopo il mese vale per questo gruppo.
        after = text[mm.end():mm.end() + 12]
        ym = _YEAR_RE.search(after)
        year = int(ym.group(1)) if ym else fallback_year
        if year is None:
            continue

        # Niente numeri a quattro cifre: sono anni, non giorni.
        segment = _YEAR_RE.sub(" ", segment)
        rng = _RANGE_RE.search(segment)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            days = list(range(a, b + 1)) if a <= b else [a, b]
        else:
            days = [int(d) for d in _DAY_RE.findall(segment)]

        for d in days:
            if 1 <= d <= 31:
                out.append((d, month, year))
    return out


def _looks_like_date(line: str) -> bool:
    """True per le righe che sono una data, non un titolo."""
    return bool(_MONTH_RE.search(line) and _DAY_RE.search(line))


# Etichette di rassegna: da sole non sono il titolo dello spettacolo, ma
# messe davanti lo qualificano ("Laboratorio Puccini — La deriva...").
_SERIES_LABELS = {
    "laboratorio puccini", "visioni", "visioni autunno fiorentino",
    "per grandi e puccini", "fuori abbonamento", "altri eventi",
    "spettacoli in abbonamento", "il cartellone",
}


def _pick_title(lines: list[str]) -> str | None:
    useful = [l.strip() for l in lines
              if len(l.strip()) >= 3 and not _looks_like_date(l)]
    if not useful:
        return None
    first = useful[0]
    if first.lower() in _SERIES_LABELS and len(useful) > 1:
        return f"{first} — {useful[1]}"
    return first


def _card_of(date_div):
    """Risale dal blocco data alla scheda che contiene il link allo spettacolo."""
    node = date_div
    for _ in range(6):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            return None
        for a in node.find_all("a", href=True):
            m = _EVENT_URL_RE.match(urljoin(BASE_URL, a["href"].split("?")[0]))
            if m and m.group(1) not in _SECTION_SLUGS:
                return node
    return None


def _events_from(url: str, today: date) -> list[Event]:
    try:
        resp = http_get(url, timeout=REQUEST_TIMEOUT)
    except Exception:  # noqa: BLE001
        return []
    soup = BeautifulSoup(resp.text, "html.parser")

    out: list[Event] = []
    for div in soup.find_all("div", class_="date-container"):
        text = div.get_text(" ", strip=True)
        triples = _days_by_month(text)
        if not triples:
            continue

        card = _card_of(div)
        if card is None:
            continue
        link_a = next(
            (a for a in card.find_all("a", href=True)
             if (m := _EVENT_URL_RE.match(urljoin(BASE_URL, a["href"].split("?")[0])))
             and m.group(1) not in _SECTION_SLUGS),
            None,
        )
        if link_a is None:
            continue
        ev_url = urljoin(BASE_URL, link_a["href"].split("?")[0])

        # Titolo: la prima riga della scheda che non sia essa stessa una data.
        # Confrontare con il testo del blocco data non basta: quando le date
        # sono articolate ("Da venerdì 16 a domenica 18 ottobre / lunedì 14 e
        # martedì 15 dicembre 2026") il sito le spezza in più nodi, nessuno
        # coincide col testo intero e come titolo finiva la data stessa.
        title = _pick_title([l for l in card.stripped_strings if l.strip()])
        if not title:
            continue

        tm = _TIME_RE.search(text)
        hh, mi = (int(tm.group(1)), int(tm.group(2) or 0)) if tm else (0, 0)
        if not (0 <= hh <= 23 and 0 <= mi <= 59):
            hh, mi = 0, 0

        for day, month, year in triples:
            try:
                start = datetime(year, month, day, hh, mi, tzinfo=ROME)
            except ValueError:
                continue
            if start.date() < today:
                continue
            out.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=ev_url,
                venue=VENUE,
                category=CATEGORY,
            ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    events: list[Event] = []
    for url in LISTING_URLS:
        events.extend(_events_from(url, today))

    if not events:
        raise RuntimeError(
            "Nessuno spettacolo riconosciuto sul cartellone del Teatro Puccini: "
            "la struttura del sito è probabilmente cambiata."
        )

    # Le sezioni si sovrappongono: stessa replica può comparire più volte.
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
