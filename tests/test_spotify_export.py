import json
import socket
import threading
import time

import requests

import vibematch_poc.__main__ as cli
from vibematch_poc.http import Response
from vibematch_poc.sources import spotify_user as su

from .fakes import FakeHttp


def track(name, artists, uri, album="Album"):
    return {"name": name, "uri": uri, "album": {"name": album},
            "artists": [{"name": a} for a in artists]}


def test_pkce_challenge_is_base64url_sha256_without_padding():
    import base64
    import hashlib
    v = su.make_verifier()
    assert 43 <= len(v) <= 128 and set(v) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    c = su.code_challenge(v)
    assert len(c) == 43 and "=" not in c
    assert base64.urlsafe_b64decode(c + "=") == hashlib.sha256(v.encode()).digest()


def test_auth_url_has_pkce_and_no_secret():
    url = su.build_auth_url("cid", su.DEFAULT_REDIRECT, "v" * 50, "st")
    assert "code_challenge_method=S256" in url and "client_secret" not in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8888%2Fcallback" in url


def test_resolve_prefers_studio_version_and_main_artist():
    items = [
        track("Corazon Mentiroso", ["Karina"], "uri:karaoke", album="Karaoke la Princesita"),
        track("Corazón Mentiroso - En Vivo", ["Karina"], "uri:live"),
        track("Corazon Mentiroso", ["Karina"], "uri:studio", album="Sin Vergüenza"),
    ]
    http = FakeHttp([("GET", "/v1/search", lambda p, b: Response(200, {"tracks": {"items": items}}))])
    res = su.SpotifyExporter(http, "tok").resolve("Karina", "Corazón mentiroso")
    assert res["uri"] == "uri:studio" and res["flags"] == []
    assert len(http.calls) == 1  # con versión limpia no hace la segunda búsqueda


def test_resolve_accepts_live_when_it_is_the_only_one():
    items = [track("Pobre Corazón - En Vivo", ["Ke Personajes", "Onda Sabanera"], "uri:live")]
    http = FakeHttp([("GET", "/v1/search", lambda p, b: Response(200, {"tracks": {"items": items}}))])
    res = su.SpotifyExporter(http, "tok").resolve("Ke Personajes", "Pobre corazón")
    assert res["found"] and res["flags"] == ["en vivo"]


def test_resolve_not_found():
    items = [track("Entre Beso y Beso", ["Ke Personajes"], "uri:x")]
    http = FakeHttp([("GET", "/v1/search", lambda p, b: Response(200, {"tracks": {"items": items}}))])
    assert not su.SpotifyExporter(http, "tok").resolve("Ke Personajes", "Tu forma de ser")["found"]


def test_add_items_batches_and_falls_back_to_tracks_endpoint():
    http = FakeHttp([
        ("POST", "/items", lambda p, b: Response(405, None)),
        ("POST", "/tracks", lambda p, b: Response(201, {"snapshot_id": "s"})),
    ])
    used = su.SpotifyExporter(http, "tok").add_items("pl", [f"u{i}" for i in range(150)])
    assert used == "tracks"
    sent = [c[3]["uris"] for c in http.calls if c[1].endswith("/tracks")]
    assert [len(s) for s in sent] == [100, 50]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_wait_for_code_receives_redirect():
    redirect = f"http://127.0.0.1:{_free_port()}/callback"
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("code", su.wait_for_code(redirect, "st", timeout=10)))
    t.start()
    time.sleep(0.3)
    r = requests.get(redirect, params={"code": "abc", "state": "st"}, timeout=5)
    t.join(5)
    assert r.status_code == 200 and out["code"] == "abc"


