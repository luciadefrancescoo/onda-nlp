"""Verifica cada candidato contra las fuentes abiertas y deriva señales."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from .matching import dedup_key
from .sources.lastfm import Lastfm
from .sources.listenbrainz import ListenBrainz
from .sources.musicbrainz import MusicBrainz
from .sources.spotify import Spotify
from .tags import mood_tags, useful_tags


@dataclass
class Sources:
    musicbrainz: MusicBrainz
    listenbrainz: ListenBrainz
    lastfm: Lastfm | None = None
    spotify: Spotify | None = None


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, file=sys.stderr, flush=True)


def verify(candidates: dict[str, list[dict]], src: Sources, cfg: dict,
           quiet: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tag_cfg = cfg["tags"]
    pop_cfg = cfg["popularity"]
    records: list[dict[str, Any]] = []

    # 1) MusicBrainz: existencia (secuencial, 1 req/s).
    total = sum(len(v) for v in candidates.values())
    done = 0
    for prompt_id, cands in candidates.items():
        seen: set[str] = set()
        for rank, c in enumerate(cands, 1):
            done += 1
            key = dedup_key(c["artist"], c["title"])
            dup = key in seen
            seen.add(key)
            mb = src.musicbrainz.lookup(c["artist"], c["title"])
            _log(f"[{done}/{total}] {prompt_id}: {c['artist']} - {c['title']} -> "
                 f"{'OK' if mb.found else 'no está en MusicBrainz'}", quiet)
            records.append({
                "prompt_id": prompt_id, "rank": rank,
                "artist": c["artist"], "title": c["title"], "duplicate": dup,
                "_mb": mb,
            })

    # 2) ListenBrainz: popularidad de todas las grabaciones que matchearon.
    all_mbids = [m.recording_mbid for r in records for m in r["_mb"].matches]
    _log(f"ListenBrainz: popularidad de {len(all_mbids)} grabaciones...", quiet)
    pop = src.listenbrainz.popularity(all_mbids) if all_mbids else {}
    lb_pop_ok = bool(pop) or not all_mbids

    for r in records:
        mb = r["_mb"]
        chosen = None
        best = (-1, -1)
        for m in mb.matches:
            listens, users = pop.get(m.recording_mbid, (None, None))
            score = (listens or 0, m.mb_score)
            if score > best:
                best, chosen = score, m
        listens, users = pop.get(chosen.recording_mbid, (None, None)) if chosen else (None, None)
        r["musicbrainz"] = {
            "found": mb.found, "n_matches": len(mb.matches),
            "recording_mbid": chosen.recording_mbid if chosen else None,
            "matched_title": chosen.title if chosen else None,
            "matched_artist": chosen.artist_credit if chosen else None,
            "year": mb.earliest_year, "error": mb.error,
        }
        r["listenbrainz"] = {"listen_count": listens, "user_count": users}
        r["_chosen"] = chosen

    # 3) Tags: ListenBrainz (batch) con fallback a MusicBrainz.
    chosen_mbids = [r["_chosen"].recording_mbid for r in records if r["_chosen"]]
    _log(f"Tags de {len(chosen_mbids)} grabaciones...", quiet)
    lb_tags = src.listenbrainz.tags(chosen_mbids) if chosen_mbids else {}
    for r in records:
        ch = r["_chosen"]
        t = {"recording": [], "artist": [], "release_group": []}
        source = None
        if ch is not None:
            if ch.recording_mbid in lb_tags:
                t, source = lb_tags[ch.recording_mbid], "listenbrainz"
            else:
                mbt = src.musicbrainz.tags(ch.recording_mbid, ch.artist_mbids)
                t = {"recording": mbt["recording"], "artist": mbt["artist"], "release_group": []}
                source = "musicbrainz"
        r["_brainz_tags"] = t
        r["tag_source"] = source

    # 4) Last.fm (opcional).
    for i, r in enumerate(records, 1):
        if src.lastfm is None:
            r["lastfm"] = {"enabled": False}
            continue
        lf = src.lastfm.lookup(r["artist"], r["title"])
        if i % 20 == 0:
            _log(f"Last.fm: {i}/{len(records)}", quiet)
        r["lastfm"] = {
            "enabled": True, "found": lf.found, "listeners": lf.listeners,
            "playcount": lf.playcount,
            "tags": [name for name, cnt in lf.tags if cnt >= tag_cfg["min_count_lastfm"]],
            "error": lf.error,
        }

    # 5) Spotify (opcional, solo resolución).
    for i, r in enumerate(records, 1):
        if src.spotify is None:
            r["spotify"] = {"enabled": False}
            continue
        sp = src.spotify.lookup(r["artist"], r["title"])
        if i % 20 == 0:
            _log(f"Spotify: {i}/{len(records)}", quiet)
        r["spotify"] = {"enabled": True, "found": sp.found, "uri": sp.uri, "error": sp.error}

    # 6) Señales derivadas.
    for r in records:
        bt = r.pop("_brainz_tags")
        r.pop("_mb"), r.pop("_chosen")
        song_raw = [n for n, _ in bt["recording"]] + [n for n, _ in bt["release_group"]]
        if r["lastfm"].get("found"):
            song_raw += r["lastfm"]["tags"]
        artist_raw = [n for n, _ in bt["artist"]]
        song = useful_tags(song_raw, r["artist"], tag_cfg["junk"])
        any_level = useful_tags(song_raw + artist_raw, r["artist"], tag_cfg["junk"])
        lf_listeners = r["lastfm"].get("listeners") if r["lastfm"].get("found") else None
        lb_users = r["listenbrainz"]["user_count"]
        r["derived"] = {
            "useful_tags_song": song,
            "useful_tags_any": any_level,
            "mood_tags_song": mood_tags(song, tag_cfg["mood_lexicon"]),
            "mood_tags_any": mood_tags(any_level, tag_cfg["mood_lexicon"]),
            "recognizable": bool(
                (lf_listeners or 0) >= pop_cfg["lastfm_min_listeners"]
                or (lb_users or 0) >= pop_cfg["listenbrainz_min_users"]
            ),
            "hit": bool((lf_listeners or 0) >= pop_cfg["lastfm_hit_listeners"]),
            "found_anywhere": bool(
                r["musicbrainz"]["found"] or r["lastfm"].get("found") or r["spotify"].get("found")
            ),
        }
    info = {
        "listenbrainz_popularity_ok": lb_pop_ok,
        "listenbrainz_tags_ok": bool(lb_tags) or not chosen_mbids,
        "listenbrainz_error": src.listenbrainz.last_error,
        "lastfm_enabled": src.lastfm is not None,
        "spotify_enabled": src.spotify is not None,
        "spotify_auth_error": src.spotify.auth_error if src.spotify else None,
    }
    if not lb_pop_ok:
        _log(f"AVISO: ListenBrainz popularidad falló ({src.listenbrainz.last_error}).", quiet)
    return records, info
