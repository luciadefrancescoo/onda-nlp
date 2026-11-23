import json

import pytest

from onda_poc import scene
from onda_poc.http import Response
from onda_poc.sources.lastfm import Lastfm

from .fakes import FakeHttp


def chat(content):
    return Response(200, {"choices": [{"message": {"content": content}}]})


INTERP = {"moods": ["Chill", "rainy day"], "generos": ["lo-fi"], "artistas": ["Norah Jones", "Inventado XYZ"],
          "epoca": ""}


# --- Interpretación ----------------------------------------------------------

def test_parse_interpretation_keeps_raw_tags_and_era():
    i = scene.parse_interpretation(json.dumps({**INTERP, "epoca": "2000s"}))
    assert i.moods == ["chill", "rainy day"] and i.genres == ["lo-fi"]
    assert i.tags == ["chill", "rainy day", "lo-fi", "2000s"]
    assert i.artists == ["Norah Jones", "Inventado XYZ"]


def test_parse_interpretation_empty_returns_none():
    assert scene.parse_interpretation('{"moods": [], "generos": [], "artistas": []}') is None


def test_interpret_retries_until_usable():
    answers = iter([chat('{"moods": []}'), chat(json.dumps(INTERP))])
    http = FakeHttp([("POST", "/chat/completions", lambda p, b: next(answers))])
    i = scene.interpret(http, "lluvia", "http://h/v1", "m")
    assert i.genres == ["lo-fi"]


# --- Catálogo (Last.fm falso) ------------------------------------------------

def lastfm_handler(params, body):
    m = params["method"]
    if m == "artist.getInfo":
        if params["artist"] == "Norah Jones":
            return Response(200, {"artist": {"name": "Norah Jones", "stats": {"listeners": "2000000"}}})
        return Response(200, {"error": 6, "message": "The artist you supplied could not be found"})
    if m == "tag.getTopTracks":
        tracks = {
            "chill": [{"name": "Amber", "artist": {"name": "311"}},
                      {"name": "Amber (Live)", "artist": {"name": "311"}},
                      {"name": "Don't Know Why", "artist": {"name": "Norah Jones"}}],
            "rainy day": [{"name": "Riders on the Storm", "artist": {"name": "The Doors"}}],
        }.get(params["tag"], [])
        return Response(200, {"tracks": {"track": tracks}})
    if m == "artist.getTopTracks":
        if params["artist"] == "Norah Jones":
            return Response(200, {"toptracks": {"track": [
                {"name": "Don't Know Why", "listeners": "900000", "artist": {"name": "Norah Jones"}},
                {"name": "Come Away With Me", "listeners": "700000", "artist": {"name": "Norah Jones"}},
                {"name": "Sunrise", "listeners": "500000", "artist": {"name": "Norah Jones"}}]}})
        if params["artist"] == "Madeleine Peyroux":
            return Response(200, {"toptracks": {"track": [
                {"name": "Dance Me to the End of Love", "listeners": "300000",
                 "artist": {"name": "Madeleine Peyroux"}}]}})
        return Response(200, {"toptracks": {"track": []}})
    if m == "artist.getSimilar":
        return Response(200, {"similarartists": {"artist": [{"name": "Madeleine Peyroux"}]}})
    if m == "track.getInfo":
        return Response(200, {"track": {"name": params["track"], "artist": {"name": params["artist"]},
                                        "listeners": "100000"}})
    if m == "track.getTopTags":
        tags = {"Amber": [{"name": "chill", "count": 100}, {"name": "mellow", "count": 40}],
                "Don't Know Why": [{"name": "Lo-Fi", "count": 30}, {"name": "jazz", "count": 100},
                                   {"name": "seen live", "count": 90}]}.get(params["track"], [])
        return Response(200, {"toptags": {"tag": tags}})
    return Response(404, None)


@pytest.fixture
def lastfm():
    return Lastfm(FakeHttp([("GET", "audioscrobbler", lastfm_handler)]), "key")


