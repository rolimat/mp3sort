from pathlib import Path


def check_folders(source: Path, dest: Path) -> str | None:
    for label, d in (("destination", dest), ("source", source)):
        if not d.is_dir():
            return f"Error: the {label} folder does not exist: {d}"
    s, d = source.resolve(), dest.resolve()
    if s == d or s in d.parents or d in s.parents:
        return "Error: the destination cannot be inside the source (or vice versa)"
    return None
