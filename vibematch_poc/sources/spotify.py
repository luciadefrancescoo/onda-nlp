"""Spotify: SOLO resolver (artista, título) -> URI para poder exportar.

Por la cláusula 14 de la Developer Policy (no ingerir contenido de Spotify
en modelos de IA), de acá no sale nada hacia el LLM ni al ranking: solo se
guarda si se encontró y el URI. Nada de metadatos de Spotify en los resultados,
y las respuestas no se cachean en disco.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..http import HttpClient
from ..matching import artist_similarity, primary_artist, title_similarity

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"


@dataclass
class SpotifyResult:
    found: bool
    uri: str | None = None
    error: str | None = None


class Spotify:
    def __init__(self, http: HttpClient, client_id: str, client_secret: str,
                 market: str = "AR", title_min: float = 0.85, artist_min: float = 0.85):
        self.http = http
        self.client_id = client_id
        self.client_secret = client_secret
        self.market = market
        self.title_min = title_min
        self.artist_min = artist_min
        self._token: str | None = None
        self._token_exp = 0.0
        self.auth_error: str | None = None

    def _get_token(self) -> str | None:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        r = self.http.request("POST", TOKEN_URL, data={"grant_type": "client_credentials"},
                              auth=(self.client_id, self.client_secret), use_cache=False)
        if not r.ok or not r.data or "access_token" not in r.data:
            self.auth_error = f"token http {r.status}: {(r.data or {}).get('error_description') or (r.data or {}).get('error')}"
            return None
        self._token = r.data["access_token"]
        self._token_exp = time.time() + int(r.data.get("expires_in", 3600))
        return self._token

    def _search(self, q: str):
        tok = self._get_token()
        if tok is None:
            return None
        return self.http.get(
            SEARCH_URL,
            params={"q": q, "type": "track", "limit": 10, "market": self.market},
            headers={"Authorization": f"Bearer {tok}"},
            use_cache=False,  # no guardamos respuestas de Spotify en disco
        )

    def lookup(self, artist: str, title: str) -> SpotifyResult:
        main = primary_artist(artist)
        for q in (f'track:"{title}" artist:"{main}"', f"{title} {main}"):
            r = self._search(q)
            if r is None:
                return SpotifyResult(False, error=self.auth_error)
            if not r.ok or not r.data:
                return SpotifyResult(False, error=f"search http {r.status}")
            for item in (r.data.get("tracks", {}) or {}).get("items", []) or []:
                names = [a.get("name", "") for a in item.get("artists", [])]
                if (title_similarity(title, item.get("name", "")) >= self.title_min
                        and artist_similarity(artist, names, ", ".join(names)) >= self.artist_min):
                    return SpotifyResult(True, uri=item.get("uri"))
        return SpotifyResult(False)
