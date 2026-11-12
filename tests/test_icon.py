import xml.etree.ElementTree as ET
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def test_icon_svg_master():
    svg = ASSETS / "icon.svg"
    root = ET.parse(svg).getroot()
    assert root.get("viewBox") == "0 0 1024 1024"
    text = svg.read_text().lower()
    for colour in ("#3478f6", "#7b5cff", "#1d1e23"):
        assert colour in text


def test_icns_present():
    icns = ASSETS / "mp3sort.icns"
    assert icns.read_bytes()[:4] == b"icns"
    assert icns.stat().st_size > 10 * 1024
