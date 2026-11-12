"""Collect the project licence and bundled third-party licences into <out_dir>."""
import re
import shutil
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://github.com/rolimat/mp3sort"
LICENSE_RE = re.compile(r"(^|/)(licen[cs]e|copying|notice)[^/]*$", re.I)


def _bundled() -> dict:
    """pywebview's runtime dependency closure plus mutagen (+ pyinstaller if installed)."""
    found, todo = {}, ["pywebview", "mutagen", "pyinstaller"]
    while todo:
        name = todo.pop()
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if name in ("pyinstaller",):  # build-only, absent from the test env
                continue
            raise
        key = dist.metadata["Name"].lower()
        if key in found:
            continue
        found[key] = dist
        for r in dist.requires or []:
            req = Requirement(r)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                todo.append(req.name)
    return found


def collect_licenses(out: Path) -> list[Path]:
    out = Path(out)
    written = []

    def put(src: Path, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)

    put(ROOT / "LICENSE", out / "LICENSE")
    (out / "SOURCE.txt").write_text(SOURCE_URL + "\n")
    written.append(out / "SOURCE.txt")
    put(Path(sysconfig.get_paths()["stdlib"]) / "LICENSE.txt", out / "third-party/python/LICENSE.txt")

    missing = []
    for name, dist in sorted(_bundled().items()):
        files = [f for f in dist.files or [] if LICENSE_RE.search(str(f))]
        if not files:
            # Some wheels (proxy_tools, pyobjc-framework-*) ship no licence file; fall back to the
            # declared licence metadata so the notice still travels. No metadata at all = fail.
            lic = dist.metadata["License-Expression"] or dist.metadata["License"]
            if not lic:
                missing.append(name)
                continue
            dst = out / "third-party" / name / "LICENSE-METADATA.txt"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(f"{name} {dist.version}\nLicense: {lic}\nAuthor: {dist.metadata['Author'] or dist.metadata['Author-email']}\n"
                           f"Home-page: {dist.metadata['Home-page']}\n(no license file shipped in the distribution)\n")
            written.append(dst)
        for f in files:
            put(Path(dist.locate_file(f)), out / "third-party" / name / Path(str(f)).name)
    if missing:
        raise SystemExit("no license file for: " + ", ".join(missing))
    return written


if __name__ == "__main__":
    collect_licenses(Path(sys.argv[1]))
