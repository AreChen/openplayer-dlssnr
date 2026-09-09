# Select the NR processing GPU

**Development native-module support, not a shipped plugin UI.** Selection applies
to the NR worker's D3D12 device, not mpv decode/presentation or WebView. While the
user is gaming, use the headless probe rather than window tests that take focus.

The native-v1 module supports `devices.list` before runtime configuration. It
returns `uuid`, `name`, `pciBusId`, current Windows `luid`, and `nodeMask`. Device
enumeration creates no CUDA context or workload.

```javascript
const devices = await openplayer.native.call("enhance", "devices.list");
// selectedUuid is a user selection from this list, persisted in plugin storage.
await openplayer.native.call("enhance", "frames.open", {
  settings: { gpu_uuid: selectedUuid, intensity: 0.5 }
});
```

Start the module with native launch consent first, and configure the authorized
external runtime before `frames.open`. This only opens a frame owner, not video
attachment in the normal player. Rebuild older bundles to declare `devices.list`.

Persist UUID, not an ordinal or LUID. At worker startup the driver resolves the
chosen UUID to its current Windows LUID, the native DLL selects that DXGI adapter,
and the worker verifies `ID3D12Device::GetAdapterLuid` after initialization.
Missing/unsupported devices, old DLLs without selection exports, and identity
mismatches fail explicitly without fallback to the default GPU. Only single-node
WDDM devices are supported. Changing GPU requires closing/reopening the frame
owner, not a live settings update. Omission retains legacy automatic selection.

Identity mapping uses NVIDIA's documented
[CUDA device queries](https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__DEVICE.html).
These are plugin-specific methods/settings, not vendor-specific host permissions.
A future custom view can populate a GPU menu and persist UUID through the existing
plugin storage API.

## Verify without taking focus

Rebuild using `scripts/build-native.ps1`, then stage a new portable bundle using
`scripts/build-portable-module.py`. The build applies the checked-in adapter patch
to `.local/build/patched`, never the upstream submodule. From this repository:

```powershell
$env:OPENPLAYER_GPU_BUNDLE = (Resolve-Path .local/portable-gpu-selection).Path
$env:OPENPLAYER_GPU_RUNTIME = (Resolve-Path .local/runtime/nvngx_dlssnr.dll).Path
$env:OPENPLAYER_GPU_UUID = 'GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b'
$env:OPENPLAYER_GPU_REPORT = Join-Path $PWD '.local/gpu-check.json'
rtk proxy .local/build/mpv_frame_probe.exe --owned-run "$env:OPENPLAYER_GPU_BUNDLE/runtime/python.exe" "$PWD/scripts/gpu_frame_probe.py"
```

The report path must not exist. Replace GPU identity on another machine. This
workspace's second RTX 3080 Ti maps to the UUID above and PCI `0000:07:00.0`.
The supervisor contains the process tree in a kill-on-close job. The probe checks
720p processed frames, device identity, same-worker reconnect and owner close;
it creates no player windows and injects no input.

Evidence on 2026-09-09: `.local/gpu1-frame-probe.json` passed on that second card.
The host's gated real-package test separately passed disable/replacement/uninstall
with `OPENPLAYER_NATIVE_FRAME_OPTIONS` set to
`{"settings":{"gpu_uuid":"GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b","intensity":0.5}}`.
Those checks cover registry/store/job cleanup, not combined window attachment or
GUI authorization. NR tests after the user's GPU-selection request used GPU 1.
