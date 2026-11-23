"""Pipeline completo con HTTP falso: MB + LB + Last.fm + Spotify -> métricas -> reporte."""

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from onda_poc.http import Response
from onda_poc.metrics import summarize
from onda_poc.pipeline import Sources, verify
from onda_poc.report import render, results_rows
from onda_poc.sources.lastfm import Lastfm
from onda_poc.sources.listenbrainz import ListenBrainz
from onda_poc.sources.musicbrainz import MusicBrainz
from onda_poc.sources.spotify import Spotify

from .fakes import FakeHttp, mb_recording

CFG = tomllib.loads((Path(__file__).parent.parent / "config.toml").read_text())

CANDIDATES = {
    "preboliche": [
        {"artist": "Daddy Yankee", "title": "Gasolina"},
        {"artist": "Grupo Inventado", "title": "Canción Que No Existe"},
        {"artist": "Daddy Yankee", "title": "Gasolina"},  # duplicado
    ],
    "lluvia": [
        {"artist": "Radiohead", "title": "No Surprises"},
    ],
}


def mb_search(params, body):
    q = params["query"]
    if "Gasolina" in q:
        return Response(200, {"recordings": [
            mb_recording("gas-album", "Gasolina", "Daddy Yankee", "dy", score=100, date="2004-07-13"),
            mb_recording("gas-single", "Gasolina", "Daddy Yankee", "dy", score=98, date="2004-10-01"),
            mb_recording("gas-video", "Gasolina", "Daddy Yankee", "dy", video=True),
            mb_recording("otra", "Gasolina", "Otro Artista", "oa"),
        ]})
    if "No Surprises" in q:
        return Response(200, {"recordings": [mb_recording("nos", "No Surprises", "Radiohead", "rh", date="1997-05-21")]})
    return Response(200, {"recordings": []})


def lb_popularity(params, body):
    counts = {"gas-album": (1000, 50), "gas-single": (90000, 400), "nos": (500000, 9000)}
    return Response(200, [
        {"recording_mbid": m, "total_listen_count": counts.get(m, (None, None))[0],
         "total_user_count": counts.get(m, (None, None))[1]}
        for m in body["recording_mbids"]
    ])


def lb_tags(params, body):
    data = {}
    if "gas-single" in body["recording_mbids"]:
        data["gas-single"] = {"tag": {
            "recording": [{"tag": "reggaeton", "count": 3}],
            "artist": [{"tag": "latin", "count": 5, "artist_mbid": "dy"}, {"tag": "hip hop", "count": 2}],
            "release_group": [{"tag": "2004", "count": 1}],
        }}
    return Response(200, data)


def mb_lookup(params, body):
    # Fallback de tags para Radiohead (no vino en LB).
    return Response(200, {"tags": [{"name": "alternative rock", "count": 4}], "genres": [{"name": "art rock", "count": 2}]})


def lastfm(params, body):
    if params["method"] == "track.getInfo":
        if params["track"] == "Gasolina":
            return Response(200, {"track": {"name": "Gasolina", "artist": {"name": "Daddy Yankee"},
                                            "listeners": "1200000", "playcount": "9000000"}})
        if params["track"] == "No Surprises":
            return Response(200, {"track": {"name": "No Surprises", "artist": {"name": "Radiohead"},
                                            "listeners": "1500000", "playcount": "20000000"}})
        return Response(200, {"error": 6, "message": "Track not found"})
    if params["method"] == "track.getTopTags":
        if params["track"] == "Gasolina":
            return Response(200, {"toptags": {"tag": [
                {"name": "party", "count": 100}, {"name": "dance", "count": 40},
                {"name": "seen live", "count": 30}, {"name": "ruido", "count": 1}]}})
        return Response(200, {"toptags": {"tag": [{"name": "sad", "count": 100}, {"name": "mellow", "count": 60}]}})
    return Response(400, None)


def spotify_token(params, body):
    return Response(200, {"access_token": "tok", "expires_in": 3600})


def spotify_search(params, body):
    if "Gasolina" in params["q"]:
        return Response(200, {"tracks": {"items": [
            {"name": "Gasolina", "artists": [{"name": "Daddy Yankee"}], "uri": "spotify:track:gas"}]}})
    return Response(200, {"tracks": {"items": []}})


