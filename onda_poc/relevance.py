"""Relevancia: ¿las canciones son de lo que pide la escena?

Las métricas de `run` miden si las canciones existen; esta mide si encajan,
contra lo que un humano escribió en config.toml para cada escena:

- genres: % de canciones con al menos un género esperado en sus tags
  (de la canción o del artista). "cumbia" cuenta "cumbia villera".
- years:  % de canciones (con año conocido) lanzadas en ese rango.

Es una medida de apoyo, no reemplaza la evaluación humana: depende de los
tags de Last.fm/ListenBrainz, que en música local son escasos.
"""

from __future__ import annotations

import json
from pathlib import Path

from .tags import clean_tag


def genre_hits(tags: list[str], genres: list[str]) -> list[str]:
    """Géneros esperados presentes en los tags, como frase completa dentro del tag."""
    padded = [f" {clean_tag(t)} " for t in tags]
    out = []
    for g in genres:
        cg = f" {clean_tag(g)} "
        if any(cg in t for t in padded):
            out.append(clean_tag(g))
    return out


def prompt_relevance(records: list[dict], expect: dict) -> dict:
    genres = expect.get("genres") or []
    years = expect.get("years")
    recs = [r for r in records if not r.get("duplicate")]
    out: dict = {"n": len(recs)}
    if genres:
        hits = [bool(genre_hits((r.get("derived") or {}).get("useful_tags_any") or [], genres)) for r in recs]
        out["genre"] = sum(hits) / len(hits) if hits else None
    if years:
        ys = [(r.get("musicbrainz") or {}).get("year") for r in recs]
        ys = [y for y in ys if isinstance(y, int)]
        out["years"] = sum(years[0] <= y <= years[1] for y in ys) / len(ys) if ys else None
    return out


def relevance_of_run(run_dir: Path, expectations: dict[str, dict]) -> dict:
    records: dict[str, list[dict]] = {}
    with open(run_dir / "results.jsonl") as f:
        for line in f:
            r = json.loads(line)
            records.setdefault(r["prompt_id"], []).append(r)
    per = {pid: prompt_relevance(rs, expectations[pid]) for pid, rs in records.items() if pid in expectations}
    vals = [v for m in per.values() for k, v in m.items() if k in ("genre", "years") and v is not None]
    return {"per_prompt": per, "mean": sum(vals) / len(vals) if vals else None}


def run_label(run_dir: Path) -> str:
    try:
        s = json.loads((run_dir / "summary.json").read_text())
        model = (s.get("generator") or {}).get("model")
        if model:
            return f"{model} ({run_dir.name[:13]})"
    except (OSError, ValueError):
        pass
    return run_dir.name


def render(runs: list[Path], expectations: dict[str, dict]) -> str:
    res = [relevance_of_run(r, expectations) for r in runs]
    labels = [run_label(r) for r in runs]
    pct = lambda v: "—" if v is None else f"{v:.0%}"
    L = ["## Relevancia: ¿las canciones son de lo que pide la escena?", "",
         "Género esperado en los tags de la canción o del artista; en nostalgia, año de lanzamiento. "
         "Lo esperado está en `config.toml` y se escribió antes de ajustar el ranking.", "",
         "| Escena | Qué se mide | " + " | ".join(labels) + " |",
         "|---|---|" + "---|" * len(runs)]
    for pid, exp in expectations.items():
        if exp.get("genres"):
            what = "género: " + ", ".join(exp["genres"][:3]) + ("…" if len(exp["genres"]) > 3 else "")
            L.append(f"| {pid} | {what} | " + " | ".join(pct(r["per_prompt"].get(pid, {}).get("genre")) for r in res) + " |")
        if exp.get("years"):
            what = f"lanzada {exp['years'][0]}–{exp['years'][1]}"
            L.append(f"| {pid} | {what} | " + " | ".join(pct(r["per_prompt"].get(pid, {}).get("years")) for r in res) + " |")
    L.append("| **Promedio** | | " + " | ".join(f"**{pct(r['mean'])}**" for r in res) + " |")
    return "\n".join(L) + "\n"
