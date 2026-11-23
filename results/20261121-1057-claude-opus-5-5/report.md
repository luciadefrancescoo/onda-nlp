# onda. — prueba de factibilidad de datos

Corrida: 2026-11-21 10:57  
Candidatos: Claude Opus 5.5 (generado a mano en el chat, misma consigna que llm.USER_TEMPLATE)  
Total: 180 candidatos en 6 prompts

**Fuentes**

- MusicBrainz (existencia, año): ✅
- ListenBrainz popularidad: ✅
- ListenBrainz tags: ✅
- Last.fm (oyentes, tags de mood): ✅
- Spotify (solo resolución): ❌ (sin credenciales)

## Veredicto: INCOMPLETO: faltan fuentes para evaluar todos los criterios

| Criterio | Valor | Umbral | Estado | Prompts por debajo |
|---|---|---|---|---|
| Existe en MusicBrainz (no es alucinación) | 97% | 80% | PASA | — |
| Se encuentra en Spotify (exportable) | — | 70% | N/A | — |
| ≥3 tags útiles a nivel canción | 70% | 50% | PASA | previa_local |
| Música reconocible | 92% | 60% | PASA | — |

Señales complementarias (sin umbral):

- No encontradas en ninguna fuente (alucinación probable): 1%
- Con ≥3 tags útiles contando tags del artista: 89%
- Con al menos un tag de mood/escena: 22% a nivel canción, 23% contando artista
- Hits (≥ corte alto de oyentes en Last.fm): 43%
- Lanzadas en 2024 o después: 2% (año mediano: 2006)
- Duplicados: 0; artistas distintos / canciones: 82%

## Por prompt

| Prompt | Existe MB | No encontrada | Spotify | Reconocible | ≥3 tags canción | ≥3 tags c/artista | Mood canción | Año mediano | Oyentes Last.fm (mediana) |
|---|---|---|---|---|---|---|---|---|---|
| preboliche | 100% | 0% | — | 97% | 80% | 100% | 13% | 2019 | 350.474 |
| lluvia | 100% | 0% | — | 100% | 93% | 93% | 40% | 2005 | 852.613 |
| estudio | 97% | 0% | — | 93% | 77% | 97% | 23% | 2003 | 302.730 |
| entrenamiento | 100% | 0% | — | 100% | 93% | 100% | 33% | 2003 | 1.801.688 |
| nostalgia | 100% | 0% | — | 100% | 73% | 87% | 23% | 2004 | 651.656 |
| previa_local | 87% | 3% | — | 63% | 3% | 60% | 0% | 2005 | 12.551 |

- **preboliche**: Preboliche con amigos: reguetón divertido y conocido para cantar todos
- **lluvia**: Domingo de lluvia, tranqui, mirando por la ventana
- **estudio**: Música para estudiar concentrada para un parcial, que no me distraiga
- **entrenamiento**: Entrenamiento de fuerza en el gimnasio, algo que me dé mucha energía
- **nostalgia**: Nostalgia de la secundaria: temas que escuchábamos en los 2000
- **previa_local**: Previa en Buenos Aires con cumbia, cuarteto y RKT

## No encontradas en MusicBrainz

Revisarlas a mano: pueden ser alucinaciones o falsos negativos del matching (títulos largos de música clásica, nombres con símbolos).

- `estudio` Johann Sebastian Bach — Cello Suite No. 1 in G Major, BWV 1007: Prelude (sí está en Last.fm)
- `previa_local` Los Palmeras — Bombón asesino (sí está en Last.fm)
- `previa_local` Ke Personajes — Pobre corazón (sí está en Last.fm)
- `previa_local` Ke Personajes — Tu forma de ser
- `previa_local` L-Gante — Pistola (sí está en Last.fm)

## Muestra de tags (primeras 4 por prompt)

**preboliche**

