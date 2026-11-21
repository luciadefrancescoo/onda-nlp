import json

import pytest

from vibematch_poc import llm
from vibematch_poc.http import Response

from .fakes import FakeHttp


def chat(content):
    return Response(200, {"choices": [{"message": {"content": content}}]})


GOOD = json.dumps({"canciones": [{"artista": "Gilda", "titulo": "Fuiste"}]})


def test_parse_ignores_think_block_with_braces():
    text = "<think>Quizás {algo} o {otra cosa}...</think>\n" + GOOD
    assert llm.parse_candidates(text) == [{"artist": "Gilda", "title": "Fuiste"}]


def test_generate_drops_json_mode_if_server_rejects_it():
    bodies = []

    def handler(p, body):
        bodies.append(body)
        return Response(400, {"error": "response_format not supported"}) if "response_format" in body else chat(GOOD)

    http = FakeHttp([("POST", "/chat/completions", handler)])
    assert llm.generate(http, "x", 1, "http://h/v1", "m") == [{"artist": "Gilda", "title": "Fuiste"}]
    assert "response_format" in bodies[0] and "response_format" not in bodies[1]


def test_generate_retries_on_unparseable_output():
    answers = iter([chat("perdón, no puedo"), chat(GOOD)])
    http = FakeHttp([("POST", "/chat/completions", lambda p, b: next(answers))])
    assert llm.generate(http, "x", 1, "http://h/v1", "m")[0]["title"] == "Fuiste"


def test_generate_gives_up_after_attempts():
    http = FakeHttp([("POST", "/chat/completions", lambda p, b: chat("nada"))])
    with pytest.raises(ValueError, match="tras 3 intentos"):
        llm.generate(http, "x", 1, "http://h/v1", "m")


def test_generate_retries_use_distinct_cache_keys():
    http = FakeHttp([("POST", "/chat/completions", lambda p, b: chat("nada"))])
    seen = []
    orig = http.post

    def spy(url, json_body=None, **kw):
        seen.append(kw.get("cache_tag"))
        return orig(url, json_body=json_body, **kw)

    http.post = spy
    with pytest.raises(ValueError):
        llm.generate(http, "x", 1, "http://h/v1", "m")
    assert len(set(seen)) == 3
