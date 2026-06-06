"""Render aggregated events to a single self-contained HTML page."""
from __future__ import annotations

import calendar
import dataclasses
import hashlib
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
    "Concerti", "Teatro", "Cinema", "Film italiani", "Mostre",
    "Estate Fiorentina", "Circoli", "Biblioteche", "Civici", "Altro",
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


"""Quanto a lungo, dopo lo start, un evento è ancora considerato 'in corso'
quando non ha un end esplicito. 2 ore copre la maggior parte di concerti,
spettacoli, talk; eventi più brevi (es. proiezioni di 90 minuti) restano
visibili ancora per ~30 min dopo la fine, che è una grazia ragionevole."""
_DEFAULT_DURATION_HOURS = 2

# Oltre questa durata un evento con end è una "mostra in corso" (sezione
# dedicata), non un festival da espandere giorno-per-giorno nel programma.
_MULTIDAY_MAX_SPAN_DAYS = 14


def _expand_multiday(ev: Event, today: date) -> list[Event]:
    """Espande un festival (evento con end di pochi giorni) in una card per
    ogni giornata, da oggi alla chiusura. Ogni copia ha la stessa ora di
    inizio, nessun `end` (è atomica sul suo giorno) e una descrizione
    prefissata con 'Giorno N di M'."""
    total = (ev.end.date() - ev.start.date()).days + 1
    out: list[Event] = []
    for i in range(total):
        day = ev.start.date() + timedelta(days=i)
        if day < today:
            continue  # salta i giorni già passati del festival
        day_start = ev.start.replace(year=day.year, month=day.month, day=day.day)
        label = f"Giorno {i + 1} di {total}"
        desc = ev.description or ""
        new_desc = f"{label} · {desc}" if desc else label
        out.append(dataclasses.replace(
            ev, start=day_start, end=None, description=new_desc
        ))
    return out


def _is_past_today(ev: Event, now: datetime, today: date) -> bool:
    """True se l'evento è di oggi ma è già finito (e non è un all-day)."""
    if ev.start.date() != today:
        return False
    # All-day (mostra/sagra/giornata): resta visibile tutto il giorno.
    if ev.start.hour == 0 and ev.start.minute == 0:
        return False
    if ev.end is not None and ev.end > ev.start:
        return now > ev.end
    return now > ev.start + timedelta(hours=_DEFAULT_DURATION_HOURS)


_WS_RE = __import__("re").compile(r"\s+")


def _norm_for_id(s: str | None) -> str:
    """Normalizza una stringa per la generazione dell'event-id.

    Lowercase + collapse di whitespace + strip. Così differenze innocue
    come "Cinema Firenze" vs "Cinema  Firenze" (doppio spazio) o
    "Lo Straniero" vs "Lo straniero" non cambiano l'ID, preservando i
    preferiti/nascosti dell'utente attraverso gli aggiornamenti.
    """
    if not s:
        return ""
    return _WS_RE.sub(" ", s).strip().lower()


def _event_id(ev: Event) -> str:
    """Stable opaque ID for localStorage hide/favorite tracking.

    Include source+url+venue+titolo+data, ognuno normalizzato (lowercase,
    whitespace compattati) per essere resiliente alle piccole variazioni
    di formato che gli scraper possono introdurre fra una run e l'altra.

    Usa solo la DATA, non l'orario, perché preferiti/nascosti devono
    sopravvivere ai re-parse degli scraper: se un fix dello scraper
    cambia l'orario di un evento (es. PARC passato da 00:00 a 19:00
    quando ho fatto leggere lo span "ORE 19" separato), l'orario al
    minuto cambia ma l'evento è lo stesso — non vogliamo che l'utente
    perda i suoi preferiti per questa ragione.

    Venue è incluso per distinguere lo stesso film in cinema diversi
    (es. "Le città di pianura" alla Fiorella vs al Marconi).

    Trade-off accettato: due proiezioni dello stesso film nello stesso
    cinema lo stesso giorno (es. matinée + serale) condividono l'ID e
    quindi anche il preferito/nascondi. Caso raro, costo accettabile.
    """
    date_key = ev.start.strftime("%Y-%m-%d") if ev.start else ""
    parts = [
        _norm_for_id(ev.source),
        _norm_for_id(ev.url),
        _norm_for_id(ev.venue),
        _norm_for_id(ev.title),
        date_key,
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


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

/* Bottone "Filtri" — visibile solo su mobile (su desktop la sidebar è
   sempre aperta e il bottone viene nascosto dalla media query sotto).
   DEVE essere dichiarato PRIMA della media query desktop altrimenti il
   `display: inline-flex` vince per ordine di cascata. */
#filters-toggle {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    margin: .75rem 0 .25rem;
    background: var(--card-bg);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: .5rem .9rem;
    border-radius: 8px;
    font-size: .95rem;
    cursor: pointer;
    user-select: none;
}
#filters-toggle:hover { border-color: var(--accent); }
#filters-toggle .chev {
    transition: transform .15s;
    display: inline-block;
}
#filters-toggle[aria-expanded="true"] .chev { transform: rotate(180deg); }
#filters-toggle .filters-count {
    color: var(--muted);
    font-size: .82rem;
    margin-left: .25rem;
}
.sidebar.collapsed .filters { display: none; }

