# Native playback verification

This is the baseline per-filter-worker test. The subsequent
[persistent-owner step](persistent-frame-owner.md) adds measured engine reuse
across seeks without changing the normal player or publishing an SDK attachment.

## Result and boundary

Real DLSSNR-processed frames were returned to OpenPlayer's existing libmpv video
output on Windows. The native two-window shell remains intact. This is an
**opt-in developer test, not an installable plugin or a public SDK attachment**.
Published OpenPlayer 1.6.3 does not include the new native framework or this test.

Before this step, the framework was committed locally in the host as `ee157b0`
and in `openplayer-plugins` as `ffbe061`. No push, version bump or installer was
made. The prototype remains in its independent repository.

The earlier Python/ctypes teardown hang did not reproduce in the native C++
probe or OpenPlayer smoke executable. The original hang's cause is unresolved;
the native runs, not speculation about Python, are the evidence for proceeding.

## Tested path

```text
libmpv decode -> VapourSynth YUV/RGB conversion -> CPU RGBA shared memory
  -> disposable D3D12/NGX worker -> CPU RGB/YUV -> existing mpv gpu-next/D3D11
```

OpenPlayer logs show `d3d11va` decoding and D3D11 presentation. Filtering involves
CPU transfers; it is not decoder-to-inference zero-copy. The `.vpy` adapter is
trusted Python inside the mpv process. Only the native NGX engine runs in the
isolated worker. The JSON SDK control channel does not transport frame pixels.

Host changes are limited to `window-smoke`: an opt-in fixture path, a private
mpv command helper and native window assertions. Neither bootstrap registers
the helper as an IPC command. Normal plugin filter permissions are unchanged.
Smoke WebViews use `about:blank`, so this tests native/backend controls and
overlay visibility, **not React controls, plugin panels or authorization dialogs**.

## Evidence and findings

Same GPU/runtime/SDK provenance as [the offline report](2026-09-08-validation.md).
Input is a silent 24 FPS controlled motion fixture. Other GPU workloads remained
running. These short runs do not establish sustained or isolated performance.

| Run | Sessions | Frames | Fallback | Warm callback mean/p95 |
| --- | ---: | ---: | ---: | ---: |
| 720p, overlay Alt+F4 | 3 | 84 | 0 | 33.50 / 36.51 ms |
| 1080p, overlay close | 3 | 35 | 0 | 68.84 / 72.55 ms |
| 720p, deliberate worker exit | 3 | 81 | 69 | Not a performance sample |

Warm timing excludes each session's first three frames. Callback timing includes
RGB copies, shared memory, inference, readback and diagnostic statistics. It
excludes surrounding YUV conversion, decode and display. First callbacks also
save diagnostic PNGs. Average over *all* callbacks was 41.58 ms at 720p and
108.79 ms at 1080p. These figures must not be presented as end-to-end FPS.

Findings linked to evidence:

- `.local/window-dlssnr-720p-altf4.json`: backend pause held the position; exact seek reached 0.2 seconds; detach/reattach retained the overlay. Native resize, maximized fullscreen and a single Alt+F4 closed both windows and released mpv. All three worker closes reported exit 0.
- `.local/window-dlssnr-720p-altf4.frames/presented.png`: actual mpv video screenshot, 1280x720, RGB mean 142.71 and standard deviation 66.07. Nonblack pixels and changes prove execution, not enhanced quality or temporal/color fidelity.
- `.local/window-dlssnr-1080p.json`: the same window lifecycle passed at 1920x1080, but the callback alone exceeded the 41.67 ms budget for 24 FPS. This CPU-buffer implementation is not ready for realtime 1080p playback on the tested system.
- `.local/window-dlssnr-crash-720p.json`: the worker deliberately exited with code 89 on its fifth frame. Each session processed four frames first, then returned unchanged original RGB frames. Pause/seek, window operations and teardown still passed. The fault is selected only by a dedicated test fixture.
- `.local/native-dlssnr-crash-720p.json`: the standalone native probe also passed stop/reload and `mpv_terminate_destroy` after faults, with 78 original-frame fallbacks among 94 frames.

