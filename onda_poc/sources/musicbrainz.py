"""MusicBrainz: ¿existe la canción? (sin API key, 1 req/s).

Devuelve todas las grabaciones que matchean (una misma canción tiene muchas:
single, álbum, compilados). ListenBrainz después elige la más escuchada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..http import HttpClient
from ..matching import artist_similarity, primary_artist, title_similarity

BASE = "https://musicbrainz.org/ws/2"
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


def lucene_escape(s: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", s)


@dataclass
class MBMatch:
    recording_mbid: str
    title: str
    artist_credit: str
    artist_mbids: list[str]
    first_release_date: str | None
    mb_score: int
    title_sim: float
    artist_sim: float


@dataclass
class MBResult:
    found: bool
    matches: list[MBMatch] = field(default_factory=list)
    query_used: str = ""
    error: str | None = None

    @property
    def earliest_year(self) -> int | None:
        years = []
        for m in self.matches:
            if m.first_release_date and m.first_release_date[:4].isdigit():
                years.append(int(m.first_release_date[:4]))
        return min(years) if years else None


def _credit_names(rec: dict) -> tuple[list[str], list[str], str]:
    names, mbids, parts = [], [], []
    for ac in rec.get("artist-credit", []) or []:
        if isinstance(ac, str):
            parts.append(ac)
            continue
        names.append(ac.get("name") or ac.get("artist", {}).get("name", ""))
        art = ac.get("artist", {})
        if art.get("name") and art.get("name") != names[-1]:
            names.append(art["name"])
        if art.get("id"):
            mbids.append(art["id"])
        parts.append((ac.get("name") or "") + (ac.get("joinphrase") or ""))
    return names, mbids, "".join(parts)


class MusicBrainz:
    def __init__(self, http: HttpClient, title_min: float = 0.85, artist_min: float = 0.85,
                 limit: int = 25):
        self.http = http
        self.title_min = title_min
        self.artist_min = artist_min
        self.limit = limit

    def _search(self, artist: str, title: str) -> tuple[list[dict], str, str | None]:
        q = f'recording:"{lucene_escape(title)}" AND artist:"{lucene_escape(artist)}"'
        r = self.http.get(f"{BASE}/recording", params={"query": q, "fmt": "json", "limit": self.limit})
        if not r.ok or r.data is None:
            return [], q, f"http {r.status}"
        return r.data.get("recordings", []) or [], q, None

    def _filter(self, recs: list[dict], artist: str, title: str) -> list[MBMatch]:
        out = []
        for rec in recs:
            if rec.get("video"):
                continue
            names, mbids, credit = _credit_names(rec)
            ts = title_similarity(title, rec.get("title", ""))
            as_ = artist_similarity(artist, names, credit)
            if ts >= self.title_min and as_ >= self.artist_min:
                out.append(MBMatch(
                    recording_mbid=rec["id"], title=rec.get("title", ""),
                    artist_credit=credit, artist_mbids=mbids,
                    first_release_date=rec.get("first-release-date"),
                    mb_score=int(rec.get("score", 0)), title_sim=ts, artist_sim=as_,
                ))
        return out

    def lookup(self, artist: str, title: str) -> MBResult:
        recs, q, err = self._search(artist, title)
        matches = self._filter(recs, artist, title)
        main = primary_artist(artist)
        if not matches and main != artist:
            # Reintento con el artista principal ("X feat. Y" -> "X").
            recs, q, err = self._search(main, title)
            matches = self._filter(recs, artist, title)
        return MBResult(found=bool(matches), matches=matches, query_used=q, error=err)

    def tags(self, recording_mbid: str, artist_mbids: list[str]) -> dict[str, list[tuple[str, int]]]:
        """Fallback de tags si ListenBrainz no responde: lookup directo en MB."""
        out: dict[str, list[tuple[str, int]]] = {"recording": [], "artist": []}
        r = self.http.get(f"{BASE}/recording/{recording_mbid}", params={"inc": "tags genres", "fmt": "json"})
        if r.ok and r.data:
            out["recording"] = [(t["name"], int(t.get("count", 0))) for t in r.data.get("tags", []) + r.data.get("genres", [])]
        for amb in artist_mbids[:2]:
            r = self.http.get(f"{BASE}/artist/{amb}", params={"inc": "tags genres", "fmt": "json"})
            if r.ok and r.data:
                out["artist"] += [(t["name"], int(t.get("count", 0))) for t in r.data.get("tags", []) + r.data.get("genres", [])]
        return out
