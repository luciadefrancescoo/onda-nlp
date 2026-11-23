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
from .matching import dedup_key, normalize_artist, strip_accents
from .sources.lastfm import Lastfm
from .relevance import genre_hits
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
    dropped_era: str = ""  # época que propuso el LLM pero la escena no menciona

    @property
    def tags(self) -> list[str]:
        """Tags a buscar y a matchear, sin repetir, en orden."""
        out: list[str] = []
        for t in self.moods + self.genres + ([self.era] if self.era else []):
            if t and t not in out:
                out.append(t)
        return out

    @property
    def era_tags(self) -> list[str]:
        """Tags de Last.fm para la época: "2000s" -> ["2000s", "00s"]."""
        m = re.search(r"(\d{2,4})", self.era or "")
        if not m:
            return []
        d = m.group(1)
        if len(d) == 2:  # "80s" / "00s"
            d = ("19" if int(d) >= 30 else "20") + d
        if len(d) != 4:
            return []
        return [f"{d}s", f"{d[2:]}s"]

    @property
    def retrieval_tags(self) -> list[str]:
        """Tags que TRAEN canciones: géneros y época. Los moods solo ordenan, salvo
        que no haya géneros: un top de "party" trae hits globales de cualquier género."""
        base = self.genres if self.genres else self.moods
        out: list[str] = []
        # La época se busca con la forma corta ("80s", "00s"): es la que más se usa en Last.fm.
        for t in base + self.era_tags[1:2]:
            if t and t not in out:
                out.append(t)
        return out

    def to_dict(self) -> dict:
        return {"moods": self.moods, "generos": self.genres, "artistas": self.artists, "epoca": self.era,
                "epoca_descartada": self.dropped_era}


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


def era_mentioned(scenario: str, interp: Interpretation) -> bool:
    """¿La escena nombra la época que propuso el LLM? ("los 2000", "pop de los 80")."""
    tags = interp.era_tags
    if not tags:
        return False
    full, short = tags[0][:4], tags[1][:2]          # "2000", "00" / "1980", "80"
    text = strip_accents(scenario.lower())
    return bool(re.search(rf"\b({full}|{short})(s|'s)?\b", text))


def interpret(http: HttpClient, scenario: str, base_url: str, model: str,
              api_key: str | None = None, reasoning_effort: str | None = "none") -> Interpretation:
    messages = [
        {"role": "system", "content": INTERPRET_SYSTEM},
        {"role": "user", "content": INTERPRET_TEMPLATE.format(scenario=scenario)},
    ]
    interp = llm.chat_json(http, messages, base_url, model, parse_interpretation, api_key=api_key,
                           reasoning_effort=reasoning_effort, max_tokens=1024, cache_prefix="interpret")
    # El modelo a veces agrega una época que la escena no pide ("asado" -> "1980s") y eso
    # penaliza canciones sin motivo: se usa solo si la escena la nombra.
    if interp.era and not era_mentioned(scenario, interp):
        interp.dropped_era = interp.era
        interp.era = ""
    return interp


# --- 2. Armar el pool de canciones reales ------------------------------------

# Versiones que no queremos en una playlist salvo que no haya otra.
_UNWANTED_VERSION = re.compile(
    r"\b(live|en vivo|ao vivo|remix|rmx|karaoke|instrumental|cover|demo|sped up|slowed|nightcore|8d"
    r"|alternate|extended|radio edit|\w+ mix)\b",
    re.IGNORECASE)


@dataclass
class Track:
    artist: str
    title: str
    sources: set[str] = field(default_factory=set)  # "tag:chill", "artista:Bon Iver", "similar:Bon Iver"
    listeners: int | None = None
    tags: list[tuple[str, int]] = field(default_factory=list)  # (tag limpio, peso 0-100)
    artist_tags: list[str] = field(default_factory=list)  # tags del artista (limpios)
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
    enrich: int = 120


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


