#!/usr/bin/env python3
"""End-to-end checks: every verb runs, and the analysis finds what was planted.

Deliberately not pytest. The suite has to run on a Windows engineering VM that
may have nothing installed but uv, so it is stdlib only and drives the real CLI
through subprocess - which also means it tests the interface an agent actually
uses, not internal functions an agent never calls.

Usage:  uv run tests/test_verbs.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TCSCOPE = ROOT / "scripts" / "tcscope.py"
FIXTURES = ROOT / "tests" / "fixtures"

# Drive the CLI exactly as the documentation tells a user to. Reaching for
# sys.executable instead would run tcscope.py under *this* file's interpreter,
# which has no dependencies declared and therefore no numpy - every analysis
# check would then fail for a reason that has nothing to do with the code.
_UV = shutil.which("uv")
BASE_CMD = [_UV, "run", str(TCSCOPE)] if _UV else [sys.executable, str(TCSCOPE)]

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def run(*args, expect_ok=True):
    """Invoke the CLI the way a caller would, and parse its JSON."""
    proc = subprocess.run([*BASE_CMD, *map(str, args)], capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return {"ok": False, "error": f"non-JSON output: {proc.stdout[:200]}{proc.stderr[:200]}"}
    if expect_ok and not payload.get("ok"):
        print(f"      (command failed: {payload.get('error')})")
    return payload


def near(got, want, tol=0.05):
    return got is not None and abs(got - want) < tol


def first(events, channel, kind):
    for event in events:
        if event["channel"] == channel and event["kind"] == kind:
            return event
    return None


def main():
    subprocess.run([sys.executable, str(ROOT / "tests" / "make_fixture.py")],
                   check=True, capture_output=True)
    truth = json.loads((FIXTURES / "ground_truth.json").read_text())["planted"]

    # --- both locales must parse identically -----------------------------
    us = run("manifest", FIXTURES / "planted.csv")
    eu = run("manifest", FIXTURES / "planted_eu.csv")
    check("manifest parses US-locale export", us.get("rows") == 20000, f"rows={us.get('rows')}")
    check("manifest parses EU-locale export (; and , decimal)",
          eu.get("rows") == 20000, f"rows={eu.get('rows')}")
    check("both locales agree on duration",
          near(us.get("duration"), eu.get("duration"), 1e-9))
    check("sample rate detected as 1 kHz", near(us.get("estimated_rate_hz"), 1000.0, 1.0))
    check("no NaN columns from a misread header",
          all(c["nan_fraction"] == 0 for c in us.get("channels", [])))

    # --- events must find every planted defect ---------------------------
    ev = run("events", FIXTURES / "planted.csv")
    events = ev.get("events", [])
    step = first(events, "Axis1.ActPos", "step")
    spike = first(events, "Axis1.PosDiff", "spike")
    flat = first(events, "Axis1.ActTorque", "flatline")
    clip = first(events, "Axis1.ActVelo", "clipping")

    check("finds the planted step", near((step or {}).get("time"), truth["step"]["time"]),
          f"at {(step or {}).get('time')}")
    check("finds the planted 3-sample spike, classified as a spike not a step",
          near((spike or {}).get("time"), truth["spike"]["time"]),
          f"at {(spike or {}).get('time')}")
    check("finds the planted flatline",
          near((flat or {}).get("time"), truth["flatline"]["start"]),
          f"at {(flat or {}).get('time')}")
    check("finds the planted clipping", clip is not None)

    # --- stats -----------------------------------------------------------
    st = run("stats", FIXTURES / "planted.csv", "--channels", "Axis1.ActVelo")
    velo = (st.get("channels") or [{}])[0]
    check("stats reports the clipped rail as max",
          near(velo.get("max"), truth["clipping"]["limit"], 1e-6), f"max={velo.get('max')}")
    check("stats flags time spent at the rail", (velo.get("pct_at_max") or 0) > 1.0,
          f"{velo.get('pct_at_max'):.1f}%" if velo.get("pct_at_max") else "")

    # --- window enforces its cap -----------------------------------------
    win = run("window", FIXTURES / "planted.csv", "--start", 12.0, "--end", 12.01)
    check("window returns real rows for a narrow range", len(win.get("rows", [])) > 0,
          f"{len(win.get('rows', []))} rows")
    flood = run("window", FIXTURES / "planted.csv", "--start", 0, "--end", 20, expect_ok=False)
    check("window refuses to flood the context window", flood.get("ok") is False)

    # --- plot: the spike must survive the envelope -----------------------
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "out.png"
        pl = run("plot", FIXTURES / "planted.csv", "-o", png, "--channels", "Axis1.PosDiff")
        check("plot writes a PNG", png.exists() and png.stat().st_size > 1000,
              f"{png.stat().st_size if png.exists() else 0} bytes")
        check("plot uses a min/max envelope, not decimation",
              pl.get("method", "").startswith("min/max"))

    # --- correlate -------------------------------------------------------
    co = run("correlate", FIXTURES / "planted.csv",
             "--channels", "Axis1.ActPos,Axis1.ActTorque")
    check("correlate returns a ranked pair list", len(co.get("pairs", [])) == 1)

    # --- acquisition side, no third-party imports ------------------------
    tpl = ROOT / "templates" / "axis-diagnosis.tcscopex"
    if tpl.exists():
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.tcscopex", Path(tmp) / "b.tcscopex"
            run("newscope", tpl, "-o", a, "--channels", "MAIN.fbAxis.NcToPlc.ActPos",
                "--netid", "1.2.3.4.1.1")
            run("newscope", tpl, "-o", b, "--channels", "MAIN.fbAxis.NcToPlc.ActPos",
                "--netid", "1.2.3.4.1.1")
            guids_a = set(re_guids(a))
            guids_b = set(re_guids(b))
            check("newscope mints fresh GUIDs on every run",
                  guids_a and not (guids_a & guids_b))
            check("newscope output starts with a UTF-8 BOM, as TwinCAT writes",
                  a.read_bytes().startswith(b"\xef\xbb\xbf"))
            check("newscope output uses CRLF, as TwinCAT writes",
                  b"\r\n" in a.read_bytes())
            chk = run("checkscope", a)
            check("checkscope passes its own generated file", chk.get("ok") is True,
                  str(chk.get("problems")))

    print()
    failed = [name for name, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


def re_guids(path):
    import re
    return re.findall(r"<Guid>([^<]+)</Guid>", path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    raise SystemExit(main())
