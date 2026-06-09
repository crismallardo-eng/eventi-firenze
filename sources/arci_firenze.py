"""Arci Firenze — eventi dai circoli ARCI fiorentini (Vie Nuove, Quinto Basso, ecc.).

Arci Firenze federa decine di circoli che pubblicano i loro eventi sul portale
centralizzato arcifirenze.it (WordPress + EventON, protetto da Wordfence).

STORIA — perché NON si usa il REST WordPress (/wp-json/wp/v2/ajde_events):
  1. Ordina per data di PUBBLICAZIONE, non per data dell'evento: con 4000+
     eventi in archivio e i circoli che pubblicano a ridosso della data, gli
     eventi futuri sono sepolti in profondità → il filtro "futuri" su 100 post
     recenti restituiva quasi nulla.
  2. Richiedeva ~100 fetch di pagine di dettaglio in parallelo: Wordfence
     (il firewall del sito) bloccava l'IP con un 503 "access limited",
     azzerando la fonte per ore.

APPROCCIO ATTUALE — l'endpoint AJAX di EventON, lo stesso usato dalla pagina
/agenda/ del sito:
  1. GET /agenda/  → estrae lo shortcode del calendario (attributo data-sc)
     e i nonce ("n" e "nonce" nel config evo_general_params).
  2. POST /?evo-ajax=eventon_get_events con lo shortcode serializzato come
     campi form annidati (shortcode[chiave]=valore, come fa jQuery)
     → JSON con html della lista eventi del mese corrente.
  3. Stessa POST con ajaxtype=switch/month_incre=1 → mese successivo.
  Totale: 3 richieste HTTP invece di ~103. Wordfence contento.

PARSING — si usa l'HTML della lista (campo "html" della risposta), NON i
timestamp unix del campo "json": i circoli inseriscono le date con timezone
incoerenti, quindi i timestamp sono inaffidabili (verificato: nessuna
conversione combacia con gli orari mostrati per tutte le righe). L'orario
visualizzato in .evo_start/.evo_end è l'unica fonte di verità.

L'anno non è mostrato: si inferisce scegliendo l'occorrenza più vicina nel
futuro (con tolleranza di qualche giorno nel passato per eventi in corso).
"""
from __future__ import annotations

import json
import re
import time as _time
from datetime import date, datetime, time, timedelta
from html import unescape

import requests
from bs4 import BeautifulSoup

from sources.base import Event, ROME, new_session

SOURCE_NAME = "Arci Firenze"
CATEGORY = "Circoli"
BASE_URL = "https://www.arcifirenze.it"
AGENDA_URL = f"{BASE_URL}/agenda/"
AJAX_URL = f"{BASE_URL}/?evo-ajax=eventon_get_events"
REQUEST_TIMEOUT = 30
POLITE_DELAY = 1.0  # pausa fra le (poche) richieste, per non irritare Wordfence

_SC_RE = re.compile(r'data-sc="(\{.*?\})"')
_N_RE = re.compile(r'"n":"([0-9a-f]+)"')
_NONCE_RE = re.compile(r'"nonce":"([0-9a-f]+)"')
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")

_MONTHS_IT = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}


