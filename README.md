# OpenPlayer DLSSNR prototype

Independent, Windows-only experiment for processing SDR video frames with
DLSSNR. **An installable development plugin is now available; published OpenPlayer
1.6.3 cannot run it.** The current host checkout exposes permissioned single-stage
video attachment. See [build and test the plugin](docs/plugin-ui.md) for the GPU
selector, runtime selection and enhancement controls. No window capture or
replacement renderer is used. Installation grants declared permissions without
repeat launch prompts. The user confirmed GUI installation and playback.

## What works

- Reuses the native D3D12 backend from [DLSS5Tool](https://github.com/banbanzhige/DLSS5Tool), pinned as a Git submodule.
- A generic `FrameSession` sends RGBA8 frames through shared memory to a disposable worker. The parent process never loads NGX.
- Frames retain submission order; the first frame, explicit discontinuities, and parameter updates reset temporal history.
- Evaluation failure, worker crash, or timeout disables the worker and passes subsequent original frames through. Startup failures raise explicitly; the caller must retain its original video path.
- A CLI accepts an image or short SDR video and generates metrics, PNG comparisons, and an optional silent side-by-side MP4.
- A native libmpv probe and a test-only OpenPlayer adapter exercise live frame reinsertion, pause, seek, filter detach/reattach, resize, fullscreen and close without hiding the overlay.
- An opt-in owner-scoped frame service reuses one engine across filter rebuilds, resets temporal history for every new lease, and releases it when the owner closes.
- A native-v1 frame owner module uses the existing SDK control protocol; a separate opt-in host test verifies real NGX worker cleanup on plugin disable, upgrade and uninstall.
- A relocatable private runtime can be staged and verified through real host package import, without global Python or VapourSynth configuration. See [portable runtime deployment](docs/portable-runtime.md).
- The Windows host loads a verified private copy, reuses one resident runtime, rejects conflicts and reclaims stale copies on the next run. `scripts/verify-host-runtime.py` checks this in two real window runs.
- The native module can enumerate GPUs and select a stable GPU UUID without falling back to another card. See [GPU selection](docs/gpu-selection.md) for the tested headless path.
- Production attachment commands passed eight GPU-1 window scenarios: stop/reconnect, disable, upgrade, uninstall, worker crash, app exit, public detach and media replacement. See [attachment validation](docs/host-attachment.md). The isolated harness registers test sessions instead of clicking consent.
- The development plugin view uses host theme components and redb storage. GPU choice is explicit and persists UUID, never a default display ordinal. Browser tests exercise the real generated view bridge with simulated host replies.

This prototype uses CPU frame buffers with GPU upload/readback, **not zero-copy
GPU textures**. It is single-caller, synchronous, limited to 3840x2160 and one
in-flight frame. Process isolation limits native crashes; it is not a security
sandbox for untrusted native code. All processor factories are trusted local code.

Version 0.3.0 adds live style/intensity/local-tone/structure/skin-mask controls.
HDR/Dolby Vision compatibility uses the host's libplacebo conversion **to SDR**,
preserving resolution but not HDR output. Native-resolution 4K is expensive:
multi-second seeks and A/V lag were observed; real-time 4K is not established.
See [plugin operation and evidence](docs/plugin-ui.md).

Version 0.4.0 adds paused-frame preview, automatic saved-GPU detection and a
15 FPS default processing cap (selectable before enabling). The user's 1080p59.94
video passed a 20-second GPU-1 run with 303 enhanced frames and no accumulating
A/V error. This reduces output motion cadence, not audio speed; it does not make
19 FPS hardware process 60 enhanced frames per second. Shared host controls and
side-panel spacing now follow the player chrome and transport bounds.

## Run the tests

Use Python 3.11+ x64 (3.12 was tested). Install only into a project virtual
environment, not OpenPlayer or a shared system Python installation:

```powershell
rtk proxy git submodule update --init --recursive
rtk proxy py -3.12 -m venv .venv
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

## Test the playback adapter

See [native playback verification](docs/native-playback-probe.md) for prerequisites,
reproduction commands, measured limits, and the difference between a smoke harness
and an installable plugin. The original 1080p CPU-buffer baseline was too slow
for 24 FPS. The opt-in planar path reduced warm callbacks to about 34.4 ms, but
does not establish sustained decode/presentation throughput or A/V sync.

[Persistent frame ownership](docs/persistent-frame-owner.md) adds `--persistent`
to the same probe. Real 720p window tests reused one worker through seek and
detach/reattach; reconnect took about 1-11 ms instead of reinitializing the engine.
This measures the connection, not complete seek-to-display latency.

## Scope and next gate

See [the measured results and integration gate](docs/2026-09-08-validation.md).

Current OpenPlayer SDK UI, settings, and storage can be reused eventually, but its
safe JS filter API does not allow native processors. No fictitious SDK method or
nonfunctional plugin manifest is shipped here.

The initial Python/ctypes teardown hang was not reproduced in the native C++
probe or the real OpenPlayer window harness. Its original root cause remains
unresolved. These tests use a private VapourSynth/Python runtime, and execute the
trusted adapter in the player process; only the NGX engine is isolated in a worker.

Do not add window capture/reparenting, a replacement renderer, arbitrary Python
execution permissions, or large native plugin infrastructure to make this test
look integrated. Before a public release, validate GUI consent, color handling,
mid-stream format changes and sustained A/V performance. The experimental
owner resolves engine reinitialization on same-format seeks. Its
[native control module](docs/native-frame-module.md) now has real SDK registry
cleanup coverage, and the development UI now composes existing SDK primitives
with permissioned attachment. This remains an experimental single-stage CPU-copy
path, not an interpolation/upscaling framework.
