"""Normalización y comparación de (artista, título) entre fuentes."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_PARENS = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_FEAT = re.compile(r"\s(feat\.?|ft\.?|featuring)\s.*$", re.IGNORECASE)
_VERSION_SUFFIX = re.compile(
    r"\s-\s.*\b(remaster(ed)?|live|version|versión|edit|mix|mono|stereo|en vivo)\b.*$",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_ARTIST_SPLIT = re.compile(
    r"\s+(?:feat\.?|ft\.?|featuring|with|x)\s+|\s*,\s*|\s+&\s+", re.IGNORECASE
)


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _basic(s: str) -> str:
    s = strip_accents(s).lower()
    return _NON_ALNUM.sub(" ", s).strip()


def normalize_title(title: str) -> str:
    t = _PARENS.sub(" ", title)
    t = _VERSION_SUFFIX.sub("", t)
    t = _FEAT.sub("", t)
    return _basic(t)


def normalize_artist(artist: str) -> str:
    return _basic(_PARENS.sub(" ", artist))


def primary_artist(artist: str) -> str:
    """'Bad Bunny feat. Chencho Corleone' -> 'Bad Bunny'."""
    return _ARTIST_SPLIT.split(artist.strip())[0].strip() or artist


def ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def title_similarity(a: str, b: str) -> float:
    return ratio(normalize_title(a), normalize_title(b))


def artist_similarity(candidate_artist: str, credited: list[str], credit_string: str = "") -> float:
    """Similitud entre el artista propuesto y los artistas acreditados.

    Toma el máximo entre: artista completo vs crédito completo, artista principal
    vs cada artista acreditado, y contención de tokens (el crédito suele incluir
    invitados que el LLM no menciona, o al revés).
    """
    cand_full = normalize_artist(candidate_artist)
    cand_main = normalize_artist(primary_artist(candidate_artist))
    scores = [ratio(cand_full, normalize_artist(credit_string))] if credit_string else []
    for name in credited:
        n = normalize_artist(name)
        scores.append(ratio(cand_main, n))
        scores.append(ratio(cand_full, n))
        if cand_main and n and (set(cand_main.split()) <= set(n.split()) or set(n.split()) <= set(cand_main.split())):
            # Contención de tokens, solo si el lado chico no es trivial.
            shorter = min(cand_main, n, key=len)
            if len(shorter) >= 4:
                scores.append(0.95)
    return max(scores, default=0.0)


def dedup_key(artist: str, title: str) -> str:
    return f"{normalize_artist(primary_artist(artist))}|{normalize_title(title)}"