/* Layout 2 colonne su desktop: sidebar filtri a sinistra, eventi a destra.
   Breakpoint basso (720px) così anche finestre non massimizzate sui PC
   mostrano la sidebar laterale invece di un viewport stretto di tipo mobile. */
@media (min-width: 720px) {
    .container {
        max-width: 1200px;
        display: grid;
        grid-template-columns: 260px 1fr;
        gap: 2rem;
        align-items: start;
    }
    header { grid-column: 1 / -1; }
    .sidebar {
        position: sticky;
        top: 1rem;
        max-height: calc(100vh - 2rem);
        overflow-y: auto;
    }
    /* Su desktop in sidebar i filtri vanno verticali: etichetta sopra,
       pill sotto a wrap. Il container .filters perde la stretta orizzontale. */
    .sidebar .filters {
        border-bottom: none;
        padding: 0;
        margin: 0;
    }
    .sidebar .filter-row {
        flex-direction: column;
        align-items: flex-start;
        margin-bottom: 1.25rem;
    }
    .sidebar .filter-row .filter-label {
        margin-bottom: .35rem;
    }
    .sidebar .filter-actions {
        margin-left: 0;
        margin-top: .35rem;
    }
    /* Su desktop il toggle "Filtri" non serve: la sidebar è sempre aperta. */
    #filters-toggle { display: none; }
    /* In desktop la sidebar è sempre visibile, ignoro la classe collapsed. */
    .sidebar.collapsed .filters { display: block; }
}

/* Header giorno sticky mentre scrolli, così sai sempre in che data sei.
   Sfondo opaco che copre gli eventi sotto quando si "appiccica". */
h2.day {
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 5;
    padding-top: .5rem;
    /* Piccolo "scrim" sotto per stacco visivo quando è sticky */
    box-shadow: 0 6px 6px -6px var(--bg);
}

/* Stile compatto per smartphone (incluso landscape ~600px) */
@media (max-width: 600px) {
    body { padding: 1rem .75rem 3rem; }
    header h1 { font-size: 1.35rem; }
    header .meta { font-size: .82rem; }
    .event {
        padding: .65rem 3.4rem .65rem .8rem;
        margin-bottom: .45rem;
        grid-template-columns: 52px 1fr;
        gap: 0 .65rem;
    }
    .event .time { font-size: .9rem; }
    .event .title { font-size: .97rem; }
    .event .meta-line { font-size: .8rem; }
    .event .desc { font-size: .84rem; margin-top: .25rem; }
    .ongoing-event {
        padding: .6rem 3.4rem .6rem .8rem;
        margin-bottom: .4rem;
    }
    h2.day {
        font-size: 1rem;
        margin: 1.25rem 0 .5rem;
    }
    /* Tap-target più grandi per ×/★ */
    .hide-btn, .star-btn {
        opacity: .55;          /* su mobile sempre un po' visibili */
        padding: .35rem .55rem;
        font-size: 1.1rem;
    }
    .star-btn { font-size: 1.2rem; }
    .filter-pill {
        padding: .4rem .9rem;
        font-size: .9rem;
    }
}

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
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .5rem;
}
h2.day .day-label { flex: 1; min-width: 0; }
.day-collapse {
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: .25rem .55rem;
    border-radius: 4px;
    transition: color .15s, transform .15s, background .15s;
    flex-shrink: 0;
}
.day-collapse:hover {
    color: var(--accent);
    background: rgba(255, 106, 74, 0.08);
}
/* Quando il giorno e' collassato, il chevron punta verso destra. */
h2.day.collapsed .day-collapse { transform: rotate(-90deg); }
/* Gli eventi del giorno collassato sono nascosti finche' non viene riaperto. */
.event.day-collapsed { display: none; }
.event {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .85rem 3.6rem .85rem 1rem;
    margin-bottom: .6rem;
    display: grid;
    grid-template-columns: 64px 1fr;
    gap: 0 .9rem;
    position: relative;
}
.event.hidden, h2.day.hidden { display: none; }

/* Eventi gia' passati di oggi (orario di inizio < now-2h e nessuna end).
   Collassati: visibili ma compatti, opacita' ridotta e descrizione nascosta. */
