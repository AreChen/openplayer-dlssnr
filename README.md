# OpenPlayer DLSSNR prototype

Independent, Windows-only experiment for processing SDR video frames with
DLSSNR. **This is not an installable `.opplugin`, and it does not enhance live
OpenPlayer playback yet.** No OpenPlayer source, window hierarchy, SDK permission,
registry setting, or installed player binary is changed by this project.

## What works

- Reuses the native D3D12 backend from [DLSS5Tool](https://github.com/banbanzhige/DLSS5Tool), pinned as a Git submodule.
- A generic `FrameSession` sends RGBA8 frames through shared memory to a disposable worker. The parent process never loads NGX.
- Frames retain submission order; the first frame, explicit discontinuities, and parameter updates reset temporal history.
- Evaluation failure, worker crash, or timeout disables the worker and passes subsequent original frames through. Startup failures raise explicitly; the caller must retain its original video path.
- A CLI accepts an image or short SDR video and generates metrics, PNG comparisons, and an optional silent side-by-side MP4.

This prototype uses CPU frame buffers with GPU upload/readback, **not zero-copy
GPU textures**. It is single-caller, synchronous, limited to 1920x1080 and one
in-flight frame. Process isolation limits native crashes; it is not a security
sandbox for untrusted native code. All processor factories are trusted local code.

## Run the tests

Use Python 3.11+ x64 (3.12 was tested). Install only into a project virtual
environment, not OpenPlayer or a shared system Python installation:

```powershell
rtk proxy git submodule update --init --recursive
rtk proxy py -3.13 -m venv .venv
rtk proxy .venv/Scripts/python.exe -m pip install -r requirements.txt
rtk proxy .venv/Scripts/python.exe -m unittest discover -s tests -v
```

Unit tests do not require NVIDIA libraries, a GPU, or FFmpeg. They cover process
failure/timeout, explicit initialization failure, settings updates, temporal
reset, buffer validation, strict errors, and process/shared-memory cleanup.

## Build and run real inference

Prerequisites: Visual Studio C++ x64 tools, Windows SDK, a compatible NVIDIA GPU
and driver, FFmpeg on PATH for video input/output, and NVIDIA libraries you are
authorized to use. Review [third-party boundaries](THIRD_PARTY_NOTICES.md) before
building or distributing. This repository does not supply the proprietary runtime.

Obtain the NVIDIA DLSS SDK separately, then pass its directory to the build script:

```powershell
./scripts/build-native.ps1 -DlssSdk ../RustPlayer/target/investigation/NVIDIA-DLSS
rtk proxy .venv/Scripts/python.exe benchmark.py --image third_party/DLSS5Tool/img/01.png --runtime .local/runtime/nvngx_dlssnr.dll --width 1280 --height 720 --frames 24 --output .local/results/my-still-test
```

The SDK path above is the local checkout used in this workspace; replace it with
your own SDK location on another machine. `--runtime` may point to any explicitly
selected, authorized local runtime file; it is not auto-downloaded or patched.

For a short SDR video:

```powershell
rtk proxy .venv/Scripts/python.exe benchmark.py --video .local/motion-source.mp4 --runtime .local/runtime/nvngx_dlssnr.dll --width 1920 --height 1080 --frames 48 --fps 24 --encode --output .local/results/my-video-test
```

The output directory must not already exist. `comparison.mp4` and
`comparison.png` put **original on the left, processed on the right**.
`updated.png` tests a live intensity change to 0.25. The MP4 has no audio;
it is an inspection artifact, not a full media export feature.

`report.json` includes per-frame timing, warm-up-excluded mean/p95, pixel change,
runtime/host hashes, reset indices, fallback count, and worker exit status.
Timing excludes decode, encode, audio synchronization, and player presentation.
Nonzero output and pixel differences establish execution, not improved quality.

## Scope and next gate

See [the measured results and integration gate](docs/2026-09-08-validation.md).

Current OpenPlayer SDK UI, settings, and storage can be reused eventually, but its
safe JS filter API does not allow native processors. No fictitious SDK method or
nonfunctional plugin manifest is shipped here.

The shipped libmpv recognizes `vapoursynth`; a private-runtime passthrough probe
played video but hung during teardown in the Python/ctypes test environment.
The root cause is not established, and this does **not** prove OpenPlayer itself
would hang. This path is not approved for host integration on that evidence.

Do not add window capture/reparenting, a replacement renderer, arbitrary Python
execution permissions, or large native plugin infrastructure to make this test
look integrated. First establish a bounded, lifecycle-safe native filter adapter
that preserves existing decoding/presentation and the controls overlay. If it
requires substantial host complexity, keep this an independent/offline experiment.
