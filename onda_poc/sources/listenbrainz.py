"""ListenBrainz: popularidad (escuchas/oyentes) y tags. Datos CC0.

Token opcional (gratis, en listenbrainz.org/settings). Algunos endpoints
lo empezaron a exigir por abuso de scrapers; si falla sin token, se reporta.
"""

from __future__ import annotations

from ..http import HttpClient

BASE = "https://api.listenbrainz.org/1"


class ListenBrainz:
    def __init__(self, http: HttpClient, token: str | None = None, batch_size: int = 25):
        self.http = http
        self.token = token
        self.batch_size = batch_size
        self.last_error: str | None = None

    def _headers(self) -> dict | None:
        return {"Authorization": f"Token {self.token}"} if self.token else None

    def _post(self, path: str, body: dict):
        return self.http.post(f"{BASE}{path}", json_body=body, headers=self._headers(),
                              cache_tag="token" if self.token else "")

    def popularity(self, mbids: list[str]) -> dict[str, tuple[int | None, int | None]]:
        """mbid -> (total_listen_count, total_user_count). None si no hay datos."""
        out: dict[str, tuple[int | None, int | None]] = {}
        uniq = list(dict.fromkeys(mbids))
        for i in range(0, len(uniq), self.batch_size):
            batch = uniq[i:i + self.batch_size]
            r = self._post("/popularity/recording", {"recording_mbids": batch})
            if not r.ok or not isinstance(r.data, list):
                self.last_error = f"popularity http {r.status}"
                continue
            for item in r.data:
                out[item.get("recording_mbid")] = (item.get("total_listen_count"), item.get("total_user_count"))
        return out

    def tags(self, mbids: list[str]) -> dict[str, dict[str, list[tuple[str, int]]]]:
        """mbid -> {'recording': [...], 'artist': [...], 'release_group': [...]} con (tag, count)."""
        out: dict[str, dict[str, list[tuple[str, int]]]] = {}
        uniq = list(dict.fromkeys(mbids))
        for i in range(0, len(uniq), self.batch_size):
            batch = uniq[i:i + self.batch_size]
            r = self._post("/metadata/recording/", {"recording_mbids": batch, "inc": "tag"})
            if not r.ok or not isinstance(r.data, dict):
                self.last_error = f"metadata http {r.status}"
                continue
            for mbid, meta in r.data.items():
                tag = (meta or {}).get("tag", {}) or {}
                out[mbid] = {
                    level: [(t.get("tag", ""), int(t.get("count", 0) or 0)) for t in tag.get(level, []) or []]
                    for level in ("recording", "artist", "release_group")
                }
        return out
