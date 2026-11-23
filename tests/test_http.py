from onda_poc.http import HttpClient


class FakeResp:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = 0

    def request(self, *a, **kw):
        self.calls += 1
        return self.responses.pop(0)


def test_retries_on_429_then_caches(tmp_path):
    sess = FakeSession([FakeResp(429, None, {"Retry-After": "1"}), FakeResp(200, {"ok": 1})])
    sleeps = []
    http = HttpClient(cache_path=tmp_path / "c.sqlite", session=sess, sleep=sleeps.append)
    r = http.get("https://example.org/x", params={"a": 1})
    assert r.ok and r.data == {"ok": 1} and sess.calls == 2
    assert 1.0 in sleeps
    r2 = http.get("https://example.org/x", params={"a": 1})
    assert r2.from_cache and sess.calls == 2


def test_404_is_cached_but_500_is_not(tmp_path):
    sess = FakeSession([FakeResp(404, {"e": 1}), FakeResp(500, None)])
    http = HttpClient(cache_path=tmp_path / "c.sqlite", session=sess, max_retries=0, sleep=lambda s: None)
    assert http.get("https://example.org/a").status == 404
    assert http.get("https://example.org/a").from_cache
    assert http.get("https://example.org/b").status == 500
    assert http.stats["errors"] == 2


def test_cache_tag_separates_entries(tmp_path):
    sess = FakeSession([FakeResp(200, {"v": 1}), FakeResp(200, {"v": 2})])
    http = HttpClient(cache_path=tmp_path / "c.sqlite", session=sess, sleep=lambda s: None)
    assert http.get("https://example.org/a").data == {"v": 1}
    assert http.get("https://example.org/a", cache_tag="token").data == {"v": 2}