def test_authorize_reuses_refresh_token(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text(json.dumps({"refresh_token": "r1"}))
    http = FakeHttp([("POST", "accounts.spotify.com/api/token",
                      lambda p, b: Response(200, {"access_token": "new", "expires_in": 3600}))])
    tok = su.authorize(http, "cid", su.DEFAULT_REDIRECT, path,
                       open_browser=lambda u: (_ for _ in ()).throw(AssertionError("no debería abrir")))
    assert tok == "new" and http.calls[0][3] is None  # va como form data, no JSON
    assert json.loads(path.read_text())["refresh_token"] == "r1"


def test_cli_export_creates_private_playlist(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda p: None)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(su, "authorize", lambda *a, **k: "tok")
    created = {}

    def search(p, b):
        if "Gasolina" in p["q"]:
            return Response(200, {"tracks": {"items": [track("Gasolina", ["Daddy Yankee"], "spotify:track:g")]}})
        return Response(200, {"tracks": {"items": []}})

    def create(p, b):
        created.update(b)
        return Response(201, {"id": "pl1", "external_urls": {"spotify": "https://open.spotify.com/playlist/pl1"}})

    http = FakeHttp([
        ("GET", "/v1/search", search),
        ("POST", "/me/playlists", create),
        ("POST", "/playlists/pl1/items", lambda p, b: Response(201, {"snapshot_id": "s"})),
    ])
    monkeypatch.setattr(cli, "make_http", lambda cache=True, timeout=20: http)
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"prompts": {"preboliche": [
        {"artist": "Daddy Yankee", "title": "Gasolina"}, {"artist": "Nadie", "title": "Inventada"}]}}))
    cfg_path = str(cli.Path(__file__).parent.parent / "config.toml")
    assert cli.main(["--config", cfg_path, "export", "--candidates", str(cands), "--prompt", "preboliche"]) == 0
    assert created["public"] is False and "VibeMatch" in created["name"]
    summary = json.loads(next(tmp_path.glob("results/*/export_summary.json")).read_text())
    assert summary["found"] == 1 and summary["playlist_url"].endswith("pl1")


def test_cli_export_dry_run_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda p: None)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(su, "authorize", lambda *a, **k: "tok")
    http = FakeHttp([("GET", "/v1/search", lambda p, b: Response(200, {"tracks": {"items": [
        track("Gasolina", ["Daddy Yankee"], "spotify:track:g")]}}))])
    monkeypatch.setattr(cli, "make_http", lambda cache=True, timeout=20: http)
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"prompts": {"preboliche": [{"artist": "Daddy Yankee", "title": "Gasolina"}]}}))
    cfg_path = str(cli.Path(__file__).parent.parent / "config.toml")
    assert cli.main(["--config", cfg_path, "export", "--candidates", str(cands),
                     "--prompt", "preboliche", "--dry-run"]) == 0
    assert all(c[0] == "GET" for c in http.calls)


def test_auth_url_forces_account_dialog():
    assert "show_dialog=true" in su.build_auth_url("cid", su.DEFAULT_REDIRECT, "v" * 50, "st")


def _export_setup(tmp_path, monkeypatch, created, seen_paths):
    monkeypatch.setattr(cli, "load_dotenv", lambda p: None)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setattr(cli, "ROOT", tmp_path)

    def fake_authorize(http, client_id, redirect, token_path, **kw):
        seen_paths.append(token_path)
        return "tok"

    monkeypatch.setattr(su, "authorize", fake_authorize)

    def create(p, b):
        created.update(b)
        return Response(201, {"id": "pl1", "external_urls": {"spotify": "https://open.spotify.com/playlist/pl1"}})

    http = FakeHttp([
        ("GET", "/v1/search", lambda p, b: Response(200, {"tracks": {"items": [
            track("Gasolina", ["Daddy Yankee"], "spotify:track:g")]}})),
        ("POST", "/me/playlists", create),
        ("POST", "/playlists/pl1/items", lambda p, b: Response(201, {"snapshot_id": "s"})),
    ])
    monkeypatch.setattr(cli, "make_http", lambda cache=True, timeout=20: http)
    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"prompts": {"preboliche": [{"artist": "Daddy Yankee", "title": "Gasolina"}]}}))
    return cands, str(cli.Path(__file__).parent.parent / "config.toml")


def test_export_team_account_public_with_qr(tmp_path, monkeypatch):
    created, paths = {}, []
    cands, cfg = _export_setup(tmp_path, monkeypatch, created, paths)
    assert cli.main(["--config", cfg, "export", "--candidates", str(cands), "--prompt", "preboliche",
                     "--account", "equipo", "--public", "--qr"]) == 0
    assert created["public"] is True
    assert paths[0].name == "spotify_token_equipo.json"
    png = next(tmp_path.glob("results/*/playlist_qr.png"))
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_export_migrates_legacy_token_for_personal(tmp_path, monkeypatch):
    created, paths = {}, []
    cands, cfg = _export_setup(tmp_path, monkeypatch, created, paths)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "spotify_token.json").write_text("{}")
    assert cli.main(["--config", cfg, "export", "--candidates", str(cands), "--prompt", "preboliche"]) == 0
    assert paths[0].name == "spotify_token_personal.json" and paths[0].exists()
    assert created["public"] is False


def test_export_rejects_weird_account_names(tmp_path, monkeypatch):
    created, paths = {}, []
    cands, cfg = _export_setup(tmp_path, monkeypatch, created, paths)
    assert cli.main(["--config", cfg, "export", "--candidates", str(cands), "--prompt", "preboliche",
                     "--account", "../x"]) == 2
    assert not paths