def artist_profile(lastfm: Lastfm, artists: list[str], junk: list[str], top: int = 10) -> dict[str, float]:
    """El "sonido" de la escena según sus artistas de referencia.

    Para cada tag, la fracción de artistas de referencia que lo tienen entre sus
    `top` tags. "Tipo Carlos Vives" -> latin, colombia, vallenato, colombian…
    Sirve para separar a Fonseca (latin, colombia) de TWICE (k-pop, korean), aunque
    las dos canciones tengan el tag "tropical".
    """
    counts: dict[str, int] = {}
    n = 0
    for a in artists:
        tags = useful_tags(lastfm.artist_tags(a), a, junk)[:top]
        if not tags:
            continue
        n += 1
        for t in set(tags):
            counts[t] = counts.get(t, 0) + 1
    return {t: c / n for t, c in counts.items()} if n else {}


def artist_fit(t: Track, profile: dict[str, float], top: int = 10) -> float:
    """Coseno entre los tags del artista de la canción y el perfil de la escena (0-1)."""
    tags = list(dict.fromkeys(t.artist_tags[:top]))
    if not profile or not tags:
        return 0.0
    dot = sum(profile.get(x, 0.0) for x in tags)
    norm_p = math.sqrt(sum(v * v for v in profile.values()))
    return dot / (math.sqrt(len(tags)) * norm_p) if norm_p else 0.0


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

    for tag in interp.retrieval_tags:
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
    """Agrega oyentes, tags de canción y tags del artista. Descarta las que Last.fm no confirma.

    Los tags del artista importan para el género: en música local las canciones casi
    no tienen tags, pero el artista sí ("L-Gante": cumbia, rkt, argentina).
    """
    out = []
    artist_cache: dict[str, list[str]] = {}
    for t in tracks:
        r = lastfm.lookup(t.artist, t.title)
        if not r.found:
            continue
        t.artist, t.title = r.artist or t.artist, r.name or t.title
        t.listeners = r.listeners if r.listeners is not None else t.listeners
        weights = dict((clean_tag(n), c) for n, c in r.tags)
        t.tags = [(tag, weights.get(tag, 0)) for tag in useful_tags([n for n, _ in r.tags], t.artist, junk)]
        a = normalize_artist(t.artist)
        if a not in artist_cache:
            artist_cache[a] = useful_tags(lastfm.artist_tags(t.artist), t.artist, junk)[:15]
        t.artist_tags = artist_cache[a]
        out.append(t)
    return out


# --- 3. Ranking --------------------------------------------------------------

@dataclass
class RankWeights:
    semantic: float = 0.30
    tags: float = 0.15
    genre: float = 0.20
    era: float = 0.10
    artist_fit: float = 0.15      # parecido del artista al perfil de los artistas de referencia
    sources: float = 0.15
    popularity: float = 0.10
    genre_penalty: float = 0.25   # multiplica el puntaje si la canción no tiene ningún género pedido
    fit_min: float = 0.25         # afinidad (0-1, reescalada) por debajo de la cual se penaliza…
    fit_penalty: float = 0.50     # …multiplicando el puntaje por esto
    era_penalty: float = 0.60     # idem si se pidió una época y la canción no tiene ese tag


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
    artist = ", ".join(t.artist_tags[:6]) or "sin tags"
    return f"{t.artist} - {t.title}. Tags: {tags}. Artista: {artist}"


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


def genre_evidence(t: Track, genres: list[str]) -> list[str]:
    """Géneros pedidos que aparecen en los tags de la canción o del artista."""
    return genre_hits([tag for tag, _ in t.tags] + t.artist_tags, genres)


def era_evidence(t: Track, era_tags: list[str]) -> bool:
    """La época se mira solo en los tags de la canción: un artista de los 2000 puede
    tener temas de 2015, y el tag del artista no distingue."""
    return bool(genre_hits([tag for tag, _ in t.tags], era_tags))


