import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "mpv_probe", Path(__file__).resolve().parents[1] / "scripts" / "probe-mpv.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_timeout_is_not_reported_as_success(self):
        failure = subprocess.TimeoutExpired("native probe", 12, output=b"playback reached EOF")
        with patch("sys.argv", ["probe-mpv.py", "test.dll"]), \
                patch.object(probe.subprocess, "run", side_effect=failure), \
                patch("builtins.print") as output:
            with self.assertRaises(SystemExit) as result:
                probe.main()
            self.assertEqual(result.exception.code, 124)
            self.assertIn('"timed_out": true', output.call_args.args[0])

    def test_native_failure_exit_code_is_preserved(self):
        child = subprocess.CompletedProcess("probe", 7, b"", b"native failure")
        with patch("sys.argv", ["probe-mpv.py", "test.dll"]), \
                patch.object(probe.subprocess, "run", return_value=child), \
                patch("builtins.print") as output:
            with self.assertRaises(SystemExit) as result:
                probe.main()
            self.assertEqual(result.exception.code, 7)
            self.assertIn("native failure", output.call_args.args[0])
