"""Filtrado de tags útiles y detección de tags de mood/escena."""

from __future__ import annotations

import re

from .matching import normalize_artist, strip_accents

_YEAR = re.compile(r"^(19|20)\d\d$")


def clean_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(tag).lower().replace("-", " ")).strip()


def useful_tags(tags: list[str], artist: str, junk: list[str]) -> list[str]:
    """Saca basura (favoritos, 'seen live', años sueltos, el nombre del artista).

    Las décadas ('80s', '2000s') se conservan: sirven para época/nostalgia.
    """
    junk_set = {clean_tag(j) for j in junk}
    artist_norm = normalize_artist(artist)
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        c = clean_tag(t)
        if len(c) < 2 or c in junk_set or _YEAR.match(c):
            continue
        if normalize_artist(c) == artist_norm:
            continue
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# Palabras de relleno que se sacan del final antes de comparar:
# 'party music' -> 'party', 'rainy day' -> 'rainy'.
_GENERIC_SUFFIX = {"music", "songs", "song", "vibes", "vibe", "mood", "day", "days", "time"}


def _core(tag: str) -> str:
    words = tag.split()
    while len(words) > 1 and words[-1] in _GENERIC_SUFFIX:
        words.pop()
    return " ".join(words)


def mood_tags(tags: list[str], lexicon: list[str]) -> list[str]:
    """Un tag es de mood si, sin relleno, ES una entrada del léxico.

    Se compara el tag entero y no una subcadena: así 'soft rock', 'indie dance'
    o 'ambient pop' (géneros) no cuentan como mood. Las entradas con '*' son
    raíces y matchean una sola palabra: 'nostalg*' -> 'nostalgic'.
    """
    exact, stems = set(), []
    for entry in lexicon:
        e = clean_tag(entry)
        if e.endswith("*"):
            stems.append(e[:-1])
        else:
            exact.add(e)
    out = []
    for t in tags:
        core = _core(t)
        if core in exact or (" " not in core and any(core.startswith(s) for s in stems)):
            out.append(t)
    return out
