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
_RE_DATE_RANGE = re.compile(
    rf"\bdal\s+(\d{{1,2}})(?:\s+({_MONTH_ALT}))?\s+al\s+(\d{{1,2}})\s+({_MONTH_ALT})"
    rf"(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "fino al 25 luglio", "fino a 25 luglio" (solo data di fine)
_RE_FINO_AL = re.compile(
    rf"\bfino\s+a(?:l)?\s+(\d{{1,2}})\s+({_MONTH_ALT})(?:\s+(\d{{4}}))?",
    re.IGNORECASE,
)


def parse_italian_date_range(
    text: str,
    *,
    reference: Optional[date] = None,
    default_year: Optional[int] = None,
) -> tuple[Optional[date], Optional[date]]:
    """Estrae un intervallo di date da prosa italiana.

    Riconosce "dal X [mese] al Y mese" → (inizio, fine) e "fino al Y mese" →
    (None, fine). Il mese d'inizio, se omesso ("dal 4 al 25 luglio"), eredita
    quello di fine. Se la fine cade in un mese precedente all'inizio si assume
    l'anno successivo (es. "dal 28 dicembre al 6 gennaio"). Torna (None, None)
    se non trova nulla.
    """
    if not text:
        return (None, None)
    today = reference or datetime.now(tz=ROME).date()

    m = _RE_DATE_RANGE.search(text)
    if m:
        s_day, e_day = int(m.group(1)), int(m.group(3))
        e_month = ITALIAN_MONTHS.get(m.group(4).lower())
        s_month = ITALIAN_MONTHS.get(m.group(2).lower()) if m.group(2) else e_month
        if m.group(5):
            year = int(m.group(5))
        elif default_year is not None:
            year = default_year
        else:
            year = _infer_year(today, s_day, s_month) if s_month else today.year
        try:
            start = date(year, s_month, s_day)
            e_year = year + 1 if e_month < s_month else year
            end = date(e_year, e_month, e_day)
            if end >= start:
                return (start, end)
        except (TypeError, ValueError):
            pass

    m = _RE_FINO_AL.search(text)
    if m:
        e_day = int(m.group(1))
        e_month = ITALIAN_MONTHS.get(m.group(2).lower())
        year = int(m.group(3)) if m.group(3) else (
            default_year or _infer_year(today, e_day, e_month)
        )
        try:
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
