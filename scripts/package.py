"""Build an installable ZIP using an explicit runtime file list."""

import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "qgislab_plugin"


def build(output, version=None):
    metadata = (ROOT / "metadata.txt").read_text(encoding="utf-8")
    if version:
        version = version.removeprefix("v")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)", version):
            raise ValueError("Use a version such as 0.1.0 or v0.1.0")
        metadata = re.sub(
            r"^version=.*$", f"version={version}", metadata, flags=re.MULTILINE
        )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [
        ROOT / name for name in ("__init__.py", "icon.svg", "LICENSE", "README.md")
    ]
    files += sorted((ROOT / "qgislab").rglob("*.py"))
    files += sorted((ROOT / "qgislab").rglob("*.svg"))
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(f"{PLUGIN_NAME}/metadata.txt", metadata)
        for path in files:
            archive.write(path, f"{PLUGIN_NAME}/{path.relative_to(ROOT).as_posix()}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--output", default=f"dist/{PLUGIN_NAME}.zip")
    args = parser.parse_args()
    print(build(args.output, args.version))
