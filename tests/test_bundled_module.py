import hashlib
from pathlib import Path
import tempfile
import unittest

from bundled_frame_module import BundledModule


class FakeModule:
    def __init__(self, options):
        self.options = options
        self.closed = False

    def close(self):
        self.closed = True

    def call(self, method, params):
        return {"method": method}


class BundledModuleTests(unittest.TestCase):
    def test_inspection_hashes_without_loading_or_configuring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "nvngx_dlssnr.dll"
            library.write_bytes(b"test only")
            module = BundledModule(root, root / "log", module_factory=FakeModule)
            inspected = module.call("runtime.inspect", {"path": str(library)})
            self.assertEqual(inspected["sha256"], hashlib.sha256(b"test only").hexdigest())
            self.assertIsNone(module.module)
            for params in ({}, {"path": "relative.dll"}, {"path": None}, {"path": str(library), "extra": 1}):
                with self.assertRaises(ValueError):
                    module.call("runtime.inspect", params)

    def test_explicit_runtime_and_reconfigure_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "nvngx_dlssnr.dll"
            library.write_bytes(b"unit test bytes, never loaded")
            settings = {"path": str(library), "sha256": hashlib.sha256(library.read_bytes()).hexdigest()}
            module = BundledModule(root, root / "log", module_factory=FakeModule)
            self.assertFalse(module.call("frames.status", None)["runtimeConfigured"])
            with self.assertRaises(ValueError):
                module.call("frames.open", None)
            self.assertTrue(module.call("runtime.configure", settings)["configured"])
            previous = module.module
            self.assertEqual(previous.options["host"], str(root / "native/dlssnr_host_v2.dll"))
            self.assertEqual(module.call("frames.open", None), {"method": "frames.open"})
            module.call("runtime.configure", settings)
            self.assertTrue(previous.closed)
            active = module.module
            module.close()
            self.assertTrue(active.closed)
            self.assertTrue(library.exists(), "external runtime is not owned by the plugin")

    def test_rejects_missing_relative_and_mismatched_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "nvngx_dlssnr.dll"
            library.write_bytes(b"fixture")
            module = BundledModule(root, root / "log", module_factory=FakeModule)
            for params in (None, {}, {"path": "nvngx_dlssnr.dll", "sha256": "0" * 64},
                           {"path": str(library), "sha256": "0" * 64},
                           {"path": str(library), "sha256": "x" * 64},
                           {"path": str(library), "sha256": "0" * 64, "extra": True}):
                with self.subTest(params=params), self.assertRaises(ValueError):
                    module.call("runtime.configure", params)
            self.assertIsNone(module.module)
