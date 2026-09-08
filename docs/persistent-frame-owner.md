# Persistent frame ownership

## Result

The experimental frame worker now survives same-format mpv filter rebuilds. A
720p OpenPlayer window test processed 117 frames through three filter instances
using **one NGX process**, with no fallback and a clean exit. Reconnects took
10.74 ms and 1.07 ms; the initial engine startup was 1147.63 ms. These are attach
times, **not complete seek-to-display latency** or frame-rate guarantees.

This is still a developer probe, not an installable `.opplugin`. No public SDK,
normal player behavior, window hierarchy or installed binary changed in this
step. The preceding baseline was committed as host `5981be4` and prototype
`878f946`. All commits remain local.

## Why separate ownership

mpv's [VapourSynth filter implementation](https://raw.githubusercontent.com/mpv-player/mpv/master/video/filter/vf_vapoursynth.c)
destroys the VS graph during reset. Tying an expensive engine to that graph
therefore repeats initialization on seek. A graph should hold a temporary lease,
while an explicit owner controls the engine's lifetime.

```text
test Job Object
  -> owner process: FrameService + one FrameSession
       -> isolated NGX worker
       -> native mpv/OpenPlayer harness
            -> short-lived VapourSynth FrameClient leases
```

- `FrameService` owns at most one engine and two fixed-size RGBA8 shared buffers. The owner chooses the trusted processor factory and its options; clients cannot select executables, models or paths.
- `FrameClient` reconnects after the VS graph is rebuilt. It reuses the worker only for identical dimensions. Format changes close the old worker before starting another; there is no accumulating resolution cache.
- Every accepted lease receives a new generation. The first frame always resets engine temporal history; later frames can explicitly request reset. Ordered sequence numbers and generation checks reject stale control requests/replies.
- `FrameSession.process_shared()` evaluates existing shared memory without routing pixels through JSON or adding a second pair of full-frame staging buffers. After failure, mappings remain valid until the owner closes; no failed output buffer is consumed.
- Worker failure remains sticky for the same format: later leases return original frames instead of silently retrying startup. A new owner or explicit format replacement establishes a new engine lifecycle.
- Filter detach closes the client mapping/connection, not the engine. The test owner closes the service after mpv exits, joins the worker and releases the shared memory. A production disable/uninstall flow must explicitly close this owner.

The control endpoint is loopback-only TCP on an OS-assigned port with a random
per-owner token, bounded 4096-byte length-prefixed JSON and read deadlines. It
uses no pickle deserialization and never transports pixels. Tokens stay in child
environment configuration, not reports. This remains trusted single-client code,
not a hostile-client security boundary: shared-memory holders can write buffers.
Concurrent graph evaluation and multi-plugin ownership need host coordination.

The C++ supervisor establishes its kill-on-close Job Object **before launching
the owner**, so both the persistent worker and player are contained on forced
timeout. The owner starts no background service outside that test job. Global
Python, environment variables, registry settings and user databases are untouched.

## Reproduce and inspect

Use the prerequisites and fixtures from [native playback verification](native-playback-probe.md).
Rebuild `./scripts/build-mpv-probe.ps1`, then run from this repository:

```powershell
rtk proxy .venv/Scripts/python.exe scripts/run-native-probe.py ../RustPlayer/target/release/libmpv-2.dll --video .local/motion-720p-long.mp4 --script tests/dlssnr.vpy --window-smoke ../RustPlayer/target/debug/window-smoke.exe --close-target overlay-alt-f4 --persistent --timeout 55 --report .local/my-persistent-window.json
```

`--persistent` is opt-in; omitting it retains the baseline per-filter lifetime.
The native harness and the actual controlled window are still test-only.
Do not interact with other windows during the native Alt+F4 test.

| Evidence artifact | Finding |
| --- | --- |
| `.local/persistent-window-720p.json` | 3 filter leases, 1 engine, 117 frames, 0 fallbacks; pause/seek, detach/reattach, resize/maximized fullscreen, one Alt+F4 close and mpv teardown passed |
| `.local/persistent-window-720p.frames/owner-events.jsonl` | Matching engine start/close with exit 0, one PID across all three generations; all leases detached |
| `.local/persistent-native-720p-v2.json` | 4 leases, 1 engine, 154 frames, 0 fallbacks; stop/reload and `DESTROY_COMPLETE` passed |
| `.local/persistent-window-crash-720p.json` | 4 processed frames followed by 113 original-frame fallbacks; one deliberately failed engine, no restart on subsequent leases, window lifecycle passed |
| `.local/persistent-watchdog-720p.json` | Deliberate 3.5-second timeout reported 124 and failed evidence, not success; no test worker/owner/probe process remained |

The 720p window run's warm callback mean/p95 was 32.54/37.01 ms, excluding the
first three callbacks of each lease. This is close to the baseline's 33.50/36.51
ms under non-isolated GPU load; it is not a demonstrated throughput improvement.
The purpose of this step is avoiding repeated startup. GPU upload/readback,
color conversion, diagnostic copies, A/V synchronization and 1080p realtime
performance remain separate work. First callbacks still save diagnostic images.

The full 26-test GPU-independent suite passed, including engine reuse/reset,
format replacement, stale generations, invalid tokens, owner shutdown with an
active client, crash/timeout fallback, bounded wire messages and separate owner
cleanup evidence. `git diff --check` passed. No installer or release was built.

## Next integration boundary

### Planar transport follow-up

`--persistent --planar` now writes decoded RGB planes straight into the owner's
RGBA input mapping and copies output planes straight back to the writable VS
frame. It avoids per-frame RGBA staging/output arrays. Pixel diagnostics sample
every 16th row/column; initial PNGs and the presentation screenshot remain full
resolution. This is both a transfer optimization and reduced diagnostic work,
not a claim that every pixel is checked on every frame.

Window evidence `.local/planar-window-720p.json` recorded 118 frames, one engine,
zero fallback, warm callback mean/p95 19.92/22.13 ms and successful Alt+F4 close.
`.local/planar-window-1080p.json` recorded 92 frames, one engine, zero fallback,
34.45/39.26 ms and successful window/teardown checks. Timing excludes decode,
surrounding YUV conversion and presentation; sustained A/V playback is still
unverified. All 28 unit tests passed, including full-image planar/RGBA equivalence,
source immutability, non-contiguous planes and exact failure pass-through.

### Remaining host integration

The playback probe's owner is still supplied by the developer launcher. A separate
[native frame module](native-frame-module.md) now connects the owner to the
existing native control protocol and verifies real registry/store cleanup on
disable/update/uninstall. Package deployment, interactive consent, public playback
attachment and a real plugin UI are still required.
Keep the public video-plan validator non-executable until that boundary exists.
This step adds no interpolation, super-resolution engine or arbitrary Python SDK
permission. Existing normal-player controls and persistence stay unchanged.
