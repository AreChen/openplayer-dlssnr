# Validate session-owned video attachment

**Developer harness only. No public attach API or plugin UI is exposed yet.**
The host associates one filter cleanup lease with its registered native session.
Mount/detach/stop are serialized; failed mounts roll back, failed cleanup stays
tracked for retry, and stopped sessions cannot reattach.

The fixture imports a real portable package into an isolated store, resolves its
installed executable, copies its runtime into the host cache, and starts its
native-v1 frame owner. A generated private `.vpy` connects to that owner without
changing process environment or accepting a public script path. A process-wide
claim prevents overlapping native attachments; unique labels preserve unrelated
filters. Package cleanup does not need to unload cached embedded Python.

Stop kills the processor job before removing the filter so outstanding callbacks
can fall back. Registry records are removed only after cleanup succeeds. Idle
parent exit schedules cleanup on a blocking task, not the async executor. This
is not a sandbox or a guarantee against in-process mpv/Python deadlocks.

## Run the window matrix

Build the sibling host's `window-smoke` binary and a fresh portable bundle, then:

```powershell
rtk proxy .venv/Scripts/python.exe scripts/verify-host-attachment.py .local/portable-gpu-selection --window-smoke ../RustPlayer/target/debug/window-smoke.exe --video .local/motion-720p-long.mp4 --runtime .local/runtime/nvngx_dlssnr.dll --gpu GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b --report .local/attachment-check.json
```

Report/artifact paths must be new. `--scenario stop|disable|upgrade|uninstall|crash`
narrows the matrix. These real windows with inert WebViews change focus, resize,
enter fullscreen and inject Alt+F4 after verifying focus. Do not run during
foreground gaming. GPU selection controls NR, not mpv/WebView's display device.

Acceptance requires processed/changed frames, same-worker reuse, nonblack
processed/recovered screenshots, native close markers, zero job processes,
generated-script cleanup and unchanged source/user configuration. A disabled mpv
filter fails the runner even if original playback continued. Timeouts retain
partial stdout/stderr for diagnosis.

## Evidence and remaining work

- 2026-09-09 `.local/host-attachment-lifecycle.json`: `stop` passed with processed
  frames, reused worker, pause/seek, detach/reattach, maximized fullscreen,
  unrelated-filter preservation, recovery and single Alt+F4.
- The following `disable` run produced processed/recovered screenshots but the
  supervisor timed out. Completion is **not verified**; the exact cause remains
  unresolved. The old runner did not retain partial timeout output.
- Foreground runs stopped when the user started gaming and requested GPU 1.
  Explicit-GPU headless processing and actual package disable/replacement/
  uninstall passed separately; see [GPU selection](gpu-selection.md).
- Unit tests cover failed rollback, retained cleanup, terminal stop, callback
  keywords, frame properties and reset handling. The protocol integration test
  checks that cleanup failure retains registry tracking and permits retry.

Remaining gates: the complete post-selection window matrix, active-window app-exit
ownership, media/format changes, real React controls/consent and A/V synchronization.
This batch does not establish HDR, interpolation, super-resolution or sustained
playback performance.
