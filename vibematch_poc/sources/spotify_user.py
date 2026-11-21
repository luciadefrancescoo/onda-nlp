"""Exportar a Spotify con la cuenta de una persona (Authorization Code + PKCE).

Es el camino que usaría la app real: la persona inicia sesión, la app busca
cada canción y crea una playlist privada en su cuenta. Con PKCE no hace falta
el client secret, solo el Client ID.

Igual que en sources/spotify.py: lo que devuelve Spotify sirve solo para
elegir la canción y exportarla. No entra a ningún modelo ni al ranking.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

from ..http import HttpClient
from ..matching import (
    artist_similarity, normalize_artist, primary_artist, strip_accents, title_similarity,
)

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-private playlist-modify-public"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"  # Spotify ya no acepta 'localhost'

# Palabras que delatan una versión que no es la original de estudio.
VERSION_WORDS = ["en vivo", "live", "karaoke", "remix", "instrumental", "cover",
                 "sped up", "slowed", "acoustic", "acustic", "version cancha",
                 "demo", "tribute", "tributo", "8 bit", "lullaby"]


# ---------------------------------------------------------------------- PKCE
def make_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_auth_url(client_id: str, redirect_uri: str, verifier: str, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
        "code_challenge_method": "S256", "code_challenge": code_challenge(verifier),
        "scope": SCOPES, "state": state,
    })


def wait_for_code(redirect_uri: str, expected_state: str, timeout: float = 180) -> str:
    """Levanta un servidor en 127.0.0.1 y espera la redirección de Spotify."""
    parsed = urlparse(redirect_uri)
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path != parsed.path:
                self.send_response(404)
                self.end_headers()
                return
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            result.update(q)
            ok = "code" in q and q.get("state") == expected_state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Listo, ya podés cerrar esta pestaña y volver a la terminal." if ok
                   else "No se pudo autorizar. Volvé a la terminal para ver el error.")
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *a):
            pass

    server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 80), Handler)
    server.timeout = 1
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        raise TimeoutError("No llegó la autorización de Spotify a tiempo.")
    if "error" in result:
        raise PermissionError(f"Spotify devolvió: {result['error']}")
    if result.get("state") != expected_state:
        raise PermissionError("El parámetro state no coincide (posible redirección ajena).")
    return result["code"]


def _save(path: Path, token: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    token = {**token, "obtained_at": time.time()}
    path.write_text(json.dumps(token))
    path.chmod(0o600)


def authorize(http: HttpClient, client_id: str, redirect_uri: str, token_path: Path,
              open_browser: Callable[[str], bool] = webbrowser.open,
              waiter: Callable[[str, str], str] = wait_for_code) -> str:
    """Devuelve un access token. Reusa el refresh token guardado si existe."""
    if token_path.exists():
        saved = json.loads(token_path.read_text())
        if saved.get("refresh_token"):
            r = http.request("POST", TOKEN_URL, use_cache=False, data={
                "grant_type": "refresh_token", "refresh_token": saved["refresh_token"],
                "client_id": client_id})
            if r.ok and r.data and "access_token" in r.data:
                _save(token_path, {**saved, **r.data})
                return r.data["access_token"]

    verifier, state = make_verifier(), secrets.token_urlsafe(16)
    url = build_auth_url(client_id, redirect_uri, verifier, state)
    print("\nAbrí este link para autorizar (se intenta abrir solo):\n" + url + "\n", flush=True)
    open_browser(url)
    code = waiter(redirect_uri, state)
    r = http.request("POST", TOKEN_URL, use_cache=False, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "code_verifier": verifier})
    if not r.ok or not r.data or "access_token" not in r.data:
        raise PermissionError(f"No se pudo obtener el token (http {r.status}): {r.data}")
    _save(token_path, r.data)
    return r.data["access_token"]


# -------------------------------------------------------------- resolución
def _pad(s: str) -> str:
    for ch in "-()[]":
        s = s.replace(ch, " ")
    return " " + " ".join(strip_accents(s).lower().split()) + " "


def version_flags(track_name: str, album_name: str, candidate_title: str) -> list[str]:
    """Palabras de 'otra versión' presentes en el track/álbum y no pedidas por el candidato."""
    name, album, wanted = _pad(track_name), _pad(album_name), _pad(candidate_title)
    flags = []
    for w in VERSION_WORDS:
        token = f" {w} "
        if (token in name or (w in ("karaoke", "tribute", "tributo", "lullaby", "8 bit") and token in album)) \
                and token not in wanted:
            flags.append(w)
    return flags


class SpotifyExporter:
    def __init__(self, http: HttpClient, token: str, market: str = "AR",
                 title_min: float = 0.85, artist_min: float = 0.85):
        self.http = http
        self.token = token
        self.market = market
        self.title_min = title_min
        self.artist_min = artist_min

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _search(self, q: str) -> list[dict]:
        r = self.http.request("GET", f"{API}/search", use_cache=False, headers=self._h(),
                              params={"q": q, "type": "track", "limit": 10, "market": self.market})
        if r.status == 401:
            raise PermissionError("Token vencido o inválido (401).")
        if not r.ok or not r.data:
            return []
        return (r.data.get("tracks") or {}).get("items") or []

    def resolve(self, artist: str, title: str) -> dict:
        main = primary_artist(artist)
        best, best_key = None, None
        for q in (f'track:"{title}" artist:"{main}"', f"{title} {main}"):
            for item in self._search(q):
                names = [a.get("name", "") for a in item.get("artists", [])]
                ts = title_similarity(title, item.get("name", ""))
                as_ = artist_similarity(artist, names, ", ".join(names))
                if ts < self.title_min or as_ < self.artist_min:
                    continue
                flags = version_flags(item.get("name", ""), (item.get("album") or {}).get("name", ""), title)
                lead_ok = bool(names) and normalize_artist(names[0]) == normalize_artist(main)
                key = (not flags, lead_ok, round(ts + as_, 3))
                if best_key is None or key > best_key:
                    best, best_key = (item, names, flags), key
            if best is not None and not best[2]:
                break  # ya hay una versión limpia, no hace falta la búsqueda libre
        if best is None:
            return {"found": False, "uri": None, "spotify_name": None, "spotify_artists": None, "flags": []}
        item, names, flags = best
        return {"found": True, "uri": item.get("uri"), "spotify_name": item.get("name"),
                "spotify_artists": ", ".join(names), "flags": flags}

    # ------------------------------------------------------------ escritura
    def create_playlist(self, name: str, description: str, public: bool = False) -> tuple[str, str]:
        r = self.http.request("POST", f"{API}/me/playlists", use_cache=False, headers=self._h(),
                              json_body={"name": name, "description": description, "public": public})
        if not r.ok or not r.data or "id" not in r.data:
            raise RuntimeError(f"No se pudo crear la playlist (http {r.status}): {r.data}")
        return r.data["id"], (r.data.get("external_urls") or {}).get("spotify", "")

    def add_items(self, playlist_id: str, uris: list[str]) -> str:
        """Agrega de a 100. Prueba el endpoint nuevo (/items) y si no existe, el viejo (/tracks)."""
        used = "items"
        for i in range(0, len(uris), 100):
            body = {"uris": uris[i:i + 100]}
            r = self.http.request("POST", f"{API}/playlists/{playlist_id}/items",
                                  use_cache=False, headers=self._h(), json_body=body)
            if r.status in (404, 405):
                used = "tracks"
                r = self.http.request("POST", f"{API}/playlists/{playlist_id}/tracks",
                                      use_cache=False, headers=self._h(), json_body=body)
            if not r.ok:
                raise RuntimeError(f"No se pudieron agregar canciones (http {r.status}): {r.data}")
        return used
