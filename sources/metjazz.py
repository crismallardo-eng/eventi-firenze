"""MetJazz — rassegna jazz del Teatro Metastasio di Prato.

Il calendario eventi del Metastasio è caricato via AJAX dal widget
`/inc/php/widget/calendario-lista.php` con filtro `mac=3` per la macro
"MetJazz". L'endpoint richiede header X-Requested-With e Referer e
restituisce HTML con card `article.event__card`.

Card structure:
    article.event__card
      a.event__link[href]                → URL evento
      img alt="..."                      → titolo immagine
      p.event__macro                     → "MetJazz"
      h2.event__title                    → titolo
      p.event__subtitle                  → sottotitolo / artista
      div.event__time                    → "20.45"
      p.event__place                     → luogo

Le date sono in `<div class="calendar__date">` che precede una serie di
card sullo stesso giorno: "Gio<strong>21</strong>.05" → giovedi' 21/05.
L'anno viene inferito (italian_dates._infer_year).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sources.base import DEFAULT_HEADERS, Event, ROME
from sources.italian_dates import ITALIAN_MONTHS

SOURCE_NAME = "MetJazz"
CATEGORY = "Concerti"
BASE_URL = "https://www.metastasio.it"
CALENDAR_URL = f"{BASE_URL}/inc/php/widget/calendario-lista.php"
MACRO_ID = "3"  # MetJazz (recuperato dal modale filtri della home)
HORIZON_DAYS = 365  # un anno avanti

REQUEST_TIMEOUT = 15

_DAY_NUM_RE = re.compile(r"\b(\d{1,2})\b")
_TIME_RE = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")


def _post_calendar(macro_id: str, from_date: date, to_date: date) -> str:
    headers = dict(DEFAULT_HEADERS)
    headers["Referer"] = f"{BASE_URL}/"
    headers["X-Requested-With"] = "XMLHttpRequest"
    headers["Origin"] = BASE_URL
    data = {
        "mac": macro_id,
        "dda": from_date.strftime("%Y%m%d"),
        "dal": to_date.strftime("%Y%m%d"),
    }
    try:
        resp = requests.post(
            CALENDAR_URL, data=data, headers=headers, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


def _parse_calendar_html(html: str) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []
    current_day: date | None = None
    today = datetime.now(tz=ROME).date()

    # Iteriamo TUTTI gli elementi di livello superiore in ordine documentale:
    # i div.calendar__date precedono le article.event__card che vi appartengono.
    for el in soup.find_all(["div", "article"], recursive=True):
        if el.name == "div" and "calendar__date" in (el.get("class") or []):
            # "Gio 21 .05"
            text = el.get_text(" ", strip=True)
            m_day = re.search(r"\b(\d{1,2})\b", text)
            m_month = re.search(r"\.(\d{1,2})", text)
            if not (m_day and m_month):
                continue
            day = int(m_day.group(1))
            month = int(m_month.group(1))
            try:
                cand = date(today.year, month, day)
            except ValueError:
                continue
            # Se la candidata è nel passato lontano, considera l'anno successivo
            if (today - cand).days > 30:
                cand = date(today.year + 1, month, day)
            current_day = cand
            continue

        if el.name == "article" and "event__card" in (el.get("class") or []):
            if current_day is None:
                continue
            title_el = el.find(class_="event__title")
            if not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if not title:
                continue

            link = el.find("a", class_="event__link", href=True)
            url = urljoin(BASE_URL, link["href"]) if link else BASE_URL

            time_el = el.find(class_="event__time")
            t: time | None = None
            if time_el:
                mt = _TIME_RE.search(time_el.get_text())
                if mt:
                    try:
                        t = time(int(mt.group(1)), int(mt.group(2)))
                    except ValueError:
                        t = None

            place_el = el.find(class_="event__place")
            venue = place_el.get_text(" ", strip=True) if place_el else None

            subtitle_el = el.find(class_="event__subtitle")
            description = (
                subtitle_el.get_text(" ", strip=True) if subtitle_el else None
            )

            start = datetime.combine(current_day, t or time(0, 0), tzinfo=ROME)
            out.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=url,
                venue=venue,
                description=description,
                category=CATEGORY,
            ))
    return out


def fetch() -> list[Event]:
    today = datetime.now(tz=ROME).date()
    horizon = today + timedelta(days=HORIZON_DAYS)
    html = _post_calendar(MACRO_ID, today, horizon)
    if not html:
        return []

    events = _parse_calendar_html(html)
    # Dedup
    seen: set[tuple] = set()
    unique: list[Event] = []
    for e in events:
        key = (e.title, e.start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique
