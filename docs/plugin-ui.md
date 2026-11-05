# Build and test the development plugin

**Requires OpenPlayer 1.6.4, Windows x64 and a compatible NVIDIA GPU.**
OpenPlayer 1.6.3 is insufficient. This is experimental SDR processing up to 3840x2160,
with optional HDR/Dolby Vision input conversion to SDR. It is not HDR passthrough
or a claim of real-time 4K playback. Update the host as well as the plugin.

## Build

Paused parameter changes use the host's `native.video.refreshPaused` after the
worker acknowledges settings. This re-filters the same position without resuming.
The current host is required; older development hosts lack this API.

With the prepared CPython 3.12/NumPy environment and native DLL:

```powershell
rtk proxy python scripts/build-portable-module.py --vapoursynth .local/python/vapoursynth --host .local/build/dlssnr_host_v2.dll --output .local/plugin-ui --plugin-ui --archive .local/DLSSNR_0.5.0.opplugin
```

Output paths must be new. `--plugin-ui` adds the plugin action, themed side panel,
storage defaults and declared `vapoursynth-rgb-v1` adapter. The archive contains
312 files, approximately 75 MB uncompressed. It excludes the NVIDIA runtime.
The builder checks the package bounds, records hashes and validates archive CRCs.
Validate the staged directory with the sibling official repository's exported
`validatePluginDirectory` before distribution.

## Try it in OpenPlayer

1. Build the current host frontend and desktop executable. A test build can use
   `TAURI_CONFIG` with a separate application identifier to isolate settings.
2. Import the `.opplugin` through Plugins settings and open an eligible video.
3. Open **DLSSNR** from the player controls. GPU detection runs automatically.
   Saved UUIDs are resolved after enumeration, not reported missing while loading.
   Failed detection offers a retry button. Installation
   grants declared permissions; the current host does not repeat launch prompts.
4. Select the processing GPU explicitly. The options show PCI bus first so
   identically named cards remain distinguishable. No GPU is selected by default.
5. Select the directory containing a trusted `nvngx_dlssnr.dll`, or enter its full
   path. Choose intensity, then enable enhancement. The plugin hashes the DLL
   without loading it first; configuration rechecks that hash before use.
6. **Stop and release** terminates processing and its control process. Closing the
   panel alone keeps enhancement running. Switching media stops enhancement;
   re-enable explicitly for the next item.

The compatibility checkbox enables the host's fixed SDR input normalization.
Already-compatible SDR bypasses it. For Profile 5, the host first downloads 10-bit
hardware frames, then libplacebo interprets RPU metadata and produces BT.709 SDR
before NR. Turning the checkbox off restores the SDR-only input requirement.
Conversion keeps the input resolution; a 3840x1606 source remains 3840x1606.
NR GPU selection does not select the independent mpv color-conversion GPU.

GPU UUID, runtime path and all NR settings persist through SDK storage in host redb.
The active device identity is shown separately from the saved selection. A missing
saved GPU fails explicitly; there is no automatic fallback to GPU 0. This choice
does not select mpv's decoding/display or WebView GPU.

Native modules are trusted user-privileged code, not sandboxed. The video runtime
also loads inside OpenPlayer and remains resident until exit. A runtime-inventory
change requires restarting the player. The separate NR worker cannot protect the
player from faults in the embedded adapter itself. A locally computed DLL hash
is not a publisher signature; select only a runtime you are authorized to use.

## Verification and limits

The GPU-1 window runner now calls production attach/status commands, rejects a
false enabled-filter state, and checks processed frames, recovery and job cleanup.
`public-lifecycle-matrix.json` covers six lifecycle cases; `public-media-detach.json`
adds public detach and actual 720p-to-1080p media replacement. These isolated tests
register a test session rather than confirming the GUI dialog.
`public-final-cleanup.json` additionally verifies the final package's cold runtime
load through the public command, duplicate-attach rejection and actual host-cache
script cleanup on stop and app exit.

```powershell
rtk proxy node scripts/verify-plugin-ui.mjs --modules C:/path/to/node_modules --output .local/plugin-ui-check
```

This browser test requires TypeScript in the sibling host and Playwright plus
installed Chrome (`--channel` can choose another installed distribution). It
loads the actual host-generated bridge/styles and checks explicit selection,
settings restore, directory picking, enable/stop, error retention and responsive
layouts at 420x720 and 320x480. Replies are simulated: it does not load a GPU,
install a plugin, bypass native consent or establish actual GUI enhancement.

The user confirmed actual GUI installation and playback on 2026-09-10.
Long-duration audio synchronization, mid-stream
format changes, color fidelity, HDR and sustained performance still need manual
or dedicated tests. The plugin does not expose interpolation or super-resolution.

## Live NR controls

Style (default/natural/cinema), intensity, local tone, local structure, automatic
skin mask and skin structure are exposed. Numeric NR strengths accept 0..5,
matching the pinned engine; skin structure is enabled when the mask is enabled.
GPU, runtime and model preset changes require stopping enhancement. Automatic
selection recognizes the published RTX 30 optimized 0.4.0 runtime by SHA256
and uses Small preset 2; unrecognized runtimes retain preset 1. Presets can
also be selected manually. No inert depth, motion-vector or upscaling controls
are presented as working NR settings.

