"""Estrazione della descrizione breve di un evento da una pagina o da HTML.

Più fonti (mostre soprattutto) espongono il testo di presentazione come prosa
dentro la pagina di dettaglio o in un campo HTML dell'API. Serve isolarne il
primo paragrafo davvero descrittivo, scartando titoli, didascalie, voci di
menu, crediti e avvisi pratici su orari e biglietti.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Un paragrafo utile ha una lunghezza minima: sotto si tratta quasi sempre di
# un sottotitolo, una didascalia o una riga di crediti.
MIN_LEN = 80
# Oltre questa soglia si taglia, per non riempire la card di testo.
MAX_LEN = 280

# Righe da scartare: navigazione, crediti, informazioni di servizio.
_SKIP_RE = re.compile(
    r"^(a cura di|in collaborazione|con il (?:patrocinio|contributo)|"
    r"orari|biglietti|biglietteria|tariffe|riduzioni|ingresso|visita|"
    r"il caff[eè]|il café|come arrivare|"
    r"info(?:rmazioni)?|prenotazion|"
    r"vai al|salta al|skip to|cookie|privacy|newsletter|condividi|share)\b",
    re.IGNORECASE,
)
# Informazioni pratiche per il visitatore (orari di apertura, tariffe,
# categorie di riduzione). Hanno la lunghezza di un paragrafo descrittivo ma
# non dicono nulla della mostra: su musefirenze.it precedono il testo vero.
_PRACTICAL_RE = re.compile(
    r"dalle\s+\d{1,2}(?:[:.]\d{2})?\s+alle\s+\d{1,2}"      # "dalle 10 alle 20"
    r"|\bresidenti della citt[àa]\b"                        # fasce di tariffa
    r"|\bbiglietto\s+(?:intero|ridotto|gratuito)\b"
    r"|\b(?:intero|ridotto)\s*€"
    r"|\bè aperto\b[^.]{0,60}\bdal(?:le)?\b",               # "è aperto dal ..."
    re.IGNORECASE,
)
# Frasi che iniziano a metà (il tag precedente ha spezzato la frase).
_STARTS_MID_RE = re.compile(r"^[,;:)\]\.\-–—]")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_good(text: str) -> bool:
    if len(text) < MIN_LEN:
        return False
    if _SKIP_RE.match(text) or _STARTS_MID_RE.match(text):
        return False
    if _PRACTICAL_RE.search(text):
        return False
    # Deve contenere parole, non solo date/numeri/maiuscole da titolo.
    letters = sum(c.isalpha() for c in text)
    if letters < len(text) * 0.6:
        return False
    # Un titolo tutto maiuscolo non è una descrizione.
    upper = sum(c.isupper() for c in text if c.isalpha())
    return upper <= letters * 0.6


def _shorten(text: str) -> str:
    if len(text) <= MAX_LEN:
        return text
    # Taglia all'ultimo confine di parola per non troncare a metà.
    cut = text[:MAX_LEN].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def describe_html(html_text: str) -> str | None:
    """Primo paragrafo descrittivo trovato in un frammento o pagina HTML."""
    if not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()

    # Prima i <p>: sono quasi sempre il corpo del testo.
    for p in soup.find_all("p"):
        candidate = _clean(p.get_text(" ", strip=True))
        if _is_good(candidate):
            return _shorten(candidate)

    # Altrimenti si ripiega sulle righe del testo semplice.
    for line in soup.get_text("\n", strip=True).split("\n"):
        candidate = _clean(line)
        if _is_good(candidate):
            return _shorten(candidate)
    return None
