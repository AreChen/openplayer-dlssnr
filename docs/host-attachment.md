# Validate session-owned video attachment

**Developer harness for the host's native video lifecycle.** The current host
also exposes permissioned attachment and a [development plugin UI](plugin-ui.md).
The harness does not exercise GUI launch consent.
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

Report/artifact paths must be new. `--scenario stop|disable|upgrade|uninstall|crash|app-exit|detach|media-change`
narrows the matrix. These real windows with inert WebViews change focus, resize,
enter fullscreen and inject Alt+F4 after verifying focus and rejecting held
modifiers. Run only when focus changes are acceptable; the user explicitly
authorized them for this verification. GPU selection controls NR, not
mpv/WebView's display device.
For `detach` or `media-change`, provide a `--plugin-ui` bundle with a declared
video adapter. `media-change` also requires `--replacement-video`.

Acceptance requires processed/changed frames, same-worker reuse, nonblack
processed/recovered screenshots, native close markers, zero job processes,
generated-script cleanup and unchanged source/user configuration. A disabled mpv
filter fails the runner even if original playback continued. Timeouts retain
partial stdout/stderr for diagnosis.
Add `--realtime --require-smooth` to measure playback for 20 seconds and fail
when video output drops exceed 5% of processed frames, with a minimum allowance
of 10 frames. Use a display whose refresh rate meets or exceeds the tested frame
rate; intentional display-rate conversion otherwise affects the drop count.
This short sample is not a guarantee of sustained performance.
The `app-exit` case retains the active attachment until normal application
shutdown, then checks session/job/script cleanup. Other cases also require a
recovered screenshot. Every case requires the native event loop to return before
the supervisor accepts process completion.

## Evidence and remaining work

- Public-command follow-up: `public-lifecycle-matrix.json` passed six lifecycle
  cases with enabled-filter status and real GPU-1 output. `public-media-detach.json`
  passed formal detach and actual 720p-to-1080p replacement. Normal GUI consent
  remains a separate manual step; these runs register an internal test session.

- 2026-09-09 `.local/host-attachment-lifecycle.json`: `stop` passed with processed
  frames, reused worker, pause/seek, detach/reattach, maximized fullscreen,
  unrelated-filter preservation, recovery and single Alt+F4.
- The following historical `disable` run produced processed/recovered screenshots
  but timed out. Its cause remains unresolved; the old runner did not retain
  partial timeout output. It did not recur in the isolated repeat or subsequent
  full matrices. This is not evidence of a diagnosed timeout fix.
- 2026-09-09 `.local/attachment-matrix-final.json`: all six cases passed on GPU 1
  (`GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b`), including disable, upgrade,
  uninstall, worker crash and active-enhancement app exit. Each finished in
  16-19 seconds with unchanged source/user configuration. See
  [GPU selection](gpu-selection.md) for device identity checks.
- Host shutdown now executes session-owned attachment cleanup instead of only
  stopping jobs and clearing the registry. The harness uses `run_return` to
  verify loop completion and clean its temporary WebView directory; normal
  player window behavior is unchanged.
- Unit tests cover failed rollback, retained cleanup, terminal stop, callback
  keywords, frame properties and reset handling. The protocol integration test
  checks that cleanup failure retains registry tracking and permits retry, and
  that application shutdown executes attachment cleanup.

Remaining gates: mid-stream format changes, full GUI launch consent and sustained
A/V synchronization. Production authorization is implemented; browser tests use
the real view bridge/styles but simulate privileged replies.
This batch does not establish HDR, interpolation, super-resolution or sustained
playback performance.
