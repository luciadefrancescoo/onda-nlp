# onda. — prueba de factibilidad de datos

Corrida: 2026-11-23 17:36  
Candidatos: onda. (gemma4:12b + embeddinggemma) (el LLM interpreta la escena; canciones de Last.fm; ranking por embeddings y tags)  
Total: 180 candidatos en 6 prompts

**Fuentes**

- MusicBrainz (existencia, año): ✅
- ListenBrainz popularidad: ✅
- ListenBrainz tags: ✅
- Last.fm (oyentes, tags de mood): ✅
- Spotify (solo resolución): ✅

## Veredicto: GO

| Criterio | Valor | Umbral | Estado | Prompts por debajo |
|---|---|---|---|---|
| Existe en MusicBrainz (no es alucinación) | 94% | 80% | PASA | — |
| Se encuentra en Spotify (exportable) | 99% | 70% | PASA | — |
| ≥3 tags útiles a nivel canción | 91% | 50% | PASA | — |
| Música reconocible | 99% | 60% | PASA | — |

Señales complementarias (sin umbral):

- No encontradas en ninguna fuente (alucinación probable): 0%
- Con ≥3 tags útiles contando tags del artista: 96%
- Con al menos un tag de mood/escena: 36% a nivel canción, 37% contando artista
- Hits (≥ corte alto de oyentes en Last.fm): 67%
- Lanzadas en 2024 o después: 8% (año mediano: 2010)
- Duplicados: 0; artistas distintos / canciones: 63%

## Por prompt

| Prompt | Existe MB | No encontrada | Spotify | Reconocible | ≥3 tags canción | ≥3 tags c/artista | Mood canción | Año mediano | Oyentes Last.fm (mediana) |
|---|---|---|---|---|---|---|---|---|---|
| preboliche | 93% | 0% | 100% | 100% | 100% | 100% | 27% | 2016 | 791.716 |
| lluvia | 97% | 0% | 97% | 100% | 93% | 97% | 47% | 2002 | 935.834 |
| estudio | 100% | 0% | 100% | 100% | 90% | 100% | 40% | 2005 | 471.565 |
| entrenamiento | 90% | 0% | 100% | 100% | 93% | 100% | 20% | 2012 | 751.156 |
| nostalgia | 97% | 0% | 100% | 100% | 100% | 100% | 30% | 2005 | 1.472.460 |
| previa_local | 87% | 0% | 100% | 93% | 70% | 80% | 53% | 2010 | 849.844 |

- **preboliche**: Preboliche con amigos: reguetón divertido y conocido para cantar todos
- **lluvia**: Domingo de lluvia, tranqui, mirando por la ventana
- **estudio**: Música para estudiar concentrada para un parcial, que no me distraiga
- **entrenamiento**: Entrenamiento de fuerza en el gimnasio, algo que me dé mucha energía
- **nostalgia**: Nostalgia de la secundaria: temas que escuchábamos en los 2000
- **previa_local**: Previa en Buenos Aires con cumbia, cuarteto y RKT

## No encontradas en MusicBrainz

Revisarlas a mano: pueden ser alucinaciones o falsos negativos del matching (títulos largos de música clásica, nombres con símbolos).

- `preboliche` Future — Life Is Good (feat. Drake) (sí está en Last.fm, sí está en Spotify)
- `preboliche` fun. — We Are Young (feat. Janelle Monáe) (sí está en Last.fm, sí está en Spotify)
- `lluvia` Brian Eno — An Ending (Ascent) - Remastered 2005 (sí está en Last.fm, sí está en Spotify)
- `entrenamiento` Waka Flocka Flame — No Hands (feat. Roscoe Dash & Wale) (sí está en Last.fm, sí está en Spotify)
- `entrenamiento` Skrillex — Bangarang (feat. Sirah) (sí está en Last.fm, sí está en Spotify)
- `entrenamiento` Gesaffelstein — Lost in the Fire (feat. The Weeknd) (sí está en Last.fm, sí está en Spotify)
- `nostalgia` Britney Spears — Overprotected - Radio Edit (sí está en Last.fm, sí está en Spotify)
- `previa_local` Usher — DJ Got Us Fallin' in Love (feat. Pitbull) (sí está en Last.fm, sí está en Spotify)
- `previa_local` Ariana Grande — Stuck with U (with Justin Bieber) (sí está en Last.fm, sí está en Spotify)
- `previa_local` Future — Life Is Good (feat. Drake) (sí está en Last.fm, sí está en Spotify)
- `previa_local` Waka Flocka Flame — No Hands (feat. Roscoe Dash & Wale) (sí está en Last.fm, sí está en Spotify)

