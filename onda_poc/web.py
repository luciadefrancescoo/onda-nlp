"""Demo web de onda. para el AI Fest: servidor local, sin dependencias nuevas.

    python -m onda_poc demo                 # http://127.0.0.1:8000
    python -m onda_poc demo --host 0.0.0.0  # para abrirla desde una tablet en la misma red

Rutas:
    GET  /                  la página
    GET  /api/build?scene=  arma la playlist y transmite el progreso (Server-Sent Events)
    POST /api/export        {"id": ...} crea la playlist en la cuenta de Spotify del equipo y devuelve el QR
    GET  /api/health        qué está andando (para revisar antes de abrir el stand)

Las escenas se arman de a una (Ollama atiende una a la vez); si llega otra, espera.
Cada escena queda anotada en results/demo-log.jsonl para revisar después qué falló.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import service
from .http import HttpClient
from .sources.lastfm import Lastfm

MAX_SCENE = 280
PAGE = Path(__file__).with_name("web") / "index.html"


class DemoApp:
    def __init__(self, cfg: dict, http: HttpClient, lastfm: Lastfm, settings: service.Settings,
                 root: Path, account: str = "equipo", credit: str = ""):
        self.cfg = cfg
        self.http = http
        self.lastfm = lastfm
        self.settings = settings
        self.root = root
        self.account = account
        self.credit = credit
        self.build_lock = threading.Lock()
        self.export_lock = threading.Lock()
        # Últimas playlists armadas: el export usa estas, no lo que mande el navegador.
        self.recent: OrderedDict[str, dict] = OrderedDict()
        self.log_path = root / "results" / "demo-log.jsonl"

    # --- armar -----------------------------------------------------------------
    def build(self, scene_text: str, emit) -> None:
        if not self.build_lock.acquire(blocking=False):
            emit({"type": "status", "step": "queue", "msg": "Hay otra escena en curso; la tuya sigue enseguida…"})
            self.build_lock.acquire()
        t0 = time.monotonic()
        entry = {"ts": datetime.now().isoformat(timespec="seconds"), "scene": scene_text}
        try:
            res = service.build_playlist(scene_text, self.http, self.lastfm, self.settings, emit)
            pid = secrets.token_urlsafe(8)
            self.recent[pid] = {"scene": scene_text, "tracks": [service.track_dict(t) for t in res.tracks]}
            while len(self.recent) > 200:
                self.recent.popitem(last=False)
            emit({"type": "done", "id": pid, "seconds": round(res.seconds, 1), "warnings": res.warnings})
            entry.update(ok=True, id=pid, seconds=round(res.seconds, 1),
                         interpretation=res.interpretation_dict(),
                         tracks=[f"{t.artist} — {t.title}" for t in res.tracks])
        except Exception as e:
            msg = friendly_error(e)
            emit({"type": "error", "msg": msg})
            entry.update(ok=False, error=str(e)[:500], seconds=round(time.monotonic() - t0, 1))
        finally:
            self.build_lock.release()
            self._log(entry)

    # --- exportar --------------------------------------------------------------
    def export(self, pid: str) -> tuple[int, dict]:
        from .sources import spotify_user as su

        item = self.recent.get(pid)
        if not item:
            return 404, {"error": "No encuentro esa playlist. Armala de nuevo."}
        if item.get("url"):
            return 200, item["export"]
        client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        token_path = self.root / "cache" / f"spotify_token_{self.account}.json"
        if not client_id or not token_path.exists():
            return 503, {"error": "Spotify no está configurado en esta compu "
                                  f"(falta iniciar sesión con la cuenta '{self.account}')."}
        with self.export_lock:
            try:
                token = su.authorize(self.http, client_id,
                                     os.environ.get("SPOTIFY_REDIRECT_URI") or su.DEFAULT_REDIRECT, token_path,
                                     open_browser=lambda url: False, waiter=_no_interactive_login)
                m = self.cfg["matching"]
                exp = su.SpotifyExporter(self.http, token, market=self.cfg["run"]["spotify_market"],
                                         title_min=m["title_min_similarity"], artist_min=m["artist_min_similarity"])
                uris = []
                for t in item["tracks"]:
                    r = exp.resolve(t["artist"], t["title"])
                    if r["found"] and r["uri"] not in uris:
                        uris.append(r["uri"])
                if not uris:
                    return 502, {"error": "No encontré estas canciones en Spotify."}
                name = f"onda. · {item['scene'][:80]}"
                desc = f"{item['scene'][:200]} · {self.credit}"
                spid, url = exp.create_playlist(name, desc, public=True)
                exp.add_items(spid, uris)
            except su.RateLimited as e:
                return 429, {"error": "Spotify está saturado por ahora; la playlist igual queda en pantalla.",
                             "retry_after": e.wait}
            except Exception as e:
                return 502, {"error": f"No se pudo crear la playlist en Spotify: {friendly_error(e)}"}
        out = {"url": url, "found": len(uris), "n": len(item["tracks"]), "qr": qr_data_uri(url)}
        item["url"], item["export"] = url, out
        self._log({"ts": datetime.now().isoformat(timespec="seconds"), "export": pid, "url": url,
                   "found": len(uris)})
        return 200, out

    def health(self) -> dict:
        out = {"lastfm": bool(os.environ.get("LASTFM_API_KEY")), "model": self.settings.model,
               "embed_model": self.settings.embed_model,
               "spotify_account": (self.root / "cache" / f"spotify_token_{self.account}.json").exists()}
        r = self.http.request("GET", self.settings.base_url.rstrip("/") + "/models", use_cache=False)
        names = [m.get("id") for m in (r.data or {}).get("data", [])] if r.ok else []
        out["ollama"] = r.ok
        out["model_ready"] = self.settings.model in names
        out["embed_ready"] = any(n and n.split(":")[0] == self.settings.embed_model.split(":")[0] for n in names)
        return out

    def _log(self, entry: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _no_interactive_login(redirect_uri: str, state: str) -> str:
    raise PermissionError("el permiso de Spotify venció; volvé a correr export --account equipo")


def friendly_error(e: Exception) -> str:
    text = str(e)
    if "Connection refused" in text or "11434" in text or "LLM http 0" in text:
        return "No pude hablar con el modelo. ¿Está abierto Ollama?"
    if "No se pudo obtener una respuesta válida" in text:
        return "El modelo no entendió la escena. Probá escribirla de otra forma."
    return text[:200]


def qr_data_uri(url: str) -> str | None:
    try:
        import segno
    except ModuleNotFoundError:
        return None
    return segno.make(url, error="m").svg_data_uri(scale=8, border=2, dark="#111111", light="#ffffff")


def make_handler(app: DemoApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "onda-demo"

        def log_message(self, fmt, *args):  # una línea corta por request
            sys.stderr.write(f"[{datetime.now():%H:%M:%S}] {self.command} {self.path.split('?')[0]}\n")

        def _json(self, status: int, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/health":
                self._json(200, app.health())
            elif u.path == "/api/build":
                scene_text = " ".join((parse_qs(u.query).get("scene") or [""])[0].split())
                if not scene_text:
                    return self._json(400, {"error": "Escribí una escena."})
                if len(scene_text) > MAX_SCENE:
                    return self._json(400, {"error": f"Máximo {MAX_SCENE} caracteres."})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                alive = [True]

                def emit(event: dict) -> None:
                    if not alive[0]:
                        return  # el visitante cerró la página: igual terminamos (queda en caché)
                    try:
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        alive[0] = False

                app.build(scene_text, emit)
            else:
                self._json(404, {"error": "no existe"})

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/api/export":
                return self._json(404, {"error": "no existe"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(min(n, 10_000)) or b"{}")
            except ValueError:
                return self._json(400, {"error": "pedido inválido"})
            status, out = app.export(str(data.get("id", "")))
            self._json(status, out)

    return Handler


def serve(app: DemoApp, host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    print(f"onda. demo en http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}  (Ctrl+C para cortar)")
    if host == "0.0.0.0":
        print("Abierta a la red local: cualquiera en la misma red puede usarla.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nChau.")
