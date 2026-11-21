"""HTTP falso para testear sin red."""

from __future__ import annotations

from vibematch_poc.http import Response


class FakeHttp:
    """Despacha por (método, fragmento de URL) a una función que arma la respuesta."""

    def __init__(self, routes):
        self.routes = routes  # lista de (method, url_contains, handler(params, body) -> Response)
        self.calls = []
        self.stats = {"network": 0, "cache_hits": 0, "errors": 0}

    def request(self, method, url, *, params=None, json_body=None, data=None, **kw):
        self.calls.append((method, url, params, json_body))
        for m, frag, handler in self.routes:
            if m == method and frag in url:
                return handler(params or {}, json_body if json_body is not None else data)
        return Response(404, None)

    def get(self, url, params=None, **kw):
        return self.request("GET", url, params=params, **kw)

    def post(self, url, json_body=None, **kw):
        return self.request("POST", url, json_body=json_body, **kw)


def mb_recording(rid, title, artist, artist_id="a1", score=100, date="2005-01-01", video=False):
    return {
        "id": rid, "title": title, "score": score, "first-release-date": date, "video": video,
        "artist-credit": [{"name": artist, "artist": {"id": artist_id, "name": artist}, "joinphrase": ""}],
    }
