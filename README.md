# onda. — prueba de factibilidad de datos

Antes de comprometernos con onda., esta prueba responde cuatro preguntas con números:

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

python -m onda_poc check          # prueba cada fuente con "Gasolina"
python -m onda_poc run --candidates data/candidates/claude-opus-5-5.json
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
python -m onda_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche --dry-run
# Después crear la playlist privada:
python -m onda_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche
```

La primera vez se abre el navegador para autorizar. El permiso queda guardado en `cache/spotify_token.json` (ignorado por git). Para revocarlo: [spotify.com/account/apps](https://www.spotify.com/account/apps/).

En la terminal, `✓` es la versión original, `~` es otra versión (en vivo, remix, karaoke…) porque no había original, y `✗` es que no la encontró. El detalle queda en `results/<fecha>-export-<prompt>/export.csv`: es para revisarlo a mano, no para alimentar modelos.

### Para el AI Fest: cuenta del equipo + QR

En modo desarrollo solo 5 cuentas pueden usar la app, así que los visitantes no van a poder exportar a la suya. La alternativa: exportar siempre a una cuenta del equipo, como playlist pública, y mostrar un QR.

1. Creen una cuenta de Spotify del equipo. Premium se le pide al dueño de la app, no a los usuarios agregados.
2. Agreguen ese mail en *User Management* de la app.
3. Corran:

```bash
python -m onda_poc export --candidates data/candidates/claude-opus-5-5.json --prompt preboliche \
  --account equipo --public --qr
```

`--account equipo` guarda ese permiso aparte del personal. En la pantalla de Spotify usen "¿No sos vos?" para entrar con la cuenta del equipo. El QR se muestra en la terminal y queda como PNG en `results/<fecha>-export-<prompt>/playlist_qr.png`.

## Probar con un modelo chico (Ollama)

Los candidatos incluidos los generó un modelo grande. Para saber si el proyecto funciona con el modelo que van a usar:

1. Instalen [Ollama](https://ollama.com/download) y bajen un modelo según la memoria de la compu ( → Acerca de esta Mac). Si un nombre no existe, busquen el actual en [ollama.com/library](https://ollama.com/library).
   ```bash
   ollama pull gemma4:12b     # 16 GB o más
   ollama pull qwen3.5:4b     # 8 GB
   ```
2. En `.env`: `LLM_BASE_URL=http://localhost:11434/v1` (sin API key).
3. Generar, verificar y comparar:
   ```bash
   LLM_MODEL=gemma4:12b python -m onda_poc generate --out data/candidates/gemma4-12b.json
   python -m onda_poc run --candidates data/candidates/gemma4-12b.json
   python -m onda_poc compare results/<corrida-claude> results/<corrida-nueva> --out results/comparacion.md
   ```

`generate` intenta modo JSON, ignora bloques de razonamiento (`<think>`) y reintenta si la respuesta no se puede leer. Un modelo local puede tardar varios minutos por prompt.

## Demo web (AI Fest, 12/12)

```bash
python -m onda_poc demo          # abrir http://127.0.0.1:8000
```

El visitante escribe la escena y ve cómo la interpreta el modelo, la playlist con el porqué de cada canción y, si quiere, un botón que la crea en la cuenta de Spotify del equipo y muestra un QR. Al arrancar, la demo chequea Ollama, los modelos y la cuenta de Spotify (antes hay que haber corrido una vez `export --account equipo` para dejar el permiso guardado). Cada escena queda en `results/demo-log.jsonl` (no se sube a git).

Tiempos: una escena ya vista sale al instante; una nueva tarda 50–70 s, casi todo leyendo tags de Last.fm a 4 consultas por segundo.

## Enfoque de onda.: `build`

> **Atribución a Last.fm.** Las canciones salen de Last.fm. Sus términos (cláusula 2.7) piden mostrar "Powered by AudioScrobbler" con link a last.fm donde se usen sus datos: `build` lo imprime y `export` lo pone en la descripción de la playlist. La demo tiene que mostrarlo en pantalla. Pedimos permiso para uso académico y para la demo a partners@last.fm el 23/11.

Con `gemma4:12b`, `generate` da NO-GO: 1 de cada 3 canciones no existe (ver `results/comparacion.md`). Por eso el enfoque de onda. cambia el rol del LLM: **interpreta la escena, no nombra canciones.**

```
escena ──► LLM interpreta ──► moods, géneros, artistas, época      (los artistas se verifican en Last.fm)
                                    │
                                    ▼
           Last.fm: top tracks por tag, por artista y por similares ──► pool de canciones reales
                                    │
                                    ▼
           tags de cada canción ──► ranking: embeddings + tags + búsquedas + popularidad
                                    │
                                    ▼
                   30 canciones, como mucho 2 por artista, cada una con su "por qué"
```

Necesita `LASTFM_API_KEY` y un modelo de embeddings en Ollama:

```bash
ollama pull embeddinggemma
LLM_MODEL=gemma4:12b python -m onda_poc build --out data/candidates/onda-gemma4-12b.json
python -m onda_poc build --prompt lluvia --out /tmp/lluvia.json      # una sola escena
python -m onda_poc build --scene "volviendo del trabajo, algo cantable tipo Carlos Vives" --out /tmp/mia.json
python -m onda_poc run --candidates data/candidates/onda-gemma4-12b.json
```

La salida tiene el mismo formato que `generate`, así que `run`, `export` y `compare` funcionan igual. Además guarda, por escena, la interpretación del LLM, los artistas descartados por no existir y, por canción, el puntaje desglosado y su explicación.

### Medir relevancia y ajustar sin hacer trampa

`run` mide si las canciones existen; `relevance` mide si son de lo que pide la escena (el género o la época que `config.toml` espera para cada prompt, escritos a mano antes de ajustar):

```bash
python -m onda_poc relevance results/<corrida-1> results/<corrida-2> --out results/relevancia.md
```

Para ajustar el ranking usen **solo** las escenas de desarrollo (`[[dev_prompts]]`), y corran las de evaluación una vez al final:

```bash
python -m onda_poc build --dev --out /tmp/dev.json
python -m onda_poc run --dev --no-spotify --candidates /tmp/dev.json --out /tmp/run-dev
python -m onda_poc relevance --dev /tmp/run-dev
```

`--no-spotify` en las corridas de desarrollo: en modo desarrollo Spotify bloquea la app por horas si se hacen muchas búsquedas (nos pasó: 21 h).

Los pesos del ranking y los tamaños de búsqueda están en `config.toml`, sección `[build]`. Si el modelo de embeddings no está, `build` rankea igual con tags, búsquedas y popularidad, y lo avisa.

## Candidatos

`data/candidates/claude-opus-5-5.json` tiene 30 canciones por prompt, propuestas por Claude Opus 5.5 con la misma consigna que usa `generate`. **Es un modelo grande: tómenlo como cota optimista.** La comparación que importa es con el modelo chico que piensen usar:

```bash
# Ejemplo con Ollama local
LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=qwen2.5:7b \
  python -m onda_poc generate --out data/candidates/qwen2.5-7b.json
python -m onda_poc run --candidates data/candidates/qwen2.5-7b.json
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
onda_poc/
  __main__.py               CLI: check / generate / build / run / export / compare
  llm.py                    consignas y parser de las respuestas del LLM
  scene.py                  build: interpretar la escena, armar el pool, rankear
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