.event.past-today {
    opacity: .45;
    padding-top: .45rem;
    padding-bottom: .45rem;
}
.event.past-today .desc { display: none; }
.event.past-today .meta-line { font-size: .78rem; }
.event.past-today .title { font-size: .92rem; font-weight: 500; }
/* Quando il toggle "Nascondi passati" e' attivo, spariscono del tutto. */
body.hide-past .event.past-today { display: none; }
.hide-btn, .star-btn {
    position: absolute;
    top: .25rem;
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font-size: 1.05rem;
    line-height: 1;
    padding: .25rem .4rem;
    border-radius: 4px;
    opacity: .35;
    transition: opacity .15s, color .15s, background .15s;
}
.hide-btn { right: 1.85rem; }
.star-btn { right: .35rem; font-size: 1.15rem; }
.hide-btn:hover {
    opacity: 1;
    color: var(--accent);
    background: rgba(255, 106, 74, 0.08);
}
.star-btn:hover {
    opacity: 1;
    color: #ffcc44;
    background: rgba(255, 204, 68, 0.10);
}
.star-btn.starred {
    opacity: 1;
    color: #ffcc44;
}
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
.ongoing-section .section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .5rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: .25rem;
    margin: 0 0 .75rem;
}
.ongoing-section h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--accent);
    margin: 0;
    padding: 0;
    border: none;
}
.section-toggle {
    background: none;
    border: 1px solid var(--border);
    color: var(--muted);
    cursor: pointer;
    font-size: .8rem;
    line-height: 1;
    padding: .3rem .55rem;
    border-radius: 4px;
    transition: color .15s, border-color .15s;
}
.section-toggle:hover { color: var(--accent); border-color: var(--accent); }
.ongoing-list.collapsed { display: none; }
.ongoing-section.hidden { display: none; }
.ongoing-event {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .75rem 3.6rem .75rem 1rem;
    margin-bottom: .5rem;
    position: relative;
}

