"""Rileva festival/rassegne multi-giorno NUOVI nei feed civici del Comune.

Gli eventi "spalmati" su più giorni (festival, rassegne, arene) vengono
annunciati dal Comune con una sola voce. Per il programma DETTAGLIATO serata
per serata serve un passaggio manuale (vedi sources/rassegne_estive.py). Questo
script gira ogni giorno nel workflow GitHub Actions e segnala quando spunta un
festival multi-giorno MAI VISTO PRIMA, così non sfugge nulla.

Meccanica:
  • legge output/events.json (prodotto da run.py);
  • tiene un "festival" se: viene da una fonte civica, dura più giorni (ha un
    `end` su un giorno diverso dallo `start`) e il testo contiene parole da
    programma (festival, rassegna, cinema, concerti, ecc.);
  • confronta con il registro data/seen_festivals.json (URL già visti);
  • i NUOVI finiscono in output/new_festivals_report.md e vengono aggiunti al
    registro. Exit code 1 se ce ne sono → il workflow apre una issue.

Così ogni festival viene segnalato UNA volta sola, senza spam.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS_FILE = ROOT / "output" / "events.json"
LEDGER_FILE = ROOT / "data" / "seen_festivals.json"
REPORT_FILE = ROOT / "output" / "new_festivals_report.md"

# Solo i feed civici "annuncio" (i festival che già abbiamo come fonti dedicate
# non passano di qui con un URL del Comune da segnalare).
CIVIC_SOURCES = {"Comune di Firenze", "Cultura Comune Firenze"}
# Parole che indicano un programma con appuntamenti (non una mostra statica).
_PROGRAM_RE = re.compile(
    r"festival|rassegna|arena|cinema|concert|spettacol|musica|danz|teatr|"
    r"proiezion|\blive\b|jazz|sonorizzaz|reading|dj\b",
    re.IGNORECASE,
)
# Non-festival ricorrenti/rumore da NON segnalare (riepiloghi, avvisi, servizi).
_EXCLUDE_RE = re.compile(
    r"best of the week|best week|allerta|ondata di calore|navetta|infoday|"
    r"avviso|chiusura|sciopero",
    re.IGNORECASE,
)


def _load_ledger() -> set[str]:
    if not LEDGER_FILE.exists():
        return set()
    try:
        data = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_ledger(seen: set[str]) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(
        json.dumps({"seen": sorted(seen)}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def _is_multiday_festival(ev: dict) -> bool:
    if ev.get("source") not in CIVIC_SOURCES:
        return False
    if not ev.get("end"):
        return False
    try:
        start = datetime.fromisoformat(ev["start"]).date()
        end = datetime.fromisoformat(ev["end"]).date()
    except (ValueError, KeyError):
        return False
    if end <= start:  # serve un arco di più giorni
        return False
    text = f"{ev.get('title', '')} {ev.get('description') or ''}"
    if _EXCLUDE_RE.search(text):
        return False
    return bool(_PROGRAM_RE.search(text))


def _fmt_range(ev: dict) -> str:
    s = datetime.fromisoformat(ev["start"]).date()
    e = datetime.fromisoformat(ev["end"]).date()
    return f"{s.strftime('%d/%m')}–{e.strftime('%d/%m/%Y')}"


def main() -> int:
    if not EVENTS_FILE.exists():
        print(f"[detect-festivals] {EVENTS_FILE} non trovato — esegui run.py prima.")
        return 0

    events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    seen = _load_ledger()

    new: list[dict] = []
    seen_now = set(seen)
    for ev in events:
        if not _is_multiday_festival(ev):
            continue
        url = ev.get("url") or ""
        if not url or url in seen_now:
            continue
        new.append(ev)
        seen_now.add(url)

    _save_ledger(seen_now)

    if not new:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(
            f"# Festival · {date.today().isoformat()}\n\n"
            "Nessun nuovo festival multi-giorno da approfondire.\n",
            encoding="utf-8",
        )
        print("[detect-festivals] Nessun nuovo festival.")
        return 0

    new.sort(key=lambda e: e["start"])
    lines = [
        f"# 🎪 Nuovi festival multi-giorno · {date.today().isoformat()}",
        "",
        f"Trovati {len(new)} festival/rassegne multi-giorno non ancora "
        "approfonditi serata-per-serata. Per ognuno conviene controllare il "
        "programma ufficiale e, se ha appuntamenti distinti con orario, "
        "trascriverli in `sources/rassegne_estive.py`.",
        "",
    ]
    for ev in new:
        lines.append(f"- **{ev['title']}** — {_fmt_range(ev)}")
        lines.append(f"  - {ev.get('url')}")
        desc = (ev.get("description") or "").strip()
        if desc:
            lines.append(f"  - _{desc[:200]}_")
    lines += [
        "",
        "*Issue generata automaticamente. Quando approfonditi, chiudere a mano.*",
    ]
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for ev in new:
        print(f"[detect-festivals] NUOVO: {ev['title']} ({_fmt_range(ev)})",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
