"""Turn a release tag (vX.Y.Z) into a version string."""
import re
import sys


def version_from_tag(tag: str) -> str:
    m = re.fullmatch(r"v([0-9]+\.[0-9]+\.[0-9]+)", tag)
    if not m:
        raise ValueError(f"invalid tag: {tag}")
    return m.group(1)


if __name__ == "__main__":
    try:
        print(version_from_tag(sys.argv[1] if len(sys.argv) > 1 else ""))
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
