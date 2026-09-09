# Build and test the development plugin

**Requires the current OpenPlayer host checkout, Windows x64 and a compatible
NVIDIA GPU. Published 1.6.3 is insufficient despite sharing the development host's
unchanged version number.** This is experimental 8-bit, limited-range BT.709 SDR
processing up to 1080p, not a production release or a claim of real-time 1080p.

## Build

With the prepared CPython 3.12/NumPy environment and native DLL:

```powershell
rtk proxy .venv/Scripts/python.exe scripts/build-portable-module.py --vapoursynth .local/python/vapoursynth --host .local/build/dlssnr_host_v2.dll --output .local/plugin-ui --plugin-ui --archive .local/DLSSNR_0.2.0.opplugin
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
3. Open **DLSSNR** from the player controls. Choose **List GPUs**. Installation
   grants declared permissions; the current host does not repeat launch prompts.
4. Select the processing GPU explicitly. The options show PCI bus first so
   identically named cards remain distinguishable. No GPU is selected by default.
5. Select the directory containing a trusted `nvngx_dlssnr.dll`, or enter its full
   path. Choose intensity, then enable enhancement. The plugin hashes the DLL
   without loading it first; configuration rechecks that hash before use.
6. **Stop and release** terminates processing and its control process. Closing the
   panel alone keeps enhancement running. Switching media stops enhancement;
   re-enable explicitly for the next item.

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
GPU/runtime changes require stopping enhancement. No inert depth, motion-vector,
DLSS preset or upscaling controls are presented as working NR settings.

`frames.update({settings: patch})` returns `applied`, `revision`, and effective
settings after the worker acknowledges the update. Invalid controls return an
`applied: false` result rather than terminating a healthy native session. Changes
are serialized with frame processing, reset temporal history on the next frame,
and retain the worker, GPU and shared buffers. Rebuilds inherit updated settings.
The panel coalesces input over 150 ms and does not stop/reattach for adjustments.
Paused playback applies settings to the next processed frame, not a cached frame.

Evidence: 45 Python tests; `.local/plugin-live-ui-check/report.json` exercises live
controls through the actual generated bridge with simulated replies;
`.local/gpu1-live-update.json` records all five update groups changing actual NR
pixels on the same GPU-1 worker (PID 81228), followed by lease reuse and cleanup.
