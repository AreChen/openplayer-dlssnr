import copy
import unittest

from scripts.probe_evidence import analyze_events


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {"session": "a", "event": "start", "startup_ms": 100, "worker_pid": 123},
            {"session": "a", "event": "frame", "n": 0, "reset": True, "mean": 100,
             "changed_mean": 2, "elapsed_ms": 20, "fallback": None},
            {"session": "a", "event": "close", "frames": 1, "worker_exitcode": 0},
        ]

    def test_success(self):
        result = analyze_events(self.events)
        self.assertEqual(result["frames"], 1)
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(result["fallback_frames"], 0)

    def test_missing_lifecycle_evidence_fails(self):
        for events in ([], self.events[1:], self.events[:-1], self.events * 2):
            with self.subTest(events=events), self.assertRaises(ValueError):
                analyze_events(events)

    def test_false_success_fails(self):
        for index, field, value in ((1, "mean", 0), (1, "changed_mean", 0),
                                    (1, "reset", False), (1, "elapsed_ms", float("nan")),
                                    (1, "fallback", "crash"), (2, "frames", 0),
                                    (2, "worker_exitcode", None), (2, "worker_exitcode", 89)):
            events = copy.deepcopy(self.events)
            events[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                analyze_events(events)

    def test_discontinuity_requires_reset(self):
        event = {**self.events[1], "n": 5, "reset": False}
        self.events.insert(2, event)
        self.events[-1]["frames"] = 2
        with self.assertRaisesRegex(ValueError, "reset"):
            analyze_events(self.events)
        event["reset"] = True
        self.assertEqual(analyze_events(self.events)["frames"], 2)

    def test_fault_must_fall_back_to_original(self):
        with self.assertRaisesRegex(ValueError, "not exercised"):
            analyze_events(self.events, expect_fallback=True)
        fault = {**self.events[1], "n": 1, "reset": False, "changed_mean": 0, "fallback": "disconnected"}
        self.events.insert(2, fault)
        self.events[-1].update(frames=2, worker_exitcode=89)
        self.assertEqual(analyze_events(self.events, expect_fallback=True)["fallback_frames"], 1)
        fault["changed_mean"] = 2
        with self.assertRaisesRegex(ValueError, "preserve"):
            analyze_events(self.events, expect_fallback=True)


if __name__ == "__main__":
    unittest.main()
