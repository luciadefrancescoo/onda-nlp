"""Enfoque de onda.: el LLM interpreta la escena, el catálogo pone las canciones.

    escena ──► LLM interpreta ──► moods, géneros, artistas de referencia, época
                                        │
                                        ▼
               Last.fm: top tracks por tag, por artista y por artistas similares
                                        │  (pool de canciones reales)
                                        ▼
               tags de cada canción ──► ranking: embeddings + tags + popularidad
                                        │
                                        ▼
                         30 canciones con su explicación

El LLM nunca nombra canciones: así no puede inventarlas. Los artistas que
propone se verifican en Last.fm y los que no existen se descartan.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import llm
from .http import HttpClient
from .matching import dedup_key, normalize_artist
from .sources.lastfm import Lastfm
from .tags import clean_tag, useful_tags

# --- 1. Interpretar la escena ------------------------------------------------

INTERPRET_SYSTEM = (
    "Sos un curador musical. Traducís la descripción de una situación a tags de "
    "Last.fm y artistas reales. No nombrás canciones."
)

INTERPRET_TEMPLATE = """Escena: "{scenario}"

Describí qué música pide esta escena para buscarla en Last.fm.
Respondé SOLO con JSON, sin texto extra, con este formato:
{{"moods": ["..."], "generos": ["..."], "artistas": ["..."], "epoca": ""}}

