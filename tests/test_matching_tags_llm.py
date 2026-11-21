import pytest

from vibematch_poc.llm import parse_candidates
from vibematch_poc.matching import (
    artist_similarity, dedup_key, normalize_title, primary_artist, title_similarity,
)
from vibematch_poc.tags import mood_tags, useful_tags


@pytest.mark.parametrize("raw,expected", [
    ("Despacito (feat. Daddy Yankee)", "despacito"),
    ("Mr. Brightside - Remastered 2015", "mr brightside"),
    ("Tití Me Preguntó", "titi me pregunto"),
    ("La_Original.mp3", "la original mp3"),
    ("Hasta el Amanecer [Live]", "hasta el amanecer"),
    ("Despacito ft. Justin Bieber", "despacito"),
])
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_title_similarity_does_not_confuse_prefixes():
    assert title_similarity("Hola", "Hola Perdida") < 0.85
    assert title_similarity("Dákiti", "DAKITI") == 1.0


def test_primary_artist():
    assert primary_artist("Bad Bunny feat. Chencho Corleone") == "Bad Bunny"
    assert primary_artist("Luck Ra, Khea") == "Luck Ra"
    assert primary_artist("Karol G") == "Karol G"


def test_artist_similarity_with_featured_credit():
    # El LLM dice "Bizarrap", MusicBrainz acredita "Bizarrap & Quevedo".
    assert artist_similarity("Bizarrap", ["Bizarrap", "Quevedo"], "Bizarrap & Quevedo") >= 0.95
    # Dúo como entidad única.
    assert artist_similarity("Wisin & Yandel", ["Wisin & Yandel"], "Wisin & Yandel") == 1.0
    # Artista distinto.
    assert artist_similarity("Karol G", ["Feid"], "Feid") < 0.85


def test_dedup_key_ignores_feat_and_case():
    assert dedup_key("Luis Fonsi feat. Daddy Yankee", "Despacito") == dedup_key("luis fonsi", "DESPACITO (Remix)")


def test_useful_tags_filters_junk_years_and_artist():
    tags = ["Reggaeton", "seen live", "2004", "2000s", "Daddy Yankee", "party", "favorites", "latin"]
    out = useful_tags(tags, "Daddy Yankee", ["seen live", "favorites"])
    assert out == ["reggaeton", "2000s", "party", "latin"]


def test_mood_tags_word_boundaries_and_stems():
    lex = ["rain", "fun", "nostalg*", "feel good"]
    tags = ["training", "funk", "rain", "nostalgic", "feel good", "rainy day"]
    # El tag entero tiene que ser la entrada: 'rain' no matchea 'training' ni 'rainy day'.
    assert mood_tags(tags, lex) == ["rain", "nostalgic", "feel good"]
    # Relleno al final se ignora.
    assert mood_tags(["rainy day", "party music"], ["rainy", "party"]) == ["rainy day", "party music"]
    # Géneros que contienen una palabra de mood no cuentan.
    assert mood_tags(["soft rock", "indie dance", "hip hop rnb and dance hall", "ambient pop"],
                     ["soft", "dance", "ambient"]) == []
    # Las raíces matchean una sola palabra.
    assert mood_tags(["melancholic", "melancholic rock"], ["melanchol*"]) == ["melancholic"]


def test_parse_candidates_tolerates_fences_and_spanish_keys():
    text = 'Acá va:\n```json\n{"canciones": [{"artista": "Gilda", "titulo": "Fuiste"}, {"artista": "", "titulo": "x"}]}\n```'
    assert parse_candidates(text) == [{"artist": "Gilda", "title": "Fuiste"}]


def test_parse_candidates_english_keys():
    assert parse_candidates('{"songs":[{"artist":"Queen","title":"Don\'t Stop Me Now"}]}') == [
        {"artist": "Queen", "title": "Don't Stop Me Now"}
    ]


def test_parse_candidates_no_json():
    with pytest.raises(ValueError):
        parse_candidates("no sé")
