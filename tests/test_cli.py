import json

import vibematch_poc.__main__ as cli

from .test_pipeline import build


def test_run_writes_all_outputs(tmp_path, monkeypatch):
    for var in ("LASTFM_API_KEY", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "LISTENBRAINZ_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    http, _ = build(with_optional=False)
    monkeypatch.setattr(cli, "make_http", lambda cache=True, timeout=20: http)

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


def test_compare_two_runs(tmp_path, capsys):
    def summary(model, exists, rec):
        o = {k: None for k in ("not_found_anywhere", "hit", "has_3_useful_tags_song", "has_mood_tag_song",
                               "released_2024_or_later", "median_year", "unique_artist_ratio")}
        o.update(exists_in_musicbrainz=exists, recognizable=rec, duplicates=0, n=30, median_year=2006.0)
        return {"generator": {"model": model}, "verdict": "GO", "overall": o,
                "per_prompt": {"preboliche": {"exists_in_musicbrainz": exists, "recognizable": rec}}}
    for name, s in (("a", summary("Claude Opus 5.5", 0.97, 0.92)), ("b", summary("qwen3.5:4b", 0.7, 0.6))):
        (tmp_path / name).mkdir()
        (tmp_path / name / "summary.json").write_text(json.dumps(s))
    out = tmp_path / "cmp.md"
    assert cli.main(["compare", str(tmp_path / "a"), str(tmp_path / "b"), "--out", str(out)]) == 0
    md = out.read_text()
    assert "| Existe en MusicBrainz | 97% | 70% |" in md
    assert "| preboliche | 97% / 92% | 70% / 60% |" in md
    assert "| Año mediano | 2006 | 2006 |" in md