- moods: 3 a 6 tags de ánimo, actividad o momento, en inglés y en minúscula, como se usan en Last.fm (por ejemplo "chill", "party", "workout", "melancholic", "rainy day").
- generos: 2 a 5 géneros en minúscula, como tags de Last.fm (por ejemplo "reggaeton", "indie folk", "cumbia").
- artistas: 5 a 8 artistas reales y conocidos que encajen con la escena.
- epoca: la década si la escena la pide (por ejemplo "2000s"); si no, "".
Si la escena es de un lugar o una cultura, priorizá su música."""


@dataclass
class Interpretation:
    moods: list[str]
    genres: list[str]
    artists: list[str]
    era: str = ""

    @property
    def tags(self) -> list[str]:
        """Tags a buscar y a matchear, sin repetir, en orden."""
        out: list[str] = []
        for t in self.moods + self.genres + ([self.era] if self.era else []):
            if t and t not in out:
                out.append(t)
        return out

    def to_dict(self) -> dict:
        return {"moods": self.moods, "generos": self.genres, "artistas": self.artists, "epoca": self.era}


def _str_list(x, limit: int) -> list[str]:
    if isinstance(x, str):
        x = [x]
    if not isinstance(x, list):
        return []
    out: list[str] = []
    for v in x:
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
    return out[:limit]


def parse_interpretation(text: str) -> Interpretation | None:
    data = llm.extract_json(text)
    # Los tags se guardan como los escribió el modelo (en minúscula): Last.fm distingue
    # "lo-fi" de "lo fi". Se normalizan recién al compararlos (tag_match).
    moods = [t.lower() for t in _str_list(data.get("moods"), 8)]
    genres = [t.lower() for t in _str_list(data.get("generos") or data.get("genres"), 6)]
    artists = _str_list(data.get("artistas") or data.get("artists"), 10)
    era = data.get("epoca") or data.get("era") or ""
    era = era.strip().lower() if isinstance(era, str) else ""
    if not (moods or genres) and not artists:
        return None  # chat_json lo toma como respuesta vacía y reintenta
    return Interpretation(moods, genres, artists, era)


def interpret(http: HttpClient, scenario: str, base_url: str, model: str,
              api_key: str | None = None, reasoning_effort: str | None = "none") -> Interpretation:
    messages = [
        {"role": "system", "content": INTERPRET_SYSTEM},
        {"role": "user", "content": INTERPRET_TEMPLATE.format(scenario=scenario)},
    ]
    return llm.chat_json(http, messages, base_url, model, parse_interpretation, api_key=api_key,
                         reasoning_effort=reasoning_effort, max_tokens=1024, cache_prefix="interpret")


# --- 2. Armar el pool de canciones reales ------------------------------------

# Versiones que no queremos en una playlist salvo que no haya otra.
_UNWANTED_VERSION = re.compile(
    r"\b(live|en vivo|ao vivo|remix|rmx|karaoke|instrumental|cover|demo|sped up|slowed|nightcore|8d)\b",
    re.IGNORECASE)


@dataclass
class Track:
    artist: str
    title: str
    sources: set[str] = field(default_factory=set)  # "tag:chill", "artista:Bon Iver", "similar:Bon Iver"
    listeners: int | None = None
    tags: list[tuple[str, int]] = field(default_factory=list)  # (tag limpio, peso 0-100)
    positions: dict[str, int] = field(default_factory=dict)  # búsqueda -> posición en su resultado
    score: float = 0.0
    parts: dict = field(default_factory=dict)
    why: list[str] = field(default_factory=list)


@dataclass
class CatalogParams:
    tag_limit: int = 50
    artist_limit: int = 10
    similar_artists: int = 3
    similar_limit: int = 5
    enrich: int = 90


def verify_artists(lastfm: Lastfm, names: list[str]) -> tuple[list[str], list[str]]:
    """Separa artistas reales de inventados. Devuelve (verificados con nombre canónico, descartados)."""
    ok, bad = [], []
    for name in names:
        info = lastfm.artist_info(name)
        if info and info[0] not in ok:
            ok.append(info[0])
        elif not info:
            bad.append(name)
    return ok, bad


def build_pool(lastfm: Lastfm, interp: Interpretation, artists: list[str],
               params: CatalogParams) -> dict[str, Track]:
    pool: dict[str, Track] = {}

    def add(items: list[dict], source: str):
        for i, it in enumerate(items):
            if _UNWANTED_VERSION.search(it["title"]):
                continue
            key = dedup_key(it["artist"], it["title"])
            t = pool.get(key)
            if t is None:
                t = pool[key] = Track(it["artist"], it["title"])
            t.sources.add(source)
            if it.get("listeners"):
                t.listeners = max(t.listeners or 0, it["listeners"])
            t.positions.setdefault(source, i)

    for tag in interp.tags:
        add(lastfm.tag_top_tracks(tag, params.tag_limit), f"tag:{tag}")
    for a in artists:
        add(lastfm.artist_top_tracks(a, params.artist_limit), f"artista:{a}")
    seen = {normalize_artist(a) for a in artists}
    for a in artists:
        for s in lastfm.similar_artists(a, params.similar_artists):
            if normalize_artist(s) in seen:
                continue
            seen.add(normalize_artist(s))
            add(lastfm.artist_top_tracks(s, params.similar_limit), f"similar:{a}")
    return pool


def prefilter(pool: dict[str, Track], k: int) -> list[Track]:
    """Elige qué canciones enriquecer (cada una cuesta 2 requests a Last.fm).

    Primero las que aparecieron en varias búsquedas; después, por turnos, la mejor
    restante de cada búsqueda (cada tag, cada artista). Así ninguna búsqueda tapa a
    las demás: un top de tag de 50 no deja afuera a los artistas de referencia.
    """
    multi = sorted((t for t in pool.values() if len(t.sources) > 1),
                   key=lambda t: (len(t.sources), t.listeners or 0), reverse=True)
    out = multi[:k]
    chosen = {id(t) for t in out}
    queues: dict[str, list[Track]] = {}
    for t in pool.values():
        for src, pos in t.positions.items():
            queues.setdefault(src, []).append(t)
    # Turnos en orden de búsqueda: tags, artistas de referencia, similares.
    group = {"tag": 0, "artista": 1, "similar": 2}
    order = sorted(queues, key=lambda src: group.get(src.split(":", 1)[0], 3))
    queues = {src: sorted(queues[src], key=lambda t, src=src: t.positions[src]) for src in order}
    while len(out) < k and any(queues.values()):
        for src in list(queues):
            q = queues[src]
            while q and id(q[0]) in chosen:
                q.pop(0)
            if q and len(out) < k:
                t = q.pop(0)
                chosen.add(id(t))
                out.append(t)
    return out


def enrich(lastfm: Lastfm, tracks: list[Track], junk: list[str]) -> list[Track]:
    """Agrega oyentes y tags de canción. Descarta las que Last.fm no confirma."""
    out = []
    for t in tracks:
        r = lastfm.lookup(t.artist, t.title)
        if not r.found:
            continue
        t.artist, t.title = r.artist or t.artist, r.name or t.title
        t.listeners = r.listeners if r.listeners is not None else t.listeners
        weights = dict((clean_tag(n), c) for n, c in r.tags)
        t.tags = [(tag, weights.get(tag, 0)) for tag in useful_tags([n for n, _ in r.tags], t.artist, junk)]
        out.append(t)
    return out


# --- 3. Ranking --------------------------------------------------------------

@dataclass
class RankWeights:
    semantic: float = 0.45
    tags: float = 0.30
    sources: float = 0.15
    popularity: float = 0.10


def embed(http: HttpClient, texts: list[str], base_url: str, model: str,
          api_key: str | None = None) -> list[list[float]]:
    """Embeddings vía API compatible con OpenAI (/v1/embeddings; Ollama lo soporta)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = http.post(f"{base_url.rstrip('/')}/embeddings", json_body={"model": model, "input": texts},
                  headers=headers, cache_tag=f"embed:{model}")
    if not r.ok or not r.data or "data" not in r.data:
        raise RuntimeError(f"embeddings http {r.status}: {str(r.data)[:200]}")
    rows = sorted(r.data["data"], key=lambda d: d.get("index", 0))
    if len(rows) != len(texts):
        raise RuntimeError(f"embeddings: pedí {len(texts)} y llegaron {len(rows)}")
    return [d["embedding"] for d in rows]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def scene_text(scenario: str, interp: Interpretation) -> str:
    return f"{scenario}. Música: {', '.join(interp.tags)}"