## Muestra de tags (primeras 4 por prompt)

**preboliche**

- J Balvin — Mi Gente: afrobeat, reggaeton, hip hop, pop, electronic, latin, latin pop. Mood: —
- Bad Bunny — VeLDÁ: electronic, pop, house, hip hop, salsa, latin pop, latin, english. Mood: —
- KAROL G — PROVENZA: party, pop, reggaeton, latin, afrobeats, latin pop, summer. Mood: party, summer
- Daddy Yankee — Gasolina: latin pop, latin, reggaeton, club, regueton, extremely droopy, pop, dance. Mood: —

**lluvia**

- The Microphones — I Want Wind to Blow: indie, lo fi, psychedelic folk, rock, folk, folk rock, indie folk, lo fi indie. Mood: mellow
- C418 — Subwoofer Lullaby: soundtrack, minecraft, vgm, movie soundtrack, video game music, chiptune, background, electronic. Mood: chillout
- 311 — Amber: pop/rock, alternative rock, alternative and punk, rap rock, nu metal, alternative pop/rock, alternative/indie rock, rap metal. Mood: chill, mellow
- Bon Iver — Rosyln: indie rock, folk, pop rock, indie, stage and screen, pop, alternative rock, rock. Mood: —

**estudio**

- Aphex Twin — Avril 14th: experimental, soundtrack, electronic, movie soundtrack, showtunes, idm, ambient, drum and bass. Mood: chillout
- Radiohead — Treefingers: pop/rock, britannique, electronica, alternative, experimental rock, alt rock, indie electronic, alternative and punk. Mood: dark, melancholic, atmospheric
- Aphex Twin — Xtal: electronic, ambient techno, idm, ambient, dark ambient, techno, acid house, acid techno. Mood: chillout
- C418 — Subwoofer Lullaby: soundtrack, minecraft, vgm, movie soundtrack, video game music, chiptune, background, electronic. Mood: chillout

**entrenamiento**

- BLACKPINK — JUMP: electronic, techno, edm, dance, soty, k pop, hardstyle. Mood: —
- Jane Remover — TURN UP OR DIE: electronic, experimental, edm, hard dance, experimental hip hop, industrial hip hop, rage, bass house. Mood: —
- PinkPantheress — Passion: alternative r&b, liquid funk, electronic, pop, liquid drum and bass, atmospheric drum and bass, bedroom pop, sambass. Mood: —
- Avenged Sevenfold — Hail to the King: metal, metalcore, alternative metal, heavy metal, hard rock, rock, symphonic metal, hardnheavy. Mood: —

**nostalgia**

- Fall Out Boy — Dance, Dance: pop punk, alternative, pop rock, pop/rock, pop general, party, alternative and punk, punk. Mood: party
- Weezer — Across the Sea: alternative and punk, alternative rock, alternative pop/rock, alternative/indie rock, pop/rock, emo, power pop, punk pop. Mood: melancholic, sad, angry, energetic, anthemic
- Good Charlotte — The Anthem: pop rock, third wave ska revival, alternative/indie rock, pop/rock, punk revival, alternative and punk, alternative punk, ska punk. Mood: —
- Fall Out Boy — This Ain't a Scene, It's an Arms Race: pop/rock, emo, pop punk, power pop, punk, alternative pop/rock, alternative/indie rock, rock. Mood: —

**previa_local**

- Far East Movement — Like a G6: dance, club, party, electronic, like a g6, techno, hip hop. Mood: party
- Flo Rida — Good Feeling: hip hop, electro, metal, rap, dubstep, southern hip hop, pop rap, pop. Mood: party, happy
- Black Eyed Peas — I Gotta Feeling: rnb/swing, party, pop rap, electropop, trance, pop, electro house, dance. Mood: party
- Ariana Grande — pov: happy, r&b, vocal, contemporary r&b, pop, pop rap, english, pop soul. Mood: happy

## Cómo leer esto

- Los candidatos vienen de **onda. (gemma4:12b + embeddinggemma)**. El LLM no nombra canciones: salen del catálogo de Last.fm.
- "Reconocible" = supera el corte de oyentes de Last.fm o de usuarios de ListenBrainz definido en `config.toml`. La base de ListenBrainz es chica y sesgada a ciertos géneros.
- Los tags de artista suelen ser de género, no de mood: por eso el umbral se mide a nivel canción.
- Spotify se usa solo para ver si se puede exportar; sus datos no entran a ningún modelo ni se guardan.
