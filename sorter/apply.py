import shutil
from pathlib import Path

from mutagen import apev2
from mutagen.id3 import ID3, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp3 import MP3

from sorter.scan import Item, name_key


def apply_item(item: Item, dest: Path) -> str | None:
    """Mueve item.src a dest con tags limpios. None si va bien, o mensaje de error."""
    name = item.proposal.filename
    if name is None:
        return "sin nombre propuesto"
    target = dest / name
    try:
        if any(name_key(p.name) == name_key(name) for p in dest.iterdir()):
            return "ya existe en destino, no se sobrescribe"
    except OSError as e:
        return f"no se pudo leer el destino: {e}"
    try:
        with open(item.src, "rb") as r, open(target, "xb") as w:  # "x": nunca sobrescribe
            try:
                shutil.copyfileobj(r, w)
            except BaseException:
                w.close()
                target.unlink(missing_ok=True)  # solo si open "xb" tuvo éxito: es nuestra
                raise
    except FileExistsError:
        return "ya existe en destino, no se sobrescribe"
    except OSError as e:
        return f"no se pudo copiar: {e}"
    try:
        shutil.copystat(item.src, target)
        try:
            tags = ID3(target)
            v2 = tags.version[1] if tags.version[1] in (3, 4) else 4  # v2.2 no se puede escribir
        except ID3NoHeaderError:
            tags, v2 = ID3(), 4
        tags.setall("TPE1", [TPE1(encoding=3, text=item.proposal.artist)])
        tags.setall("TIT2", [TIT2(encoding=3, text=item.proposal.title)])
        for k in ("TALB", "TCON", "COMM"):
            tags.delall(k)
        tags.save(target, v1=1, v2_version=v2)
        size0 = target.stat().st_size
        apev2.delete(target)  # APEv2 lleva basura (webs, comentarios); PRIV/Traktor (ID3) se conserva
        chk = ID3(target)
        if chk["TPE1"].text != [item.proposal.artist] or chk["TIT2"].text != [item.proposal.title]:
            raise ValueError("los tags escritos no coinciden")
        try:
            apev2.APEv2(target)
            raise ValueError("queda un tag APEv2")
        except apev2.APENoHeaderError:
            pass
        info = MP3(target).info
        # sin cabecera Xing mutagen estima la duración con el tamaño total: el APE borrado la acorta
        extra = (size0 - target.stat().st_size) * 8 / info.bitrate if info.bitrate else 0
        if abs(info.length - MP3(item.src).info.length) > 0.1 + extra:
            raise ValueError("la duración cambió")
    except Exception as e:
        target.unlink(missing_ok=True)
        return f"error al escribir tags, original intacto: {e}"
    except BaseException:  # Ctrl-C: no dejar una copia sin verificar
        target.unlink(missing_ok=True)
        raise
    try:
        item.src.unlink()
    except OSError as e:
        return f"copiado y verificado, pero no se pudo borrar el original (quedan ambos): {e}"
    return None
