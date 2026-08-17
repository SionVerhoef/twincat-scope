#!/usr/bin/env python3
"""Wall clock and peak memory for each verb, at a stated file size.

The claim this measures is SKILL.md's opening one - that a 400 MB recording is
triaged without reading it into the conversation. Wall clock alone cannot check
it: the number that decides whether the ladder works at scale is peak RSS, and
whether it tracks the file or the array.

Peak RSS is read from /proc/<pid>/status VmHWM, which is a high-water mark, so
sampling it while the child runs catches the peak even if the sampler misses the
moment. /usr/bin/time is not present on a Beckhoff engineering VM either.

Usage:
    python3 tests/make_scale_fixture.py --rows 500000 -o /tmp/scale.csv
    python3 tests/bench_scale.py /tmp/scale.csv
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TCSCOPE = ROOT / "scripts" / "tcscope.py"
_UV = shutil.which("uv")
BASE_CMD = [_UV, "run", str(TCSCOPE)] if _UV else [sys.executable, str(TCSCOPE)]


def _status(pid):
    """(PPid, VmHWM kB) for one process, or None if it has gone."""
    ppid = hwm = None
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                elif line.startswith("VmHWM:"):
                    hwm = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        return None
    return ppid, (hwm or 0)


def peak_rss_kb(root, stop, out):
    """Peak RSS across the whole tree under `root`.

    Measuring `root` alone reports uv, which forks the interpreter that actually
    holds the data - and gives a flat ~25 MB for every verb at every file size,
    which is how this was caught. VmHWM only ever rises, so polling is enough.
    """
    while not stop.is_set():
        try:
            pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
        except OSError:
            return
        parents, hwm = {}, {}
        for pid in pids:
            got = _status(pid)
            if got:
                parents[pid], hwm[pid] = got
        for pid in pids:
            seen, cur = 0, pid
            while cur in parents and seen < 20:
                if cur == root:
                    out["kb"] = max(out.get("kb", 0), hwm.get(pid, 0))
                    break
                cur, seen = parents[cur], seen + 1
        time.sleep(0.05)


def measure(*args):
    started = time.time()
    proc = subprocess.Popen([*BASE_CMD, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stop, peak = threading.Event(), {}
    watcher = threading.Thread(target=peak_rss_kb, args=(proc.pid, stop, peak))
    watcher.start()
    stdout, stderr = proc.communicate()
    stop.set()
    watcher.join()
    elapsed = time.time() - started

    try:
        payload = json.loads(stdout.decode())
        ok = payload.get("ok")
        note = payload.get("error", "")
    except ValueError:
        ok, note = False, (stdout[:120].decode(errors="replace")
                           or stderr[:120].decode(errors="replace"))
    return {"seconds": round(elapsed, 2), "peak_rss_mb": round(peak.get("kb", 0) / 1024, 1),
            "output_bytes": len(stdout), "ok": ok, "note": str(note)[:100]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--channels", default=None,
                    help="restrict stats/events/plot to these, as a caller would")
    args = ap.parse_args()

    path = Path(args.input)
    size_mb = path.stat().st_size / 1e6
    sel = ["--channels", args.channels] if args.channels else []

    runs = [
        ("manifest", ("manifest", path)),
        ("stats", ("stats", path, *sel)),
        ("events", ("events", path, *sel)),
        ("window", ("window", path, "--start", 10.0, "--end", 10.2, *sel)),
    ]
    results = {}
    for name, argv in runs:
        results[name] = measure(*argv)
        r = results[name]
        print(f"  {name:9s} {r['seconds']:7.2f}s  {r['peak_rss_mb']:8.1f} MB peak  "
              f"{r['output_bytes']:>9,} B out  ok={r['ok']} {r['note']}")

    print(json.dumps({"file_mb": round(size_mb, 1), "results": results}, indent=2))


if __name__ == "__main__":
    main()