In this baseline, session startup was approximately 1.1 seconds. Seek rebuilds the
VapourSynth session and its NGX worker, causing a visible initialization delay.
No A/V sync, HDR, 10-bit color, device loss, long playback, interpolation or
upscaling was validated. Conversion is explicitly 8-bit limited-range BT.709;
do not use this fixture to assess arbitrary media color correctness.

The launcher uses a kill-on-close Windows Job Object. Its external timeout kills
only this test process tree. `FrameSession` closes workers/shared memory normally;
events must include matching starts/frames/closes. This containment is **not yet
connected to the host's plugin-native registry or disable/update/uninstall flow**.

## Reproduce

Use Python 3.12 x64 with this repository's requirements, Visual Studio C++ tools,
FFmpeg, the authorized local NGX runtime and the native host built as described
in the [README](../README.md). Keep dependencies and configuration private.

From this repository, install VapourSynth into the ignored dependency directory
and obtain the matching official mpv client header:

```powershell
rtk proxy .venv/Scripts/python.exe -m pip install --target .local/python VapourSynth==79
New-Item -ItemType Directory -Force .local/include/mpv | Out-Null
rtk proxy curl.exe --fail --location https://raw.githubusercontent.com/mpv-player/mpv/v0.41.0/include/mpv/client.h --output .local/include/mpv/client.h
./scripts/build-mpv-probe.ps1
```

The runner calls VapourSynth's configuration helper in a child process with
private `APPDATA`, `PYTHONPATH` and `VSSCRIPT_PATH`. It does not register VSScript
globally or modify the running player. Use the **same Python executable** to
install dependencies and launch the test. Do not run tests concurrently because
they share the private runtime configuration and compete for GPU resources.

Generate `.local/motion-source.mp4` using the offline report, then:

```powershell
rtk proxy ffmpeg -nostdin -v error -n -i .local/motion-source.mp4 -vf scale=1280:720 -an -c:v libx264 -preset fast -crf 18 .local/motion-720p.mp4
rtk proxy ffmpeg -nostdin -v error -n -stream_loop 7 -i .local/motion-720p.mp4 -c copy .local/motion-720p-long.mp4
rtk proxy .venv/Scripts/python.exe scripts/run-native-probe.py ../RustPlayer/target/release/libmpv-2.dll --video .local/motion-720p-long.mp4 --script tests/dlssnr.vpy --timeout 30 --report .local/my-native-run.json
```

From the host repository, build the opt-in harness:

```powershell
rtk proxy cargo build -p openplayer-desktop --features window-smoke --bin window-smoke
```

Back in this repository, run the real window test. It opens/resizes/fullscreens
an independent test window, then injects Alt+F4 only after verifying that its
overlay owns foreground focus. Do not interact with other windows during it.
The window executable uses the host build's libmpv; the positional library path
selects the DLL only in the standalone native probe mode.

```powershell
rtk proxy .venv/Scripts/python.exe scripts/run-native-probe.py ../RustPlayer/target/release/libmpv-2.dll --video .local/motion-720p-long.mp4 --script tests/dlssnr.vpy --window-smoke ../RustPlayer/target/debug/window-smoke.exe --close-target overlay-alt-f4 --timeout 55 --report .local/my-window-run.json
```

For fault testing, use `--script tests/dlssnr-crash.vpy --expect-fallback` with a
new report path. For 1080p, loop the unscaled source. Existing reports/artifact
directories are never overwritten. Reports include process status and frame
evidence; missing close events, black output, unchanged healthy frames or an
unexpected fallback make the command fail even when the executable exits 0.

Fourteen GPU-independent unit tests covered the baseline transport, watchdog and evidence
validator. Host Rust tests, strict Clippy with `window-smoke`, shell architecture
checks and frontend build were also verified for this change.

## Next production gate

Keep the scope to one bounded frame processor before expanding to more engines.
The remaining work is runtime packaging without global Python/environment
mutation, host-owned consent/lifecycle, avoiding expensive seek reinitialization,
and a realtime transport budget. Then connect an actual plugin UI using existing
SDK components. Do not expose arbitrary `.vpy` paths as a low-risk plugin API or
report `native.video.validatePlan().executable` as true based on this harness.