def _polite_get(session: requests.Session, url: str) -> requests.Response | None:
    """GET senza retry-storm: su 503 (= Wordfence) molla subito.

    Ritentare durante un blocco Wordfence lo PROLUNGA soltanto. Un solo
    retry, e solo per errori di rete (non per status code).
    """
    for attempt in (0, 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 0:
                _time.sleep(2)
                continue
            return None
        return resp if resp.status_code == 200 else None
    return None


def _shortcode_payload(sc: dict) -> dict[str, str]:
    """Serializza lo shortcode come campi form annidati, alla maniera di jQuery."""
    out: dict[str, str] = {}
    for k, v in sc.items():
        if v is None:
            out[f"shortcode[{k}]"] = ""
        elif isinstance(v, (dict, list)):
            out[f"shortcode[{k}]"] = json.dumps(v)
        else:
            out[f"shortcode[{k}]"] = str(v)
    return out


def _fetch_month_html(
    session: requests.Session, sc: dict, n: str, nonce: str, *, next_month: bool
) -> str | None:
    sc_eff = dict(sc)
    payload = _shortcode_payload(sc_eff)
    if next_month:
        sc_eff["month_incre"] = 1
        payload = _shortcode_payload(sc_eff)
        payload.update({"direction": "next", "ajaxtype": "switch"})
    else:
        payload.update({"direction": "none", "ajaxtype": "init"})
    payload.update({"nonce": n, "nonceX": nonce})
    # Il server a volte tronca la connessione sulle risposte grosse (~400KB):
    # un retry con pausa lunga di solito basta. "Connection: close" evita di
    # riusare una keep-alive già degradata.
    resp = None
    for attempt in (0, 1, 2):
        if attempt:
            _time.sleep(5 * attempt)
        try:
            resp = session.post(
                AJAX_URL, data=payload,
                headers={"Connection": "close"},
                timeout=REQUEST_TIMEOUT,
            )
            break
        except (requests.ConnectionError, requests.Timeout):
            resp = None
    if resp is None or resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data.get("html") or None


def _parse_dm(block) -> tuple[int, int, time | None] | None:
    """Da un blocco .evo_start/.evo_end estrae (giorno, mese, orario)."""
    if block is None:
        return None
    day_el = block.select_one("em.date")
    month_el = block.select_one("em.month")
    if day_el is None or month_el is None:
        return None
    try:
        day = int(day_el.get_text(strip=True))
    except ValueError:
        return None
    month = _MONTHS_IT.get(month_el.get_text(strip=True).lower()[:3])
    if month is None:
        return None
    t = None
    time_el = block.select_one("em.time")
    if time_el is not None:
        # Rimuovi il marker di ripetizione "(Giu 3)" prima di cercare HH:MM
        for i_tag in time_el.find_all("i"):
            i_tag.decompose()
        m = _TIME_RE.search(time_el.get_text(" ", strip=True))
        if m:
            try:
                t = time(int(m.group(1)), int(m.group(2)))
            except ValueError:
                t = None
    return day, month, t


def _infer_year(day: int, month: int, today: date, grace_days: int = 21) -> int:
    """L'agenda non mostra l'anno: scegli l'occorrenza più vicina nel futuro.

    grace_days di tolleranza nel passato: il mese corrente può contenere
    eventi multi-giorno iniziati poche settimane fa e ancora in corso.
    """
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today - timedelta(days=grace_days):
            return year
    return today.year + 1


def _events_from_html(html_str: str, today: date) -> list[Event]:
    soup = BeautifulSoup(html_str, "html.parser")
    out: list[Event] = []
    for row in soup.select(".eventon_list_event"):
        title_el = row.select_one(".evcal_event_title")
        if title_el is None:
            continue
        title = unescape(title_el.get_text(" ", strip=True))
        if not title:
            continue

        link_el = row.find("a", href=True)
        url = link_el["href"] if link_el else AGENDA_URL

        start_parsed = _parse_dm(row.select_one(".evo_start"))
        if start_parsed is None:
            continue
        s_day, s_month, s_time = start_parsed
        s_year = _infer_year(s_day, s_month, today)
        start = datetime.combine(
            date(s_year, s_month, s_day), s_time or time(0, 0), tzinfo=ROME
        )

        end = None
        end_parsed = _parse_dm(row.select_one(".evo_end"))
        if end_parsed is not None:
            e_day, e_month, e_time = end_parsed
            e_year = start.year + 1 if e_month < s_month else start.year
            end = datetime.combine(
                date(e_year, e_month, e_day), e_time or time(23, 59), tzinfo=ROME
            )
            if end < start:
                end = None

        subtitle_el = row.select_one(".evcal_event_subtitle")
        description = (
            unescape(subtitle_el.get_text(" ", strip=True)) if subtitle_el else None
        )

        venue = None
        loc_el = row.select_one(".event_location_attrs")
        if loc_el is not None:
            venue = unescape(loc_el.get("data-location_name", "").strip()) or None

        out.append(Event(
            source=SOURCE_NAME,
            title=title,
            start=start,
            end=end,
            url=url,
            venue=venue,
            description=description,
            category=CATEGORY,
        ))
    return out


def fetch() -> list[Event]:
    now = datetime.now(tz=ROME)
    today = now.date()
    session = new_session()

    # 1) Pagina agenda: shortcode del calendario + nonce.
    resp = _polite_get(session, AGENDA_URL)
    if resp is None:
        return []
    page = resp.text
    sc_m = _SC_RE.search(page)
    n_m = _N_RE.search(page)
    nonce_m = _NONCE_RE.search(page)
    if not (sc_m and n_m and nonce_m):
        return []
    try:
        sc = json.loads(unescape(sc_m.group(1)))
    except ValueError:
        return []
    n, nonce = n_m.group(1), nonce_m.group(1)

    # 2) Mese corrente + 3) mese successivo.
    events: list[Event] = []
    for next_month in (False, True):
        _time.sleep(POLITE_DELAY)
        html_str = _fetch_month_html(session, sc, n, nonce, next_month=next_month)
        if html_str:
            events.extend(_events_from_html(html_str, today))

    # Tieni futuri + in corso (multi-giorno con fine nel futuro).
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    kept = [e for e in events if (e.end or e.start) >= cutoff]

    # Dedup (eventi a cavallo di due mesi compaiono in entrambe le risposte).
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in kept:
        key = (e.title, e.start, e.venue)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
