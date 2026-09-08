# DLSSNR validation - 2026-09-08

## Result and boundary

Real DLSSNR inference succeeds outside OpenPlayer using the existing local
runtime. Parameter changes affect pixels; worker teardown succeeds. An
installable OpenPlayer plugin and live video reinsertion are **not implemented**.

No player architecture change, new SDK permission or new installer was made.
The existing player changes were first committed as `0c3a548` on local `main`.
Neither repository was published or pushed during this experiment.

## Environment and provenance

| Item | Value |
| --- | --- |
| GPU | Two RTX 3080 Ti devices, 12 GiB each; backend uses default D3D12 adapter, not multi-GPU processing |
| Driver | 616.64 |
| Python | 3.12.14 x64 |
| NumPy | 2.3.5 |
| Native build | MSVC /O2 /MT, DLSS5Tool native_host_v2, unchanged upstream |
| Upstream commit | 78ee043e2800317b8140859bec85726b15189696 |
| Runtime source | Local copy of the existing Magpie runtime; original installation untouched |
| Runtime SHA256 | e67dee209320cdafe0e93e45675d7aa34323a53acc57a72b2e40a181581c989a |
| Native host SHA256 | 3e8d802e94a5a2b3c94af40ef29a48de6aeadc034a6c7ddc05b193643ea5ac56 |

Other GPU workloads were present. Adapter selection, isolated GPU performance,
peak VRAM and dual-GPU compatibility were not measured. No unrelated process was
stopped, and no global environment or driver setting was changed.

## Measured frame processing

These are short CPU-buffer-to-CPU-buffer measurements including shared-memory
IPC, D3D12 upload, inference and readback. They exclude FFmpeg decode/encode,
player presentation and audio synchronization. Mean/p95 exclude the first three
frames but include the mid-sequence reset. Processing FPS is 1000 / mean latency.

| Input | Frames | Mean ms | p95 ms | Processing FPS | Startup ms | Close ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 720p repeated still | 12 | 21.06 | 22.00 | 47.48 | 2707.79 | 128.06 |
| 720p moving test clip | 48 | 20.01 | 28.88 | 49.97 | 1232.79 | 139.32 |
| 1080p moving test clip | 48 | 35.92 | 44.09 | 27.84 | 1353.14 | 138.89 |

All three runs returned changed, nonblack output with zero fallback frames and
worker exit code 0. Updating intensity from 1.0 to 0.25 also changed output.
These pixel checks do not establish artistic quality, temporal correctness,
absence of hallucinated detail, or color accuracy.

The 1080p p95 already exceeds the 41.67 ms budget for 24 FPS before presentation
overhead. Stable realtime playback is not demonstrated. The tests are only two
seconds long, use generated motion from one upstream sample, and include no
audio, HDR, hardware-decoder integration, window resize or long-duration stress.

## Inspect the outputs

All nine unit tests pass. The normal filter parser probe exits cleanly, and an
intentionally shortened 50 ms deadline confirms the outer watchdog reports a
timeout rather than success. No prototype Python or FFmpeg process remains after
verification.

Local artifacts, deliberately not committed:

- `.local/results/motion-1080p/comparison.mp4`: 3840x1080 H.264, 24 FPS, 48 frames, two seconds, original left / processed right.
- `.local/results/motion-720p/comparison.mp4`: corresponding 720p comparison.
- Each run includes `comparison.png`, `input.png`, `output.png`, `updated.png`, `native.log` and `report.json`.
- `.local/motion-source.mp4`: 1920x1080 SDR input; 48 distinct decoded pixel hashes.

The 1080p comparison PNG was visually inspected; both sides contain the expected
subject and composition. FFprobe confirmed the comparison MP4's dimensions,
frame count, rate and duration. This was not an in-player GUI test.

Generate the controlled input used here, from the repository root:

```powershell
rtk proxy ffmpeg -nostdin -v error -n -loop 1 -i third_party/DLSS5Tool/img/01.png -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.001,1.1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=24" -frames:v 48 -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p .local/motion-source.mp4
```

## libmpv filter integration probe

The existing `target/release/libmpv-2.dll` reports
`mpv v0.41.0-773-g2bd9c3229`. Public client API commands accepted both `hflip` and
`vapoursynth`, and rejected a nonexistent filter with error -12. Thus this build
has the generic VapourSynth filter entry; it is not exposed by the current safe
OpenPlayer plugin filter allowlist.

The first playback probe failed because VSScript was missing. Installing
VapourSynth R79 under this repository's `.local/python` and generating its config
under `.local/vs-config` allowed `video_in.set_output()` to decode and play the
test clip into `vo=null`. No DLSSNR was attached in this probe.

The Python/ctypes probe then hung during `mpv_terminate_destroy` after playback
had reached EOF. Only that verified probe process was terminated. The underlying
reason is unresolved; embedding VSScript into an already-running Python host is
not identical to the real Rust player environment. Do not infer a player bug or
claim lifecycle-safe filter integration from this probe.

`scripts/probe-mpv.py` now runs its native calls in a bounded child process and
reports timeout as exit code 124. Optional reproduction, in a disposable shell:

```powershell
rtk proxy .venv/Scripts/python.exe -m pip install --target .local/python VapourSynth==79
$env:APPDATA = Join-Path (Get-Location) '.local/vs-config'
$env:VSSCRIPT_PATH = (Resolve-Path .local/python/vapoursynth/vsscript.dll).Path
rtk proxy .venv/Scripts/python.exe -c "import sys; sys.path.insert(0, r'.local/python'); from vapoursynth._utils import vapoursynth_config; vapoursynth_config()"
rtk proxy .venv/Scripts/python.exe scripts/probe-mpv.py ../RustPlayer/target/release/libmpv-2.dll --video .local/motion-source.mp4 --script tests/passthrough.vpy --python-deps .local/python --report .local/mpv-probe.json
```

Do not set APPDATA or VSSCRIPT_PATH globally, or point the running OpenPlayer
installation at this experimental runtime.

## Next gate, not an expansion roadmap

The independent native processing module is viable for more testing. It is not
yet a reason to add a large plugin subsystem to the player. Before a host adapter,
establish clean startup/seek/stop/resize/unload in a native mpv test process,
representative realtime performance, and a trusted-native-extension boundary.
Only then decide whether the minimal generic integration is small enough.

The UI, presets and storage can reuse existing SDK primitives. Frame transport
and native lifecycle are the missing capabilities. A standalone repository does
not remove these costs, and a source-code license does not resolve proprietary
runtime redistribution.
