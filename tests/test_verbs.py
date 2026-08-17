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
          any(s.startswith("Axes.Linear Axis1 (") for s in symbols)
          and any(s.startswith("gPlc.emTransport.") for s in symbols),
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
              and any(c["symbol_name"].startswith("Axes.Linear Axis")
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

    # A repeat-padded group prints each sample again on the next row. window
    # used to index those raw rows, so it emitted every slow-group sample twice
    # under one timestamp - in a table this same tool had just called 4 ms.
    for block in win.get("groups", []):
        times = [row["time"] for row in block["rows"]]
        dupes = sum(1 for a, b in zip(times, times[1:]) if a == b)
        span = block["sample_time_ms"] / 1000.0
        expected = sum(1 for t in times if t <= 0.02)
        check(f"window group {block['group']}: no repeated timestamps",
              dupes == 0, f"{dupes} duplicates in {len(times)} rows")
        check(f"window group {block['group']}: rows land one sample time apart",
              all(near(b - a, span, span * 0.01) for a, b in zip(times, times[1:])),
              f"sample_time={span}s rows={len(times)}")
        check(f"window group {block['group']}: every returned row is in range",
              expected == len(times), f"{len(times)} rows, {expected} in range")

    # The cap has to count real samples too, or it bites at half the width it
    # promises on any group that is padded.
    padded = run("window", REAL / "real_comma_3group.csv", "--start", 0.0,
                 "--end", 0.4, "--channels", "PosDiff", "--max-rows", 210)
    check("window's row cap is evaluated on de-duplicated samples",
          padded.get("ok") is True,
          str(padded.get("error", ""))[:70])

    # --- stats is auditable -------------------------------------------------
    man = run("manifest", REAL / "real_comma_3group.csv")
    counts = {g["group"]: g["n_samples"] for g in man.get("groups", [])}
    st = run("stats", REAL / "real_comma_3group.csv")
    per_group = {c.get("group"): c.get("n_samples") for c in st.get("channels", [])}
    check("stats reports a per-channel sample count",
          all(c.get("n_samples") for c in st.get("channels", [])),
          f"{len(st.get('channels', []))} channels")
    check("stats counts distinct instants, not padded file rows",
          per_group == counts, f"stats={per_group} manifest={counts}")

    # --- the reader is faithful, even where the source is malformed ---------
    tab_ch = run("manifest", REAL / "real_tab_2group.csv").get("channels", [])
    symbols = [c["symbol_name"] for c in tab_ch]
    check("a symbol truncated by Beckhoff's own exporter is left truncated",
          any(s.count("(") == 1 and s.count(")") == 0 for s in symbols),
          next((s for s in symbols if "(" in s), "")[:60])
    check("the literal unit string '(None)' is not coerced to null",
          all(c["unit"] == "(None)" for c in tab_ch),
          str({c["unit"] for c in tab_ch}))


def at_rest_checks():
    """The shape that made `events` unusable on real machine data.

    An axis at rest has a first-difference MAD of ~1e-9 - non-zero, so it passed
    the old zero-guard, and every sample of a move then cleared 6*MAD*1.4826.
    On this fixture the old detector produced 713 events, 601 of them on one
    position channel that moved exactly once, and the default 100 came back from
    the first third of the recording without the planted fault in it.
    """
    truth = json.loads((REAL / "ground_truth.json").read_text())
    want = truth["real_comma_atrest.csv"]["groups"][0]

    ev = run("events", REAL / "real_comma_atrest.csv")
    events, summary = ev.get("events", []), ev.get("summary", {})

    check("an at-rest recording does not flood: under 5 events per channel",
          0 < (summary.get("per_channel_max") or 999) < 5,
          f"worst channel has {summary.get('per_channel_max')}, "
          f"{ev.get('count')} events total")

    # The torque channel also steps twice as the move loads and unloads it, so
    # "the first ActTorque step" is not the planted one. Rank picks it out,
    # which is the property under test.
    worst = max(events, key=lambda e: e["severity"])
    check("the planted disturbance is the most severe thing in the recording",
          worst["channel"] == "ActTorque" and worst["kind"] == "step"
          and near(worst.get("time"), want["step_time_s"], 0.005)
          and near(worst.get("delta"), want["step_delta"], 0.5),
          f"{worst['channel']} {worst['kind']} at {worst.get('time')} "
          f"delta={worst.get('delta')} severity={worst['severity']}")

    # A commanded move is one event, not one per sample. Naming it `ramp` is
    # what keeps `step` meaning a discontinuity worth looking at.
    ramps = [e for e in events if e["kind"] == "ramp" and e["channel"] == "ActVelo"]
    check("a commanded move is reported once, as a ramp",
          len(ramps) == 2 and all(e["width_samples"] > 10 for e in ramps),
          f"{len(ramps)} ramps, widths={[e['width_samples'] for e in ramps]}")
    check("no analysis verb calls the move a step",
          not [e for e in events
               if e["kind"] == "step" and e["channel"] in ("ActPos", "ActVelo")],
          str([e["channel"] for e in events if e["kind"] == "step"]))

    # A digital channel sits at both rails 100% of the time and holds each state
    # as long as the machine needs it. Neither is clipping or a frozen signal.
    check("a BOOL's toggles are transitions, not steps at a rail",
          [e["kind"] for e in events if e["channel"] == "bEnable"] == ["transition"] * 2,
          str([e["kind"] for e in events if e["channel"] == "bEnable"]))

    # --- what a truncated answer is allowed to hide -------------------------
    # Measured against the span the events themselves occupy, not the span of
    # the recording: no ranking can return an event from a stretch where none
    # happened, and this fixture is deliberately quiet at both ends.
    whole = [e["time"] for e in events if "time" in e]
    span = max(whole) - min(whole)
    cut = run("events", REAL / "real_comma_atrest.csv", "--max-events", 4)
    times = [e["time"] for e in cut.get("events", []) if "time" in e]
    check("a truncated answer still spans the events it is truncating",
          cut.get("truncated") is True and times
          and (max(times) - min(times)) > 0.8 * span,
          f"covers {(max(times) - min(times)) / span * 100:.0f}% of the {span:.2f}s "
          f"the {len(whole)} timed events occupy" if times else "no timed events")
    check("truncation never drops the worst event in the file",
          max(cut.get("events", []), key=lambda e: e["severity"])["severity"]
          == worst["severity"],
          f"kept {max(cut.get('events', []), key=lambda e: e['severity'])['severity']}")
    check("a truncated answer still totals every event it did not return",
          cut.get("summary", {}).get("by_kind") == summary.get("by_kind")
          and cut.get("summary", {}).get("by_channel") == summary.get("by_channel"),
          f"returned {cut.get('summary', {}).get('returned')} of {cut.get('count')}")
    histogram = cut.get("summary", {}).get("time_histogram", {})
    check("a truncated answer says where the activity actually is",
          sum(histogram.get("bins", [])) == histogram.get("timed") == len(whole),
          f"bins={histogram.get('bins')} timed={histogram.get('timed')}")


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

    # A spike's return edge is its own excursion, and classified on its own it
    # comes back as a second event at the far side of the spike. Checking that
    # the spike is *found* does not catch that; counting does.
    diffs = [e for e in events if e["channel"] == "Axis1.PosDiff"
             and e["kind"] in ("step", "spike", "ramp")]
    check("the planted spike is reported once, not as a spike and a step",
          len(diffs) == 1 and diffs[0]["kind"] == "spike",
          str([(e["kind"], round(e["time"], 3)) for e in diffs]))

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

            # Capture strategy, not wiring. The templates record a fixed 60 s
            # window with an empty TriggerModule, which is a lottery ticket for
            # the intermittent faults a scope is usually reached for. It is a
            # warning, never a problem: a file can be perfectly built and still
            # be the wrong plan.
            check("checkscope reads RecordTime as seconds",
                  near(chk.get("record_seconds") or 0, 60.0, tol=0.001),
                  f"record_seconds={chk.get('record_seconds')}")
            check("checkscope sees the empty TriggerModule as no trigger",
                  chk.get("trigger_configured") is False)
            check("a fixed window with no trigger warns but does not fail the file",
                  chk.get("ok") is True
                  and any("no trigger configured" in w for w in chk.get("warnings", [])),
                  str(chk.get("warnings")))

            # Acquisition load. The previous threshold sat above every real
            # project a commissioning engineer had ever built - 100 000, then
            # 20 000, against a densest-measured 16 250 - so it never fired and
            # graded nothing. Both directions are checked here for that reason.
            check("a four-channel recording is reported as a typical load",
                  chk.get("load_band") == "typical"
                  and not any("samples/s" in w for w in chk.get("warnings", [])),
                  f"band={chk.get('load_band')} rate={chk.get('total_samples_per_second')}")

            dense = Path(tmp) / "dense.tcscopex"
            run("newscope", tpl, "-o", dense, "--netid", "1.2.3.4.1.1",
                "--channels", ",".join(f"MAIN.fbAxis.Ch{i}" for i in range(14)))
            heavy = run("checkscope", dense)
            check("a dense recording lands in a band that says so",
                  heavy.get("load_band") == "high"
                  and any("samples/s" in w for w in heavy.get("warnings", [])),
                  f"band={heavy.get('load_band')} "
                  f"rate={heavy.get('total_samples_per_second')}")
            check("a dense-but-buildable recording is still not a problem",
                  heavy.get("ok") is True, str(heavy.get("problems"))[:70])

            # The negative case, or the check above is just a string that is
            # always present. Re-arming after each window is a different plan
            # and must not draw the same warning.
            c = Path(tmp) / "c.tcscopex"
            c.write_bytes(a.read_bytes().replace(
                b"<AutoRestartRecord>false</AutoRestartRecord>",
                b"<AutoRestartRecord>true</AutoRestartRecord>"))
            chk_restart = run("checkscope", c)
            check("a re-arming recording draws no fixed-window warning",
                  chk_restart.get("auto_restart_record") is True
                  and not any("no trigger configured" in w
                              for w in chk_restart.get("warnings", [])),
                  str(chk_restart.get("warnings")))

    real_fixture_checks()
    at_rest_checks()

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
