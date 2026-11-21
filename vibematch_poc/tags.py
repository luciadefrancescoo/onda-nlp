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


def _lexicon_patterns(lexicon: list[str]) -> list[re.Pattern]:
    pats = []
    for entry in lexicon:
        e = clean_tag(entry)
        if e.endswith("*"):  # raíz: 'nostalg*' -> nostalgia, nostalgic
            pats.append(re.compile(r"\b" + re.escape(e[:-1])))
        else:                # palabra o frase completa: 'rain' no matchea 'training'
            pats.append(re.compile(r"\b" + re.escape(e) + r"\b"))
    return pats


def mood_tags(tags: list[str], lexicon: list[str]) -> list[str]:
    pats = _lexicon_patterns(lexicon)
    return [t for t in tags if any(p.search(t) for p in pats)]