`frames.update({settings: patch})` returns `applied`, `revision`, and effective
settings after the worker acknowledges the update. Invalid controls return an
`applied: false` result rather than terminating a healthy native session. Changes
are serialized with frame processing, reset temporal history on the next frame,
and retain the worker, GPU and shared buffers. Rebuilds inherit updated settings.
The panel coalesces input over 150 ms and does not stop/reattach for adjustments.
Paused playback requests `native.video.refreshPaused` after settings are applied;
the exact seek re-filters the paused position instead of waiting for playback.

## Playback capacity

Version 0.4.0 defaults to a 15 FPS enhancement cap, saved separately from NR
settings. Choose 10, 15, 20, 24, 30 or source rate before enabling. The host's
typed `frameRateLimit` drops frames before expensive conversion/NR and maintains
audio speed and media timing. Every delivered frame still undergoes NR; this
does not alternate enhanced frames with unprocessed source frames. It trades
motion smoothness for a sustainable workload, not 60 FPS inference on a 19 FPS GPU.
Choose a cap below sustained end-to-end processing capacity. Source rate can
still desynchronize when processing cannot keep up; 4K may need a lower rate
than the current panel offers. No automatic GPU performance selection is claimed.

Evidence for the user's 1080p59.94 food video on GPU 1:
`.local/realtime-1080p60-final.json` records 303 NR frames over 20.21 seconds
with 20.20 seconds of media progression and peak mpv A/V error below 1ms.
`.local/paused-1080p60-final.json` verifies changed paused screenshots, stable
position and worker reuse with the same 15 FPS cap. UI tests include delayed GPU
enumeration, failed-detection retry without losing the saved UUID, themed select
popups/checkboxes and measured host chrome/transport avoidance across window sizes.

Rejected experiments: inference-only budgeting still accumulated 3.1 seconds of
lag; local wall-clock bypass restored sync by starving enhancement. Neither is
included. The shipped path uses the existing FFmpeg rate filter instead.

Delivery: `.local/delivery-0.4.0/DLSSNR_0.4.0.opplugin` and the sibling
`OpenPlayerNRTest/openplayer-desktop.exe` test host. Exit the old player before
importing the update and restart after import, because private video runtimes
remain pinned until process exit. The test host is a standalone build, not NSIS.
The final package also passes `.local/dv-rate-final.json`: the user's 3840x1606
Profile-5 file at 30 seconds with a 10 FPS cap, SDR conversion and full stop/cleanup.
That check does not establish sustained 4K synchronization.

Evidence: 45 Python tests; `.local/plugin-live-ui-check/report.json` exercises live
controls through the actual generated bridge with simulated replies;
`.local/gpu1-live-update.json` records all five update groups changing actual NR
pixels on the same GPU-1 worker (PID 81228), followed by lease reuse and cleanup.

## Dolby Vision evidence and limits

The user's episode is HEVC 3840x1606, full-range 10-bit, Dolby Vision Profile 5
with RPU and no HDR10-compatible base layer. It must not be interpreted as ordinary
BT.2020/PQ YUV. The host uses FFmpeg's documented
[libplacebo DV conversion](https://ffmpeg.org/ffmpeg-filters.html#libplacebo),
which applies and strips RPU metadata before the SDR processor sees pixels.

`.local/dv-profile5-batched.json` verifies that exact source through the public
attachment command. The test seeks to 180 seconds and waits for seeking to finish,
SDR output metadata and time advancement. The scene screenshot has the original
3840x1606 dimensions; stopping removes all conversion/NR labels and restores
original Dolby Vision playback without changing user configuration.

Earlier `.local/dv-profile5-scene.json` captured too early during a multi-second
seek and showed the old intro frame. The stronger readiness check replaced fixed
sleeps; that earlier nonblank-image check was not proof of correct seek output.
4K CPU transport, conversion and inference remain too costly to promise 25 FPS;
the test observed A/V lag. Formal colorimetric validation and long playback tests
remain outstanding. No forced downscaling or fake HDR-preservation flag is used.

Final 0.3.0 package evidence: `sdr-1080-final-package.json` passes the unchanged
SDR path; `dv-profile5-final-package.json` passes uninstall but fails its separate
180-second seek/exit run because seeking exceeds the eight-second readiness gate.
`dv-profile5-final-exit.json` then independently passes active-enhancement exit
with the ordinary near-start seek. Do not summarize this as all 4K timing tests
passing. The Windows test host is `.local/openplayer-nr-test-0.3.0/` and the plugin
is `.local/DLSSNR_0.3.0.opplugin` (SHA256
`184331d50b893ca3827a673bdc0dae455813214b6f985c38fe0658b143f0b299`).
The host has 207 passing Rust tests (three explicitly gated tests ignored), the
plugin has 46 passing Python tests, and the SDK has 48 passing tests plus type
checks. The final UI bridge test is `.local/plugin-0.3.0-ui-check/report.json`.
