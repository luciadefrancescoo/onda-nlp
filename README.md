# VibeMatch: prueba de factibilidad de datos

Antes de comprometernos con VibeMatch, esta prueba responde cuatro preguntas con números:

1. Si un LLM propone canciones para una escena ("preboliche con reguetón conocido"), **¿existen o las inventa?**
2. **¿Son reconocibles?** (oyentes en Last.fm / ListenBrainz)
3. **¿Las fuentes abiertas tienen tags de mood/escena** para rankear y explicar a nivel canción?
4. **¿Se pueden encontrar en Spotify** para exportar?

Si no pasa los umbrales de `config.toml`, replanteamos el proyecto antes de construir nada.

## Cómo funciona

```
prompt ──► LLM propone 30 (artista, título)
              │
              ├─► MusicBrainz     ¿existe? año, todas las grabaciones que matchean
              ├─► ListenBrainz    popularidad (elige la grabación más escuchada) + tags   [CC0]
              ├─► Last.fm         oyentes + tags de folksonomía (mood)                     [opcional]
              └─► Spotify         solo ¿se encuentra? → URI para exportar                  [opcional]
                                    │
                                    ▼
                    métricas por prompt ─► umbrales ─► report.md (GO / NO-GO)
```

El LLM **genera**, las fuentes abiertas **verifican y fundamentan**, Spotify **solo exporta**.

## Correrlo

Requiere Python 3.10+ y salida a internet.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # completar lo que tengan (todo es opcional salvo CONTACT_EMAIL)

python -m vibematch_poc check          # prueba cada fuente con "Gasolina"
python -m vibematch_poc run --candidates data/candidates/claude-opus-5-5.json
```

Para probar rápido antes de la corrida completa: `--limit 3` (3 canciones por prompt).

La primera corrida tarda unos **5–8 minutos** (MusicBrainz permite 1 request por segundo). Todo queda en `cache/`, así que las siguientes son casi instantáneas.

El resultado queda en `results/<fecha>-<candidatos>/`:

| Archivo | Qué tiene |
|---|---|
| `report.md` | Veredicto, tabla por prompt, canciones no encontradas, muestra de tags |
| `results.csv` | Una fila por candidato, para mirar en una planilla |
| `results.jsonl` | Todo el detalle |
| `summary.json` | Métricas y estado de cada fuente |

## Credenciales (`.env`)

| Variable | Para qué | Cómo conseguirla |
|---|---|---|
| `CONTACT_EMAIL` | MusicBrainz exige un User-Agent con contacto | Un mail del equipo |
| `LASTFM_API_KEY` | Oyentes y tags de mood (la fuente más importante para mood) | [last.fm/api/account/create](https://www.last.fm/api/account/create) |
| `LISTENBRAINZ_TOKEN` | Opcional; algunos endpoints lo empezaron a pedir | [listenbrainz.org/settings](https://listenbrainz.org/settings/) |
| `SPOTIFY_CLIENT_ID` / `_SECRET` | Ver si la canción se puede exportar | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard): el dueño de la app necesita Premium |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Solo para `generate` | Cualquier API compatible con OpenAI, u Ollama local |

Sin una fuente opcional, los criterios que dependen de ella salen como `N/A` y el veredicto queda `INCOMPLETO`.

> **Last.fm y uso académico.** Sus términos piden escribir a partners@last.fm *antes* de usar la API con fines de investigación o académicos. Manden ese mail cuanto antes.

## Exportar a Spotify

Prueba el camino real de la app: iniciás sesión con tu cuenta, el script busca cada canción y crea una **playlist privada** en tu cuenta. Usa OAuth con PKCE, así que solo hace falta el Client ID (no el secret).

**Una sola vez, en [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)** (el dueño de la app necesita Premium):

1. *Create app*. Nombre y descripción a gusto. En **Redirect URIs** poné exactamente `http://127.0.0.1:8888/callback` (Spotify ya no acepta `localhost`). En las APIs, marcá **Web API**.
2. En *Settings*, copiá el **Client ID** a `.env` como `SPOTIFY_CLIENT_ID=...`.
3. En *User Management*, agregá tu nombre y el mail de tu cuenta de Spotify. En modo desarrollo solo pueden usar la app hasta 5 usuarios agregados ahí.

