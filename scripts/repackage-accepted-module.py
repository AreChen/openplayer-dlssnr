"""Release accepted runtime bytes with current plugin metadata, without rebuilding dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    source = args.accepted.resolve(strict=True)
    output, archive = args.output.resolve(), args.archive.resolve()
    if output.exists() or archive.exists() or archive.is_relative_to(output):
        parser.error("output/archive must be new; archive must be outside output")
    inventory = json.loads((source / "bundle-inventory.json").read_text(encoding="utf-8"))
    files = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    if files != set(inventory["files"]) | {"bundle-inventory.json"}:
        raise ValueError("accepted inventory file set differs")
    for name, entry in inventory["files"].items():
        file = source / name
        if not file.resolve().is_relative_to(source) or file.stat().st_size != entry["size"] or digest(file) != entry["sha256"]:
            raise ValueError(f"accepted bytes differ: {name}")
    old = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    current = json.loads((Path(__file__).resolve().parent.parent / "plugin/manifest.json").read_text(encoding="utf-8"))
    current["contributes"]["nativeModules"] = old["contributes"]["nativeModules"]
    if any(old.get(key) != value for key, value in current.items() if key not in {"minHostVersion", "description"}):
        raise ValueError("metadata-only release cannot change other manifest fields")
    shutil.copytree(source, output)
    (output / "manifest.json").write_text(json.dumps(current, indent=2), encoding="utf-8")
    manifest = output / "manifest.json"
    inventory["files"]["manifest.json"] = {"size": manifest.stat().st_size, "sha256": digest(manifest)}
    (output / "bundle-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
        for file in sorted(output.rglob("*")):
            if file.is_file():
                package.write(file, file.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("archive CRC check failed")
    sha = digest(archive)
    archive.with_suffix(archive.suffix + ".sha256").write_text(f"{sha}  {archive.name}\n", encoding="ascii")
    print(json.dumps({"archive": str(archive), "sha256": sha, "runtimeUnchanged": True}))


if __name__ == "__main__":
    main()
