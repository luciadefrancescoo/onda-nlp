"""Armar una playlist para una escena: lo que usan la CLI (`build`) y la demo web.

Emite eventos de progreso para que la demo muestre el proceso mientras espera:

    {"type": "status", "msg": "..."}
    {"type": "interpretation", "moods": [...], "genres": [...], "artists": [...], ...}
    {"type": "pool", "size": 300}
    {"type": "progress", "done": 40, "total": 120}
    {"type": "playlist", "tracks": [...]}
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

from . import scene
from .http import HttpClient
from .sources.lastfm import Lastfm

Event = dict
OnEvent = Callable[[Event], None]


@dataclass
class Settings:
    base_url: str
    model: str
    embed_model: str
    api_key: str | None
    reasoning_effort: str | None
    params: scene.CatalogParams
    weights: scene.RankWeights
    max_per_artist: int
    junk: list[str]
    n: int

    @classmethod
    def from_config(cls, cfg: dict, n: int | None = None) -> "Settings":
        b = cfg.get("build", {})
        return cls(
            base_url=os.environ["LLM_BASE_URL"],
            model=os.environ["LLM_MODEL"],
            embed_model=os.environ.get("LLM_EMBED_MODEL") or b.get("embed_model", "embeddinggemma"),
            api_key=os.environ.get("LLM_API_KEY"),
            reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "none") or None,
            params=scene.CatalogParams(**{k: b[k] for k in
                                          ("tag_limit", "artist_limit", "similar_artists", "similar_limit",
                                           "enrich") if k in b}),
            weights=scene.RankWeights(**b.get("weights", {})),
            max_per_artist=b.get("max_per_artist", 2),
            junk=cfg["tags"]["junk"],
            n=n or cfg["run"]["candidates_per_prompt"],
        )


@dataclass
class Result:
    interp: scene.Interpretation
    artists: list[str]
    dropped: list[str]
    profile: dict[str, float]
    pool_size: int
    enriched: int
    embeddings: bool
    tracks: list[scene.Track]
    seconds: float
    warnings: list[str]

    def interpretation_dict(self) -> dict:
        return {**self.interp.to_dict(), "artistas_verificados": self.artists,
                "artistas_descartados": self.dropped, "pool": self.pool_size,
                "con_tags": self.enriched, "embeddings": self.embeddings,
                "perfil": dict(sorted(self.profile.items(), key=lambda kv: -kv[1])[:12])}


def track_dict(t: scene.Track) -> dict:
    return {"artist": t.artist, "title": t.title, "score": round(t.score, 3), "why": t.why,
            "parts": t.parts, "listeners": t.listeners}


def build_playlist(scenario: str, http: HttpClient, lastfm: Lastfm, s: Settings,
                   on_event: OnEvent | None = None) -> Result:
    emit = on_event or (lambda e: None)
    t0 = time.monotonic()
    warnings: list[str] = []

    emit({"type": "status", "step": "interpret", "msg": "Interpretando la escena…"})
    interp = scene.interpret(http, scenario, s.base_url, s.model, s.api_key, s.reasoning_effort)
    emit({"type": "status", "step": "artists", "msg": "Verificando artistas en Last.fm…"})
    artists, dropped = scene.verify_artists(lastfm, interp.artists)
    emit({"type": "interpretation", "moods": interp.moods, "genres": interp.genres, "era": interp.era,
          "dropped_era": interp.dropped_era, "artists": artists, "dropped_artists": dropped})

    emit({"type": "status", "step": "pool", "msg": "Buscando canciones reales en Last.fm…"})
    profile = scene.artist_profile(lastfm, artists, s.junk)
    pool = scene.build_pool(lastfm, interp, artists, s.params)
    emit({"type": "pool", "size": len(pool)})

    emit({"type": "status", "step": "tags", "msg": "Leyendo los tags de cada canción…"})
    candidates = scene.prefilter(pool, s.params.enrich)
    tracks = scene.enrich(lastfm, candidates, s.junk,
                          on_progress=lambda done: emit({"type": "progress", "done": done,
                                                         "total": len(candidates)}))

    emit({"type": "status", "step": "rank", "msg": "Ordenando por qué tan bien encajan…"})
    sims = None
    if tracks:
        try:
            texts = [scene.scene_text(scenario, interp)] + [scene.track_text(t) for t in tracks]
            vecs = scene.embed(http, texts, s.base_url, s.embed_model, s.api_key)
            sims = [scene.cosine(vecs[0], v) for v in vecs[1:]]
        except Exception as e:  # sin embeddings rankea igual con tags y popularidad
            warnings.append(f"sin embeddings ({e}); rankeo sin similitud semántica")
    ranked = scene.rank(tracks, interp, s.weights, sims, profile)
    chosen = scene.select(ranked, s.n, s.max_per_artist, interp.genres)
    emit({"type": "playlist", "tracks": [track_dict(t) for t in chosen]})
    return Result(interp, artists, dropped, profile, len(pool), len(tracks), sims is not None,
                  chosen, time.monotonic() - t0, warnings)
