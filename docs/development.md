# Development and testing

For installation, see the [README](../README.md). Commands below run from the
repository root and do not require the maintainer's RTK command wrapper.

## Unit tests

Use Python 3.11+ x64 (3.12 was tested) in a project virtual environment:

```powershell
git submodule update --init --recursive
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Unit tests do not require NVIDIA libraries, a GPU, or FFmpeg. They cover worker
failure and timeout, settings updates, temporal resets, frame validation and
process/shared-memory cleanup.

## Native build and inference

Prerequisites: Visual Studio C++ x64 tools, Windows SDK, a compatible NVIDIA GPU
and driver, and NVIDIA libraries you are authorized to use. FFmpeg must be on PATH
for video input/output. Read the [third-party notices](../THIRD_PARTY_NOTICES.md)
before building or distributing.

Obtain the NVIDIA DLSS SDK separately. Supply its local directory to
`scripts/build-native.ps1` with `-DlssSdk`. The runtime DLL is selected separately
with the benchmark's `--runtime` argument; it is not downloaded or patched.

With the native backend built and the runtime at `.local/runtime/nvngx_dlssnr.dll`:

```powershell
.venv/Scripts/python.exe benchmark.py --image third_party/DLSS5Tool/img/01.png --runtime .local/runtime/nvngx_dlssnr.dll --width 1280 --height 720 --frames 24 --output .local/results/my-still-test
```

For a local short SDR video at `.local/motion-source.mp4`:

```powershell
.venv/Scripts/python.exe benchmark.py --video .local/motion-source.mp4 --runtime .local/runtime/nvngx_dlssnr.dll --width 1920 --height 1080 --frames 48 --fps 24 --encode --output .local/results/my-video-test
```

Output directories must be new. Comparison images and videos show original on
the left and processed on the right. The comparison MP4 is silent, not a media
export feature. Timing in `report.json` excludes decoding, encoding, audio sync
and player presentation; pixel differences establish execution, not quality.

## Architecture and integration

The current path uses CPU frame buffers with GPU upload/readback, not zero-copy
GPU textures. It is synchronous, single-stage and limited to one in-flight frame.
The NGX engine runs in a separate worker; the trusted video adapter still loads
inside OpenPlayer. Process isolation is not a security sandbox.

- [Plugin packaging, controls and host validation](plugin-ui.md)
- [Portable private runtime deployment](portable-runtime.md)
- [GPU selection](gpu-selection.md)
- [Production attachment lifecycle validation](host-attachment.md)
- [Native module control protocol](native-frame-module.md)
- [Persistent frame ownership](persistent-frame-owner.md)
- [Playback probe and reproduction commands](native-playback-probe.md)
- [Historical prototype measurements](2026-09-08-validation.md)

Historical measurements describe their tested revision and scenario, not general
performance guarantees for the current release.
