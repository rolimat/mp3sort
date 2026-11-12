import re
from dataclasses import dataclass

from mutagen.id3 import ID3

from sorter.apply import FIELDS, FRAME
from sorter.clean import odd_flag, remix_flag, safe_filename
from sorter.scan import Item

# Collision flags are recomputed by the collection, never taken from the item.
_COLLISION = ("duplicate of", "already exists")  # recomputed by the collection, not origin flags

_BPM = re.compile(r"^\d{1,3}([.,]\d+)?$", re.ASCII)
_YEAR = re.compile(r"^(19|20)\d\d(-\d\d(-\d\d)?)?$", re.ASCII)


@dataclass
class Row:
    item: Item
    suggested: dict[str, str]
    values: dict[str, str]
    selected: bool
    kbps: int | None = None
    vbr: bool = False
    forced: frozenset = frozenset()  # fields written even when equal to the suggestion (year shortened)

    def edited(self) -> bool:
        return self.values != self.suggested

    def filename(self) -> str | None:
        a, t = self.values["artist"], self.values["title"]
        return f"{safe_filename(a)} - {safe_filename(t)}.mp3" if a and t else None

    def flags(self, extra: list[str]) -> list[str]:
        if not self.edited():
            base = [f for f in self.item.proposal.flags if not f.startswith(_COLLISION)]
        elif self.filename() is None:
            base = ["no artist or title"]
        else:
            base = [f for f in (remix_flag(self.values["title"]),
                                odd_flag(self.values["artist"], self.values["title"])) if f]
        return base + extra

    def edit(self, field: str, value: str) -> str | None:
        if field not in FIELDS:
            return "unknown field"
        if not isinstance(value, str):
            return "invalid value"
        v = value.strip()
        if field == "bpm" and v:
            if not _BPM.match(v) or not 1 <= float(v.replace(",", ".")) <= 999:
                return "BPM must be a number from 1 to 999"
            v = v.replace(",", ".")
        if field == "year" and v and not _YEAR.match(v):
            return "Year must be YYYY, YYYY-MM or YYYY-MM-DD (1900-2099)"
        self.values[field] = v
        if self.filename() is None:
            self.selected = False
        return None

    def reset(self) -> None:
        self.values = dict(self.suggested)


def _file_tags(item: Item) -> dict[str, str]:
    try:
        tags = ID3(item.src)
    except Exception:
        return {}
    return {k: "; ".join(map(str, tags[FRAME[k]].text)) for k in ("year", "key", "bpm", "label") if FRAME[k] in tags}


def row_from_item(item: Item) -> Row:
    s = dict.fromkeys(FIELDS, "")
    s.update(_file_tags(item))
    forced = frozenset()
    if (m := re.match(r"\d{4}", s["year"], re.ASCII)) and s["year"] != m.group():
        s["year"], forced = m.group(), frozenset({"year"})
    s["artist"], s["title"] = item.proposal.artist, item.proposal.title
    return Row(item, s, dict(s), item.selected, item.bitrate, item.vbr, forced)
