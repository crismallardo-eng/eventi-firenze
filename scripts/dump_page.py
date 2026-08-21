"""Diagnostica una tantum: scarica una pagina e ne salva un estratto leggibile.

Serve quando il sito non è raggiungibile dall'ambiente di sviluppo ma lo è dal
runner CI: il runner scarica, salva l'estratto nel repo, si legge il file.

Uso:  python scripts/dump_page.py <url> [<url> ...]
Output: data/_dump.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from sources.base import http_get, new_session  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "_dump.txt"


def dump(url: str, session) -> str:
    parts = [f"\n{'=' * 70}\nURL: {url}\n{'=' * 70}"]
    try:
        resp = http_get(url, session=session)
    except Exception as exc:  # noqa: BLE001
        return "\n".join(parts + [f"ERRORE: {type(exc).__name__}: {exc}"])

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # 1. Testo visibile, che contiene data/ora/luogo in chiaro.
    text = soup.get_text("\n", strip=True)
    parts.append("--- TESTO VISIBILE (primi 2500 char) ---")
    parts.append(text[:2500])

    # 2. Elementi con classi che sembrano portare data/ora/luogo: servono per
    #    scrivere selettori precisi invece di euristiche sul testo.
    parts.append("\n--- ELEMENTI CON CLASSI date/time/venue/location ---")
    keys = ("date", "time", "ora", "venue", "location", "luogo", "place", "when", "where")
    seen = 0
    for el in soup.find_all(attrs={"class": True}):
        cls = " ".join(el.get("class"))
        if not any(k in cls.lower() for k in keys):
            continue
        content = el.get_text(" ", strip=True)[:160]
        if not content:
            continue
        parts.append(f"  <{el.name} class='{cls}'> {content}")
        seen += 1
        if seen >= 40:
            break
    return "\n".join(parts)


def main() -> int:
    urls = sys.argv[1:]
    if not urls:
        print("uso: python scripts/dump_page.py <url> [...]")
        return 2
    session = new_session()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(dump(u, session) for u in urls), encoding="utf-8")
    print(f"scritto {OUT} ({OUT.stat().st_size} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