def track_text(t: Track, max_tags: int = 12) -> str:
    tags = ", ".join(tag for tag, _ in t.tags[:max_tags]) or "sin tags"
    return f"{t.artist} - {t.title}. Tags: {tags}"


def tag_match(t: Track, wanted: list[str]) -> tuple[float, list[str]]:
    """Qué tanto los tags de la canción cubren los tags pedidos. 0-1 y la lista de coincidencias."""
    weights = dict(t.tags)
    wanted = list(dict.fromkeys(clean_tag(w) for w in wanted))
    matched = [w for w in wanted if w in weights]
    if not wanted:
        return 0.0, []
    # Cada tag pedido suma según cuánto lo usan los oyentes (peso 0-100); con 3 tags fuertes ya es ~1.
    s = sum(min(1.0, (weights[w] or 10) / 100) for w in matched)
    return min(1.0, s / min(3, len(wanted))), matched


def popularity(listeners: int | None) -> float:
    """0-1 en escala log: 1k oyentes ~0.0, 10M ~1.0."""
    if not listeners:
        return 0.0
    return max(0.0, min(1.0, (math.log10(listeners) - 3) / 4))


def rank(tracks: list[Track], interp: Interpretation, weights: RankWeights,
         sims: list[float] | None = None) -> list[Track]:
    """Puntaje = suma ponderada de similitud semántica, tags, búsquedas que la trajeron y popularidad.

    La similitud semántica se reescala a 0-1 dentro de la escena (min-max): los cosenos
    crudos de un modelo de embeddings caen en un rango angosto y su escala depende del modelo.
    Sin embeddings (sims=None), el peso semántico se reparte entre los demás.
    """
    w = weights
    if sims is not None and sims:
        lo, hi = min(sims), max(sims)
        sims = [(x - lo) / (hi - lo) if hi > lo else 0.5 for x in sims]
    if sims is None:
        rest = w.tags + w.sources + w.popularity
        w = RankWeights(0.0, w.tags / rest, w.sources / rest, w.popularity / rest)
    wanted_artists = {normalize_artist(a) for a in interp.artists}
    for i, t in enumerate(tracks):
        tm, matched = tag_match(t, interp.tags)
        src = min(1.0, len(t.sources) / 3)
        sem = sims[i] if sims is not None else 0.0
        pop = popularity(t.listeners)
        t.parts = {"semantica": round(sem, 3), "tags": round(tm, 3), "busquedas": round(src, 3),
                   "popularidad": round(pop, 3)}
        t.score = w.semantic * sem + w.tags * tm + w.sources * src + w.popularity * pop
        why = [f"tags: {', '.join(matched[:4])}"] if matched else []
        if normalize_artist(t.artist) in wanted_artists:
            why.append("artista de referencia")
        elif any(s.startswith("similar:") for s in t.sources):
            ref = sorted(s.split(":", 1)[1] for s in t.sources if s.startswith("similar:"))[0]
            why.append(f"parecido a {ref}")
        t.why = why
    return sorted(tracks, key=lambda t: t.score, reverse=True)


def select(ranked: list[Track], n: int, max_per_artist: int = 2) -> list[Track]:
    """Top n con diversidad: como mucho max_per_artist canciones por artista."""
    out, per_artist = [], {}
    for t in ranked:
        a = normalize_artist(t.artist)
        if per_artist.get(a, 0) >= max_per_artist:
            continue
        per_artist[a] = per_artist.get(a, 0) + 1
        out.append(t)
        if len(out) == n:
            break
    return out