- Daddy Yankee — Gasolina: latin pop, latin, reggaeton, club, regueton, extremely droopy, pop, dance. Mood: —
- Daddy Yankee — Con Calma: reggaeton, dancehall, party. Mood: party
- Luis Fonsi — Despacito: pop, latin, reggaeton, todd in the shadows, latin pop, 2010s, daddy yankee. Mood: —
- J Balvin — Mi Gente: afrobeat, reggaeton, hip hop, pop, electronic, latin, latin pop. Mood: —

**lluvia**

- Norah Jones — Don't Know Why: soft jazz vocals, jazz: jazz vocals, vocal jazz, adult contemporary, ballad, soul, vocal, folk/country. Mood: mellow
- Bon Iver — Holocene: rock, folk, indie rock, folk rock, indie, baroque pop, indie folk, post rock. Mood: chill, mellow
- Radiohead — No Surprises: rock, electronic, alternative rock, owned, i own this, experimental, british, uk. Mood: melancholic, atmospheric
- Coldplay — The Scientist: piano rock, jazz, alternative rock, rock, alternative rock / pop, electronic, alternative pop, pop rock. Mood: sad

**estudio**

- Ludovico Einaudi — Nuvole Bianche: neoclassicism, modern classical, classical crossover, contemporary classical, classical. Mood: —
- Ludovico Einaudi — Experience: instrumental, locations, post modern, modern classical, contemporary, classical crossover, classical, podcast. Mood: —
- Yann Tiersen — Comptine d'un autre été, l'après-midi: (sin tags de canción). Mood: —
- Erik Satie — Gymnopédie No. 1: classical, piano, instrumental, ambient. Mood: —

**entrenamiento**

- Eminem — Till I Collapse: boastful, vulgar, anthemic, rhythmic, conscious hip hop, hardcore hip hop, angry, aggressive. Mood: anthemic, angry, aggressive, energetic
- Eminem — Lose Yourself: rap/hip hop, rap rock, movie soundtrack, film soundtrack, gangsta, midwestern rap, hip hop/rap, hardcore rap. Mood: —
- Survivor — Eye of the Tiger: soundtrack, soft rock, pop rock, album rock, classic rock, рок, synth pop, hard rock. Mood: —
- Kanye West — Stronger: hip hop, alternative rap, midwestern hip hop, midwest rap, hip hop rap, electro, pop rap, rap. Mood: —

**nostalgia**

- The Killers — Mr. Brightside: rock, indie rock, indie, alternative, alternative rock, 00s. Mood: —
- Coldplay — Viva la Vida: rock, pop, alternative rock, uk, britannique, acoustic, alternative, britpop. Mood: —
- Linkin Park — In the End: nu metal, rock, alternative rock, heavy metal, industrial rock, heavy, melodic, post grunge. Mood: energetic
- Green Day — Boulevard of Broken Dreams: catchy, alternative, classic pop punk, power pop, punk rock, rock, punk, punk pop. Mood: catchy, melancholy, sad, romantic

**previa_local**

- Los Palmeras — Bombón asesino: (sin tags de canción). Mood: —
- Los Palmeras — Soy sabalero: (sin tags de canción). Mood: —
- Gilda — No me arrepiento de este amor: latin, cumbia. Mood: —
- Gilda — Fuiste: cumbia, latin. Mood: —

## Cómo leer esto

- Los candidatos vienen de **Claude Opus 5.5**. Es un modelo grande: tomen estos números como cota optimista. Para la decisión final, regeneren con el modelo chico que piensan usar (comando generate) y comparen.
- "Reconocible" = supera el corte de oyentes de Last.fm o de usuarios de ListenBrainz definido en `config.toml`. La base de ListenBrainz es chica y sesgada a ciertos géneros.
- Los tags de artista suelen ser de género, no de mood: por eso el umbral se mide a nivel canción.
- Spotify se usa solo para ver si se puede exportar; sus datos no entran a ningún modelo ni se guardan.