.starred-section {
    margin: 1.5rem 0 .75rem;
    padding: .9rem 1rem 1rem;
    background: linear-gradient(180deg, rgba(255,204,68,.06), transparent);
    border: 1px solid rgba(255,204,68,.25);
    border-radius: 10px;
}
.starred-section.empty { display: none; }
.starred-section .section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .5rem;
    margin: 0 0 .75rem;
}
.starred-section h2 {
    font-size: 1.05rem;
    font-weight: 600;
    color: #ffcc44;
    margin: 0;
    padding: 0;
    border: none;
}
.starred-section .starred-event {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: .75rem 3.6rem .75rem 1rem;
    margin-bottom: .5rem;
    position: relative;
}
.starred-section .starred-event .time {
    color: var(--muted);
    font-size: .85rem;
    margin-right: .35rem;
    font-variant-numeric: tabular-nums;
}
.starred-section .starred-event .title { margin: 0 0 .15rem; font-size: 1rem; font-weight: 600; }
.starred-section .starred-event .title a { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--border); }
.starred-section .starred-event .title a:hover { border-bottom-color: #ffcc44; }
.starred-section .starred-event .meta-line { color: var(--muted); font-size: .85rem; }
.starred-section .starred-event .desc { color: var(--muted); font-size: .85rem; margin-top: .25rem; }
.starred-section .starred-event .closing { color: var(--accent); font-size: .82rem; margin-top: .2rem; }

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
    const HIDDEN_KEY = 'eventi-firenze-hidden';
    const STARRED_KEY = 'eventi-firenze-starred';
    const COLLAPSED_DAYS_KEY = 'eventi-firenze-collapsed-days';
    const UI_KEY = 'eventi-firenze-ui';
    const WEEK_END = __WEEK_END__;
    const NEXT_WEEK_START = __NEXT_WEEK_START__;
    const NEXT_WEEK_END = __NEXT_WEEK_END__;
    const MONTH_END = __MONTH_END__;
    const NEXT_MONTH_START = __NEXT_MONTH_START__;
    const NEXT_MONTH_END = __NEXT_MONTH_END__;
    const WEEKEND_START = __WEEKEND_START__;
    const WEEKEND_END = __WEEKEND_END__;
    const NEXT_WEEKEND_START = __NEXT_WEEKEND_START__;
    const NEXT_WEEKEND_END = __NEXT_WEEKEND_END__;
    const WINDOW_VALUES = ['week', 'next-week', 'weekend', 'next-weekend', 'month', 'next-month'];

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
                window: WINDOW_VALUES.includes(obj.window) ? obj.window : null,
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

    function loadHidden() {
        try {
            const raw = localStorage.getItem(HIDDEN_KEY);
            return raw ? new Set(JSON.parse(raw)) : new Set();
        } catch (e) { return new Set(); }
    }
    function saveHidden(s) {
        try { localStorage.setItem(HIDDEN_KEY, JSON.stringify(Array.from(s))); } catch (e) {}
    }

    // Preferiti come Map<id, snapshot>. Lo snapshot è una fotografia
    // completa dell'evento (titolo, data, luogo...) così il preferito resta
    // visibile anche se l'evento esce dal feed o se cambiano gli scraper —
    // niente più preferiti persi ad ogni aggiornamento.
    // Retrocompat: il vecchio formato era un array di soli id; lo carico come
    // Map con snapshot null e lo "promuovo" automaticamente alla prima
    // visualizzazione catturando i dati dalla card live.
    function loadStarred() {
        try {
            const raw = localStorage.getItem(STARRED_KEY);
            if (!raw) return new Map();
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                return new Map(parsed.map(id => [id, null]));  // legacy
            }
            return new Map(Object.entries(parsed));
        } catch (e) { return new Map(); }
    }
    function saveStarred(m) {
        try {
            localStorage.setItem(STARRED_KEY, JSON.stringify(Object.fromEntries(m)));
        } catch (e) {}
    }

    function _escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }
    // Cattura i dati visibili di una card per ricostruirla in futuro.
    function captureSnapshot(card) {
        const titleEl = card.querySelector('.title');
        const metaEl = card.querySelector('.meta-line');
        const descEl = card.querySelector('.desc');
        const closingEl = card.querySelector('.closing');
        const timeEl = card.querySelector('.time');
        return {
            titleHtml: titleEl ? titleEl.innerHTML : '',
            metaHtml: metaEl ? metaEl.innerHTML : '',
            desc: descEl ? descEl.textContent.trim() : '',
            closing: closingEl ? closingEl.textContent.trim() : '',
            isoDate: card.dataset.isoDate || '',
            time: timeEl ? timeEl.textContent.trim() : '',
            category: card.dataset.category || ''
        };
    }
    // Ricostruisce una card della sezione preferiti a partire dallo snapshot.
    function buildStarredCard(id, snap) {
        const div = document.createElement('div');
        div.className = 'starred-event';
        div.dataset.eventId = id;
        if (snap.category) div.dataset.category = snap.category;
        if (snap.isoDate) div.dataset.isoDate = snap.isoDate;

        // Etichetta tempo: "Sab 6 giu · 21:00" (le mostre con 'closing' no).
        let timeLabel = snap.time || '';
        if (!snap.closing && snap.isoDate) {
            const d = new Date(snap.isoDate + 'T00:00:00');
            if (!isNaN(d)) {
                let dl = d.toLocaleDateString('it-IT', {
                    weekday: 'short', day: 'numeric', month: 'short'
                });
                dl = dl.charAt(0).toUpperCase() + dl.slice(1);
                timeLabel = snap.time ? dl + ' · ' + snap.time : dl;
            }
        }

        let inner = '';
        if (timeLabel) inner += '<div class="time">' + _escapeHtml(timeLabel) + '</div>';
        inner += '<div class="body">';
        if (snap.titleHtml) inner += '<p class="title">' + snap.titleHtml + '</p>';
        if (snap.metaHtml) inner += '<div class="meta-line">' + snap.metaHtml + '</div>';
        if (snap.desc) inner += '<div class="desc">' + _escapeHtml(snap.desc) + '</div>';
        if (snap.closing) inner += '<div class="closing">' + _escapeHtml(snap.closing) + '</div>';
        inner += '</div>';
        inner += '<button class="hide-btn" data-event-id="' + id + '" title="Nascondi questo evento">×</button>';
        inner += '<button class="star-btn starred" data-event-id="' + id + '" title="Rimuovi dai preferiti">★</button>';
        div.innerHTML = inner;
        return div;
    }

    function loadCollapsedDays() {
        try {
            const raw = localStorage.getItem(COLLAPSED_DAYS_KEY);
            return raw ? new Set(JSON.parse(raw)) : new Set();
        } catch (e) { return new Set(); }
    }
    function saveCollapsedDays(s) {
        try { localStorage.setItem(COLLAPSED_DAYS_KEY, JSON.stringify(Array.from(s))); } catch (e) {}
    }

    function loadUI() {
        try {
            const raw = localStorage.getItem(UI_KEY);
            const obj = raw ? JSON.parse(raw) : {};
            return {
                ongoingCollapsed: !!obj.ongoingCollapsed,
                showHidden: !!obj.showHidden,
                hidePast: !!obj.hidePast,
                // filtri aperti di default; l'utente li chiude se vuole.
                filtersOpen: obj.filtersOpen !== false,
            };
        } catch (e) { return { ongoingCollapsed: false, showHidden: false, hidePast: false, filtersOpen: true }; }
    }
    function saveUI(s) {
        try { localStorage.setItem(UI_KEY, JSON.stringify(s)); } catch (e) {}
    }

    let state = loadState();
    if (state.cats.size === 0) state.cats = new Set(allCategories);
    let hidden = loadHidden();
    let starred = loadStarred();
    let collapsedDays = loadCollapsedDays();
    let ui = loadUI();

    // Ricostruisce la sezione "I tuoi preferiti" dagli snapshot salvati.
    // I preferiti restano visibili indipendentemente dal feed corrente.
    function renderStarred() {
        const section = document.getElementById('starred-section');
        const list = document.getElementById('starred-list');
        const count = document.getElementById('starred-count');
        if (!section || !list) return;
        list.innerHTML = '';

        // Pass 1: promuovi i legacy (snapshot null) catturando dalla card live.
        let mutated = false;
        starred.forEach((snap, id) => {
            if (!snap) {
                const orig = document.querySelector(
                    '.event[data-event-id="' + id + '"], .ongoing-event[data-event-id="' + id + '"]'
                );
                if (orig) { starred.set(id, captureSnapshot(orig)); mutated = true; }
            }
        });
        if (mutated) saveStarred(starred);

        // Pass 2: raccogli i renderizzabili, scarta i passati (non-mostra),
        // ordina per data e costruisci le card.
        const todayIso = new Date().toLocaleDateString('en-CA');  // YYYY-MM-DD locale
        const items = [];
        starred.forEach((snap, id) => {
            if (!snap) return;  // legacy non ancora in feed: non renderizzabile
            if (snap.isoDate && snap.isoDate < todayIso && !snap.closing) return;
            items.push([id, snap]);
        });
        items.sort((a, b) => (a[1].isoDate || '').localeCompare(b[1].isoDate || ''));
        items.forEach(([id, snap]) => list.appendChild(buildStarredCard(id, snap)));

        if (count) count.textContent = items.length ? '(' + items.length + ')' : '';
        section.classList.toggle('empty', items.length === 0);
        refreshStarButtons();
    }

    function refreshStarButtons() {
        document.querySelectorAll('.star-btn').forEach(btn => {
            const id = btn.dataset.eventId;
            const isStar = id && starred.has(id);
            btn.textContent = isStar ? '★' : '☆';
            btn.title = isStar ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti';
            btn.classList.toggle('starred', !!isStar);
        });
    }

    function passes(el) {
        const id = el.dataset.eventId;
        const isHidden = id && hidden.has(id);
        // "Nascosti" mode flips the meaning: only hidden items are shown.
        if (ui.showHidden) {
            if (!isHidden) return false;
        } else {
            if (isHidden) return false;
        }
        if (!state.cats.has(el.dataset.category)) return false;
        // Ongoing exhibits (in the "Mostre in corso" section) always pass
        // window/time-of-day filters because they're open today by definition.
        if (el.classList.contains('ongoing-event')) return true;
        const iso = el.dataset.isoDate;
        if (state.window === 'week' && iso > WEEK_END) return false;
        if (state.window === 'next-week' && (iso < NEXT_WEEK_START || iso > NEXT_WEEK_END)) return false;
        if (state.window === 'month' && iso > MONTH_END) return false;
        if (state.window === 'next-month' && (iso < NEXT_MONTH_START || iso > NEXT_MONTH_END)) return false;
        if (state.window === 'weekend' && (iso < WEEKEND_START || iso > WEEKEND_END)) return false;
        if (state.window === 'next-weekend' && (iso < NEXT_WEEKEND_START || iso > NEXT_WEEKEND_END)) return false;
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
            // Stato "giorno collassato": indipendente da filtri/nascosti.
            const iso = el.dataset.isoDate;
            el.classList.toggle('day-collapsed', !!(iso && collapsedDays.has(iso)));
        });
        document.querySelectorAll('h2.day').forEach(h => {
            const iso = h.dataset.isoDate;
            // Stato visivo collassato (chevron ruotato).
            h.classList.toggle('collapsed', !!(iso && collapsedDays.has(iso)));
            // Cerca almeno un evento del giorno che passi i filtri. Se il
            // giorno è collassato l'h2 rimane comunque visibile (cosi'
            // l'utente puo' riaprirlo), a meno che TUTTI gli eventi siano
            // filtrati via — in quel caso nasconde anche l'h2.
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
        // Per-event hide button: × normally, ↺ when in "Nascosti" mode on a hidden item.
        document.querySelectorAll('.hide-btn').forEach(btn => {
            const id = btn.dataset.eventId;
            const isHidden = id && hidden.has(id);
            btn.textContent = isHidden ? '↺' : '×';
            btn.title = isHidden ? 'Ripristina questo evento' : 'Nascondi questo evento';
        });
        // "Nascosti" pill: visible only if there's at least one hidden item.
        const nascostiPill = document.getElementById('filter-nascosti');
        if (nascostiPill) {
            const n = hidden.size;
            const countEl = nascostiPill.querySelector('.count');
            if (countEl) countEl.textContent = n;
            nascostiPill.style.display = n > 0 ? '' : 'none';
            nascostiPill.classList.toggle('active', ui.showHidden);
            if (n === 0 && ui.showHidden) {
                // Auto-leave "Nascosti" mode when nothing is hidden anymore.
                ui.showHidden = false;
                saveUI(ui);
                nascostiPill.classList.remove('active');
            }
        }
        // Ongoing section collapse state.
        const ongoingList = document.getElementById('ongoing-list');
        const ongoingToggle = document.getElementById('ongoing-toggle');
        if (ongoingList) ongoingList.classList.toggle('collapsed', ui.ongoingCollapsed);
        if (ongoingToggle) {
            ongoingToggle.textContent = ui.ongoingCollapsed ? 'Mostra' : 'Nascondi';
            ongoingToggle.setAttribute('aria-expanded', ui.ongoingCollapsed ? 'false' : 'true');
        }
        // Toggle filtri (mobile): sidebar aperta/chiusa + label conteggio attivi.
        const sidebar = document.getElementById('sidebar-filters');
        const filtersToggle = document.getElementById('filters-toggle');
        if (sidebar && filtersToggle) {
            sidebar.classList.toggle('collapsed', !ui.filtersOpen);
            filtersToggle.setAttribute('aria-expanded', ui.filtersOpen ? 'true' : 'false');
            // Conteggio filtri attivi (categorie non-default + periodo + orario)
            let activeBits = 0;
            if (state.cats.size && state.cats.size < allCategories.length) activeBits++;
            if (state.window) activeBits++;
            if (state.weekdayTime) activeBits++;
            if (ui.hidePast) activeBits++;
            if (ui.showHidden) activeBits++;
            const countEl = document.getElementById('filters-active-count');
            if (countEl) countEl.textContent = activeBits ? `· ${activeBits} attiv${activeBits === 1 ? 'o' : 'i'}` : '';
        }
        // Toggle "Nascondi passati di oggi": classe sul body + stato pill.
        document.body.classList.toggle('hide-past', ui.hidePast);
        const hidePastPill = document.getElementById('filter-hide-past');
        if (hidePastPill) {
            const pastCount = document.querySelectorAll('.event.past-today').length;
            hidePastPill.style.display = pastCount > 0 ? '' : 'none';
            hidePastPill.classList.toggle('active', ui.hidePast);
            // Aggiorno la label con il count
            hidePastPill.firstChild.nodeValue = pastCount > 0
                ? 'Nascondi passati '
                : 'Nascondi passati';
            // Aggiungo span count se non c'e'
            let countEl = hidePastPill.querySelector('.count');
            if (!countEl && pastCount > 0) {
                countEl = document.createElement('span');
                countEl.className = 'count';
                hidePastPill.appendChild(countEl);
            }
            if (countEl) countEl.textContent = pastCount;
        }
        const anyVisible = document.querySelector('.event:not(.hidden), .ongoing-event:not(.hidden)');
        const empty = document.getElementById('empty-filter');
        if (empty) empty.style.display = anyVisible ? 'none' : 'block';
    }

    document.querySelectorAll('.filter-pill[data-category]').forEach(p => {
        p.addEventListener('click', () => {
            const cat = p.dataset.category;
            if (state.cats.size === allCategories.length) {
                // Si parte da "tutto attivo": il primo click isola la categoria scelta.
                state.cats = new Set([cat]);
            } else if (state.cats.has(cat)) {
                // Categoria gia' attiva: la rimuovo (toggle off).
                state.cats.delete(cat);
                // Se ho appena rimosso l'ultima, torno al default "tutto attivo".
                if (state.cats.size === 0) state.cats = new Set(allCategories);
            } else {
                // Categoria non attiva: la aggiungo all'accumulo.
                state.cats.add(cat);
            }
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

    // Event delegation: gestisce × e ★ anche sui cloni della sezione preferiti.
    document.addEventListener('click', (e) => {
        const hideBtn = e.target.closest('.hide-btn');
        if (hideBtn) {
            e.preventDefault(); e.stopPropagation();
            const id = hideBtn.dataset.eventId;
            if (!id) return;
            if (hidden.has(id)) hidden.delete(id);
            else hidden.add(id);
            saveHidden(hidden);
            apply();
            return;
        }
        const starBtn = e.target.closest('.star-btn');
        if (starBtn) {
            e.preventDefault(); e.stopPropagation();
            const id = starBtn.dataset.eventId;
            if (!id) return;
            if (starred.has(id)) {
                starred.delete(id);
            } else {
                // Cattura lo snapshot dalla card cliccata così il preferito
                // sopravvive anche se l'evento poi esce dal feed.
                const card = starBtn.closest('.event, .ongoing-event, .starred-event');
                starred.set(id, card ? captureSnapshot(card) : {});
            }
            saveStarred(starred);
            renderStarred();
            return;
        }
        const dayBtn = e.target.closest('.day-collapse');
        if (dayBtn) {
            e.preventDefault(); e.stopPropagation();
            const iso = dayBtn.dataset.isoDate;
            if (!iso) return;
            if (collapsedDays.has(iso)) collapsedDays.delete(iso);
            else collapsedDays.add(iso);
            saveCollapsedDays(collapsedDays);
            apply();
            return;
        }
    });

    const nascostiPill = document.getElementById('filter-nascosti');
    if (nascostiPill) {
        nascostiPill.addEventListener('click', () => {
            if (hidden.size === 0) return;
            ui.showHidden = !ui.showHidden;
            saveUI(ui);
            apply();
        });
    }

    const ongoingToggle = document.getElementById('ongoing-toggle');
    if (ongoingToggle) {
        ongoingToggle.addEventListener('click', () => {
            ui.ongoingCollapsed = !ui.ongoingCollapsed;
            saveUI(ui);
            apply();
        });
    }

    const hidePastPill = document.getElementById('filter-hide-past');
    if (hidePastPill) {
        hidePastPill.addEventListener('click', () => {
            ui.hidePast = !ui.hidePast;
            saveUI(ui);
            apply();
        });
    }

    const filtersToggleBtn = document.getElementById('filters-toggle');
    if (filtersToggleBtn) {
        filtersToggleBtn.addEventListener('click', () => {
            ui.filtersOpen = !ui.filtersOpen;
            saveUI(ui);
            apply();
        });
    }

    apply();
    renderStarred();
})();
"""


def _compute_boundaries(today: date) -> dict[str, str]:
    """ISO date boundaries per i pill 'Periodo'.

    Definizioni:
      week        = oggi → domenica della settimana corrente
      next-week   = lunedì → domenica della settimana successiva
      weekend     = venerdì → domenica del weekend in corso o più imminente
                    (il venerdì è incluso, anche se è passato e siamo già a
                     sabato/domenica: gli eventi passati sono comunque
                     filtrati a monte da run.py).
      next-weekend = il weekend Ven-Dom dopo quello "weekend".
      month       = oggi → ultimo giorno del mese corrente
      next-month  = primo → ultimo giorno del mese successivo
    """
    wd = today.weekday()  # 0=Lun, 6=Dom

    # Questa settimana → fino a domenica corrente
    week_end = today + timedelta(days=(6 - wd))
    # Prossima settimana → lun-dom successivi
    next_week_start = today + timedelta(days=(7 - wd))
    next_week_end = next_week_start + timedelta(days=6)

    # Weekend = Ven + Sab + Dom
    if wd <= 4:  # Lun-Ven
        weekend_start = today + timedelta(days=(4 - wd))
    elif wd == 5:  # Sab → ven era ieri
        weekend_start = today - timedelta(days=1)
    else:  # Dom → ven era 2 giorni fa
        weekend_start = today - timedelta(days=2)
    weekend_end = weekend_start + timedelta(days=2)

    # Prossimo weekend = +7 giorni rispetto a quello corrente
    next_weekend_start = weekend_start + timedelta(days=7)
    next_weekend_end = weekend_end + timedelta(days=7)

    # Mesi
    last_dom = calendar.monthrange(today.year, today.month)[1]
    month_end = today.replace(day=last_dom)
    nm_year = today.year + (1 if today.month == 12 else 0)
    nm_month = 1 if today.month == 12 else today.month + 1
    next_month_start = date(nm_year, nm_month, 1)
    next_month_end = date(
        nm_year, nm_month, calendar.monthrange(nm_year, nm_month)[1]
    )

    return {
        "week_end": week_end.isoformat(),
        "next_week_start": next_week_start.isoformat(),
        "next_week_end": next_week_end.isoformat(),
        "weekend_start": weekend_start.isoformat(),
        "weekend_end": weekend_end.isoformat(),
        "next_weekend_start": next_weekend_start.isoformat(),
        "next_weekend_end": next_weekend_end.isoformat(),
        "month_end": month_end.isoformat(),
        "next_month_start": next_month_start.isoformat(),
        "next_month_end": next_month_end.isoformat(),
    }


def render(
    events: Iterable[Event],
    errors: list[tuple[str, str]],
    generated_at: datetime,
    source_count: int,
) -> str:
    now = generated_at.astimezone(ROME)
    today = now.date()
    bounds = _compute_boundaries(today)
    events = sorted(events, key=lambda e: e.sort_key())

    ongoing: list[Event] = []
    regular: list[Event] = []
    for ev in events:
        span = (ev.end.date() - ev.start.date()).days if ev.end is not None else 0
        if (
            ev.end is not None
            and span > _MULTIDAY_MAX_SPAN_DAYS
            and ev.start.date() <= today <= ev.end.date()
        ):
            # Mostra lunga attualmente in corso → sezione "Mostre in corso".
            ongoing.append(ev)
        elif ev.end is not None and 1 <= span <= _MULTIDAY_MAX_SPAN_DAYS:
            # Festival/rassegna breve → una card per ogni giornata.
            regular.extend(_expand_multiday(ev, today))
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
        '<div class="filter-pill" data-window="next-week">Prossima settimana</div>'
        '<div class="filter-pill" data-window="weekend">Weekend</div>'
        '<div class="filter-pill" data-window="next-weekend">Prossimo weekend</div>'
        '<div class="filter-pill" data-window="month">Questo mese</div>'
        '<div class="filter-pill" data-window="next-month">Prossimo mese</div>'
    )
    weekday_time_pills_html = (
        '<div class="filter-pill" data-weekday-time="after14">Feriali dalle 14:00</div>'
        '<div class="filter-pill" data-weekday-time="after17">Feriali dalle 17:00</div>'
    )
    # Always render the "Nascosti" pill; JS hides it when count is 0.
    nascosti_pill_html = (
        '<div class="filter-pill" id="filter-nascosti" style="display:none">'
        'Nascosti<span class="count">0</span>'
        '</div>'
    )
    # Pill "Nascondi passati di oggi". Visibile sempre, JS la disattiva se
    # non ci sono past-today da nascondere.
    hide_past_pill_html = (
        '<div class="filter-pill" id="filter-hide-past" title="Nascondi gli '
        'eventi di oggi che sono gi&agrave; finiti">Nascondi passati</div>'
    )
    filters_html = (
        '<div class="filters">'
        f'<div class="filter-row"><span class="filter-label">Categorie</span>{cat_pills_html}'
        f'{nascosti_pill_html}'
        '<div class="filter-actions"><button id="filter-all">Reset</button></div></div>'
        f'<div class="filter-row"><span class="filter-label">Periodo</span>{window_pills_html}</div>'
        f'<div class="filter-row"><span class="filter-label">Orario</span>{weekday_time_pills_html}{hide_past_pill_html}</div>'
        '</div>'
    )

    body_parts: list[str] = []

    # "I tuoi preferiti" section: populated by JS at load time from localStorage.
    # Rendered always (hidden via .empty class while empty).
    body_parts.append(
        '<div class="starred-section empty" id="starred-section">'
        '<div class="section-header">'
        '<h2>★ I tuoi preferiti</h2>'
        '<span class="starred-count" id="starred-count"></span>'
        '</div>'
        '<div class="starred-list" id="starred-list"></div>'
        '</div>'
    )

    # "Mostre in corso" section: long-running exhibits already open today.
    if ongoing:
        ongoing_html_parts = [
            f'<div class="ongoing-section" id="ongoing-section">'
            f'<div class="section-header">'
            f'<h2>Mostre in corso ({len(ongoing)})</h2>'
            f'<button class="section-toggle" id="ongoing-toggle" '
            f'aria-expanded="true" aria-controls="ongoing-list" '
            f'title="Mostra/nascondi la lista">Nascondi</button>'
            f'</div>'
            f'<div class="ongoing-list" id="ongoing-list">'
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
            ev_id = _event_id(ev)
            ongoing_html_parts.append(
                f'<div class="ongoing-event" '
                f'data-category="{_esc(ev.category or "Altro")}" '
                f'data-event-id="{ev_id}">'
                f'<button class="hide-btn" data-event-id="{ev_id}" '
                f'title="Nascondi questo evento">×</button>'
                f'<button class="star-btn" data-event-id="{ev_id}" '
                f'title="Aggiungi ai preferiti">☆</button>'
                f'<p class="title">{title_html}</p>'
                f'<div class="meta-line">{" · ".join(meta_bits)}</div>'
                f'<div class="closing">{_esc(closing_str)}</div>'
                f'</div>'
            )
        ongoing_html_parts.append('</div></div>')
        body_parts.append("".join(ongoing_html_parts))

    if not events:
        body_parts.append('<p class="empty">Nessun evento trovato.</p>')
    elif not by_day and not ongoing:
        body_parts.append('<p class="empty">Nessun evento trovato.</p>')
    else:
        for day in sorted(by_day.keys()):
            day_iso = day.isoformat()
            body_parts.append(
                f'<h2 class="day" data-iso-date="{day_iso}">'
                f'<span class="day-label">{_esc(_format_date_header(day))}</span>'
                f'<button class="day-collapse" data-iso-date="{day_iso}" '
                f'title="Nascondi/mostra gli eventi di questo giorno" '
                f'aria-label="Collassa giorno">▾</button>'
                f'</h2>'
            )
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
                ev_id = _event_id(ev)
                # Per il calcolo "passato di oggi" servono start/end aware.
                start_aware = ev.start if ev.start.tzinfo else ev.start.replace(tzinfo=ROME)
                end_aware = None
                if ev.end is not None:
                    end_aware = ev.end if ev.end.tzinfo else ev.end.replace(tzinfo=ROME)
                past = _is_past_today(
                    Event(source=ev.source, title=ev.title, start=start_aware,
                          url=ev.url, end=end_aware),
                    now, today,
                )
                past_class = " past-today" if past else ""
                body_parts.append(
                    f'<div class="event{past_class}" '
                    f'data-category="{_esc(ev.category or "Altro")}" '
                    f'data-iso-date="{iso_date}" '
                    f'data-time-min="{time_min}" '
                    f'data-event-id="{ev_id}">'
                    f'<div class="time">{_esc(time_str)}</div>'
                    f'<div class="body">'
                    f'<p class="title">{title_html}</p>'
                    f'<div class="meta-line">{" · ".join(meta_bits)}</div>'
                    f'{desc_html}'
                    f'</div>'
                    f'<button class="hide-btn" data-event-id="{ev_id}" '
                    f'title="Nascondi questo evento">×</button>'
                    f'<button class="star-btn" data-event-id="{ev_id}" '
                    f'title="Aggiungi ai preferiti">☆</button>'
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
        .replace("__NEXT_WEEK_START__", f'"{bounds["next_week_start"]}"')
        .replace("__NEXT_WEEK_END__", f'"{bounds["next_week_end"]}"')
        .replace("__MONTH_END__", f'"{bounds["month_end"]}"')
        .replace("__NEXT_MONTH_START__", f'"{bounds["next_month_start"]}"')
        .replace("__NEXT_MONTH_END__", f'"{bounds["next_month_end"]}"')
        .replace("__WEEKEND_START__", f'"{bounds["weekend_start"]}"')
        .replace("__WEEKEND_END__", f'"{bounds["weekend_end"]}"')
        .replace("__NEXT_WEEKEND_START__", f'"{bounds["next_weekend_start"]}"')
        .replace("__NEXT_WEEKEND_END__", f'"{bounds["next_weekend_end"]}"')
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
<button id="filters-toggle" type="button" aria-controls="sidebar-filters" aria-expanded="true">
<span>🎚 Filtri</span><span class="chev">▾</span><span class="filters-count" id="filters-active-count"></span>
</button>
<aside class="sidebar" id="sidebar-filters">
{filters_html}
</aside>
<main class="main-content">
{''.join(body_parts)}
{errors_html}
</main>
</div>
<script>{js}</script>
</body>
</html>
"""
