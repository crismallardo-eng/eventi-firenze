"""Health check delle fonti di scraping.

Si esegue dopo `python run.py`. Legge `output/run_summary.json`, appende ogni
fonte allo storico (`data/health_history.jsonl`, una riga per source/giorno),
poi confronta il count odierno con la mediana degli ultimi N run.

Una fonte viene flaggata come ANOMALIA quando:
  - il count odierno è 0
  - la mediana dei precedenti WINDOW run (escluso oggi) è >= MIN_BASELINE

Output:
  - `output/health_report.md` — sempre scritto. Se nessuna anomalia il body
    è una nota "tutto OK". Altrimenti elenco delle fonti crollate.
  - exit code 0 se tutto OK, 1 se sono state trovate anomalie. Il workflow
    GitHub Actions usa l'exit code per decidere se aprire una issue.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_FILE = ROOT / "output" / "run_summary.json"
HISTORY_FILE = ROOT / "data" / "health_history.jsonl"
REPORT_FILE = ROOT / "output" / "health_report.md"

WINDOW = 7         # quanti run precedenti considerare per la mediana
MIN_BASELINE = 3   # se la mediana < MIN_BASELINE non flaggo
# Ignora fonti note per essere "a fasi stagionali" — quando danno 0 fuori
# stagione è normale (es. Estate Fiorentina non pubblica fra ott-mag).
SEASONAL_SOURCES = {
    "Estate Fiorentina",
    "Pistoia Blues",
    "MetJazz",
    # Todo Modo: scraper statico, può legittimamente svuotarsi fra una
    # newsletter e l'altra finché l'utente non aggiorna sources/todomodo.py.
    "Todo Modo",
    # Lumen: scraper statico con il calendario stagionale.
    "Lumen",
    # Firenze Rocks: lineup pubblicata come immagine, scraper statico
    # (vuoto finché non si inseriscono a mano le date dell'edizione).
    "Firenze Rocks",
    # Secret Florence: rassegna estiva, fuori stagione la pagina programma
    # dell'anno può non esistere ancora.
    "Secret Florence",
    # Stensen Manifattura: arena cinema estiva; fuori stagione l'articolo del
    # programma dell'anno non esiste ancora.
    "Stensen Manifattura",
    # Musicus Concentus e Circolo Il Progresso: piccoli promoter/circoli che
    # restano legittimamente senza eventi futuri pubblicati per settimane
    # (es. d'estate). Lo scraper funziona, il feed è solo vuoto.
    "Musicus Concentus",
    "Circolo Il Progresso",
    # Altre arene cinema estive e festival stagionali (vuoti fuori stagione).
    "Esterno Notte Poggetto",
    "Apriti Cinema",
    "Arena Chiardiluna",
    "Estate Fiesolana",
    "Musart Festival",
    "Festival au Désert",
    "Firenze Jazz Festival",
}


def _load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    rows: list[dict] = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _append_today(today: str, counts: dict[str, int]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        for source, count in sorted(counts.items()):
            f.write(json.dumps({
                "date": today,
                "source": source,
                "count": int(count),
            }, ensure_ascii=False) + "\n")


def _detect_anomalies(today: str, rows: list[dict]) -> list[dict]:
    """Per ogni source, mediana ultimi N escluso oggi vs count odierno."""
    by_source: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append((r["date"], int(r["count"])))

    out: list[dict] = []
    for source, history in by_source.items():
        if source in SEASONAL_SOURCES:
            continue
        history.sort(key=lambda x: x[0])
        today_entries = [c for d, c in history if d == today]
        if not today_entries:
            continue
        last_count = today_entries[-1]
        baseline_counts = [c for d, c in history if d != today][-WINDOW:]
        if not baseline_counts:
            continue
        baseline_median = median(baseline_counts)
        if baseline_median >= MIN_BASELINE and last_count == 0:
            out.append({
                "source": source,
                "today": last_count,
                "baseline_median": baseline_median,
                "baseline_window": len(baseline_counts),
                "baseline_counts": baseline_counts,
            })
    return out


def _write_report(today: str, anomalies: list[dict], total_sources: int) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not anomalies:
        REPORT_FILE.write_text(
            f"# Health check eventi-firenze · {today}\n\n"
            f"Tutte le {total_sources} fonti monitorate sono OK.\n",
            encoding="utf-8",
        )
        return

    lines = [
        f"# ⚠️ Anomalie scraping eventi-firenze · {today}",
        "",
        f"{len(anomalies)} fonte/i sono crollate a 0 eventi pur avendo "
        f"una baseline storica >= {MIN_BASELINE}:",
        "",
    ]
    for a in anomalies:
        recent = ", ".join(str(c) for c in a["baseline_counts"])
        lines.append(
            f"- **{a['source']}** — oggi: **0** · mediana ultimi "
            f"{a['baseline_window']} run: **{a['baseline_median']}** "
            f"(serie: {recent})"
        )
    lines += [
        "",
        "## Cosa controllare",
        "1. Aprire il sito sorgente in un browser per verificare se è online "
        "e contiene effettivamente eventi pubblicati.",
        "2. Confrontare la struttura HTML attuale con quella attesa dallo "
        "scraper (selettori CSS, formato date).",
        "3. Verificare nei log dell'ultimo workflow run se la fonte ha "
        "ritornato 403 / 503 / timeout (problema temporaneo lato server "
        "vs. cambio strutturale del sito).",
        "",
        "*Issue generato automaticamente. Quando risolto, chiudere a mano.*",
    ]
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not SUMMARY_FILE.exists():
        print(f"[health-check] {SUMMARY_FILE} non trovato — esegui run.py prima.")
        return 0

    summary = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    today = summary.get("date") or date.today().isoformat()
    counts: dict[str, int] = summary.get("sources") or {}

    # Persisti i count di oggi nello storico
    _append_today(today, counts)

    # Carica TUTTO lo storico (incluso quello appena scritto)
    rows = _load_history()

    anomalies = _detect_anomalies(today, rows)
    _write_report(today, anomalies, total_sources=len(counts))

    if anomalies:
        for a in anomalies:
            print(
                f"[health-check] ANOMALIA: {a['source']} → 0 "
                f"(mediana {a['baseline_median']} su {a['baseline_window']} run)",
                file=sys.stderr,
            )
        return 1

    print(f"[health-check] Tutte le {len(counts)} fonti OK · report in {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
