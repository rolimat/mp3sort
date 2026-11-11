import re
import unicodedata
from dataclasses import dataclass

_WEB = re.compile(r"(?:\s*-\s*)?(?:https?://[^\s()\[\]]+|www\.[^\s()\[\]]+|[^\s()\[\]]+\.(?:com|net|org|ru|info|io)\b)")
_EMPTY = re.compile(r"\(\s*\)")
_BRACKETS = re.compile(r"\[[^\[\]]*\]")
_DUP_PARENS = re.compile(r"(\([^()]*\))(?:\s*\1)+")
_BPM = re.compile(r"^(.*\S)\s+(\d{2,3})$")


def clean_text(s: str) -> str:
    s = _WEB.sub("", s)
    s = _EMPTY.sub("", s)
    prev = None
    while prev != s:  # repetir quita corchetes anidados de dentro hacia fuera
        prev, s = s, _BRACKETS.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    s = _DUP_PARENS.sub(r"\1", s)
    m = _BPM.match(s)
    if m and 70 <= int(m.group(2)) <= 180:
        s = m.group(1)
    return s.strip(" -")


def safe_filename(s: str) -> str:
    return s.replace("/", "-").replace(":", "-")


_TRACK = re.compile(r"^\d{1,3}(?:\.\s*|\s+-\s+|\s+)")
_GROUP = re.compile(r"[a-z0-9]{2,5}")


def _title_case(s: str) -> str:
    return re.sub(r"(?:^|(?<=[\s(-]))[a-z]", lambda m: m.group().upper(), s)


def parse_filename(name: str) -> tuple[str, str] | None:
    s = name.rsplit(".", 1)[0]
    if " " in s:
        s = _TRACK.sub("", s, count=1)
        sep = " - " if " - " in s else "-"
        if sep not in s:
            return None
        artist, title = s.split(sep, 1)
    else:
        s = re.sub(r"^\d{1,3}[-_]", "", s).replace("_-_", "-")
        s = re.sub(r"-{2,}", "-", s)
        parts = s.split("-")
        if len(parts) >= 3 and _GROUP.fullmatch(parts[-1]):
            parts.pop()
        if len(parts) < 2:
            return None
        artist = _title_case("-".join(parts[:-1]).replace("__", ", ").replace("_", " "))
        title = _title_case(parts[-1].replace("__", ", ").replace("_", " "))
    artist, title = clean_text(artist), clean_text(title)
    return (artist, title) if artist and title else None


@dataclass
class Proposal:
    artist: str  # valor para el tag (puede contener / o :)
    title: str
    flags: list[str]  # motivos de aviso; vacío = OK

    @property
    def filename(self) -> str | None:
        if not self.artist or not self.title:
            return None
        return f"{safe_filename(self.artist)} - {safe_filename(self.title)}.mp3"


_NOISE = re.compile(r"\b(?:and|x|feat|ft|vs)\b")
_TAIL_GROUP = re.compile(r"\s*(\([^()]*\))\s*$")


_FOLD = str.maketrans({"ø": "o", "đ": "d", "ł": "l", "æ": "ae", "ß": "ss"})


def _norm(s: str) -> str:
    s = s.lower().translate(_FOLD)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", _NOISE.sub("", s))


def _same(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:  # sin alfanuméricos latinos: comparar el texto tal cual
        return a.casefold().strip() == b.casefold().strip()
    return na == nb


def _propose(filename: str, tag_artist: str | None, tag_title: str | None) -> Proposal:
    ta, tt = clean_text(tag_artist or ""), clean_text(tag_title or "")
    fp = parse_filename(filename)
    if not ta or not tt or " - " in tt:
        if fp:
            why = "el título contiene el artista" if ta and tt else "sin tags, sacado del nombre de fichero"
            return Proposal(fp[0], fp[1], [why])
        return Proposal("", "", ["sin artista o título"])
    if not fp:
        return Proposal(ta, tt, [])
    fa, ft = fp
    if _same(ta, fa):
        if _same(tt, ft):
            return Proposal(ta, tt, [])
        short, long_ = sorted((tt, ft), key=len)
        m = _TAIL_GROUP.search(long_)
        if m and _same(long_[: m.start()], short):
            g = m.group(1)
            flag = f"falta '{g}' en el nombre de fichero" if long_ == tt else f"añadido '{g}' desde el nombre de fichero"
            return Proposal(ta, long_, [flag])
    elif all(map(_norm, (ta, tt, fa, ft))) and _norm(tt).startswith(_norm(fa)) and _norm(ft).startswith(_norm(ta)):
        return Proposal(ta, tt, ["¿artista y título intercambiados?"])
    return Proposal(ta, tt, ["tag y nombre de fichero no coinciden"])


_MIX_PHRASE = re.compile(r"^(.+\S)\s+(Original Mix|Extended Mix|Extended Version|Extended|Radio Edit|Club Mix|Dub Mix)$", re.I)
_REMIX_TAIL = re.compile(r"\S+\s+\S*Remix$", re.I)
_WEIRD = re.compile(r'[<>|*?"]|(?<!\S)(?=[\W_])[^\s&+/\-](?=[\s,]|$)')


def _paren_mix(title: str, fp: tuple[str, str] | None, flags: list[str]) -> str:
    if title.endswith(")"):
        return title
    m = _TAIL_GROUP.search(fp[1]) if fp else None
    if m:  # el nombre de fichero ya trae el paréntesis: reutilizarlo sobre las palabras del tag
        words = title.split()
        for k in range(len(words) - 1, 0, -1):
            if _same(" ".join(words[k:]), m.group(1)[1:-1]) and _same(" ".join(words[:k]), fp[1][: m.start()]):
                return f"{' '.join(words[:k])} ({' '.join(words[k:])})"
    if m := _MIX_PHRASE.match(title):
        return f"{m.group(1)} ({m.group(2)})"
    if _REMIX_TAIL.search(title):
        flags.append("remix sin paréntesis, revisar")
    return title


def propose(filename: str, tag_artist: str | None, tag_title: str | None) -> Proposal:
    p = _propose(filename, tag_artist, tag_title)
    if p.artist and p.title:
        p.title = _paren_mix(p.title, parse_filename(filename), p.flags)
        if _WEIRD.search(p.artist) or _WEIRD.search(p.title):
            p.flags.append("caracteres raros en artista o título")
    return p
