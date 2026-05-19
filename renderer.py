"""Render aggregated events to a single self-contained HTML page."""
from __future__ import annotations

import calendar
import html
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

from sources.base import Event, ROME

ITALIAN_MONTHS = {
    1: "gennaio", 2: "febbraio", 3: "marzo", 4: "aprile",
    5: "maggio", 6: "giugno", 7: "luglio", 8: "agosto",
    9: "settembre", 10: "ottobre", 11: "novembre", 12: "dicembre",
}
ITALIAN_WEEKDAYS = {
    0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì",
    4: "Venerdì", 5: "Sabato", 6: "Domenica",
}

# Display order for category pills (most likely to be of interest first).
CATEGORY_ORDER = [
    "Concerti", "Cinema", "Film italiani", "Mostre", "Circoli",
    "Biblioteche", "Civici", "Altro",
]


def _format_date_header(d: date) -> str:
    return f"{ITALIAN_WEEKDAYS[d.weekday()]} {d.day} {ITALIAN_MONTHS[d.month]} {d.year}"


def _format_time(dt: datetime) -> str:
    if dt.hour == 0 and dt.minute == 0:
        return ""
    return dt.strftime("%H:%M")


def _esc(text: str | None) -> str:
    return html.escape(text or "")


def _slug(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


CSS = """
:root {
    --bg: #1a1a1a;
    --fg: #e8e8e8;
    --muted: #888;
    --border: #333;
    --accent: #ff6a4a;
    --card-bg: #242424;
    --badge-bg: #3a3220;
    --badge-fg: #d8c890;
    --pill-bg: #242424;
    --pill-bg-active: #e8e8e8;
    --pill-fg-active: #1a1a1a;
    --error-bg: #2a1818;
    --error-fg: #ff8888;
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--fg);
    margin: 0;
    padding: 2rem 1rem 4rem;
    line-height: 1.5;
}
.container { max-width: 880px; margin: 0 auto; }
header { border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1rem; }
header h1 { margin: 0 0 .25rem; font-size: 1.6rem; }
header .meta { color: var(--muted); font-size: .9rem; }

.filters {
    padding: 1rem 0 1.25rem;
    margin-bottom: .5rem;
    border-bottom: 1px solid var(--border);
}
.filter-row {
    display: flex;
    flex-wrap: wrap;
    gap: .4rem;
    align-items: center;
    margin-bottom: .5rem;
}
.filter-row:last-child { margin-bottom: 0; }
.filter-row .filter-label {
    color: var(--muted);
    font-size: .75rem;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-right: .25rem;
    min-width: 4.5rem;
}
.filter-pill {
    cursor: pointer;
    user-select: none;
    background: var(--pill-bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: .35rem .85rem;
    font-size: .85rem;
    transition: background .15s, color .15s, border-color .15s;
}
.filter-pill:hover { border-color: var(--accent); }
.filter-pill.active {
    background: var(--pill-bg-active);
    color: var(--pill-fg-active);
    border-color: var(--pill-bg-active);
}
.filter-pill .count {
    font-size: .75em;
    opacity: .7;
    margin-left: .35rem;
}
.filter-actions {
    display: flex;
    gap: .5rem;
    margin-left: auto;
    align-items: center;
}
.filter-actions button {
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font-size: .8rem;
    padding: .35rem .25rem;
    text-decoration: underline;
}
.filter-actions button:hover { color: var(--accent); }

h2.day {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--accent);
    border-bottom: 1px solid var(--border);
    padding-bottom: .25rem;
    margin: 2rem 0 .75rem;
    text-transform: capitalize;
}
.event {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .85rem 1rem;
    margin-bottom: .6rem;
    display: grid;
    grid-template-columns: 64px 1fr;
    gap: 0 .9rem;
}
.event.hidden, h2.day.hidden { display: none; }
.event .time {
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    font-size: .95rem;
    padding-top: .15rem;
}
.event .title { margin: 0 0 .15rem; font-size: 1.02rem; font-weight: 600; }
.event .title a { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--border); }
.event .title a:hover { border-bottom-color: var(--accent); }
.event .meta-line { color: var(--muted); font-size: .85rem; }
.badge {
    display: inline-block;
    background: var(--badge-bg);
    color: var(--badge-fg);
    font-size: .72rem;
    padding: .15rem .5rem;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: .03em;
    margin-right: .4rem;
    vertical-align: 1px;
}
.event .desc {
    color: var(--muted);
    font-size: .88rem;
    margin-top: .35rem;
}
.errors {
    margin-top: 3rem;
    padding: 1rem;
    background: var(--error-bg);
    color: var(--error-fg);
    border-radius: 8px;
    font-size: .9rem;
}
.errors h3 { margin-top: 0; }
.errors ul { margin: 0; padding-left: 1.2rem; }
.empty { text-align: center; color: var(--muted); padding: 3rem 0; }
.empty-filter { display: none; text-align: center; color: var(--muted); padding: 3rem 0; }

.ongoing-section { margin-top: 1.5rem; }
.ongoing-section h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--accent);
    border-bottom: 1px solid var(--border);
    padding-bottom: .25rem;
    margin: 0 0 .75rem;
}
.ongoing-section.hidden { display: none; }
.ongoing-event {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .75rem 1rem;
    margin-bottom: .5rem;
}
.ongoing-event.hidden { display: none; }
.ongoing-event .title { margin: 0 0 .15rem; font-size: 1rem; font-weight: 600; }
.ongoing-event .title a { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--border); }
.ongoing-event .title a:hover { border-bottom-color: var(--accent); }
.ongoing-event .meta-line { color: var(--muted); font-size: .85rem; }
.ongoing-event .closing { color: var(--accent); font-size: .82rem; margin-top: .2rem; }
"""

JS_TEMPLATE = """
(function() {
    const STORAGE_KEY = 'eventi-firenze-filters';
    const WEEK_END = __WEEK_END__;
    const MONTH_END = __MONTH_END__;
    const WEEKEND_START = __WEEKEND_START__;
    const WEEKEND_END = __WEEKEND_END__;

    const allCategories = Array.from(document.querySelectorAll('.filter-pill[data-category]'))
        .map(p => p.dataset.category);

    function defaultState() {
        return { cats: new Set(allCategories), window: null, weekdayTime: null };
    }
    function loadState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return defaultState();
            const obj = JSON.parse(raw);
            return {
                cats: new Set(Array.isArray(obj.cats) ? obj.cats.filter(c => allCategories.includes(c)) : allCategories),
                window: ['week', 'month', 'weekend'].includes(obj.window) ? obj.window : null,
                weekdayTime: ['after14', 'after17'].includes(obj.weekdayTime) ? obj.weekdayTime : null,
            };
        } catch (e) { return defaultState(); }
    }
    function saveState(s) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                cats: Array.from(s.cats), window: s.window, weekdayTime: s.weekdayTime
            }));
        } catch (e) {}
    }

    let state = loadState();
    if (state.cats.size === 0) state.cats = new Set(allCategories);

    function passes(el) {
        if (!state.cats.has(el.dataset.category)) return false;
        // Ongoing exhibits (in the "Mostre in corso" section) always pass
        // window/time-of-day filters because they're open today by definition.
        if (el.classList.contains('ongoing-event')) return true;
        const iso = el.dataset.isoDate;
        if (state.window === 'week' && iso > WEEK_END) return false;
        if (state.window === 'month' && iso > MONTH_END) return false;
        if (state.window === 'weekend' && (iso < WEEKEND_START || iso > WEEKEND_END)) return false;
        if (state.weekdayTime) {
            const dow = new Date(iso + 'T00:00:00').getDay();
            const isWeekday = dow >= 1 && dow <= 5;
            const tm = el.dataset.timeMin;
            // All-day events (00:00) on weekdays are kept — they may be daytime
            // events that the user can drop into in the evening.
            if (isWeekday && tm && tm !== '00:00') {
                const [h, m] = tm.split(':').map(Number);
                const eventMin = h * 60 + m;
                const threshold = state.weekdayTime === 'after17' ? 17 * 60 : 14 * 60;
                if (eventMin < threshold) return false;
            }
        }
        return true;
    }

    function apply() {
        document.querySelectorAll('.event, .ongoing-event').forEach(el => {
            el.classList.toggle('hidden', !passes(el));
        });
        document.querySelectorAll('h2.day').forEach(h => {
            let sib = h.nextElementSibling;
            let hasVisible = false;
            while (sib && !(sib.tagName === 'H2' && sib.classList.contains('day'))) {
                if (sib.classList && sib.classList.contains('event') && !sib.classList.contains('hidden')) {
                    hasVisible = true;
                    break;
                }
                sib = sib.nextElementSibling;
            }
            h.classList.toggle('hidden', !hasVisible);
        });
        const ongoingSection = document.getElementById('ongoing-section');
        if (ongoingSection) {
            const anyOngoing = ongoingSection.querySelector('.ongoing-event:not(.hidden)');
            ongoingSection.classList.toggle('hidden', !anyOngoing);
        }
        document.querySelectorAll('.filter-pill[data-category]').forEach(p => {
            p.classList.toggle('active', state.cats.has(p.dataset.category));
        });
        document.querySelectorAll('.filter-pill[data-window]').forEach(p => {
            p.classList.toggle('active', state.window === p.dataset.window);
        });
        document.querySelectorAll('.filter-pill[data-weekday-time]').forEach(p => {
            p.classList.toggle('active', state.weekdayTime === p.dataset.weekdayTime);
        });
        const anyVisible = document.querySelector('.event:not(.hidden), .ongoing-event:not(.hidden)');
        const empty = document.getElementById('empty-filter');
        if (empty) empty.style.display = anyVisible ? 'none' : 'block';
    }

    document.querySelectorAll('.filter-pill[data-category]').forEach(p => {
        p.addEventListener('click', () => {
            const cat = p.dataset.category;
            if (state.cats.has(cat)) state.cats.delete(cat);
            else state.cats.add(cat);
            if (state.cats.size === 0) state.cats = new Set(allCategories);
            saveState(state); apply();
        });
    });
    document.querySelectorAll('.filter-pill[data-window]').forEach(p => {
        p.addEventListener('click', () => {
            const w = p.dataset.window;
            state.window = (state.window === w) ? null : w;
            saveState(state); apply();
        });
    });
    document.querySelectorAll('.filter-pill[data-weekday-time]').forEach(p => {
        p.addEventListener('click', () => {
            const t = p.dataset.weekdayTime;
            state.weekdayTime = (state.weekdayTime === t) ? null : t;
            saveState(state); apply();
        });
    });

    const allBtn = document.getElementById('filter-all');
    if (allBtn) allBtn.addEventListener('click', () => {
        state = defaultState();
        saveState(state); apply();
    });

    apply();
})();
"""


def _compute_boundaries(today: date) -> dict[str, str]:
    """ISO date boundaries for the time-window filter pills."""
    # weekday(): Mon=0, Sun=6 → days to next Sunday inclusive
    week_end = today + timedelta(days=(6 - today.weekday()))
    last_dom = calendar.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=last_dom)
    if today.weekday() == 5:  # Saturday
        weekend_start, weekend_end = today, today + timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        weekend_start, weekend_end = today, today
    else:  # Mon–Fri: upcoming Sat–Sun
        weekend_start = today + timedelta(days=(5 - today.weekday()))
        weekend_end = weekend_start + timedelta(days=1)
    return {
        "week_end": week_end.isoformat(),
        "month_end": month_end.isoformat(),
        "weekend_start": weekend_start.isoformat(),
        "weekend_end": weekend_end.isoformat(),
    }


