import pytest
from sorter.clean import clean_text, parse_filename, safe_filename

@pytest.mark.parametrize("raw, expected", [
    ("Prisma - www.example.com", "Prisma"),
    ("Fading Light (Original Mix) www.example.net", "Fading Light (Original Mix)"),
    ("https://example.net", ""),
    ("Open Sky 122", "Open Sky"),
    ("Tension (Extended Mix) 126", "Tension (Extended Mix)"),
    ("Glitch 909", "Glitch 909"),                      # Review Focus 1: fuera de 70-180
    ("640 (Extended) (Extended)", "640 (Extended)"),
    ("Cascade (Original Mix) [Nordlicht (Se)]", "Cascade (Original Mix)"),
    ("Slow Ember (Original Mix) [BREAKS]", "Slow Ember (Original Mix)"),
    (" Aurora", "Aurora"),
    ("365  (NOVA Extended Remix)", "365 (NOVA Extended Remix)"),
    ("Harbor (Original Mix) ", "Harbor (Original Mix)"),
    ("Solenøx, RAVI (ITA)", "Solenøx, RAVI (ITA)"),
    ("A [b [c] d] e", "A e"),
    ("Title (www.x.com)", "Title"),
    ("Title [www.x.com]", "Title"),
    ("X 70", "X"),
    ("X 180", "X"),
    ("X 181", "X 181"),
    ("Daybreak feat. Ana Reed (Leo Marsh 7AM Sunrise Mix)", "Daybreak feat. Ana Reed (Leo Marsh 7AM Sunrise Mix)"),
])
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected

def test_safe_filename():
    assert safe_filename("17:42") == "17-42"
    assert safe_filename("Pixel Moth & Kal/m") == "Pixel Moth & Kal-m"

@pytest.mark.parametrize("name, expected", [
    ("Lumen - Prisma - www.example.com.mp3", ("Lumen", "Prisma")),
    ("01 - Rene Alba, Nina Roe - Drift (Original Mix).mp3", ("Rene Alba, Nina Roe", "Drift (Original Mix)")),
    ("13. Owen Tarn - Lullaby (Ivo Brandt Extended Remix).mp3", ("Owen Tarn", "Lullaby (Ivo Brandt Extended Remix)")),
    ("070. Mara & Lenz, Kit - Signal (Original Mix).mp3", ("Mara & Lenz, Kit", "Signal (Original Mix)")),
    ("17-42 - Neon Echoes (Original Mix).mp3", ("17-42", "Neon Echoes (Original Mix)")),
    ("2041 - Rushline (Leo Marsh 90' Revision).mp3", ("2041", "Rushline (Leo Marsh 90' Revision)")),
    ("Pavel Orne-Gentle Rule (Extended).mp3", ("Pavel Orne", "Gentle Rule (Extended)")),
    ("01-tara_quill_and_nomi-dust_signal_(mira_dune_remix).mp3", ("Tara Quill And Nomi", "Dust Signal (Mira Dune Remix)")),
    ("01_wolfram_-_ciao_(extended_mix)-idc.mp3", ("Wolfram", "Ciao (Extended Mix)")),
    ("01-felix_arden--spiral-wus.mp3", ("Felix Arden", "Spiral")),
    ("02-q-ensemble-distant_coast_(extended_mix).mp3", ("Q-Ensemble", "Distant Coast (Extended Mix)")),
    ("01-brisa-lumora.mp3", ("Brisa", "Lumora")),
    ("Sample Track Name (Extended Mix).mp3", None),
    ("01-zeno.__pixel_moth__fable_(sa)__corvo_(ofc)-lattice_(extended_mix).mp3", ("Zeno., Pixel Moth, Fable (Sa), Corvo (Ofc)", "Lattice (Extended Mix)")),
])
def test_parse_filename(name, expected):
    assert parse_filename(name) == expected