def test_verify_artists_drops_invented(lastfm):
    ok, bad = scene.verify_artists(lastfm, ["Norah Jones", "Inventado XYZ"])
    assert ok == ["Norah Jones"] and bad == ["Inventado XYZ"]


def test_pool_merges_sources_and_skips_live_versions(lastfm):
    i = scene.parse_interpretation(json.dumps(INTERP))
    pool = scene.build_pool(lastfm, i, ["Norah Jones"], scene.CatalogParams())
    titles = {t.title for t in pool.values()}
    assert "Amber (Live)" not in titles
    dkw = next(t for t in pool.values() if t.title == "Don't Know Why")
    assert dkw.sources == {"tag:chill", "artista:Norah Jones"}
    peyroux = next(t for t in pool.values() if t.artist == "Madeleine Peyroux")
    assert peyroux.sources == {"similar:Norah Jones"}


def test_prefilter_puts_multi_source_first_then_round_robin(lastfm):
    i = scene.parse_interpretation(json.dumps(INTERP))
    pool = scene.build_pool(lastfm, i, ["Norah Jones"], scene.CatalogParams())
    top = scene.prefilter(pool, 4)
    # Primero la que está en dos búsquedas; después una por búsqueda, por turnos
    # (tag:chill, tag:rainy day, artista:Norah Jones salteando la ya elegida).
    assert [t.title for t in top] == ["Don't Know Why", "Amber", "Riders on the Storm", "Come Away With Me"]


def test_enrich_cleans_tags_and_keeps_weights(lastfm):
    t = scene.Track("Norah Jones", "Don't Know Why")
    [e] = scene.enrich(lastfm, [t], junk=["seen live"])
    assert e.tags == [("lo fi", 30), ("jazz", 100)]
    assert e.listeners == 100000


# --- Ranking -----------------------------------------------------------------

def track(artist, title, tags, listeners=100_000, sources=("tag:chill",)):
    return scene.Track(artist, title, sources=set(sources), listeners=listeners, tags=tags)


def test_tag_match_normalizes_wanted_tags():
    t = track("A", "x", [("lo fi", 100), ("chill", 50)])
    score, matched = scene.tag_match(t, ["lo-fi", "Chill", "party"])
    assert matched == ["lo fi", "chill"]
    assert score == pytest.approx((1.0 + 0.5) / 3)


def test_rank_uses_semantic_similarity_and_explains():
    i = scene.parse_interpretation(json.dumps(INTERP))
    a = track("Norah Jones", "Don't Know Why", [("chill", 100)], sources=("tag:chill", "artista:Norah Jones"))
    b = track("Otro", "y", [("chill", 100)])
    ranked = scene.rank([b, a], i, scene.RankWeights(), sims=[0.20, 0.30])
    assert ranked[0] is a
    assert "artista de referencia" in a.why and a.why[0] == "tags: chill"
    assert a.parts["semantica"] == 1.0 and b.parts["semantica"] == 0.0


def test_rank_without_embeddings_redistributes_weight():
    i = scene.parse_interpretation(json.dumps(INTERP))
    a = track("A", "x", [("chill", 100), ("rainy day", 100), ("lo fi", 100)], listeners=10_000_000,
              sources=("tag:chill", "tag:rainy day", "tag:lo-fi"))
    [r] = scene.rank([a], i, scene.RankWeights(), sims=None)
    assert r.score == pytest.approx(1.0)


def test_select_limits_songs_per_artist():
    ts = [track("Same", f"t{k}", []) for k in range(4)] + [track("Other", "o", [])]
    for k, t in enumerate(ts):
        t.score = 1 - k / 10
    out = scene.select(ts, 3, max_per_artist=2)
    assert [t.title for t in out] == ["t0", "t1", "o"]


def test_embed_orders_by_index_and_checks_count():
    data = {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}
    http = FakeHttp([("POST", "/embeddings", lambda p, b: Response(200, data))])
    assert scene.embed(http, ["a", "b"], "http://h/v1", "e") == [[1, 0], [0, 1]]
    with pytest.raises(RuntimeError, match="pedí 3"):
        scene.embed(http, ["a", "b", "c"], "http://h/v1", "e")
