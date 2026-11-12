"""Collect the project licence, bundled third-party licences and the source offer into <out_dir>.

    collect_licenses.py OUT_DIR [VERSION]     write the licences (VERSION defaults to 0.0.0)
    collect_licenses.py --check-bundle APP    fail on a native library in APP without a notice
"""
import re
import shutil
import sys
import sysconfig
from importlib import metadata
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES = ROOT / "assets" / "licenses"
REPO = "https://github.com/rolimat/mp3sort"
LICENSE_RE = re.compile(r"(^|/)(licen[cs]e|copying|notice)(\.[a-z]+)?$", re.I)
RUNTIME = ("pywebview", "mutagen")  # walked with their runtime requirements
BOOTLOADER = "pyinstaller"  # its bootloader ships in the app; its own requirements do not
# native libraries the bundled Python ships: file name stem -> licence dir in assets/licenses
NATIVE = {"libssl": "openssl", "libcrypto": "openssl", "libmpdec": "mpdecimal",
          "libzstd": "zstd", "liblzma": "xz", "Python": "python", "libpython3": "python"}
MACHO = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def _bundled() -> dict:
    """name -> distribution: the runtime closure of RUNTIME, plus pyinstaller (if installed)."""
    found, todo = {}, list(RUNTIME)
    while todo:
        dist = metadata.distribution(todo.pop())
        key = dist.metadata["Name"].lower()
        if key in found:
            continue
        found[key] = dist
        for r in dist.requires or []:
            req = Requirement(r)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                todo.append(req.name)
    try:
        found[BOOTLOADER] = metadata.distribution(BOOTLOADER)
    except metadata.PackageNotFoundError:  # build-only, absent from the test env
        pass
    return found


def _dest(f) -> PurePosixPath | None:
    """Path of a distribution file relative to its dist-info dir (or site-packages); None if unsafe."""
    p = PurePosixPath(str(f).replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    if p.parts[0].endswith(".dist-info") and len(p.parts) > 1:
        p = PurePosixPath(*p.parts[1:])
    return p


def _python_license() -> Path:
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    tried = [d / n for d in (stdlib, Path(sys.base_prefix)) for n in ("LICENSE.txt", "LICENSE")]
    for p in tried:
        if p.is_file():
            return p
    raise SystemExit("Python license not found in: " + ", ".join(map(str, tried)))


def _source_text(version: str, dists: dict) -> str:
    ref = "main" if version == "0.0.0" else f"v{version}"
    lines = [f"mp3sort {version} source code: {REPO}/tree/{ref}", "",
             "Bundled third-party Python distributions (name, version, source):"]
    for name, dist in sorted(dists.items()):
        n = dist.metadata["Name"]
        lines.append(f"  {n} {dist.version}: https://pypi.org/project/{n}/{dist.version}/#files")
    v = sys.version.split()[0]
    lines += [f"  Python {v}: https://www.python.org/downloads/release/python-{v.replace('.', '')}/", "",
              "The complete corresponding source code is available at the URLs above.",
              "The licence texts are in the licenses folder of the dmg and inside mp3sort.app "
              "(Contents/Resources/licenses).", ""]
    return "\n".join(lines)


def collect_licenses(out: Path, version: str = "0.0.0") -> list[Path]:
    out = Path(out)
    written: list[Path] = []

    def put(src: Path, dst: Path):
        if dst in written:
            raise SystemExit(f"two license files map to {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(dst)

    def put_dir(src: Path, name: str):
        for f in sorted(src.rglob("*")):
            if f.is_file() and not any(part.startswith(".") for part in f.relative_to(src).parts):
                put(f, out / "third-party" / name / f.relative_to(src))

    dists = _bundled()
    put(ROOT / "LICENSE", out / "LICENSE")
    put(_python_license(), out / "third-party/python/LICENSE.txt")
    for name in sorted(set(NATIVE.values()) - {"python"}):
        put_dir(OVERRIDES / name, name)

    missing = []
    for name, dist in sorted(dists.items()):
        if (OVERRIDES / name).is_dir():  # committed override wins
            put_dir(OVERRIDES / name, name)
            continue
        files = [f for f in dist.files or [] if LICENSE_RE.search(str(f))]
        for f in files:
            rel = _dest(f)
            if rel is None:
                print(f"error: skipping unsafe license path {f} in {name}", file=sys.stderr)
                continue
            put(Path(dist.locate_file(f)), out / "third-party" / name / rel)
        if not (out / "third-party" / name).is_dir():
            if name.startswith("pyobjc-"):  # all of PyObjC is MIT; some wheels omit the file
                put_dir(OVERRIDES / "pyobjc", name)
            else:
                missing.append(name)
    if missing:
        raise SystemExit("no license file or override in assets/licenses for: " + ", ".join(missing))
    (out / "SOURCE.txt").write_text(_source_text(version, dists))
    written.append(out / "SOURCE.txt")
    return written


def unknown_native(app: Path) -> list[str]:
    """Native code in the app bundle whose licence is not in the app's licenses/third-party."""
    contents = Path(app) / "Contents"
    have = {p.name for p in (contents / "Resources/licenses/third-party").iterdir()}
    owners = {top: [d.lower() for d in ds] for top, ds in metadata.packages_distributions().items()}
    bad = []
    for base in (contents / "Frameworks", contents / "Resources"):
        stack = [base]
        while stack:
            d = stack.pop()
            for p in d.iterdir():
                if p.is_symlink():
                    continue
                if p.is_dir():
                    if p.suffix == ".framework":
                        if NATIVE.get(p.stem) not in have:
                            bad.append(str(p.relative_to(contents)))
                    else:
                        stack.append(p)
                    continue
                with open(p, "rb") as fh:
                    if fh.read(4) not in MACHO and p.suffix not in (".so", ".dylib"):
                        continue
                rel = p.relative_to(base)
                if p.suffix == ".so" and len(rel.parts) > 1:  # Python extension module
                    top = rel.parts[0]
                    names = ["python"] if top.startswith("python3") or top == "lib-dynload" else owners.get(top, [])
                else:
                    names = [NATIVE.get(p.name.split(".")[0])]
                if not any(n in have for n in names):
                    bad.append(str(p.relative_to(contents)))
    return bad


if __name__ == "__main__":
    if sys.argv[1:2] == ["--check-bundle"]:
        bad = unknown_native(Path(sys.argv[2]))
        if bad:
            sys.exit("native code without a licence notice (add it to NATIVE in tools/collect_licenses.py"
                     " and its text to assets/licenses/):\n  " + "\n  ".join(bad))
        print("all bundled native code has a licence notice")
    else:
        collect_licenses(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "0.0.0")