**Correrlo:**

```bash
# Primero solo buscar, sin crear nada:
python -m vibematch_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche --dry-run
# Después crear la playlist privada:
python -m vibematch_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche
```

La primera vez se abre el navegador para autorizar. El permiso queda guardado en `cache/spotify_token.json` (ignorado por git). Para revocarlo: [spotify.com/account/apps](https://www.spotify.com/account/apps/).

En la terminal, `✓` es la versión original, `~` es otra versión (en vivo, remix, karaoke…) porque no había original, y `✗` es que no la encontró. El detalle queda en `results/<fecha>-export-<prompt>/export.csv`: es para revisarlo a mano, no para alimentar modelos.

## Candidatos

`data/candidates/claude-opus-5-5.json` tiene 30 canciones por prompt, propuestas por Claude Opus 5.5 con la misma consigna que usa `generate`. **Es un modelo grande: tómenlo como cota optimista.** La comparación que importa es con el modelo chico que piensen usar:

```bash
# Ejemplo con Ollama local
LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b \
  python -m vibematch_poc generate --out data/candidates/qwen2.5-7b.json
python -m vibematch_poc run --candidates data/candidates/qwen2.5-7b.json
```

## Umbrales

Están en `config.toml`, sección `[thresholds]`. **Discútanlos y fíjenlos antes de correr**, no después de ver los números.

| Criterio | Umbral propuesto |
|---|---|
| Existe en MusicBrainz | ≥ 80% |
| Se encuentra en Spotify | ≥ 70% |
| ≥ 3 tags útiles a nivel canción | ≥ 50% |
| Reconocible (≥ 50k oyentes en Last.fm o ≥ 100 usuarios en ListenBrainz) | ≥ 60% |

Además de los 5 prompts del documento hay uno de estrés (`previa_local`: cumbia, cuarteto, RKT), porque es donde esperamos peor cobertura.

## Decisiones de diseño

- **Spotify solo resuelve.** La cláusula 14 de la Developer Policy prohíbe ingerir contenido de Spotify en modelos de IA. Por eso de Spotify solo se guarda si apareció y su URI, nada entra al LLM ni al ranking, y sus respuestas no se cachean.
- **Una canción, muchas grabaciones.** MusicBrainz devuelve la versión del álbum, el single, los compilados, etc. Se consulta la popularidad de todas y se elige la más escuchada; si no, la popularidad salía vacía por haber elegido una versión oscura.
- **Tags de canción vs. de artista.** Los de artista casi siempre son de género ("latin", "rock") y no de mood. El umbral mide tags a nivel canción; el reporte muestra los dos.
- **Matching estricto.** Título y artista con similitud ≥ 0.85 después de normalizar (tildes, "feat.", "(Remastered)"…). Puede dar falsos negativos en música clásica: el reporte lista las no encontradas para revisarlas a mano.

## Estructura

```
config.toml                 prompts, umbrales, listas de tags
data/candidates/            candidatos por modelo (JSON)
vibematch_poc/
  __main__.py               CLI: check / generate / run / export
  llm.py                    consigna y parser de la respuesta del LLM
  http.py                   caché SQLite, rate limit por host, reintentos
  matching.py               normalización y similitud artista/título
  tags.py                   filtro de tags basura, detección de mood
  pipeline.py               verificación de cada candidato
  metrics.py, report.py     agregación, umbrales, reporte
  sources/                  musicbrainz, listenbrainz, lastfm, spotify, spotify_user (export)
tests/                      pytest, todo con HTTP falso (no usa red)
```

```bash
python -m pytest -q
```
