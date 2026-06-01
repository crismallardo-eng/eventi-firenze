"""Aggregate Florence cultural events into a single HTML page."""
from __future__ import annotations

import importlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from pathlib import Path

# Windows console defaults to cp1252; force UTF-8 so non-ASCII titles print cleanly.
# line_buffering=True flushes after every newline so progress is visible in real
# time when stdout is captured to a file (background runs, .bat redirected logs).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from sources.base import Event, ROME
from renderer import render

# List of source modules to try, in order. Each module must expose:
#   SOURCE_NAME: str
#   def fetch() -> list[Event]
SOURCE_MODULES = [
    "sources.musicus_concentus",
    "sources.parc",
    "sources.villa_bardini",
    "sources.comune_firenze",
    "sources.biblioteche",
    "sources.unifi",
    "sources.firenze_al_cinema",
    "sources.mymovies_cinema",
    "sources.il_progresso",
    "sources.arci_firenze",
    "sources.museo_novecento",
    "sources.palazzo_strozzi",
    "sources.mad",
    "sources.cultura_comune",
    "sources.teatro_maggio",
    "sources.teatro_pergola",
    "sources.teatro_verdi",
    "sources.tempo_reale",
    "sources.estate_fiorentina",
    "sources.metjazz",
    "sources.pistoia_blues",
    "sources.flore_music_festival",
    "sources.todomodo",
]

# Only show events within this window from "now". Past events are dropped.
HORIZON_DAYS = 90

# Wall-clock timeout per source. If a source hangs beyond this (typically
# due to a flaky third-party server), we abandon it and move on. The thread
# may continue running in the background until the process exits — that's
# acceptable for a one-shot CLI tool.
SOURCE_TIMEOUT_SEC = 90

# Drop events whose title/description contain any of these whole-word terms.
# Used to hide kid/family-oriented activities from the main library/civic feeds.
EXCLUDE_KEYWORDS = [
    r"bambin[oiae]",
    r"bimb[oiae]",
    r"mamm[ae]", r"mammina",
    r"papà",
    r"genitor[ie]",
    r"famigli[ae]",
    r"piccolissim[oi]",
    r"baby",
    r"fiab[ae]",
    r"festa della mamma",
    r"festa del papà",
    r"merenda",
    r"laboratorio per (?:i )?(?:più )?piccoli",
]
_EXCLUDE_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(EXCLUDE_KEYWORDS) + r")(?!\w)",
    re.IGNORECASE,
)


def _is_family_event(event) -> bool:
    """Return True if title or description mentions a family/kids keyword."""
    text = f"{event.title} {event.description or ''}"
    return bool(_EXCLUDE_RE.search(text))


def main() -> int:
    now = datetime.now(tz=ROME)
    horizon = now + timedelta(days=HORIZON_DAYS)
    # All-day events come in at 00:00; treat them as valid for the whole day.
    cutoff_past = now.replace(hour=0, minute=0, second=0, microsecond=0)

    all_events: list[Event] = []
    errors: list[tuple[str, str]] = []
    successful_sources = 0
    # Per-source counts (post-filter), per health monitoring.
    source_counts: dict[str, int] = {}
    failed_sources: list[str] = []

    for module_path in SOURCE_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001
            errors.append((module_path, f"import: {exc}"))
            continue

        name = getattr(mod, "SOURCE_NAME", module_path)
        category = getattr(mod, "CATEGORY", "Altro")
        # Run fetch() in a thread with a wall-clock timeout, so a hung
        # source can't stall the whole pipeline.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix=name) as ex:
            future = ex.submit(mod.fetch)
            try:
                events = future.result(timeout=SOURCE_TIMEOUT_SEC)
            except FutureTimeout:
                ex.shutdown(wait=False, cancel_futures=True)
                errors.append((name, f"timeout dopo {SOURCE_TIMEOUT_SEC}s"))
                print(f"  {name}: TIMEOUT (>{SOURCE_TIMEOUT_SEC}s, abbandonato)")
                source_counts[name] = 0
                failed_sources.append(name)
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append((name, f"{type(exc).__name__}: {exc}"))
                print(f"  {name}: ERRORE — {type(exc).__name__}: {exc}")
                source_counts[name] = 0
                failed_sources.append(name)
                continue

        kept = 0
        skipped_family = 0
        for ev in events:
            start = ev.start
            if start.tzinfo is None:
                start = start.replace(tzinfo=ROME)
            end = ev.end
            if end is not None and end.tzinfo is None:
                end = end.replace(tzinfo=ROME)
            # Keep if event window overlaps the visible window. For
            # ongoing exhibitions (start in past, end in future) we keep
            # them so they can land in the "Mostre in corso" section.
            effective_end = end or start
            if effective_end < cutoff_past or start > horizon:
                continue
            if _is_family_event(ev):
                skipped_family += 1
                continue
            # Tag the event with the source's category for the UI filter.
            if not ev.category or ev.category == "Altro":
                ev.category = category
            all_events.append(ev)
            kept += 1
        successful_sources += 1
        source_counts[name] = kept
        suffix = f" ({skipped_family} family esclusi)" if skipped_family else ""
        print(f"  {name}: {kept} eventi{suffix}")

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "eventi.html"

    html_str = render(
        all_events,
        errors,
        generated_at=now,
        source_count=successful_sources,
    )
    output_path.write_text(html_str, encoding="utf-8")

    # Summary per health-check (consumato da scripts/health_check.py).
    summary = {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "total_events": len(all_events),
        "successful_sources": successful_sources,
        "sources": source_counts,
        "failed_sources": failed_sources,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nGenerati {len(all_events)} eventi totali da {successful_sources} fonti.")
    if errors:
        print(f"Fonti fallite: {len(errors)}")
    print(f"Output: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
