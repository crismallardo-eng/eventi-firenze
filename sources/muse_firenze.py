"""MUS.E — mostre nei musei civici fiorentini.

La Fondazione MUS.E gestisce buona parte dei musei civici di Firenze e
pubblica in un'unica pagina le mostre in corso in tutte le sedi: Palazzo
Vecchio, Palazzo Medici Riccardi, Forte di Belvedere, Complesso di Santa
Maria Novella, Cappella Brancacci, Museo Stefano Bardini, Fondazione
Salvatore Romano e altre.

Colma il buco principale sul fronte mostre: prima si coprivano solo quattro
sedi (Palazzo Strozzi, Museo Novecento, Villa Bardini, MAD), lasciando fuori
tutti i musei civici.

STRUTTURA (verificata scaricando la pagina dal runner CI):
ogni scheda contiene un `div.date` con inizio e fine senza anno, più la sede
e il titolo:

    MOSTRA
    Palazzo Medici Riccardi
    Oltre il Rinascimento. Tra Dürer e Parmigianino
    10 Set
    05 Gen

L'anno non è scritto: si deduce assumendo che le mostre elencate siano quelle
in corso o imminenti, e che una fine anteriore all'inizio cada l'anno dopo
(tipico delle mostre a cavallo di capodanno).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "Musei Civici (MUS.E)"
CATEGORY = "Mostre"
BASE_URL = "https://musefirenze.it"
LIST_URL = f"{BASE_URL}/mostre/"
REQUEST_TIMEOUT = 20

# Sedi già coperte da scraper dedicati, che le trattano con più dettaglio:
# evita di pubblicare due volte la stessa mostra.
SKIP_VENUES = ("murate", "mad", "novecento")

# "24 Set 31 Gen" — due date senza anno nello stesso blocco.
_DATE_PAIR_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-zàé]{3,10})\s+(\d{1,2})\s+([A-Za-zàé]{3,10})"
)
# Link alla scheda della mostra: /mostre/<slug>/ (esclude la pagina elenco).
_MOSTRA_URL_RE = re.compile(rf"^{re.escape(BASE_URL)}/mostre/[a-z0-9\-]+/?$")


def _month(name: str) -> int | None:
    return ITALIAN_MONTHS.get(name.strip().lower().rstrip("."))


def _card_of(date_div):
    """Risale dal div della data alla scheda che contiene il link alla mostra."""
    node = date_div
    for _ in range(6):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            return None
        for a in node.find_all("a", href=True):
            if _MOSTRA_URL_RE.match(urljoin(BASE_URL, a["href"].split("?")[0])):
                return node
    return None


def _resolve_years(s_day: int, s_mon: int, e_day: int, e_mon: int, today: date):
    """Assegna gli anni a una coppia di date senza anno.

    Le mostre elencate sono quelle in corso o appena annunciate: si parte
    dall'anno corrente e, se l'inizio risulterebbe molto nel futuro, si
    prende l'anno precedente (mostra cominciata l'anno scorso e ancora
    aperta). La fine cade l'anno dopo l'inizio se il mese è anteriore.
    """
    for year in (today.year, today.year - 1, today.year + 1):
        try:
            start = date(year, s_mon, s_day)
        except ValueError:
            continue
        end_year = year + 1 if (e_mon, e_day) < (s_mon, s_day) else year
        try:
            end = date(end_year, e_mon, e_day)
        except ValueError:
            continue
        # Mostra valida se non è già chiusa e non comincia troppo in là.
        if end >= today and start <= today + timedelta(days=400):
            return start, end
    return None


def fetch() -> list[Event]:
    resp = http_get(LIST_URL, timeout=REQUEST_TIMEOUT)
    soup = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now(tz=ROME).date()

    events: list[Event] = []
    seen: set[str] = set()
    found_cards = 0

    for div in soup.find_all("div", class_="date"):
        m = _DATE_PAIR_RE.search(div.get_text(" ", strip=True))
        if not m:
            continue
        s_mon, e_mon = _month(m.group(2)), _month(m.group(4))
        if s_mon is None or e_mon is None:
            continue

        card = _card_of(div)
        if card is None:
            continue
        found_cards += 1

        link_a = next(
            (a for a in card.find_all("a", href=True)
             if _MOSTRA_URL_RE.match(urljoin(BASE_URL, a["href"].split("?")[0]))),
            None,
        )
        url = urljoin(BASE_URL, link_a["href"].split("?")[0])
        if url in seen:
            continue

        title = link_a.get_text(" ", strip=True)
        if not title:
            continue

        # La sede è la riga che precede il titolo dentro la scheda: la si
        # riconosce perché è una delle voci note di MUS.E.
        lines = [t for t in card.stripped_strings if t.strip()]
        venue = None
        for i, line in enumerate(lines):
            if line.strip() == title.strip() and i > 0:
                cand = lines[i - 1].strip()
                if cand.upper() != "MOSTRA" and len(cand) < 80:
                    venue = cand
                break
        if venue and any(k in venue.lower() for k in SKIP_VENUES):
            continue

        span = _resolve_years(int(m.group(1)), s_mon, int(m.group(3)), e_mon, today)
        if span is None:
            continue
        start_d, end_d = span

        seen.add(url)
        events.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=datetime.combine(start_d, time(0, 0), tzinfo=ROME),
            end=datetime.combine(end_d, time(23, 59), tzinfo=ROME),
            url=url,
            venue=venue,
            category=CATEGORY,
        ))

    if found_cards == 0:
        raise RuntimeError(
            f"Nessuna scheda mostra riconosciuta su {LIST_URL}: "
            "la struttura della pagina è cambiata."
        )
    return events
