# Deploy the private runtime

The native module can be staged as a relocatable directory and imported by
the development host. The default build is a headless developer module;
`--plugin-ui` now adds the [installable development plugin](plugin-ui.md).
Published OpenPlayer 1.6.3 does not support this extension. No public release is
produced here; historical verification below predates the UI integration.

## Build and verify

Prepare Windows x64 CPython 3.12 with NumPy, the VapourSynth R79 wheel directory
and the native host DLL as described in [native playback verification](native-playback-probe.md).
From this repository, using that prepared Python interpreter:

```powershell
rtk proxy .venv/Scripts/python.exe scripts/build-portable-module.py --vapoursynth .local/python/vapoursynth --host .local/build/dlssnr_host_v2.dll --output .local/portable-module
./scripts/build-mpv-probe.ps1
rtk proxy .venv/Scripts/python.exe scripts/verify-portable-module.py .local/portable-module --mpv ../RustPlayer/target/release/libmpv-2.dll --video .local/motion-source.mp4 --report .local/portable-check.json
```

Output paths must not already exist. The builder copies an explicit minimal
Python/NumPy/VapourSynth tree, upstream engine source/license and the native host,
creates the native manifest and records every payload file's SHA256/size. It
rejects bundles above the existing 128 MiB / 1024-file package bounds. It does
not download dependencies or mutate Python installations. The inventory detects
changes relative to that build; it is not a publisher signature, and the current
host verifies declared executables rather than this entire dependency inventory.

The Windows layout is `runtime/python.exe` plus
`runtime/Lib/site-packages/vapoursynth/vsscript.dll`. VSScript R79 first checks
that relative layout before consulting user configuration. Python's DLL-named
`python312._pth` restricts module search to relative private paths and ignores
host environment/registry settings. A private site bootstrap disables bytecode
writes, including when mpv embeds Python. See the
[VSScript source](https://raw.githubusercontent.com/vapoursynth/vapoursynth/R79/src/vsscript/vsscript.cpp)
and [Python path documentation](https://docs.python.org/3.12/using/windows.html#finding-modules).

The verifier copies the directory to a path containing spaces and Unicode,
checks all payload hashes, injects deliberately invalid Python environment paths,
and removes `VSSCRIPT_PATH` only from its test-child environment. The native probe
preloads the explicit VSScript DLL without changing DLL search paths, then mpv
uses that loaded module. It verifies script rebuilds, seek, stop/reload and
`DESTROY_COMPLETE`, unchanged user configuration and unchanged bundle hashes.
This is a pass-through transport check, not an enhancement quality benchmark.

## Supply the NVIDIA runtime

The local NVIDIA DLL is 165,840,496 bytes, larger than the entire plugin package
limit. More importantly, redistribution rights are separate from the MIT engine
source. It is never included in the staged directory or automatically downloaded.

The packaged native entry point adds the module method `runtime.configure`,
accepting an explicit absolute `nvngx_dlssnr.dll` path and its expected SHA256.
It checks the file and hash before configuring the existing frame owner. This
method belongs to the plugin's native protocol, **not a new host SDK API or
permission**. It neither copies nor owns/deletes the supplied library. The
configuration is in-memory; a future UI can persist the user's selection through
existing SDK storage and configure it again after launch. Errors end the native
session under the existing fail-closed protocol.

A caller-supplied hash is not a trust certificate or a lock against subsequent
file replacement. Select only authorized trusted local libraries. No interactive
file selection UI or graphical launch-consent verification is included yet.

## Verify actual package installation

From `RustPlayer`, configure the existing test harness paths and the staged package:

```powershell
$env:OPENPLAYER_NATIVE_FRAME_ROOT = (Resolve-Path ../openplayer-dlssnr).Path
$env:OPENPLAYER_NATIVE_FRAME_PYTHON = (Resolve-Path ../openplayer-dlssnr/.venv/Scripts/python.exe).Path
$env:OPENPLAYER_NATIVE_FRAME_PACKAGE = (Resolve-Path ../openplayer-dlssnr/.local/portable-module).Path
rtk proxy cargo test -p openplayer-desktop portable_frame_module_runs_after_real_package_import -- --ignored --nocapture
```

Place the authorized DLL at the test harness's `.local/runtime/nvngx_dlssnr.dll`.
Unlike the earlier placeholder fixture, this test imports the real 308-file
directory into a temporary store, resolves the installed manifest's executable
and fixed arguments, and launches that installed Python. A real 720p NGX frame
is processed before each disable, replacement import and uninstall. It verifies
job membership/termination, removed registry entries and removal of the installed
runtime directory. The test client script is still supplied by the checkout;
the actual owner and engine use the installed private runtime. GUI consent is
bypassed by this internal test; normal starts retain the existing confirmation.

Testing exposed transient Windows DLL delete denial after native termination.
The host now retries access/sharing/lock denial for up to two seconds on its
existing blocking store path, then reports failure. Dedicated tests cover both
released and persistent file locks; no infinite wait or forced unlock is used.

Evidence on 2026-09-08: `.local/portable-module-v2` contains 308 files totaling
74,900,909 bytes (about 71.4 MiB), excluding NVIDIA's runtime.
`.local/portable-relocation-v2.json` passed with unchanged user configuration and
payload hashes. Real package lifecycle verification passed. The prototype suite
passed 37 tests; host regressions passed 196 with three opt-in tests ignored.

## Next boundary

The subsequent host-owned runtime step is implemented in the Windows developer
window harness. Rebuild with the current builder for inventory schema 2 (generic
`metadata` plus the file inventory), then use `scripts/verify-host-runtime.py` to
exercise cache-copy loading, same-process reuse, conflict rejection and next-run
stale cleanup. Host details and reproduction are in the sibling repository's
`docs/plugins/native-runtime-ownership.md`. This does not expose public attachment.

Private runtime discovery is now demonstrated without global configuration, but
production live attachment is still absent. VSScript and embedded Python maintain
process-global state: preloading directly from an installed plugin would keep its
DLLs resident in the player and interfere with uninstall/update. The next host
step now owns the runtime copy/lifetime and rejects conflicts in the developer
harness, but must still detach active video processing before plugin cleanup. Bounded
file-delete retries do not solve DLLs deliberately kept loaded in the host.

Keep `native.video.validatePlan` non-executable until that lifecycle and a real
playback attachment exist. Do not solve this by patching global Python settings,
hiding the overlay, silently restarting the player, or claiming this directory
is the finished user plugin.
