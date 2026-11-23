"""Cliente HTTP con caché en disco, rate limit por host y reintentos.

La caché hace que re-correr la prueba sea gratis y que la demo tenga
un fallback si una API externa se cae.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

USER_AGENT = "OndaPoC/0.1 (proyecto academico NLP)"

# Segundos mínimos entre requests al mismo host.
DEFAULT_MIN_INTERVAL = {
    "musicbrainz.org": 1.1,          # MusicBrainz pide <= 1 req/s
    "api.listenbrainz.org": 0.5,
    "ws.audioscrobbler.com": 0.25,   # Last.fm: "no varias por segundo"
    "api.spotify.com": 0.15,
    "accounts.spotify.com": 0.5,
}


@dataclass
class Response:
    status: int
    data: Any  # JSON decodificado, o None
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpClient:
    def __init__(
        self,
        cache_path: str | Path | None = "cache/http_cache.sqlite",
        user_agent: str = USER_AGENT,
        min_interval: dict[str, float] | None = None,
        max_retries: int = 3,
        timeout: float = 20.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.min_interval = {**DEFAULT_MIN_INTERVAL, **(min_interval or {})}
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call: dict[str, float] = {}
        self._sleep = sleep
        self.stats = {"network": 0, "cache_hits": 0, "errors": 0}
        self._db = None
        if cache_path is not None:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(cache_path))
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS cache "
                "(key TEXT PRIMARY KEY, status INTEGER, body TEXT, ts REAL)"
            )

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _key(method: str, url: str, params: dict | None, body: Any, cache_tag: str) -> str:
        raw = json.dumps([method, url, sorted((params or {}).items()), body, cache_tag],
                         ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Response | None:
        if self._db is None:
            return None
        row = self._db.execute("SELECT status, body FROM cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        return Response(row[0], json.loads(row[1]) if row[1] else None, from_cache=True)

    def _cache_put(self, key: str, resp: Response) -> None:
        if self._db is None:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?)",
            (key, resp.status, json.dumps(resp.data, ensure_ascii=False), time.time()),
        )
        self._db.commit()

    # ------------------------------------------------------------- rate limit
    def _throttle(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        interval = self.min_interval.get(host, 0.0)
        last = self._last_call.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_call[host] = time.monotonic()

    # ---------------------------------------------------------------- request
    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        data: dict | None = None,
        headers: dict | None = None,
        auth: tuple[str, str] | None = None,
        use_cache: bool = True,
        cache_tag: str = "",
    ) -> Response:
        """Hace el request. Cachea respuestas 2xx y 404 (un "no existe" también es dato).

        `cache_tag` permite separar entradas que dependen de algo que no está
        en la URL (por ejemplo, con/sin token). Nunca se guardan secretos en la clave.
        """
        key = self._key(method, url, params, json_body if json_body is not None else data, cache_tag)
        if use_cache:
            cached = self._cache_get(key)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached

        backoff = 1.0
        for attempt in range(self.max_retries + 1):
            self._throttle(url)
            try:
                r = self.session.request(
                    method, url, params=params, json=json_body, data=data,
                    headers=headers, auth=auth, timeout=self.timeout,
                )
            except requests.RequestException:
                self.stats["errors"] += 1
                if attempt == self.max_retries:
                    return Response(0, None)
                self._sleep(backoff)
                backoff *= 2
                continue

            self.stats["network"] += 1
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                retry_after = r.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else backoff
                except ValueError:
                    wait = backoff
                self._sleep(min(wait, 60))
                backoff *= 2
                continue

            try:
                payload = r.json()
            except ValueError:
                payload = None
            resp = Response(r.status_code, payload)
            if use_cache and (resp.ok or resp.status == 404):
                self._cache_put(key, resp)
            if not resp.ok:
                self.stats["errors"] += 1
            return resp
        return Response(0, None)

    def get(self, url: str, params: dict | None = None, **kw) -> Response:
        return self.request("GET", url, params=params, **kw)

    def post(self, url: str, json_body: Any = None, **kw) -> Response:
        return self.request("POST", url, json_body=json_body, **kw)


def build_user_agent(contact: str | None) -> str:
    """MusicBrainz pide un User-Agent con forma de contacto."""
    return f"OndaPoC/0.1 ( {contact} )" if contact else USER_AGENT