def render(
    events: Iterable[Event],
    errors: list[tuple[str, str]],
    generated_at: datetime,
    source_count: int,
) -> str:
    today = generated_at.astimezone(ROME).date()
    bounds = _compute_boundaries(today)
    events = sorted(events, key=lambda e: e.sort_key())

    ongoing: list[Event] = []
    regular: list[Event] = []
    for ev in events:
        # An "ongoing" event has a known end date AND its window straddles today
        # (started in the past or today, ends today or in the future).
        if ev.end is not None and ev.start.date() <= today <= ev.end.date() and ev.start.date() != ev.end.date():
            ongoing.append(ev)
        else:
            regular.append(ev)
    # Sort ongoing by closest-to-end first (so the user sees what's about to close).
    ongoing.sort(key=lambda e: e.end.date() if e.end else date.max)

    by_day: dict[date, list[Event]] = defaultdict(list)
    cat_counts: Counter[str] = Counter()
    for ev in regular:
        by_day[ev.start.date()].append(ev)
    for ev in events:
        cat_counts[ev.category or "Altro"] += 1

    # Build pill bar in canonical order, falling back to alpha for unknown cats.
    seen_cats = list(cat_counts.keys())
    ordered_cats = [c for c in CATEGORY_ORDER if c in cat_counts] + sorted(
        c for c in seen_cats if c not in CATEGORY_ORDER
    )
    cat_pills_html = "".join(
        f'<div class="filter-pill active" data-category="{_esc(c)}">'
        f'{_esc(c)}<span class="count">{cat_counts[c]}</span>'
        f'</div>'
        for c in ordered_cats
    )
    window_pills_html = (
        '<div class="filter-pill" data-window="week">Questa settimana</div>'
        '<div class="filter-pill" data-window="weekend">Weekend</div>'
        '<div class="filter-pill" data-window="month">Questo mese</div>'
    )
    weekday_time_pills_html = (
        '<div class="filter-pill" data-weekday-time="after14">Feriali dalle 14:00</div>'
        '<div class="filter-pill" data-weekday-time="after17">Feriali dalle 17:00</div>'
    )
    filters_html = (
        '<div class="filters">'
        f'<div class="filter-row"><span class="filter-label">Categorie</span>{cat_pills_html}'
        '<div class="filter-actions"><button id="filter-all">Reset</button></div></div>'
        f'<div class="filter-row"><span class="filter-label">Periodo</span>{window_pills_html}</div>'
        f'<div class="filter-row"><span class="filter-label">Orario</span>{weekday_time_pills_html}</div>'
        '</div>'
    )

    body_parts: list[str] = []

    # "Mostre in corso" section: long-running exhibits already open today.
    if ongoing:
        ongoing_html_parts = [
            f'<div class="ongoing-section" id="ongoing-section">'
            f'<h2>Mostre in corso ({len(ongoing)})</h2>'
        ]
        for ev in ongoing:
            end_date = ev.end.date() if ev.end else None
            closing_str = (
                f'In corso fino al {end_date.strftime("%d/%m/%Y")}'
                if end_date else "In corso"
            )
            meta_bits = [f'<span class="badge">{_esc(ev.source)}</span>']
            if ev.venue:
                meta_bits.append(_esc(ev.venue))
            title_html = (
                f'<a href="{_esc(ev.url)}" target="_blank" rel="noopener">{_esc(ev.title)}</a>'
                if ev.url else _esc(ev.title)
            )
            ongoing_html_parts.append(
                f'<div class="ongoing-event" data-category="{_esc(ev.category or "Altro")}">'
                f'<p class="title">{title_html}</p>'
                f'<div class="meta-line">{" · ".join(meta_bits)}</div>'
                f'<div class="closing">{_esc(closing_str)}</div>'
                f'</div>'
            )
        ongoing_html_parts.append('</div>')
        body_parts.append("".join(ongoing_html_parts))

    if not events:
        body_parts.append('<p class="empty">Nessun evento trovato.</p>')
    elif not by_day and not ongoing:
        body_parts.append('<p class="empty">Nessun evento trovato.</p>')
    else:
        for day in sorted(by_day.keys()):
            body_parts.append(f'<h2 class="day">{_esc(_format_date_header(day))}</h2>')
            for ev in by_day[day]:
                time_str = _format_time(ev.start)
                meta_bits = [f'<span class="badge">{_esc(ev.source)}</span>']
                if ev.venue:
                    meta_bits.append(_esc(ev.venue))
                title_html = (
                    f'<a href="{_esc(ev.url)}" target="_blank" rel="noopener">{_esc(ev.title)}</a>'
                    if ev.url else _esc(ev.title)
                )
                desc_html = (
                    f'<div class="desc">{_esc(ev.description)}</div>'
                    if ev.description else ""
                )
                iso_date = ev.start.date().isoformat()
                time_min = ev.start.strftime("%H:%M")
                body_parts.append(
                    f'<div class="event" '
                    f'data-category="{_esc(ev.category or "Altro")}" '
                    f'data-iso-date="{iso_date}" '
                    f'data-time-min="{time_min}">'
                    f'<div class="time">{_esc(time_str)}</div>'
                    f'<div class="body">'
                    f'<p class="title">{title_html}</p>'
                    f'<div class="meta-line">{" · ".join(meta_bits)}</div>'
                    f'{desc_html}'
                    f'</div>'
                    f'</div>'
                )
        body_parts.append(
            '<p id="empty-filter" class="empty-filter">'
            'Nessun evento corrisponde ai filtri attivi.'
            '</p>'
        )

    errors_html = ""
    if errors:
        items = "".join(
            f"<li><strong>{_esc(name)}</strong>: {_esc(msg)}</li>"
            for name, msg in errors
        )
        errors_html = (
            '<div class="errors">'
            '<h3>Fonti che non hanno risposto</h3>'
            f'<ul>{items}</ul>'
            '</div>'
        )

    gen_str = generated_at.astimezone(ROME).strftime("%d/%m/%Y %H:%M")
    n = sum(len(v) for v in by_day.values())

    js = (
        JS_TEMPLATE
        .replace("__WEEK_END__", f'"{bounds["week_end"]}"')
        .replace("__MONTH_END__", f'"{bounds["month_end"]}"')
        .replace("__WEEKEND_START__", f'"{bounds["weekend_start"]}"')
        .replace("__WEEKEND_END__", f'"{bounds["weekend_end"]}"')
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Eventi Firenze</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{CSS}</style>
</head>
<body>
<div class="container">
<header>
<h1>Eventi Firenze</h1>
<div class="meta">{n} eventi da {source_count} fonti · aggiornato il {gen_str}</div>
</header>
{filters_html}
{''.join(body_parts)}
{errors_html}
</div>
<script>{js}</script>
</body>
</html>
"""
