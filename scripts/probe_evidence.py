"""Assertions for the controlled, nonblack SDR native-probe fixture, not arbitrary media."""
import json
import math
from pathlib import Path
import statistics


def analyze_events(events, *, expect_fallback=False):
    sessions = {}
    frames = []
    warm = []
    for event in events:
        identity = event["session"]
        kind = event["event"]
        if kind == "start":
            if identity in sessions:
                raise ValueError("duplicate session start")
            sessions[identity] = {"start": event, "frames": [], "closed": False}
            continue
        if identity not in sessions or sessions[identity]["closed"]:
            raise ValueError("event outside an active session")
        session = sessions[identity]
        if kind == "frame":
            previous = session["frames"]
            if (not previous or event["n"] != previous[-1]["n"] + 1) and event["reset"] is not True:
                raise ValueError("missing temporal history reset")
            for field in ("mean", "changed_mean", "elapsed_ms"):
                if not math.isfinite(event[field]) or event[field] < 0:
                    raise ValueError(f"invalid {field}")
            if event["mean"] < 1:
                raise ValueError("black output for nonblack fixture")
            if event["fallback"]:
                if not expect_fallback:
                    raise ValueError("unexpected frame fallback")
                if event["changed_mean"] != 0:
                    raise ValueError("fallback did not preserve the original RGB frame")
            if len(previous) >= 3:
                warm.append(event["elapsed_ms"])
            previous.append(event)
            frames.append(event)
        elif kind == "close":
            if not session["frames"] or event["frames"] != len(session["frames"]):
                raise ValueError("missing frames or close count mismatch")
            failed = any(frame["fallback"] for frame in session["frames"])
            if event["worker_exitcode"] is None or (event["worker_exitcode"] != 0 and not failed):
                raise ValueError("worker did not exit cleanly")
            session["closed"] = True
        else:
            raise ValueError("unknown event")
    if not sessions or not all(session["closed"] for session in sessions.values()):
        raise ValueError("missing session start/close evidence")
    if not any(frame["changed_mean"] > 0 and not frame["fallback"] for frame in frames):
        raise ValueError("no processed pixel changes")
    fallback_count = sum(bool(frame["fallback"]) for frame in frames)
    if expect_fallback and not fallback_count:
        raise ValueError("expected fault was not exercised")
    ordered = sorted(warm)
    return {
        "sessions": len(sessions), "frames": len(frames), "fallback_frames": fallback_count,
        "startup_ms": [session["start"]["startup_ms"] for session in sessions.values()],
        "worker_pids": [session["start"]["worker_pid"] for session in sessions.values()],
        "callback_mean_ms": statistics.mean(frame["elapsed_ms"] for frame in frames),
        "warm_callback_mean_ms": statistics.mean(warm) if warm else None,
        "warm_callback_p95_ms": ordered[math.ceil(len(ordered) * .95) - 1] if ordered else None,
    }


def verify_artifacts(directory, *, window=False, expect_fallback=False):
    directory = Path(directory)
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    result = analyze_events(events, expect_fallback=expect_fallback)
    if window:
        import numpy as np
        from PIL import Image
        with Image.open(directory / "presented.png") as image:
            first = next(event for event in events if event["event"] == "start")
            if image.size != (first["width"], first["height"]):
                raise ValueError("presented screenshot has unexpected dimensions")
            pixels = np.asarray(image.convert("RGB"))
            if pixels.mean() < 1 or pixels.std() < 1:
                raise ValueError("presented screenshot is black or flat")
            result["screenshot"] = {"width": image.width, "height": image.height,
                                    "mean": float(pixels.mean()), "std": float(pixels.std())}
    return result
