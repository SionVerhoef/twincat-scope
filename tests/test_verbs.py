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
REAL = FIXTURES / "real"

# Names a channel must never carry. Every one of these was observed as a channel
# name when the group parser fell through to "the nearest non-numeric row above
# the data" - which in the TAB dialect is a row of metadata values.
FORBIDDEN_NAMES = {"0", "Name", "SymbolName", "Unit", "Offset", "Unit Offset",
                   "Data-Type", "Port", "SampleTime[ms]", "BitMask", "ScaleFactor",
                   "StartTime", "EndTime", "NetId", "IndexGroup", "IndexOffset",
                   "SymbolComment", "SymbolBased", "VariableSize"}

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
    # Both operands are guarded: `want` comes from a previous command's JSON as
    # often as `got` does, and when that command failed it is None. Comparing
    # then raised TypeError and aborted the whole run, hiding every later check.
    if got is None or want is None:
        return False
    return abs(got - want) < tol


def first(events, channel, kind):
    for event in events:
        if event["channel"] == channel and event["kind"] == kind:
            return event
    return None


def real_fixture_checks():
    """Everything that only a genuine Scope layout can exercise.

    These run against structural copies of the five layouts the 19 real exports
    used - same group boundaries, delimiters, decimal separators and time-column
    behaviour, shrunk to 200 rows.
    """
    truth = json.loads((REAL / "ground_truth.json").read_text())

    # --- structure: groups, channels, and names that are not metadata --------
    for name, want in sorted(truth.items()):
        got = run("manifest", REAL / name)
        check(f"{name}: manifest parses it",
              got.get("ok") is True, str(got.get("error", ""))[:80])
        check(f"{name}: {want['columns']} columns, {len(want['groups'])} groups",
              got.get("ncols") == want["columns"]
              and len(got.get("groups", [])) == len(want["groups"]),
              f"ncols={got.get('ncols')} groups={len(got.get('groups', []))}")
        expect_channels = sum(g["channels"] for g in want["groups"])
        check(f"{name}: {expect_channels} channels, time columns excluded",
              len(got.get("channels", [])) == expect_channels,
              f"got {len(got.get('channels', []))}")

        names = {c["name"] for c in got.get("channels", [])}
        check(f"{name}: no channel is named after a metadata key or value",
              names.isdisjoint(FORBIDDEN_NAMES),
              f"offending: {sorted(names & FORBIDDEN_NAMES)[:4]}")

        rates = [g["sample_time_ms_measured"] for g in got.get("groups", [])]
        check(f"{name}: per-group sample times measured correctly",
              rates == [g["sample_time_ms"] for g in want["groups"]],
              f"got {rates[:4]}")

        repeats = [g["repeat_factor"] for g in got.get("groups", [])]
        check(f"{name}: repeat_factor detected from the padded time column",
              repeats == [g["repeat_factor"] for g in want["groups"]],
              f"got {repeats[:4]}")

        check(f"{name}: max_skew_ms matches the layout",
              near(got.get("timing", {}).get("max_skew_ms"), want["max_skew_ms"], 1e-6),
              f"got {got.get('timing', {}).get('max_skew_ms')}")

    # --- dialects -----------------------------------------------------------
    tab = run("manifest", REAL / "real_tab_2group.csv")
    check("TAB dialect: the decimal comma does not win the delimiter vote",
          tab.get("delimiter") == "\t" and tab.get("decimal") == ",",
          f"delim={tab.get('delimiter')!r} decimal={tab.get('decimal')!r}")
    check("TAB dialect: SampleTime[ms] is read from the file, not guessed",
          [g["sample_time_ms_declared"] for g in tab.get("groups", [])] == [2.0, 4.0],
          str([g["sample_time_ms_declared"] for g in tab.get("groups", [])]))
    symbols = [c["symbol_name"] for c in tab.get("channels", [])]
    check("TAB dialect: channels carry their qualified SymbolName path",
          any(s.startswith("Axes.Smarttrak M1 (") for s in symbols)
          and any(s.startswith("gPlc.emSmartTrak.") for s in symbols),
          symbols[0] if symbols else "")
    check("TAB dialect: the short name stays available as a selector",
          run("stats", REAL / "real_tab_2group.csv",
              "--channels", "ActTorque").get("ok") is True)

    single = run("manifest", REAL / "real_tab_pergroup_single.csv")
    check("multi-line SymbolComment does not derail the metadata scan",
          single.get("ok") is True and len(single.get("groups", [])) == 60,
          f"groups={len(single.get('groups', []))}")

    # --- the broken export --------------------------------------------------
    broken = run("manifest", REAL / "real_tab_pergroup_skewed.csv")
    timing = broken.get("timing", {})
    check("unpadded export reports row_is_one_instant: false",
          timing.get("row_is_one_instant") is False)
    check("unpadded export is flagged unusable for cross-group timing",
          timing.get("cross_group_timing_valid") is False
          and "broken" in timing.get("note", ""),
          str(timing.get("note"))[:60])
    refused = run("correlate", REAL / "real_tab_pergroup_skewed.csv",
                  "--allow-cross-group", expect_ok=False)
    check("every verb refuses a cross-group claim on a broken export",
          refused.get("ok") is False)

    # --- per-group time axes: the planted step ------------------------------
    for name in ("real_comma_3group.csv", "real_tab_pergroup_skewed.csv"):
        want = truth[name]
        ev = run("events", REAL / name, "--max-events", 5000)
        seen = {}
        for event in ev.get("events", []):
            if event["kind"] == "step" and event.get("delta", 0) > 20:
                seen.setdefault(event.get("group", 0), event["time"])
        wrong = []
        for group in want["groups"]:
            tol = max(0.002, group["sample_time_ms"] / 1000.0 * 1.5)
            if not near(seen.get(group["group"]), group["step_time_s"], tol):
                wrong.append(group["group"])
        check(f"{name}: the planted step is timestamped from its own group's axis",
              not wrong and len(seen) == len(want["groups"]),
              f"{len(seen)}/{len(want['groups'])} groups, off-axis: {wrong[:4]}")

    # --- blank cells --------------------------------------------------------
    blanks = run("manifest", REAL / "real_comma_blanks.csv")
    lead = (blanks.get("groups") or [{}])[0]
    check("blanks in a time column do not poison the measured rate",
          near(lead.get("estimated_rate_hz"), 500.0, 1e-6)
          and lead.get("time_nan_count") == 2,
          f"rate={lead.get('estimated_rate_hz')} nan={lead.get('time_nan_count')}")
    check("a recording with blank cells still reports a finite duration",
          isinstance(blanks.get("duration"), float)
          and blanks["duration"] == blanks["duration"]
          and blanks["duration"] > 0,
          f"duration={blanks.get('duration')}")
    flat = run("events", REAL / "real_comma_blanks.csv", "--max-events", 5000)
    check("a gap in the data is not reported as a flatline",
          not [e for e in flat.get("events", []) if e["kind"] == "flatline"])

    # --- correlate ----------------------------------------------------------
    cross = run("correlate", REAL / "real_tab_2group.csv", "--channels", "ActTorque")
    check("correlate refuses a cross-group pair by default",
          cross.get("refused_pairs") and all(
              p["groups"][0] != p["groups"][1] for p in cross["refused_pairs"]),
          f"{len(cross.get('refused_pairs', []))} refused")
    allowed = run("correlate", REAL / "real_tab_2group.csv", "--channels", "ActTorque",
                  "--allow-cross-group")
    check("correlate says so when it resamples across groups",
          any(p.get("resampled") for p in allowed.get("pairs", [])))
    check("correlate documents its lag sign",
          "a' leads 'b" in (allowed.get("lag_sign") or ""))

    lag = run("correlate", FIXTURES / "planted.csv",
              "--channels", "Axis1.ActPos,Axis1.ActVelo")
    pair = (lag.get("pairs") or [{}])[0]
    # ActVelo is the quarter-cycle-ahead cosine of ActPos at 0.25 Hz, so it must
    # lead by ~1 s - which under the documented convention is a positive lag.
    check("correlate's lag sign matches the documented convention",
          near(pair.get("lag_seconds"), 1.0, 0.1) and pair.get("leads") == "Axis1.ActVelo",
          f"lag={pair.get('lag_seconds')} leads={pair.get('leads')}")

    # --- Parquet round-trip -------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "rec.parquet"
        run("ingest", REAL / "real_tab_2group.csv", "-o", cache)
        back = run("manifest", cache)
        check("ingest to Parquet keeps the group model and the qualified names",
              len(back.get("groups", [])) == 2
              and len(back.get("channels", [])) == 54
              and any(c["symbol_name"].startswith("Axes.Smarttrak")
                      for c in back.get("channels", [])),
              f"groups={len(back.get('groups', []))} channels={len(back.get('channels', []))}")
        rates = [g["estimated_rate_hz"] for g in back.get("groups", [])]
        check("per-group sample rates survive the Parquet round-trip",
              rates == [500.0, 250.0], str(rates))

    # --- window never merges groups ----------------------------------------
    win = run("window", REAL / "real_tab_2group.csv", "--start", 0.0, "--end", 0.02,
              "--channels", "ActTorque")
    check("window reports each group under its own time, never merged",
          len(win.get("groups", [])) == 2
          and "rows" not in win,
          f"{len(win.get('groups', []))} groups, flat rows={'rows' in win}")


def main():
    subprocess.run([sys.executable, str(ROOT / "tests" / "make_fixture.py")],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / "tests" / "make_real_fixtures.py")],
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

    real_fixture_checks()

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
