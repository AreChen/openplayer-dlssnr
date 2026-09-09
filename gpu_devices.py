"""Read NVIDIA device identities without creating a CUDA context or running work."""
import ctypes
import sys
import uuid


def normalize_uuid(value):
    if not isinstance(value, str) or not value.startswith("GPU-") or len(value) != 40:
        raise ValueError("gpu_uuid must be an NVIDIA GPU UUID")
    try:
        return "GPU-" + str(uuid.UUID(value[4:]))
    except ValueError as error:
        raise ValueError("gpu_uuid must be an NVIDIA GPU UUID") from error


def list_devices():
    if sys.platform != "win32":
        raise RuntimeError("this D3D12 device selector requires Windows")
    driver = ctypes.WinDLL("nvcuda.dll", winmode=0x800)  # System32 only.
    def call(name, types, *args):
        function = getattr(driver, name)
        function.argtypes, function.restype = types, ctypes.c_int
        code = function(*args)
        if code:
            raise RuntimeError(f"{name} failed ({code}); explicit GPU selection unavailable")
    integer = ctypes.c_int
    pointer = ctypes.c_void_p
    call("cuInit", [ctypes.c_uint], 0)
    count = integer()
    call("cuDeviceGetCount", [pointer], ctypes.byref(count))
    if not 0 <= count.value <= 32:
        raise RuntimeError("invalid GPU device count")
    devices = []
    for ordinal in range(count.value):
        device = integer()
        call("cuDeviceGet", [pointer, integer], ctypes.byref(device), ordinal)
        name, pci = ctypes.create_string_buffer(256), ctypes.create_string_buffer(32)
        identity, luid = ctypes.create_string_buffer(16), ctypes.create_string_buffer(8)
        mask = ctypes.c_uint()
        call("cuDeviceGetName", [pointer, integer, integer], name, len(name), device)
        call("cuDeviceGetPCIBusId", [pointer, integer, integer], pci, len(pci), device)
        call("cuDeviceGetUuid", [pointer, integer], identity, device)
        call("cuDeviceGetLuid", [pointer, pointer, integer], luid, ctypes.byref(mask), device)
        devices.append({"uuid": "GPU-" + str(uuid.UUID(bytes=identity.raw)),
                        "name": name.value.decode("utf-8"), "pciBusId": pci.value.decode("ascii"),
                        "luid": f"{int.from_bytes(luid.raw, 'little'):016x}", "nodeMask": mask.value})
    return devices


def resolve_device(identity):
    identity = normalize_uuid(identity)
    for device in list_devices():
        if device["uuid"] == identity:
            if device["luid"] == "0000000000000000" or device["nodeMask"] != 1:
                raise RuntimeError("selected GPU requires a supported single-node WDDM adapter")
            return device
    raise RuntimeError("selected GPU is unavailable; refusing to fall back to another adapter")
