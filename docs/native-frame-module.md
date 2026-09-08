# Native frame owner integration

`frame_module.py` implements the existing `openplayer-native-v1` protocol and
owns a persistent frame service. **It is developer source, not an installable
plugin or a public live-video attachment.** The normal player still cannot attach
this processor. No proprietary runtime is bundled.

## Control the owner

The executable runs with fixed local arguments:

```text
python.exe -u frame_module.py --host .local/build/dlssnr_host_v2.dll --runtime .local/runtime/nvngx_dlssnr.dll --log .local/native-frame.log
```

Resolve these paths before invoking from a different working directory. Use the
same private Python runtime as the earlier probes, with NumPy and a sibling
`pythonw.exe` on Windows. The module selects that sibling through Python's
`multiprocessing.set_executable`; it does not change the host's environment or
launch policy. Local integration with the host's no-console job timed out before
the worker function with `python.exe`, but passed with `pythonw.exe`. This is a
tested compatibility choice, not a claim about all Python/Windows installations.

After the standard `host.initialize` handshake, declare these three methods in
the native module manifest when packaging becomes available:

| Method | Parameters | Result |
| --- | --- | --- |
| `frames.open` | null or `{ "settings": { "intensity": 0.5 } }` | Experimental frame protocol id and a private loopback endpoint |
| `frames.status` | null or empty object | Owner `running`, `workerPid`, processing `error`, lease `generation` |
| `frames.close` | null or empty object | null after owner/worker cleanup |

`frames.open` starts only the listener; engine initialization is lazy on the first
frame lease and is not a long-running SDK control request. Repeating open reuses
the owner if settings match; close first to change settings. Settings use the
existing backend validator. No method accepts an executable, factory, library
path, environment override or frame pixels.

The endpoint is for the trusted native adapter, **not for the JavaScript worker**.
It is not a new host SDK API. Do not log or persist its random token. Native RPC
stays newline-delimited JSON with a 64 KiB message bound, increasing unsigned
request ids and matching response ids. Malformed input or a method error ends
the protocol session; EOF also closes the owner. Processor diagnostics do not
share the protocol stdout channel.

The existing SDK's `native.start/call/stop` and `native.process` permission are
enough for this control plane. No DLSSNR/AI-specific permission or host command
was added. Production start still requires the host-owned launch confirmation;
native software remains fully trusted, not sandboxed.

## Reproduce real lifecycle verification

Prepare the native DLL/runtime paths above and the sibling RustPlayer checkout.
Run from `RustPlayer`, replacing the Python path with the private runtime you
actually prepared (the example assumes the prototype's `.venv`):

```powershell
$env:OPENPLAYER_NATIVE_FRAME_ROOT = (Resolve-Path ../openplayer-dlssnr).Path
$env:OPENPLAYER_NATIVE_FRAME_PYTHON = (Resolve-Path ../openplayer-dlssnr/.venv/Scripts/python.exe).Path
rtk proxy cargo test -p openplayer-desktop native_frame_owner_follows_real_plugin_lifecycle -- --ignored --nocapture
```

This opt-in test creates an isolated redb store, installs a fixture manifest and
uses the actual Rust native `Session`, handshake, method dispatch, registry and
Windows Job Object. It sends a real 720p frame through the NGX worker, confirms
the worker is in the job, then calls the actual store's disable, upgrade and
uninstall operations. Each must remove the registry entry, reject further calls
and leave zero active processes in the job.

The package contains a non-executed integrity fixture; the test explicitly
launches the known private Python/module paths and registers that session under
the fixture plugin id. **It does not test a deployable package, the GUI consent
dialog, JavaScript-to-frame attachment, or controls during plugin disable.** The
separate window smoke test covers playback/window behavior. Never install this
lifecycle fixture as a user plugin.

On 2026-09-08, all three real lifecycle cases passed with worker PIDs 64656,
36596 and 59700. The GPU-independent prototype suite passed 34 tests, including
windowless startup, invalid parameters, protocol framing, owner closure with an
active client and exact original-frame fallback. Host regression results were
194 passed / 2 explicitly gated tests ignored; strict workspace Clippy passed.
The final-source rerun also passed all three lifecycle cases (workers 61856,
14440 and 65936). A separate 1080p window regression report,
`.local/planar-sdk-followup-1080p.json`, passed with 101 frames, one engine, no
fallback, warm callback mean/p95 33.78/42.38 ms, visible nonblack presentation,
pause/seek/fullscreen and one Alt+F4 teardown. It remains the launcher-owned
playback harness, not a combined SDK-to-playback attachment test. No associated
owner, worker or window probe process remained after verification.

## Remaining delivery work

- Deploy a private runtime and authenticated package dependency set without
  editing system Python, registry or live process-global mpv configuration.
- Connect the trusted frame adapter to a bounded public host attachment lifecycle;
  keep `native.video.validatePlan` non-executable until then.
- Verify real consent, plugin UI, interruption/recovery and A/V synchronization.
- Validate sustained playback and color handling; current scope is SDR RGBA8,
  up to 1080p, one output per input. No interpolation or super-resolution engine
  has been implemented by this adapter.