def rank(tracks: list[Track], interp: Interpretation, weights: RankWeights,
         sims: list[float] | None = None, profile: dict[str, float] | None = None) -> list[Track]:
    """Puntaje 0-1 = promedio ponderado de los rasgos activos, con penalizaciones.

    Rasgos: similitud semántica (si hay embeddings), moods en los tags, género pedido
    (si hay géneros), época (si se pidió), búsquedas que la trajeron y popularidad.
    Si se pidieron géneros y la canción no tiene ninguno, el puntaje se multiplica por
    genre_penalty: el género es un requisito de la escena, el mood una preferencia.

    La similitud semántica se reescala a 0-1 dentro de la escena (min-max): los cosenos
    crudos de un modelo de embeddings caen en un rango angosto y su escala depende del modelo.
    """
    w = weights
    if sims:
        lo, hi = min(sims), max(sims)
        sims = [(x - lo) / (hi - lo) if hi > lo else 0.5 for x in sims]
    era_tags = interp.era_tags
    active = {"semantica": w.semantic if sims else 0.0, "tags": w.tags,
              "genero": w.genre if interp.genres else 0.0, "epoca": w.era if era_tags else 0.0,
              "afinidad": w.artist_fit if profile else 0.0,
              "busquedas": w.sources, "popularidad": w.popularity}
    # El afinidad se reescala dentro de la escena como la semántica: el coseno crudo
    # depende de cuántos tags tenga el perfil.
    fits = [artist_fit(t, profile) for t in tracks] if profile else [0.0] * len(tracks)
    hi_fit = max(fits) if fits else 0.0
    fits = [f / hi_fit if hi_fit else 0.0 for f in fits]
    total = sum(active.values()) or 1.0
    wanted_artists = {normalize_artist(a) for a in interp.artists}
    for i, t in enumerate(tracks):
        tm, matched = tag_match(t, interp.moods or interp.tags)
        genres = genre_evidence(t, interp.genres)
        era_ok = era_evidence(t, era_tags) if era_tags else False
        f = {"semantica": sims[i] if sims else 0.0, "tags": tm, "genero": 1.0 if genres else 0.0,
             "epoca": 1.0 if era_ok else 0.0, "afinidad": fits[i],
             "busquedas": min(1.0, len(t.sources) / 3),
             "popularidad": popularity(t.listeners)}
        score = sum(active[k] * f[k] for k in f) / total
        if interp.genres and not genres:
            score *= w.genre_penalty
        if era_tags and not era_ok:
            score *= w.era_penalty
        if profile and t.artist_tags and fits[i] < w.fit_min:
            score *= w.fit_penalty  # artista que no se parece a los de referencia (k-pop en una cumbia)
        t.score = score
        t.parts = {k: round(v, 3) for k, v in f.items() if active[k]}
        why = []
        if genres:
            why.append(f"género: {', '.join(genres[:3])}")
        if matched:
            why.append(f"tags: {', '.join(matched[:3])}")
        if era_ok:
            why.append(f"época: {interp.era}")
        if normalize_artist(t.artist) in wanted_artists:
            why.append("artista de referencia")
        elif any(s.startswith("similar:") for s in t.sources):
            ref = sorted(s.split(":", 1)[1] for s in t.sources if s.startswith("similar:"))[0]
            why.append(f"parecido a {ref}")
        t.why = why
    return sorted(tracks, key=lambda t: t.score, reverse=True)


def select(ranked: list[Track], n: int, max_per_artist: int = 2,
           genres: list[str] | None = None) -> list[Track]:
    """Top n con diversidad.

    - Como mucho max_per_artist canciones por artista.
    - Si la escena pide varios géneros ("cumbia y reggaetón"), cada uno tiene reservado
      un mínimo de n / (2 x géneros) lugares, si hay canciones de ese género. Sin esto,
      el género con más oyentes ocupa toda la lista.
    El orden final es por puntaje.
    """
    out: list[Track] = []
    per_artist: dict[str, int] = {}
    seen: set[str] = set()  # dos entradas del pool pueden quedar iguales tras enrich (título canónico)

    def take(t: Track) -> bool:
        a = normalize_artist(t.artist)
        key = dedup_key(t.artist, t.title)
        if key in seen or per_artist.get(a, 0) >= max_per_artist or len(out) >= n:
            return False
        per_artist[a] = per_artist.get(a, 0) + 1
        seen.add(key)
        out.append(t)
        return True

    if genres and len(genres) > 1:
        quota = max(1, n // (2 * len(genres)))
        for g in genres:
            got = 0
            for t in ranked:
                if got >= quota:
                    break
                if genre_evidence(t, [g]) and take(t):
                    got += 1
    for t in ranked:
        if len(out) >= n:
            break
        take(t)
    return sorted(out, key=lambda t: t.score, reverse=True)
