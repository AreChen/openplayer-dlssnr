import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

verify = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/verify-portable-module.py"))["verify_inventory"]


class PortableInventoryTests(unittest.TestCase):
    def test_modified_missing_and_extra_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "module.py"
            data = b"fixture"
            path.write_bytes(data)
            (root / "bundle-inventory.json").write_text(json.dumps({"files": {
                "module.py": {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}}}))
            verify(root)
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify(root)
            path.unlink()
            with self.assertRaises(ValueError):
                verify(root)
            path.write_bytes(data)
            (root / "unexpected.dll").write_bytes(b"fixture")
            with self.assertRaises(ValueError):
                verify(root)
