import unittest
from unittest.mock import patch

from dlssnr_backend import validate_settings
from gpu_devices import normalize_uuid, resolve_device

GPU = "GPU-76e0cbba-1c68-0d53-26ca-b999df6f0e9b"


class GpuDeviceTests(unittest.TestCase):
    def test_settings_normalize_uuid_and_reject_ordinal_or_invalid_identity(self):
        self.assertEqual(validate_settings({"gpu_uuid": "GPU-" + GPU[4:].upper()}), {"gpu_uuid": GPU})
        for value in (0, 1, True, None, "1", "GPU-", "GPU-" + "z" * 36):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_uuid(value)

    def test_resolves_exact_device_and_never_falls_back(self):
        device = {"uuid": GPU, "luid": "0000000000012345", "nodeMask": 1}
        with patch("gpu_devices.list_devices", return_value=[device]):
            self.assertEqual(resolve_device(GPU), device)
            with self.assertRaisesRegex(RuntimeError, "refusing to fall back"):
                resolve_device("GPU-ff23d73c-7865-4e68-16f9-7b36a9c80a47")
        for values in ({"luid": "0000000000000000"}, {"nodeMask": 0}, {"nodeMask": 3}):
            with patch("gpu_devices.list_devices", return_value=[{**device, **values}]), self.assertRaises(RuntimeError):
                resolve_device(GPU)
