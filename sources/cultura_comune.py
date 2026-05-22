"""cultura.comune.fi.it — eventi dalla redazione del portale cultura del Comune.

Struttura reale della card (Drupal, class "post"):

    <article about="/dalle-redazioni/slug" class="... post ...">
      <div class="box-text">
        <header class="entry-header">
          <span class="posted-on">
            pubblicato il:
            <time datetime="2026-05-15T13:27:04+02:00">15 maggio 2026</time>
          </span>
          <h3 class="entry-title"><a href="/dalle-redazioni/slug">Titolo</a></h3>
        </header>
        <div class="entry-content">
          <p>Dal 22 al 24 maggio torna...</p>
        </div>
      </div>
    </article>

La data reale dell'evento viene estratta dal testo della descrizione con
parse_italian_datetime; se non trovata si ricade sulla data ISO della <time>.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.base import Event, ROME, http_get, new_session
from sources.italian_dates import parse_italian_datetime

SOURCE_NAME = "Cultura Comune Firenze"
CATEGORY = "Civici"
BASE_URL = "https://cultura.comune.fi.it"
LIST_URL = f"{BASE_URL}/dalle-redazioni"
# ~10 card per pagina × 4 pagine = ~40 articoli; copre ampiamente 90 giorni.
MAX_PAGES = 4


def fetch() -> list[Event]:
    events: list[Event] = []
    seen_urls: set[str] = set()

    # Shared session so cookies set by the site root carry into the
    # listing pages — needed when the host is behind a WAF that issues
    # a challenge cookie.
    session = new_session()
    try:
        http_get(BASE_URL + "/", session=session)
    except Exception:
        pass  # let the listing call below surface the real error

    for page in range(MAX_PAGES):
        url = LIST_URL if page == 0 else f"{LIST_URL}?page={page}"
        headers = {"Referer": BASE_URL + "/" if page == 0 else LIST_URL}
        try:
            resp = http_get(url, session=session, headers=headers)
        except Exception:
            # On the first page, propagate so a site-wide failure (403/5xx)
            # surfaces in "Fonti fallite" instead of vanishing. On later
            # pages a missing page is normal (less than MAX_PAGES exist).
            if page == 0:
                raise
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all("article", class_=lambda c: c and "post" in c)
        if not articles:
            break

        page_count = 0
        for art in articles:
            # URL: attributo "about" sull'<article> o href del link nel titolo
            href = art.get("about", "").strip()
            if not href:
                title_a = art.select_one("h3.entry-title a")
                href = title_a.get("href", "").strip() if title_a else ""
            if not href:
                continue
            full_url = urljoin(BASE_URL, href)
            if full_url in seen_urls:
                continue

            # Titolo
            title_el = art.select_one("h3.entry-title a")
            title = title_el.get_text(" ", strip=True) if title_el else None
            if not title:
                continue

            # Data ISO dalla <time> (data di pubblicazione, usata come fallback)
            time_el = art.select_one("time[datetime]")
            pub_dt: datetime | None = None
            if time_el:
                try:
                    iso = time_el["datetime"]          # "2026-05-15T13:27:04+02:00"
                    pub_dt = datetime.fromisoformat(iso).astimezone(ROME)
                except (ValueError, KeyError):
                    pass

            # Descrizione (primo <p> dentro .entry-content)
            desc_el = art.select_one("div.entry-content p")
            description = desc_el.get_text(" ", strip=True) if desc_el else None

            # Prova a estrarre la data reale dell'evento dal testo descrittivo.
            start: datetime | None = None
            if description:
                start = parse_italian_datetime(description)
            # Fallback: data di pubblicazione (di solito ravvicinata all'evento)
            if start is None:
                start = pub_dt
            if start is None:
                continue

            if description and len(description) > 280:
                description = description[:277] + "…"

            seen_urls.add(full_url)
            events.append(Event(
                source=SOURCE_NAME,
                title=title,
                start=start,
                url=full_url,
                description=description,
            ))
            page_count += 1

        if page_count == 0:
            break

    return events
