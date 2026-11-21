"""CLI de la prueba de factibilidad.

    python -m vibematch_poc check                      # ¿llegan las APIs?
    python -m vibematch_poc run --candidates data/candidates/claude-opus-5-5.json
    python -m vibematch_poc generate --out data/candidates/mi-modelo.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from . import llm
from .http import HttpClient, build_user_agent
from .metrics import summarize
from .pipeline import Sources, verify
from .report import render, results_rows
from .sources.lastfm import Lastfm
from .sources.listenbrainz import ListenBrainz
from .sources.musicbrainz import MusicBrainz
from .sources.spotify import Spotify

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def make_http(cache: bool = True) -> HttpClient:
    return HttpClient(
        cache_path=ROOT / "cache" / "http_cache.sqlite" if cache else None,
        user_agent=build_user_agent(os.environ.get("CONTACT_EMAIL")),
    )


def make_sources(cfg: dict, http: HttpClient, use_lastfm: bool, use_spotify: bool) -> Sources:
    m = cfg["matching"]
    kw = dict(title_min=m["title_min_similarity"], artist_min=m["artist_min_similarity"])
    lastfm = spotify = None
    if use_lastfm and os.environ.get("LASTFM_API_KEY"):
        lastfm = Lastfm(http, os.environ["LASTFM_API_KEY"], **kw)
    if use_spotify and os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET"):
        spotify = Spotify(http, os.environ["SPOTIFY_CLIENT_ID"], os.environ["SPOTIFY_CLIENT_SECRET"],
                          market=cfg["run"]["spotify_market"], **kw)
    return Sources(
        musicbrainz=MusicBrainz(http, limit=m["musicbrainz_search_limit"], **kw),
        listenbrainz=ListenBrainz(http, token=os.environ.get("LISTENBRAINZ_TOKEN")),
        lastfm=lastfm, spotify=spotify,
    )


def cmd_check(args, cfg) -> int:
    http = make_http(cache=False)
    src = make_sources(cfg, http, True, True)
    ok = True

    mb = src.musicbrainz.lookup("Daddy Yankee", "Gasolina")
    print(f"MusicBrainz:  {'OK' if mb.found else 'FALLA'} {mb.error or ''}")
    ok &= mb.found
    mbids = [m.recording_mbid for m in mb.matches]
    pop = src.listenbrainz.popularity(mbids) if mbids else {}
    print(f"ListenBrainz popularidad: {'OK' if pop else 'FALLA ' + str(src.listenbrainz.last_error)}")
    tags = src.listenbrainz.tags(mbids[:5]) if mbids else {}
    print(f"ListenBrainz tags: {'OK' if tags else 'FALLA ' + str(src.listenbrainz.last_error) + ' (se usará MusicBrainz)'}")
    if src.lastfm:
        lf = src.lastfm.lookup("Daddy Yankee", "Gasolina")
        print(f"Last.fm: {'OK' if lf.found else 'FALLA'} oyentes={lf.listeners} {lf.error or ''}")
    else:
        print("Last.fm: sin LASTFM_API_KEY (opcional, pero es la mejor fuente de mood)")
    if src.spotify:
        sp = src.spotify.lookup("Daddy Yankee", "Gasolina")
        print(f"Spotify: {'OK' if sp.found else 'FALLA'} {sp.error or ''}")
    else:
        print("Spotify: sin SPOTIFY_CLIENT_ID/SECRET (opcional)")
    return 0 if ok else 1


def cmd_generate(args, cfg) -> int:
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        print("Definí LLM_BASE_URL y LLM_MODEL (y LLM_API_KEY si hace falta) en .env", file=sys.stderr)
        return 2
    http = make_http()
    n = args.n or cfg["run"]["candidates_per_prompt"]
    out = {"generator": {"model": model, "method": f"API compatible OpenAI ({base_url})",
                         "date": datetime.now().strftime("%Y-%m-%d"), "notes": ""},
           "prompts": {}}
    for p in cfg["prompts"]:
        print(f"Generando {n} para {p['id']}...", file=sys.stderr)
        out["prompts"][p["id"]] = llm.generate(http, p["text"], n, base_url, model,
                                               os.environ.get("LLM_API_KEY"))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Guardado en {args.out}")
    return 0


def cmd_run(args, cfg) -> int:
    cand_path = Path(args.candidates)
    data = json.loads(cand_path.read_text())
    prompts = {p["id"]: p["text"] for p in cfg["prompts"]}
    candidates = {pid: data["prompts"][pid] for pid in prompts if pid in data["prompts"]}
    if args.limit:
        candidates = {k: v[:args.limit] for k, v in candidates.items()}
    http = make_http(cache=not args.no_cache)
    src = make_sources(cfg, http, not args.no_lastfm, not args.no_spotify)
    records, info = verify(candidates, src, cfg, quiet=args.quiet)
    summary = summarize(records, info, cfg)

    out = Path(args.out or ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M}-{cand_path.stem}")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    rows = results_rows(records)
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (out / "summary.json").write_text(json.dumps({**summary, "sources": info}, ensure_ascii=False, indent=2))
    (out / "report.md").write_text(render(summary, records, info, data.get("generator", {}),
                                          {k: prompts[k] for k in candidates}))
    print(f"\nVeredicto: {summary['verdict']}")
    print(f"Reporte: {out / 'report.md'}")
    print(f"HTTP: {http.stats}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="vibematch_poc")
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="prueba de conectividad con cada fuente")

    g = sub.add_parser("generate", help="genera candidatos con un LLM")
    g.add_argument("--out", required=True)
    g.add_argument("--n", type=int)

    r = sub.add_parser("run", help="verifica candidatos y genera el reporte")
    r.add_argument("--candidates", required=True)
    r.add_argument("--out")
    r.add_argument("--limit", type=int, help="solo los primeros N por prompt (para probar rápido)")
    r.add_argument("--no-lastfm", action="store_true")
    r.add_argument("--no-spotify", action="store_true")
    r.add_argument("--no-cache", action="store_true")
    r.add_argument("--quiet", action="store_true")

    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    return {"check": cmd_check, "generate": cmd_generate, "run": cmd_run}[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
