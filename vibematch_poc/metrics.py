"""Agrega resultados por prompt y contra los umbrales de config.toml."""

from __future__ import annotations

from statistics import median
from typing import Any


def _frac(xs: list[bool]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _med(xs: list[int | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return float(median(vals)) if vals else None


def group_metrics(recs: list[dict], info: dict) -> dict[str, Any]:
    uniq = [r for r in recs if not r["duplicate"]]
    found = [r for r in uniq if r["musicbrainz"]["found"]]
    years = [r["musicbrainz"]["year"] for r in found if r["musicbrainz"]["year"]]
    lastfm_on = info["lastfm_enabled"]
    spotify_on = info["spotify_enabled"] and not info.get("spotify_auth_error")
    popularity_on = info["listenbrainz_popularity_ok"] or lastfm_on
    artists = {r["artist"].lower() for r in uniq}
    return {
        "n": len(recs),
        "duplicates": len(recs) - len(uniq),
        "unique_artist_ratio": len(artists) / len(uniq) if uniq else None,
        "exists_in_musicbrainz": _frac([r["musicbrainz"]["found"] for r in uniq]),
        "not_found_anywhere": _frac([not r["derived"]["found_anywhere"] for r in uniq]),
        "resolved_in_spotify": _frac([r["spotify"]["found"] for r in uniq]) if spotify_on else None,
        "recognizable": _frac([r["derived"]["recognizable"] for r in uniq]) if popularity_on else None,
        "hit": _frac([r["derived"]["hit"] for r in uniq]) if lastfm_on else None,
        "has_3_useful_tags_song": _frac([len(r["derived"]["useful_tags_song"]) >= 3 for r in uniq]),
        "has_3_useful_tags_any": _frac([len(r["derived"]["useful_tags_any"]) >= 3 for r in uniq]),
        "has_mood_tag_song": _frac([bool(r["derived"]["mood_tags_song"]) for r in uniq]),
        "has_mood_tag_any": _frac([bool(r["derived"]["mood_tags_any"]) for r in uniq]),
        "released_2024_or_later": _frac([y >= 2024 for y in years]),
        "median_year": _med(years),
        "median_lastfm_listeners": _med([r["lastfm"].get("listeners") for r in uniq if r["lastfm"].get("found")]),
        "median_listenbrainz_users": _med([r["listenbrainz"]["user_count"] for r in uniq]),
    }


CRITERIA = [
    # (clave en thresholds, métrica, etiqueta, requisito de fuente)
    ("exists_in_musicbrainz", "exists_in_musicbrainz", "Existe en MusicBrainz (no es alucinación)", None),
    ("resolved_in_spotify", "resolved_in_spotify", "Se encuentra en Spotify (exportable)", "spotify"),
    ("has_3_useful_tags", "has_3_useful_tags_song", "≥3 tags útiles a nivel canción", "lastfm"),
    ("recognizable", "recognizable", "Música reconocible", None),
]


def summarize(records: list[dict], info: dict, cfg: dict) -> dict[str, Any]:
    by_prompt: dict[str, list[dict]] = {}
    for r in records:
        by_prompt.setdefault(r["prompt_id"], []).append(r)
    per_prompt = {pid: group_metrics(rs, info) for pid, rs in by_prompt.items()}
    overall = group_metrics(records, info)

    thr = cfg["thresholds"]
    criteria = []
    for thr_key, metric, label, needs in CRITERIA:
        value = overall[metric]
        missing = (needs == "lastfm" and not info["lastfm_enabled"]) or (
            needs == "spotify" and (not info["spotify_enabled"] or info.get("spotify_auth_error")))
        if value is None or missing:
            status = "N/A"
        else:
            status = "PASA" if value >= thr[thr_key] else "NO PASA"
        weak = [pid for pid, m in per_prompt.items()
                if m[metric] is not None and m[metric] < thr[thr_key]]
        criteria.append({"key": thr_key, "metric": metric, "label": label, "value": value,
                         "threshold": thr[thr_key], "status": status, "needs": needs,
                         "prompts_below": weak})

    statuses = {c["status"] for c in criteria}
    if "NO PASA" in statuses:
        verdict = "NO-GO (o replantear)"
    elif "N/A" in statuses:
        verdict = "INCOMPLETO: faltan fuentes para evaluar todos los criterios"
    else:
        verdict = "GO"
    return {"overall": overall, "per_prompt": per_prompt, "criteria": criteria, "verdict": verdict}
