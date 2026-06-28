"""Helpers to extract dates and times from Italian natural-language text."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Optional

from sources.base import ROME

ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    # Common abbreviations seen on Italian sites
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "sett": 9, "ott": 10, "nov": 11, "dic": 12,
}

# Build a regex alternation sorted by length desc so longer keys win
_MONTH_ALT = "|".join(
    sorted((re.escape(k) for k in ITALIAN_MONTHS.keys()), key=len, reverse=True)
)

# "28 maggio 2026", "28 mag 2026", "28 maggio" (year inferred)
_RE_ITALIAN_DATE = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_ALT})(?:\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
# "28/05/2026", "28-05-2026"
_RE_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
# "ore 21", "ore 21:30", "ore 21.30", "h 21.30"
_RE_TIME = re.compile(
    r"\b(?:ore|h\.?)\s*(\d{1,2})(?:[:.](\d{2}))?\b",
    re.IGNORECASE,
)


def _infer_year(today: date, day: int, month: int) -> int:
    """Pick the closest plausible year for an Italian date with no year given.

    If the resulting date would be more than ~10 days in the past, roll forward
    to next year. This covers the common case of a site showing "Venerdì 8 maggio"
    that is really meant to be next year's instance.
    """
    candidate = date(today.year, month, day)
    if (today - candidate).days > 10:
        return today.year + 1
    return today.year


def parse_italian_date(
    text: str,
    *,
    reference: Optional[date] = None,
    default_year: Optional[int] = None,
) -> Optional[date]:
    """Extract the FIRST date mentioned in text. Returns None if nothing parses.

    default_year: if set, use this year when text omits the year (e.g. RSS
    pubDate's year). Useful when the article was published in year N and
    references an event in the same year without explicitly stating it.
    """
    if not text:
        return None
    today = reference or datetime.now(tz=ROME).date()

    # Numeric date wins if present (more precise)
    m = _RE_NUMERIC_DATE.search(text)
    if m:
        day, month, year = map(int, m.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    m = _RE_ITALIAN_DATE.search(text)
    if m:
        day = int(m.group(1))
        month = ITALIAN_MONTHS.get(m.group(2).lower())
        year_str = m.group(3)
        if year_str:
            year = int(year_str)
        elif default_year is not None:
            year = default_year
        else:
            year = _infer_year(today, day, month)
        try:
            return date(year, month, day)
        except (TypeError, ValueError):
            pass

    return None


# "dal 4 al 25 luglio", "dal 27 maggio al 5 giugno", "dal 2 luglio al 20 settembre"
_RE_RANGE_DAL = re.compile(
    rf"\bdal\s+(\d{{1,2}})(?:\s+({_MONTH_ALT}))?\s+al\s+(\d{{1,2}})\s+({_MONTH_ALT})"
    rf"(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "13 luglio - 18 agosto" (mese su entrambe le date, separatore trattino)
_RE_RANGE_DASH_2M = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\s*[–—-]\s*(\d{{1,2}})\s+({_MONTH_ALT})"
    rf"(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "13-18 luglio", "13 – 18 luglio" (mese una volta sola, separatore trattino)
_RE_RANGE_DASH_1M = re.compile(
    rf"\b(\d{{1,2}})\s*[–—-]\s*(\d{{1,2}})\s+({_MONTH_ALT})(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "dal 13/07 al 18/07", "13/07-18/07", "13/07/2026 al 18/07/2026" (date numeriche)
_RE_RANGE_NUMERIC = re.compile(
    r"\b(?:dal\s+)?(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?"
    r"\s*(?:[–—-]|\bal\b)\s*(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?",
    re.IGNORECASE,
)
# "fino al 25 luglio", "fino a 25 luglio" (solo data di fine)
_RE_FINO_AL = re.compile(
    rf"\bfino\s+a(?:l)?\s+(\d{{1,2}})\s+({_MONTH_ALT})(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)


def _year_for(day: int, month: int, year_str: Optional[str],
              today: date, default_year: Optional[int]) -> int:
    if year_str:
        y = int(year_str)
        return y + 2000 if y < 100 else y
    if default_year is not None:
        return default_year
    return _infer_year(today, day, month)


def parse_italian_date_range(
    text: str,
    *,
    reference: Optional[date] = None,
    default_year: Optional[int] = None,
) -> tuple[Optional[date], Optional[date]]:
    """Estrae un intervallo di date da prosa italiana → (inizio, fine).

    Riconosce molte forme:
      • "dal 4 al 25 luglio", "dal 27 maggio al 5 giugno"
      • "13-18 luglio", "13 – 18 luglio"
      • "13 luglio - 18 agosto"
      • "dal 13/07 al 18/07", "13/07-18/07", "13/07/2026 al 18/07/2026"
      • "fino al 25 luglio" → (None, fine)
    Il mese d'inizio, se omesso, eredita quello di fine. Se la fine cade in un
    mese precedente all'inizio si assume l'anno successivo. Torna (None, None)
    se non trova nulla.
    """
    if not text:
        return (None, None)
    today = reference or datetime.now(tz=ROME).date()

    def _build(s_day, s_month, e_day, e_month, s_year_str, e_year_str):
        if s_month is None or e_month is None:
            return None
        try:
            s_year = _year_for(s_day, s_month, s_year_str, today, default_year)
            start = date(s_year, s_month, s_day)
            if e_year_str:
                e_year = _year_for(e_day, e_month, e_year_str, today, default_year)
            else:
                e_year = s_year + 1 if e_month < s_month else s_year
            end = date(e_year, e_month, e_day)
            return (start, end) if end >= start else None
        except (TypeError, ValueError):
            return None

    # "dal X [mese] al Y mese" (il mese d'inizio eredita quello di fine)
    m = _RE_RANGE_DAL.search(text)
    if m:
        e_month = ITALIAN_MONTHS.get(m.group(4).lower())
        s_month = ITALIAN_MONTHS.get(m.group(2).lower()) if m.group(2) else e_month
        r = _build(int(m.group(1)), s_month, int(m.group(3)), e_month,
                   m.group(5), m.group(5))
        if r:
            return r

    # "13 luglio - 18 agosto"
    m = _RE_RANGE_DASH_2M.search(text)
    if m:
        r = _build(
            int(m.group(1)), ITALIAN_MONTHS.get(m.group(2).lower()),
            int(m.group(3)), ITALIAN_MONTHS.get(m.group(4).lower()),
            m.group(5), m.group(5),
        )
        if r:
            return r

    # "13-18 luglio" (un mese solo per entrambe)
    m = _RE_RANGE_DASH_1M.search(text)
    if m:
        month = ITALIAN_MONTHS.get(m.group(3).lower())
        r = _build(int(m.group(1)), month, int(m.group(2)), month,
                   m.group(4), m.group(4))
        if r:
            return r

    # "dal 13/07 al 18/07", "13/07-18/07"
    m = _RE_RANGE_NUMERIC.search(text)
    if m:
        r = _build(
            int(m.group(1)), int(m.group(2)),
            int(m.group(4)), int(m.group(5)),
            m.group(3), m.group(6),
        )
        if r:
            return r

    # "fino al 25 luglio" → solo la fine
    m = _RE_FINO_AL.search(text)
    if m:
        e_day = int(m.group(1))
        e_month = ITALIAN_MONTHS.get(m.group(2).lower())
        try:
            year = _year_for(e_day, e_month, m.group(3), today, default_year)
            return (None, date(year, e_month, e_day))
        except (TypeError, ValueError):
            pass

    return (None, None)


def parse_italian_time(text: str) -> Optional[time]:
    """Extract the FIRST time mentioned in text (formats: 'ore 21', 'h 21.30')."""
    if not text:
        return None
    m = _RE_TIME.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def parse_italian_datetime(
    text: str,
    *,
    reference: Optional[date] = None,
    default_year: Optional[int] = None,
) -> Optional[datetime]:
    """Extract a full Europe/Rome datetime from a stretch of Italian prose."""
    d = parse_italian_date(text, reference=reference, default_year=default_year)
    if d is None:
        return None
    t = parse_italian_time(text) or time(0, 0)
    return datetime.combine(d, t, tzinfo=ROME)
