# onda. — prueba de factibilidad de datos

Corrida: 2026-11-23 16:35  
Candidatos: gemma4:12b (API compatible OpenAI (http://localhost:11434/v1))  
Total: 180 candidatos en 6 prompts

**Fuentes**

- MusicBrainz (existencia, año): ✅
- ListenBrainz popularidad: ✅
- ListenBrainz tags: ✅
- Last.fm (oyentes, tags de mood): ✅
- Spotify (solo resolución): ✅

## Veredicto: NO-GO (o replantear)

| Criterio | Valor | Umbral | Estado | Prompts por debajo |
|---|---|---|---|---|
| Existe en MusicBrainz (no es alucinación) | 57% | 80% | NO PASA | preboliche, lluvia, estudio, entrenamiento, previa_local |
| Se encuentra en Spotify (exportable) | 62% | 70% | NO PASA | preboliche, lluvia, estudio, entrenamiento, previa_local |
| ≥3 tags útiles a nivel canción | 53% | 50% | PASA | preboliche, lluvia, estudio, previa_local |
| Música reconocible | 57% | 60% | NO PASA | preboliche, lluvia, estudio, previa_local |

Señales complementarias (sin umbral):

- No encontradas en ninguna fuente (alucinación probable): 33%
- Con ≥3 tags útiles contando tags del artista: 57%
- Con al menos un tag de mood/escena: 17% a nivel canción, 19% contando artista
- Hits (≥ corte alto de oyentes en Last.fm): 40%
- Lanzadas en 2024 o después: 0% (año mediano: 2004)
- Duplicados: 30; artistas distintos / canciones: 86%

## Por prompt

| Prompt | Existe MB | No encontrada | Spotify | Reconocible | ≥3 tags canción | ≥3 tags c/artista | Mood canción | Año mediano | Oyentes Last.fm (mediana) |
|---|---|---|---|---|---|---|---|---|---|
| preboliche | 44% | 44% | 52% | 44% | 40% | 44% | 12% | 2021 | 526.814 |
| lluvia | 43% | 50% | 47% | 47% | 43% | 47% | 7% | 2010 | 634.855 |
| estudio | 60% | 27% | 67% | 57% | 47% | 60% | 7% | 2006 | 318.052 |
| entrenamiento | 60% | 27% | 67% | 63% | 60% | 60% | 27% | 2002 | 1.560.937 |
| nostalgia | 83% | 13% | 87% | 83% | 83% | 83% | 37% | 2002 | 2.142.580 |
| previa_local | 0% | 80% | 0% | 0% | 0% | 0% | 0% | — | 21 |

- **preboliche**: Preboliche con amigos: reguetón divertido y conocido para cantar todos
- **lluvia**: Domingo de lluvia, tranqui, mirando por la ventana
- **estudio**: Música para estudiar concentrada para un parcial, que no me distraiga
- **entrenamiento**: Entrenamiento de fuerza en el gimnasio, algo que me dé mucha energía
- **nostalgia**: Nostalgia de la secundaria: temas que escuchábamos en los 2000
- **previa_local**: Previa en Buenos Aires con cumbia, cuarteto y RKT

## No encontradas en MusicBrainz

Revisarlas a mano: pueden ser alucinaciones o falsos negativos del matching (títulos largos de música clásica, nombres con símbolos).

- `preboliche` Karleyn — Simmelele
- `preboliche` J Balvin — Que Yo Pertenezco A Tu Barrio
- `preboliche` Ozuna — Coriano
- `preboliche` Feid — Ferxxo (sí está en Last.fm, sí está en Spotify)
- `preboliche` J Balvin — BZRP Music Sessions, Vol. 53
- `preboliche` Maluma — Hawái Vs Toscana
- `preboliche` Natti Natasha — Esclava Tuya
- `preboliche` Arcángel — La Noche (sí está en Spotify)
- `preboliche` Ozuna — Safanda
- `preboliche` Daddy Yankee — Ella Me Perdonó
- `preboliche` Farruko — Pa' Que Me Miren
- `preboliche` Rauw Alejandro — Vice Versa (sí está en Last.fm)
- `preboliche` Daddy Yankee — Con Tra, Tra
- `preboliche` Bad Bunny — Yo Perreaba
- `lluvia` Frank Sinatra — In the Wee Small Hour (sí está en Last.fm)
- `lluvia` Chet Baker — I Get Along Without You Alone
- `lluvia` Mac DeMarco — We're Going to Be Friends
- `lluvia` Bon Iver — Hol-cen
- `lluvia` Corinne Bailey Diaz — Slow Down
- `lluvia` Joni Mitchell — Both My Loving Companions
- `lluvia` Mazards — L'amour à la plage
- `lluvia` Kings of Convenience — Cabin at the Bottom of the River
- `lluvia` Iron & Wine — Via la Luz
- `lluvia` Diana Krall — The Girl's Next Door
- `lluvia` Sufjan Stevens — Mystery Is Gone
- `lluvia` Tom Odell — Like Older People
- `lluvia` Clairo — Bubble Gum (sí está en Last.fm, sí está en Spotify)
- `lluvia` Gregory Alan Isakov — The Bachelor
- `lluvia` Alice Phoebe == — The Way I See You
- `lluvia` Slowan Dawson — Slow Down
- `lluvia` Eloise — You Know Me
- `estudio` Lofi Girl — Study Session (sí está en Spotify)
- `estudio` Nujabes — Average Woman
- `estudio` Uyama Hirodeki — A New Day
- `estudio` Fredrik Andersson — The Way of the Wind
- `estudio` Emancipator — Soon (sí está en Last.fm)
- `estudio` Aphex Twin — Say Less
- `estudio` Guise — Deep Focus
- `estudio` Marconiuts — Focus
- `estudio` Glass_Beads — Focus
- `estudio` Yann Tiersen — Comptine d'un autre été, n° 5 (sí está en Spotify)
- `estudio` Bach — Goldberg Variations (sí está en Last.fm)
- `estudio` Spotify — Deep Focus
- `entrenamiento` Royal Blood — Fake Knows Nothing
- `entrenamiento` Skrillex — Equalize
- `entrenamiento` FortMinor — Remember the Name (sí está en Last.fm, sí está en Spotify)
- `entrenamiento` Fortissachero — The Way I Feel
- `entrenamiento` Machine Head — Davidstown
- `entrenamiento` Body Count — Cease to Exist
- `entrenamiento` Motley Crue — Kickstart My Side
- `entrenamiento` Imagine Dragons — Believin'
- `entrenamiento` Travis Scott — FEIN (sí está en Last.fm)
- `entrenamiento` Hardstyle — Techno (sí está en Last.fm)
- `entrenamiento` Swedish House Mafia — One (Your Mind Won't Work) (sí está en Spotify)
- `entrenamiento` Tiësto — The Way I Are
- `nostalgia` Backstreet's Back — Quit Playing Games (With My Heart)
- `nostalgia` Gorillaz — Feel It, Feel Good
- `nostalgia` Fall Out Boy — Sugar, We're Going Down Only (sí está en Spotify)
- `nostalgia` Ne-Yo — Missalize
- `nostalgia` Timbaland — Get Closer
- `previa_local` La Deliza — La Cumbia de los Pibitos
- `previa_local` Los Palmeras — El Bombón Asesino (sí está en Last.fm)
- `previa_local` Gerardo Gutiérrez Russo — La Cumbia de los Pibitos
- `previa_local` Los Pibitos — La Cumbia de los Pibitos
- `previa_local` La Deliza — El Bombón Asesino

## Muestra de tags (primeras 4 por prompt)

**preboliche**

- Bad Bunny — Tití Me Preguntó: ph_3_stars, dembow, trap, billboard hot 100, synth pop, spanish, ph_temp_checken, latin pop. Mood: —
- Daddy Yankee — Gasolina: latin pop, latin, reggaeton, club, regueton, extremely droopy, pop, dance. Mood: —
- Karleyn — Simmelele: (sin tags de canción). Mood: —
- J Balvin — Que Yo Pertenezco A Tu Barrio: (sin tags de canción). Mood: —

**lluvia**

- Norah Jones — Sunrise: adult contemporary, americana, vocal, folk, jazz, pop, soundtrack, contemporary jazz. Mood: —
- Billie Eilish — What Was I Made For?: (sin tags de canción). Mood: —
- Frank Sinatra — In the Wee Small Hour: (sin tags de canción). Mood: —
- Lana Del Rey — Video Games: soft rock, rock, baroque pop, dream pop, indie pop, ballad, chamber pop, ambient pop. Mood: —

**estudio**

- Lofi Girl — Study Session: (sin tags de canción). Mood: —
- Idealism — controlla: ambient, jazz, hip hop, soul, neo soul, r&b. Mood: —
- Jinsang — Affection: instrumental, hip hop, soul, boom bap. Mood: —
- Nujabes — Average Woman: (sin tags de canción). Mood: —

**entrenamiento**

- Eminem — Till I Collapse: boastful, vulgar, anthemic, rhythmic, conscious hip hop, hardcore hip hop, angry, aggressive. Mood: anthemic, angry, aggressive, energetic
- Royal Blood — Fake Knows Nothing: (sin tags de canción). Mood: —
- Skrillex — Equalize: (sin tags de canción). Mood: —
- FortMinor — Remember the Name: (sin tags de canción). Mood: —

**nostalgia**

- Britney Spears — Oops!... I Did It Again: pop rock, electronic, pop, contemporary r&b, electro, hip hop, synth pop, ballad. Mood: —
- Backstreet's Back — Quit Playing Games (With My Heart): (sin tags de canción). Mood: —
- Eminem — The Real Slim Shady: vulgar, sarcastic, misanthropic, hip hop / rap, rap, pop rap, g funk, sexual. Mood: energetic, anthemic, dark, angry, aggressive
- Linkin Park — In the End: nu metal, rock, alternative rock, heavy metal, industrial rock, heavy, melodic, post grunge. Mood: energetic

**previa_local**

- La Deliza — La Cumbia de los Pibitos: (sin tags de canción). Mood: —
- Los Palmeras — El Bombón Asesino: (sin tags de canción). Mood: —
- Gerardo Gutiérrez Russo — La Cumbia de los Pibitos: (sin tags de canción). Mood: —
- Los Pibitos — La Cumbia de los Pibitos: (sin tags de canción). Mood: —

## Cómo leer esto

- Los candidatos vienen de **gemma4:12b**. Modelo elegido por el equipo, misma consigna y temperatura 0.3.
- "Reconocible" = supera el corte de oyentes de Last.fm o de usuarios de ListenBrainz definido en `config.toml`. La base de ListenBrainz es chica y sesgada a ciertos géneros.
- Los tags de artista suelen ser de género, no de mood: por eso el umbral se mide a nivel canción.
- Spotify se usa solo para ver si se puede exportar; sus datos no entran a ningún modelo ni se guardan.