def build(with_optional=True):
    http = FakeHttp([
        ("GET", "musicbrainz.org/ws/2/recording/", mb_lookup),
        ("GET", "musicbrainz.org/ws/2/artist/", lambda p, b: Response(200, {"tags": [], "genres": []})),
        ("GET", "musicbrainz.org/ws/2/recording", mb_search),
        ("POST", "/popularity/recording", lb_popularity),
        ("POST", "/metadata/recording", lb_tags),
        ("GET", "audioscrobbler", lastfm),
        ("POST", "accounts.spotify.com", spotify_token),
        ("GET", "api.spotify.com/v1/search", spotify_search),
    ])
    src = Sources(
        musicbrainz=MusicBrainz(http),
        listenbrainz=ListenBrainz(http),
        lastfm=Lastfm(http, "k") if with_optional else None,
        spotify=Spotify(http, "id", "secret") if with_optional else None,
    )
    return http, src


def test_full_pipeline():
    http, src = build()
    records, info = verify(CANDIDATES, src, CFG, quiet=True)
    assert len(records) == 4
    gas, fake, dup, nos = records

    # Elige la grabación más escuchada, ignora video y otro artista.
    assert gas["musicbrainz"]["found"] and gas["musicbrainz"]["n_matches"] == 2
    assert gas["musicbrainz"]["recording_mbid"] == "gas-single"
    assert gas["musicbrainz"]["year"] == 2004
    assert gas["listenbrainz"]["user_count"] == 400
    assert gas["tag_source"] == "listenbrainz"
    # Tags: canción = recording + release_group + Last.fm (count >= 5, sin basura, sin años).
    assert gas["derived"]["useful_tags_song"] == ["reggaeton", "party", "dance"]
    # 'dance' es género, no mood: solo cuenta 'party'.
    assert gas["derived"]["mood_tags_song"] == ["party"]
    assert gas["derived"]["useful_tags_any"] == ["reggaeton", "party", "dance", "latin", "hip hop"]
    assert gas["derived"]["recognizable"] and gas["derived"]["hit"]
    assert gas["spotify"] == {"enabled": True, "found": True, "uri": "spotify:track:gas", "error": None}

    assert not fake["musicbrainz"]["found"]
    assert not fake["derived"]["found_anywhere"]
    assert dup["duplicate"]

    # Radiohead: tags por fallback a MusicBrainz.
    assert nos["tag_source"] == "musicbrainz"
    assert "alternative rock" in nos["derived"]["useful_tags_song"]

    # Spotify: no se guarda nada más que found/uri.
    assert set(gas["spotify"]) == {"enabled", "found", "uri", "error"}

    summary = summarize(records, info, CFG)
    o = summary["overall"]
    assert o["n"] == 4 and o["duplicates"] == 1
    assert abs(o["exists_in_musicbrainz"] - 2 / 3) < 1e-9
    assert abs(o["not_found_anywhere"] - 1 / 3) < 1e-9
    assert summary["per_prompt"]["lluvia"]["exists_in_musicbrainz"] == 1.0
    crit = {c["key"]: c for c in summary["criteria"]}
    assert crit["exists_in_musicbrainz"]["status"] == "NO PASA"
    assert crit["exists_in_musicbrainz"]["prompts_below"] == ["preboliche"]
    assert summary["verdict"].startswith("NO-GO")

    md = render(summary, records, info, {"model": "test"}, {"preboliche": "x", "lluvia": "y"})
    assert "Canción Que No Existe" in md
    assert "spotify:track" not in md
    rows = results_rows(records)
    assert rows[0]["mb_found"] is True and rows[1]["mb_found"] is False


def test_without_optional_sources_marks_na():
    _, src = build(with_optional=False)
    records, info = verify({"lluvia": CANDIDATES["lluvia"]}, src, CFG, quiet=True)
    summary = summarize(records, info, CFG)
    crit = {c["key"]: c for c in summary["criteria"]}
    assert crit["resolved_in_spotify"]["status"] == "N/A"
    assert crit["has_3_useful_tags"]["status"] == "N/A"
    assert crit["exists_in_musicbrainz"]["status"] == "PASA"
    assert summary["verdict"].startswith("INCOMPLETO")


def test_lastfm_autocorrect_to_other_song_is_rejected():
    http = FakeHttp([("GET", "audioscrobbler", lambda p, b: Response(200, {"track": {
        "name": "Otra Canción", "artist": {"name": "Daddy Yankee"}, "listeners": "5"}}))])
    res = Lastfm(http, "k").lookup("Daddy Yankee", "Gasolina")
    assert not res.found and res.error == "autocorrect a otra canción"


def test_spotify_auth_failure_is_reported():
    http = FakeHttp([("POST", "accounts.spotify.com",
                      lambda p, b: Response(400, {"error": "invalid_client"}))])
    sp = Spotify(http, "id", "bad")
    res = sp.lookup("Daddy Yankee", "Gasolina")
    assert not res.found and "invalid_client" in res.error
