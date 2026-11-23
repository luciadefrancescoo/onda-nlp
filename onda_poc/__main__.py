"""CLI de la prueba de factibilidad.

    python -m onda_poc check                      # ¿llegan las APIs?
    python -m onda_poc run --candidates data/candidates/claude-opus-5-5.json
    python -m onda_poc generate --out data/candidates/mi-modelo.json
    python -m onda_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche
    python -m onda_poc compare results/<corrida-1> results/<corrida-2>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
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


def make_http(cache: bool = True, timeout: float = 20.0) -> HttpClient:
    return HttpClient(
        cache_path=ROOT / "cache" / "http_cache.sqlite" if cache else None,
        user_agent=build_user_agent(os.environ.get("CONTACT_EMAIL")),
        timeout=timeout,
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
    # Los modelos locales pueden tardar minutos en responder: timeout largo.
    http = make_http(timeout=600)
    n = args.n or cfg["run"]["candidates_per_prompt"]
    out = {"generator": {"model": model, "method": f"API compatible OpenAI ({base_url})",
                         "date": datetime.now().strftime("%Y-%m-%d"),
                         "notes": "Modelo elegido por el equipo, misma consigna y temperatura 0.3.",
                         "errors": {}},
           "prompts": {}}
    for p in cfg["prompts"]:
        t0 = datetime.now()
        print(f"Generando {n} para {p['id']}...", file=sys.stderr, flush=True)
        try:
            songs = llm.generate(http, p["text"], n, base_url, model, os.environ.get("LLM_API_KEY"))
        except Exception as e:  # seguimos con los demás prompts
            print(f"  ERROR en {p['id']}: {e}", file=sys.stderr)
            out["generator"]["errors"][p["id"]] = str(e)[:500]
            songs = []
        secs = (datetime.now() - t0).total_seconds()
        print(f"  {len(songs)} canciones en {secs:.0f} s", file=sys.stderr, flush=True)
        out["prompts"][p["id"]] = songs
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Guardado en {args.out}")
    return 0 if any(out["prompts"].values()) else 1


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
    if rows:
        with open(out / "results.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(
        {**summary, "sources": info, "generator": data.get("generator", {})}, ensure_ascii=False, indent=2))
    (out / "report.md").write_text(render(summary, records, info, data.get("generator", {}),
                                          {k: prompts[k] for k in candidates}))
    print(f"\nVeredicto: {summary['verdict']}")
    print(f"Reporte: {out / 'report.md'}")
    print(f"HTTP: {http.stats}", file=sys.stderr)
    return 0


def make_qr(url: str, path: Path) -> str | None:
    """QR del link de la playlist: PNG para proyectar y versión en la terminal."""
    try:
        import segno
    except ModuleNotFoundError:
        print("Para el QR falta segno: pip install -r requirements.txt", file=sys.stderr)
        return None
    qr = segno.make(url, error="m")
    qr.save(str(path), scale=12, border=2)
    qr.terminal(compact=True)
    print(f"QR guardado en {path}")
    return str(path)


def cmd_export(args, cfg) -> int:
    from .sources import spotify_user as su

    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        print("Falta SPOTIFY_CLIENT_ID en .env (ver README, sección Exportar a Spotify).", file=sys.stderr)
        return 2
    redirect = os.environ.get("SPOTIFY_REDIRECT_URI") or su.DEFAULT_REDIRECT
    data = json.loads(Path(args.candidates).read_text())
    prompts = {p["id"]: p["text"] for p in cfg["prompts"]}
    if args.prompt not in data["prompts"]:
        print(f"No hay candidatos para '{args.prompt}'. Opciones: {', '.join(data['prompts'])}", file=sys.stderr)
        return 2
    cands = data["prompts"][args.prompt][: args.limit or None]

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.account):
        print("--account solo admite letras, números, '-' y '_'.", file=sys.stderr)
        return 2
    http = make_http(cache=False)
    token_path = ROOT / "cache" / f"spotify_token_{args.account}.json"
    legacy = ROOT / "cache" / "spotify_token.json"  # versión anterior: una sola cuenta
    if args.account == "personal" and legacy.exists() and not token_path.exists():
        legacy.rename(token_path)
    print(f"Cuenta de Spotify: '{args.account}' (la primera vez se abre el navegador para iniciar sesión)")
    token = su.authorize(http, client_id, redirect, token_path)
    m = cfg["matching"]
    exp = su.SpotifyExporter(http, token, market=cfg["run"]["spotify_market"],
                             title_min=m["title_min_similarity"], artist_min=m["artist_min_similarity"])

    rows, uris = [], []
    print(f"\nBuscando {len(cands)} canciones de '{args.prompt}' en Spotify...\n")
    for i, c in enumerate(cands, 1):
        res = exp.resolve(c["artist"], c["title"])
        mark = "✗" if not res["found"] else ("~" if res["flags"] else "✓")
        detail = "no encontrada" if not res["found"] else f"{res['spotify_artists']} — {res['spotify_name']}"
        if res["flags"]:
            detail += f"  [{', '.join(res['flags'])}]"
        print(f"{mark} {i:2}. {c['artist']} — {c['title']}  →  {detail}")
        rows.append({"rank": i, "artist": c["artist"], "title": c["title"], **res,
                     "flags": "|".join(res["flags"])})
        if res["found"] and res["uri"] not in uris:
            uris.append(res["uri"])

    found = sum(r["found"] for r in rows)
    clean = sum(r["found"] and not r["flags"] for r in rows)
    print(f"\nEncontradas: {found}/{len(rows)} ({100 * found / len(rows):.0f}%), "
          f"versión original: {clean}, otra versión: {found - clean}")

    out = ROOT / "results" / f"{datetime.now():%Y%m%d-%H%M}-export-{args.prompt}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "export.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    summary = {"prompt": args.prompt, "n": len(rows), "found": found, "clean_version": clean,
               "dry_run": args.dry_run, "playlist_url": None, "add_endpoint": None}
    if args.dry_run:
        print("Modo --dry-run: no se creó ninguna playlist.")
    elif uris:
        name = args.name or f"onda. PoC · {args.prompt}"
        desc = f"{prompts.get(args.prompt, args.prompt)} (prueba de exportación onda.)"
        pid, url = exp.create_playlist(name, desc, public=args.public)
        summary["add_endpoint"] = exp.add_items(pid, uris)
        summary["playlist_url"] = url
        kind = "pública" if args.public else "privada"
        print(f"\nPlaylist {kind} creada con {len(uris)} canciones: {url}")
        if args.qr:
            summary["qr"] = make_qr(url, out / "playlist_qr.png")
    (out / "export_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Detalle: {out / 'export.csv'}")
    return 0


def cmd_compare(args, cfg) -> int:
    from .report import compare_runs

    runs = []
    for d in args.runs:
        path = Path(d) / "summary.json"
        if not path.exists():
            print(f"No encuentro {path}", file=sys.stderr)
            return 2
        runs.append((Path(d).name, json.loads(path.read_text())))
    md = compare_runs(runs)
    print(md)
    if args.out:
        Path(args.out).write_text(md)
        print(f"Guardado en {args.out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="onda_poc")
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

    e = sub.add_parser("export", help="crea una playlist privada en tu cuenta de Spotify")
    e.add_argument("--candidates", required=True)
    e.add_argument("--prompt", required=True, help="id del prompt (p. ej. preboliche)")
    e.add_argument("--limit", type=int)
    e.add_argument("--name", help="nombre de la playlist")
    e.add_argument("--dry-run", action="store_true", help="solo buscar, no crear la playlist")
    e.add_argument("--account", default="personal",
                   help="nombre para recordar la sesión (p. ej. equipo); cada cuenta guarda su propio permiso")
    e.add_argument("--public", action="store_true", help="crear la playlist pública (para compartir por QR)")
    e.add_argument("--qr", action="store_true", help="generar un QR con el link de la playlist")

    c = sub.add_parser("compare", help="compara dos o más corridas de run")
    c.add_argument("runs", nargs="+", help="carpetas dentro de results/")
    c.add_argument("--out", help="guardar la tabla en un .md")

    args = ap.parse_args(argv)
    cfg = load_config(Path(args.config))
    cmds = {"check": cmd_check, "generate": cmd_generate, "run": cmd_run,
            "export": cmd_export, "compare": cmd_compare}
    return cmds[args.cmd](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
