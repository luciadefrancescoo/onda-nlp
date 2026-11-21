"""Last.fm: oyentes y tags (folksonomía, la mejor fuente de mood para hits).

Requiere API key gratuita. Ojo con los términos: para uso académico/de
investigación piden escribir antes a partners@last.fm (ver README).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..http import HttpClient
from ..matching import artist_similarity, title_similarity

BASE = "https://ws.audioscrobbler.com/2.0/"


@dataclass
class LastfmResult:
    found: bool
    name: str = ""
    artist: str = ""
    listeners: int | None = None
    playcount: int | None = None
    tags: list[tuple[str, int]] = field(default_factory=list)
    error: str | None = None


class Lastfm:
    def __init__(self, http: HttpClient, api_key: str, title_min: float = 0.85,
                 artist_min: float = 0.85):
        self.http = http
        self.api_key = api_key
        self.title_min = title_min
        self.artist_min = artist_min

    def _call(self, method: str, **params):
        p = {"method": method, "api_key": self.api_key, "format": "json", **params}
        # La key no forma parte de la clave de caché.
        return self.http.request("GET", BASE, params=p, cache_tag="lastfm")

    def lookup(self, artist: str, title: str) -> LastfmResult:
        r = self._call("track.getInfo", artist=artist, track=title, autocorrect=1)
        if not r.ok or not r.data:
            return LastfmResult(False, error=f"http {r.status}")
        if "error" in r.data:
            return LastfmResult(False, error=str(r.data.get("message")))
        t = r.data.get("track", {})
        name = t.get("name", "")
        art = (t.get("artist") or {}).get("name", "") if isinstance(t.get("artist"), dict) else str(t.get("artist", ""))
        # autocorrect puede devolver otra canción: verificamos.
        if title_similarity(title, name) < self.title_min or artist_similarity(artist, [art]) < self.artist_min:
            return LastfmResult(False, name=name, artist=art, error="autocorrect a otra canción")
        res = LastfmResult(
            True, name=name, artist=art,
            listeners=_int(t.get("listeners")), playcount=_int(t.get("playcount")),
        )
        r2 = self._call("track.getTopTags", artist=art, track=name, autocorrect=1)
        if r2.ok and r2.data and "toptags" in r2.data:
            tags = r2.data["toptags"].get("tag", []) or []
            if isinstance(tags, dict):
                tags = [tags]
            res.tags = [(x.get("name", ""), _int(x.get("count")) or 0) for x in tags]
        return res


def _int(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None
