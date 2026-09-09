"""Probe libmpv filter parsing and optional playback in a time-limited process."""

import argparse
import ctypes as c
import json
from pathlib import Path
import time
import sys
import subprocess


class Event(c.Structure):
    _fields_ = [("id", c.c_int), ("error", c.c_int),
                ("reply", c.c_uint64), ("data", c.c_void_p)]


class Log(c.Structure):
    _fields_ = [("prefix", c.c_char_p), ("level", c.c_char_p),
                ("text", c.c_char_p), ("log_level", c.c_int)]


def probe(args):
    if args.python_deps:
        sys.path.insert(0, str(args.python_deps.resolve(strict=True)))
    m = c.CDLL(str(args.library.resolve(strict=True)))
    m.mpv_create.restype = c.c_void_p
    m.mpv_initialize.argtypes = [c.c_void_p]
    m.mpv_set_option_string.argtypes = [c.c_void_p, c.c_char_p, c.c_char_p]
    m.mpv_request_log_messages.argtypes = [c.c_void_p, c.c_char_p]
    m.mpv_wait_event.argtypes = [c.c_void_p, c.c_double]
    m.mpv_wait_event.restype = c.POINTER(Event)
    m.mpv_terminate_destroy.argtypes = [c.c_void_p]
    m.mpv_get_property_string.argtypes = [c.c_void_p, c.c_char_p]
    m.mpv_get_property_string.restype = c.c_void_p
    m.mpv_free.argtypes = [c.c_void_p]
    m.mpv_command.argtypes = [c.c_void_p, c.POINTER(c.c_char_p)]
    h = m.mpv_create()
    if not h:
        raise RuntimeError("mpv_create failed")
    logs = []
    try:
        m.mpv_request_log_messages(h, b"info")
        for key, value in ((b"config", b"no"), (b"load-scripts", b"no"),
                           (b"vo", b"null"), (b"ao", b"null")):
            if m.mpv_set_option_string(h, key, value) < 0:
                raise RuntimeError(f"failed option {key!r}")
        if m.mpv_initialize(h) < 0:
            raise RuntimeError("mpv_initialize failed")
        m.mpv_request_log_messages(h, b"v")
        commands = {}
        for spec in (b"hflip", b"vapoursynth", b"not-a-real-filter"):
            command = (c.c_char_p * 4)(b"vf", b"set", spec, None)
            commands[spec.decode()] = m.mpv_command(h, command)
        version_ptr = m.mpv_get_property_string(h, b"mpv-version")
        version = c.string_at(version_ptr).decode() if version_ptr else "unknown"
        if version_ptr:
            m.mpv_free(version_ptr)
        if args.video:
            spec = args.filter or f"vapoursynth=file=%{len(args.script.encode())}%{args.script}:concurrent-frames=1"
            command = (c.c_char_p * 4)(b"vf", b"set", spec.encode(), None)
            commands["set_script"] = m.mpv_command(h, command)
            command = (c.c_char_p * 3)(b"loadfile", str(args.video.resolve()).encode(), None)
            commands["loadfile"] = m.mpv_command(h, command)
        deadline = time.monotonic() + (5 if args.video else 0.5)
        while time.monotonic() < deadline:
            event = m.mpv_wait_event(h, 0.05).contents
            if event.id == 2:
                log = c.cast(event.data, c.POINTER(Log)).contents
                logs.append(log.text.decode("utf-8", errors="replace").strip())
        print(json.dumps({"version": version, "commands": commands, "logs": logs}), flush=True)
    finally:
        m.mpv_terminate_destroy(h)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--script", default="tests/passthrough.vpy")
    parser.add_argument("--filter", help="explicit developer filter graph instead of a script")
    parser.add_argument("--python-deps", type=Path)
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        parser.error("timeout must be in (0, 60]")
    if args.child:
        return probe(args)
    if args.report and args.report.exists():
        parser.error("report already exists")
    try:
        child = subprocess.run([sys.executable, __file__, *sys.argv[1:], "--child"],
                               capture_output=True, timeout=args.timeout)
        code, stdout, stderr = child.returncode, child.stdout, child.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b""
    report = {"exit_code": code, "timed_out": code == 124,
              "stdout": stdout.decode("utf-8", errors="replace"),
              "stderr": stderr.decode("utf-8", errors="replace")}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
