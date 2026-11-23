# onda. — prueba de factibilidad de datos

Corrida: 2026-11-23 19:33  
Candidatos: onda. (gemma4:12b + embeddinggemma) (el LLM interpreta la escena; canciones de Last.fm; ranking por embeddings y tags)  
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
| Existe en MusicBrainz (no es alucinación) | 98% | 80% | PASA | — |
| Se encuentra en Spotify (exportable) | — | 70% | N/A | — |
| ≥3 tags útiles a nivel canción | 78% | 50% | PASA | previa_local |
| Música reconocible | 91% | 60% | PASA | previa_local |

Señales complementarias (sin umbral):

- No encontradas en ninguna fuente (alucinación probable): 0%
- Con ≥3 tags útiles contando tags del artista: 86%
- Con al menos un tag de mood/escena: 19% a nivel canción, 20% contando artista
- Hits (≥ corte alto de oyentes en Last.fm): 43%
- Lanzadas en 2024 o después: 5% (año mediano: 2008)
- Duplicados: 0; artistas distintos / canciones: 66%

## Por prompt

| Prompt | Existe MB | No encontrada | Spotify | Reconocible | ≥3 tags canción | ≥3 tags c/artista | Mood canción | Año mediano | Oyentes Last.fm (mediana) |
|---|---|---|---|---|---|---|---|---|---|
| preboliche | 93% | 0% | — | 97% | 83% | 93% | 13% | 2017 | 377.040 |
| lluvia | 100% | 0% | — | 100% | 97% | 100% | 33% | 2007 | 713.194 |
| estudio | 100% | 0% | — | 100% | 97% | 100% | 23% | 2010 | 253.660 |
| entrenamiento | 100% | 0% | — | 100% | 80% | 87% | 10% | 2009 | 286.396 |
| nostalgia | 100% | 0% | — | 100% | 100% | 100% | 33% | 2003 | 1.593.918 |
| previa_local | 93% | 0% | — | 47% | 13% | 33% | 0% | 2007 | 27.368 |

- **preboliche**: Preboliche con amigos: reguetón divertido y conocido para cantar todos
- **lluvia**: Domingo de lluvia, tranqui, mirando por la ventana
- **estudio**: Música para estudiar concentrada para un parcial, que no me distraiga
- **entrenamiento**: Entrenamiento de fuerza en el gimnasio, algo que me dé mucha energía
- **nostalgia**: Nostalgia de la secundaria: temas que escuchábamos en los 2000
- **previa_local**: Previa en Buenos Aires con cumbia, cuarteto y RKT

## No encontradas en MusicBrainz

Revisarlas a mano: pueden ser alucinaciones o falsos negativos del matching (títulos largos de música clásica, nombres con símbolos).

- `preboliche` Nicky Jam — El Perdón (with Enrique Iglesias) (sí está en Last.fm)
- `preboliche` Selena Gomez — Fetish (feat. Gucci Mane) (sí está en Last.fm)
- `previa_local` La Joaqui — Obsesión (sí está en Last.fm)
- `previa_local` El Cuis — Piñata (sí está en Last.fm)

## Muestra de tags (primeras 4 por prompt)

**preboliche**

- J Balvin — Mi Gente: afrobeat, reggaeton, hip hop, pop, electronic, latin, latin pop. Mood: —
- Bad Bunny — VOY A LLeVARTE PA PR: latin pop, spanish, reggaeton, offizielle charts, 1–4 wochen, electronic, pop, house. Mood: —
- Daddy Yankee — Rompe: reggaeton, latin, hip hop, rap. Mood: —
- Bad Bunny — NUEVAYoL: pop, ph_temp_checken, 5+ wochen, offizielle charts, latin pop, billboard hot 100 2026, ph_3_stars, spanish. Mood: —

**lluvia**

- C418 — Danny: soundtrack, vgm, chiptune, ambient, video game music, idm, score, electronic. Mood: chillout
- Bon Iver — Rosyln: indie rock, folk, pop rock, indie, stage and screen, pop, alternative rock, rock. Mood: —
- C418 — Subwoofer Lullaby: soundtrack, minecraft, vgm, movie soundtrack, video game music, chiptune, background, electronic. Mood: chillout
- The Microphones — I Want Wind to Blow: indie, lo fi, psychedelic folk, rock, folk, folk rock, indie folk, lo fi indie. Mood: mellow

**estudio**

- Ludovico Einaudi — Una Mattina: contemporary, classical, modern classical. Mood: —
- Aphex Twin — Xtal: electronic, ambient techno, idm, ambient, dark ambient, techno, acid house, acid techno. Mood: chillout
- Max Richter — On the Nature of Daylight: classical, electronic, instrumental, ambient, contemporary instrumental, contemporary classical, modern classical, neoclassicism. Mood: —
- Aphex Twin — Tha: ambient techno, electronic, techno, ambient house, ambient, idm, acid techno, chillout. Mood: chillout

**entrenamiento**

- BLACKPINK — JUMP: electronic, techno, edm, dance, soty, k pop, hardstyle. Mood: —
- Avenged Sevenfold — Nightmare: heavy metal, post hardcore, metal, metalcore, emo, alternative metal, rock, alternative/indie rock. Mood: —
- Avenged Sevenfold — Hail to the King: metal, metalcore, alternative metal, heavy metal, hard rock, rock, symphonic metal, hardnheavy. Mood: —
- Headhunterz — The Power Of The Mind (Qlimax Anthem 2007): electronic, hardstyle. Mood: —

**nostalgia**

- Panic! at the Disco — I Write Sins Not Tragedies: emo, post punk revival, pop rock, rock, rap and hip hop, dark cabaret, punk, power pop. Mood: —
- Fall Out Boy — Dance, Dance: pop punk, alternative, pop rock, pop/rock, pop general, party, alternative and punk, punk. Mood: party
- Good Charlotte — The Anthem: pop rock, third wave ska revival, alternative/indie rock, pop/rock, punk revival, alternative and punk, alternative punk, ska punk. Mood: —
- Fall Out Boy — This Ain't a Scene, It's an Arms Race: pop/rock, emo, pop punk, power pop, punk, alternative pop/rock, alternative/indie rock, rock. Mood: —

**previa_local**

- Six Sex — AREA 69: electronic, hip hop, reggae, latin, reggaeton, neoperreo. Mood: —
- Los Palmeras — Cumbia sobre el mar: (sin tags de canción). Mood: —
- Los Palmeras — Perra: (sin tags de canción). Mood: —
- La Joaqui — Dos Besitos: (sin tags de canción). Mood: —

## Cómo leer esto

- Los candidatos vienen de **onda. (gemma4:12b + embeddinggemma)**. El LLM no nombra canciones: salen del catálogo de Last.fm.
- "Reconocible" = supera el corte de oyentes de Last.fm o de usuarios de ListenBrainz definido en `config.toml`. La base de ListenBrainz es chica y sesgada a ciertos géneros.
- Los tags de artista suelen ser de género, no de mood: por eso el umbral se mide a nivel canción.
- Spotify se usa solo para ver si se puede exportar; sus datos no entran a ningún modelo ni se guardan.
