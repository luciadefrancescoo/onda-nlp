"""Reporte en Markdown para discutir en el equipo."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def num(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x:,.0f}".replace(",", ".")


def year(x: float | None) -> str:
    return "—" if x is None else str(int(x))


def _check(ok: bool, extra: str = "") -> str:
    return ("✅" if ok else "❌") + (f" {extra}" if extra else "")


def render(summary: dict, records: list[dict], info: dict, generator: dict,
           prompts: dict[str, str]) -> str:
    o = summary["overall"]
    L: list[str] = []
    L.append("# onda. — prueba de factibilidad de datos")
    L.append("")
    L.append(f"Corrida: {datetime.now():%Y-%m-%d %H:%M}  ")
    L.append(f"Candidatos: {generator.get('model', '?')} ({generator.get('method', '')})  ")
    L.append(f"Total: {o['n']} candidatos en {len(summary['per_prompt'])} prompts")
    L.append("")
    L.append("**Fuentes**")
    L.append("")
    L.append(f"- MusicBrainz (existencia, año): {_check(True)}")
    L.append(f"- ListenBrainz popularidad: {_check(info['listenbrainz_popularity_ok'], info['listenbrainz_error'] or '')}")
    L.append(f"- ListenBrainz tags: {_check(info['listenbrainz_tags_ok'], '' if info['listenbrainz_tags_ok'] else '(se usó MusicBrainz como respaldo)')}")
    L.append(f"- Last.fm (oyentes, tags de mood): {_check(info['lastfm_enabled'], '' if info['lastfm_enabled'] else '(sin LASTFM_API_KEY)')}")
    sp_ok = info["spotify_enabled"] and not info["spotify_auth_error"]
    sp_note = info["spotify_auth_error"] or ("" if info["spotify_enabled"] else "(sin credenciales)")
    L.append(f"- Spotify (solo resolución): {_check(sp_ok, sp_note)}")
    L.append("")

    L.append(f"## Veredicto: {summary['verdict']}")
    L.append("")
    L.append("| Criterio | Valor | Umbral | Estado | Prompts por debajo |")
    L.append("|---|---|---|---|---|")
    for c in summary["criteria"]:
        L.append(f"| {c['label']} | {pct(c['value'])} | {pct(c['threshold'])} | {c['status']} | "
                 f"{', '.join(c['prompts_below']) or '—'} |")
    L.append("")
    L.append("Señales complementarias (sin umbral):")
    L.append("")
    L.append(f"- No encontradas en ninguna fuente (alucinación probable): {pct(o['not_found_anywhere'])}")
    L.append(f"- Con ≥3 tags útiles contando tags del artista: {pct(o['has_3_useful_tags_any'])}")
    L.append(f"- Con al menos un tag de mood/escena: {pct(o['has_mood_tag_song'])} a nivel canción, "
             f"{pct(o['has_mood_tag_any'])} contando artista")
    L.append(f"- Hits (≥ corte alto de oyentes en Last.fm): {pct(o['hit'])}")
    L.append(f"- Lanzadas en 2024 o después: {pct(o['released_2024_or_later'])} (año mediano: {year(o['median_year'])})")
    L.append(f"- Duplicados: {o['duplicates']}; artistas distintos / canciones: {pct(o['unique_artist_ratio'])}")
    L.append("")

    L.append("## Por prompt")
    L.append("")
    L.append("| Prompt | Existe MB | No encontrada | Spotify | Reconocible | ≥3 tags canción | ≥3 tags c/artista | Mood canción | Año mediano | Oyentes Last.fm (mediana) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for pid, m in summary["per_prompt"].items():
        L.append(f"| {pid} | {pct(m['exists_in_musicbrainz'])} | {pct(m['not_found_anywhere'])} | "
                 f"{pct(m['resolved_in_spotify'])} | {pct(m['recognizable'])} | "
                 f"{pct(m['has_3_useful_tags_song'])} | {pct(m['has_3_useful_tags_any'])} | "
                 f"{pct(m['has_mood_tag_song'])} | {year(m['median_year'])} | {num(m['median_lastfm_listeners'])} |")
    L.append("")
    for pid, text in prompts.items():
        L.append(f"- **{pid}**: {text}")
    L.append("")

    L.append("## No encontradas en MusicBrainz")
    L.append("")
    L.append("Revisarlas a mano: pueden ser alucinaciones o falsos negativos del matching "
             "(títulos largos de música clásica, nombres con símbolos).")
    L.append("")
    missing = [r for r in records if not r["musicbrainz"]["found"] and not r["duplicate"]]
    if not missing:
        L.append("Ninguna.")
    for r in missing:
        others = []
        if r["lastfm"].get("found"):
            others.append("sí está en Last.fm")
        if r["spotify"].get("found"):
            others.append("sí está en Spotify")
        L.append(f"- `{r['prompt_id']}` {r['artist']} — {r['title']}"
                 + (f" ({', '.join(others)})" if others else ""))
    L.append("")

    L.append("## Muestra de tags (primeras 4 por prompt)")
    L.append("")
    for pid in summary["per_prompt"]:
        L.append(f"**{pid}**")
        L.append("")
        for r in [x for x in records if x["prompt_id"] == pid][:4]:
            d = r["derived"]
            tags = ", ".join(d["useful_tags_song"][:8]) or "(sin tags de canción)"
            mood = ", ".join(d["mood_tags_any"][:5]) or "—"
            L.append(f"- {r['artist']} — {r['title']}: {tags}. Mood: {mood}")
        L.append("")

    L.append("## Cómo leer esto")
    L.append("")
    L.append(f"- Los candidatos vienen de **{generator.get('model', '?')}**. "
             + (generator.get("notes", "")))
    L.append("- \"Reconocible\" = supera el corte de oyentes de Last.fm o de usuarios de ListenBrainz "
             "definido en `config.toml`. La base de ListenBrainz es chica y sesgada a ciertos géneros.")
    L.append("- Los tags de artista suelen ser de género, no de mood: por eso el umbral se mide a nivel canción.")
    L.append("- Spotify se usa solo para ver si se puede exportar; sus datos no entran a ningún modelo ni se guardan.")
    return "\n".join(L) + "\n"


def results_rows(records: list[dict]) -> list[dict[str, Any]]:
    """Filas planas para CSV."""
    rows = []
    for r in records:
        d = r["derived"]
        rows.append({
            "prompt_id": r["prompt_id"], "rank": r["rank"], "artist": r["artist"], "title": r["title"],
            "duplicate": r["duplicate"],
            "mb_found": r["musicbrainz"]["found"], "mb_title": r["musicbrainz"]["matched_title"],
            "mb_artist": r["musicbrainz"]["matched_artist"], "year": r["musicbrainz"]["year"],
            "lb_users": r["listenbrainz"]["user_count"], "lb_listens": r["listenbrainz"]["listen_count"],
            "lastfm_found": r["lastfm"].get("found"), "lastfm_listeners": r["lastfm"].get("listeners"),
            "spotify_found": r["spotify"].get("found"),
            "n_tags_song": len(d["useful_tags_song"]), "n_tags_any": len(d["useful_tags_any"]),
            "mood_tags": "|".join(d["mood_tags_any"]),
            "tags_song": "|".join(d["useful_tags_song"]),
            "recognizable": d["recognizable"], "found_anywhere": d["found_anywhere"],
        })
    return rows


COMPARE_ROWS = [
    ("exists_in_musicbrainz", "Existe en MusicBrainz", "pct"),
    ("not_found_anywhere", "No encontrada en ninguna fuente", "pct"),
    ("recognizable", "Reconocible", "pct"),
    ("hit", "Hit (corte alto Last.fm)", "pct"),
    ("has_3_useful_tags_song", "≥3 tags a nivel canción", "pct"),
    ("has_mood_tag_song", "Con tag de mood (canción)", "pct"),
    ("released_2024_or_later", "Lanzadas en 2024+", "pct"),
    ("median_year", "Año mediano", "year"),
    ("unique_artist_ratio", "Artistas distintos / canciones", "pct"),
    ("duplicates", "Duplicados", "num"),
    ("n", "Candidatos", "num"),
]


def compare_runs(runs: list[tuple[str, dict]]) -> str:
    """Tabla Markdown lado a lado. `runs` = [(nombre_carpeta, summary.json), ...]."""
    fmt = {"pct": pct, "year": year, "num": lambda x: "—" if x is None else str(x)}
    labels = []
    for folder, s in runs:
        model = (s.get("generator") or {}).get("model")
        labels.append(f"{model} ({folder[:13]})" if model else folder)
    L = ["## Comparación de corridas", "", "| Métrica | " + " | ".join(labels) + " |",
         "|---|" + "---|" * len(runs)]
    for key, label, kind in COMPARE_ROWS:
        L.append(f"| {label} | " + " | ".join(fmt[kind](s["overall"].get(key)) for _, s in runs) + " |")
    L += ["", "**Veredicto:** " + " · ".join(f"{lab}: {s['verdict']}" for lab, (_, s) in zip(labels, runs)), ""]
    prompts = list(dict.fromkeys(p for _, s in runs for p in s["per_prompt"]))
    L += ["### Por prompt (existe en MB / reconocible)", "",
          "| Prompt | " + " | ".join(labels) + " |", "|---|" + "---|" * len(runs)]
    for pid in prompts:
        cells = []
        for _, s in runs:
            m = s["per_prompt"].get(pid)
            cells.append("—" if not m else f"{pct(m['exists_in_musicbrainz'])} / {pct(m['recognizable'])}")
        L.append(f"| {pid} | " + " | ".join(cells) + " |")
    return "\n".join(L) + "\n"
