import json

import vibematch_poc.__main__ as cli

from .test_pipeline import build


def test_run_writes_all_outputs(tmp_path, monkeypatch):
    for var in ("LASTFM_API_KEY", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "LISTENBRAINZ_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    http, _ = build(with_optional=False)
    monkeypatch.setattr(cli, "make_http", lambda cache=True: http)

    cands = tmp_path / "c.json"
    cands.write_text(json.dumps({"generator": {"model": "fake"}, "prompts": {
        "lluvia": [{"artist": "Radiohead", "title": "No Surprises"}],
        "no_configurado": [{"artist": "X", "title": "Y"}],  # se ignora
    }}))
    out = tmp_path / "out"
    assert cli.main(["run", "--candidates", str(cands), "--out", str(out), "--quiet"]) == 0
    for f in ("results.jsonl", "results.csv", "summary.json", "report.md"):
        assert (out / f).exists(), f
    summary = json.loads((out / "summary.json").read_text())
    assert list(summary["per_prompt"]) == ["lluvia"]
    assert summary["sources"]["lastfm_enabled"] is False
    assert "Radiohead" in (out / "report.md").read_text()
