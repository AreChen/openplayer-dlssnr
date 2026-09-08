"""Stage a relocatable developer native module; never bundle NVIDIA's runtime."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import py_compile
import shutil
import sys
import zipfile

import numpy

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__", "tests", "test", "include", "pkgconfig"}


def copy_tree(source, destination):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if (path.is_file() and not SKIP.intersection(relative.parts)
                and path.suffix not in {".pyc", ".pdb", ".pyi", ".h", ".lib"}):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def stage(output, vapoursynth, host):
    if (sys.platform != "win32" or sys.version_info[:2] != (3, 12)
            or platform.machine().lower() not in {"amd64", "x86_64"}):
        raise ValueError("build with a prepared Windows x64 CPython 3.12 runtime")
    if output.exists():
        raise ValueError("output must not exist")
    home = Path(sys.base_prefix)
    if not (home / "python312.dll").is_file() or not (vapoursynth / "vsscript.dll").is_file():
        raise ValueError("provide a complete Python runtime and VapourSynth wheel directory")
    output.mkdir(parents=True)
    runtime = output / "runtime"
    runtime.mkdir()
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python312.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copyfile(home / name, runtime / name)
    copy_tree(home / "DLLs", runtime / "DLLs")
    with zipfile.ZipFile(runtime / "python312.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((home / "Lib").rglob("*.py")):
            relative = path.relative_to(home / "Lib")
            if not (SKIP | {"site-packages", "idlelib", "tkinter", "ensurepip"}).intersection(relative.parts):
                archive.write(path, relative.as_posix())
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True)
    # A sourceless bootstrap avoids creating its own cache before this policy runs.
    py_compile.compile(str(ROOT / "portable_sitecustomize.py"), cfile=str(site / "sitecustomize.pyc"),
                       dfile="sitecustomize.py", doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    copy_tree(Path(numpy.__file__).parent, site / "numpy")
    copy_tree(Path(numpy.__file__).parent.parent / "numpy.libs", site / "numpy.libs")
    copy_tree(vapoursynth, site / "vapoursynth")
    for distribution in (importlib.metadata.distribution("numpy"), next(
            item for item in importlib.metadata.distributions(path=[str(vapoursynth.parent)])
            if item.metadata["Name"].lower() == "vapoursynth")):
        for file in distribution.files:
            if file.parts and file.parts[0].endswith(".dist-info") and ".." not in file.parts:
                target = site / file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(distribution.locate_file(file), target)
    # The DLL-named _pth also controls Python embedded by VSScript. Ignore host
    # PYTHONPATH/registry and allow only this relocatable private module tree.
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\nDLLs\nLib/site-packages\n../app\nimport site\n", encoding="ascii")
    app = output / "app"
    app.mkdir()
    for name in ("frame_module.py", "bundled_frame_module.py", "native_protocol.py", "frame_session.py",
                 "frame_service.py", "frame_client.py", "frame_wire.py", "dlssnr_backend.py"):
        shutil.copyfile(ROOT / name, app / name)
    upstream = app / "third_party/DLSS5Tool"
    upstream.mkdir(parents=True)
    for name in ("dlss_engine.py", "LICENSE"):
        shutil.copyfile(ROOT / "third_party/DLSS5Tool" / name, upstream / name)
    (output / "native").mkdir()
    shutil.copyfile(host, output / "native/dlssnr_host_v2.dll")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", output / "THIRD_PARTY_NOTICES.md")
    executable = runtime / "python.exe"
    with executable.open("rb") as stream:
        executable_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = {"id": "dev.openplayer.dlssnr.portable", "name": "DLSSNR portable developer module",
                "version": "0.1.0", "entry": "manifest", "contributes": {
                    "capabilities": [{"id": "native", "name": "Native frame processing", "kind": "nativeTool",
                                      "permissions": ["native.process"]}],
                    "nativeModules": [{"id": "enhance", "protocol": "openplayer-native-v1",
                                       "methods": ["runtime.configure", "frames.open", "frames.status", "frames.close"],
                                       "targets": {"windows-x86_64": {"entry": "runtime/python.exe",
                                           "sha256": executable_hash,
                                           "args": ["-I", "-B", "../app/bundled_frame_module.py"]}}}]}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inventory = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                inventory[path.relative_to(output).as_posix()] = {
                    "size": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    report = {"schema": 1, "python": sys.version.split()[0], "numpy": numpy.__version__,
              "nvidiaRuntimeBundled": False, "files": inventory}
    (output / "bundle-inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    files = [path for path in output.rglob("*") if path.is_file()]
    size = sum(path.stat().st_size for path in files)
    if len(files) > 1024 or size > 128 * 1024 * 1024:
        raise ValueError(f"staged module exceeds host package bounds: {len(files)} files, {size} bytes")
    return {"output": str(output), "files": len(files), "bytes": size, "nvidiaRuntimeBundled": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vapoursynth", required=True, type=Path)
    parser.add_argument("--host", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.output.resolve(), args.vapoursynth.resolve(strict=True),
                           args.host.resolve(strict=True)), indent=2))
