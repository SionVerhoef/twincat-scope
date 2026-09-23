#!/usr/bin/env python3
"""End-to-end checks: every verb runs, and the analysis finds what was planted.

Deliberately not pytest. The suite has to run on a Windows engineering VM that
may have nothing installed but uv, so it is stdlib only and drives the real CLI
through subprocess - which also means it tests the interface an agent actually
uses, not internal functions an agent never calls.

Usage:  uv run tests/test_verbs.py
"""

import json
import re
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
          any(s.startswith("Axes.Linear Axis 1 (") for s in symbols)
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


# AMS net IDs that may appear in a public repo: the unfilled template value, the
# documentation example, and the two the tests pass in. Anything else is a real
# machine address, and this skill is meant to be shareable.
ALLOWED_NET_IDS = {"0.0.0.0.0.0", "192.168.1.10.1.1", "1.2.3.4.1.1", "127.0.0.1.1.1"}
NET_ID = re.compile(r"\b(?:\d{1,3}\.){5}\d{1,3}\b")


def recordability_checks():
    """Whether a generated file could actually record, which is not validity.

    Every check here is a defect a real machine found first: a file that opened
    cleanly in Scope View, passed checkscope, and recorded nothing
    (evals/field-review-1fa0e9b.md).
    """
    import xml.etree.ElementTree as ET

    tpl = ROOT / "templates" / "axis-diagnosis.tcscopex"
    if not tpl.exists():
        check("a generated file could record", True, "skipped: no template")
        return

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mixed.tcscopex"
        made = run("newscope", tpl, "-o", out, "--netid", "1.2.3.4.1.1",
                   "--record-time", "180",
                   "--channels",
                   "MAIN.fbStation.seStep:INT,MAIN.fbStation.sbFlag:BOOL,"
                   "Axes.Mover 1 (Drive1_ChA).SetPosModulo")
        # Read the file back rather than the JSON newscope printed about it.
        # The report is built in memory, so it would still look right if the
        # write into the XML silently did nothing - which is the whole class of
        # bug this section exists for.
        written = {}
        for acq in ET.fromstring(out.read_text(encoding="utf-8-sig")).findall(
                ".//AdsAcquisition"):
            written[(acq.findtext("SymbolName") or "").strip()] = {
                "port": (acq.findtext("TargetPort") or "").strip(),
                "data_type": (acq.findtext("DataType") or "").strip(),
                "variable_size": (acq.findtext("VariableSize") or "").strip(),
                "name": (acq.findtext("Name") or "").strip(),
                "title": (acq.findtext("Title") or "").strip(),
            }
        reported = {c["symbol"]: c for c in made["channels"]}
        check("the report and the file agree, field by field",
              all(written[s]["port"] == str(c["port"])
                  and written[s]["data_type"] == c["data_type"]
                  and written[s]["variable_size"] == str(c["variable_size"])
                  and written[s]["name"] == c["name"]
                  and written[s]["title"] == s
                  for s, c in reported.items()),
              str(written))

        by_symbol = written
        nc = by_symbol["Axes.Mover 1 (Drive1_ChA).SetPosModulo"]
        plc = by_symbol["MAIN.fbStation.sbFlag"]

        # The showstopper: one port across every channel resolves the PLC
        # symbols and leaves every axis symbol unfindable.
        check("an NC symbol is recorded on the NC port",
              nc["port"] == "501" and plc["port"] == "851",
              f"nc={nc['port']} plc={plc['port']}")

        check("declared types become Scope's vocabulary, not IEC's",
              (plc["data_type"], plc["variable_size"]) == ("BIT", "1")
              and (by_symbol["MAIN.fbStation.seStep"]["data_type"],
                   by_symbol["MAIN.fbStation.seStep"]["variable_size"]) == ("INT16", "2"),
              str([(c["data_type"], c["variable_size"]) for c in written.values()]))

        # An NC field's type is Beckhoff's, so it is known from the name and is
        # not a guess to warn about.
        check("a known NC axis field is typed from the NC table, not defaulted",
              "types_defaulted" not in made
              and reported["Axes.Mover 1 (Drive1_ChA).SetPosModulo"]["type_source"]
              == "nc-field"
              and (nc["data_type"], nc["variable_size"]) == ("REAL64", "8"),
              str(made.get("types_defaulted")))

        # <Name> is the CSV column header. Fifty-three columns called Signal is
        # an export nobody can read, discovered after the machine has moved on.
        names = [c["name"] for c in written.values()]
        check("every channel gets its own name, not the placeholder",
              len(set(names)) == 3 and "Signal" not in names, str(names))

        check("--record-time sets the window",
              made.get("record_seconds") == 180.0
              and ET.fromstring(out.read_text(encoding="utf-8-sig")
                                ).findtext(".//RecordTime") == "1800000000",
              str(made.get("record_seconds")))

        # Prefix-style names match no quantity keyword; the type still says
        # what they are, so they do not pile onto one axis - and a step enum
        # does not share one with a 0/1 flag it would flatten.
        bands = {c["chart"]: [b["band"] for b in c["bands"]] for c in made["charts"]}
        check("a bit and an enum band by type, whatever they are called, apart",
              bands.get("fbStation") == ["Digital / state", "Step / count"],
              str(bands))

        chk = run("checkscope", out)
        check("checkscope passes a file that could record", chk.get("ok") is True,
              str(chk.get("problems")))

        # And the same file with the field session's defects put back.
        text = out.read_text(encoding="utf-8-sig")
        broken = Path(tmp) / "broken.tcscopex"
        # Each channel gets its own IEC name, so the mapping is proved per
        # type rather than three times for LREAL.
        spoiled = text.replace("<DataType>BIT</DataType>",
                               "<DataType>BOOL</DataType>")
        spoiled = spoiled.replace("<DataType>INT16</DataType>",
                                  "<DataType>INT</DataType>")
        spoiled = spoiled.replace("<DataType>REAL64</DataType>",
                                  "<DataType>LREAL</DataType>")
        spoiled = spoiled.replace("<TargetPort>501</TargetPort>",
                                  "<TargetPort>851</TargetPort>")
        for leaf in names:
            spoiled = spoiled.replace(f"<Name>{leaf}</Name>", "<Name>Signal</Name>")
        broken.write_bytes(b"\xef\xbb\xbf" + spoiled.encode("utf-8"))
        bad = run("checkscope", broken, expect_ok=False)
        problems = " | ".join(bad.get("problems", []))
        check("checkscope names the Scope type each IEC name should have been",
              all(f"'{iec}' is an IEC type name" in problems
                  and f"did you mean '{scope}'" in problems
                  for iec, scope in (("BOOL", "BIT"), ("INT", "INT16"),
                                     ("LREAL", "REAL64"))),
              problems[:120])
        check("checkscope rejects an NC symbol on a PLC port",
              "NC symbol on port 851" in problems, problems[:90])
        check("checkscope rejects channels that would export as one column",
              "share the name 'Signal'" in problems, problems[:90])
        # Two separate mistakes in one field. Reporting the shared name and
        # stopping means the placeholder is met on the next run instead.
        check("a shared name and an unreplaced placeholder are both reported",
              "share the name 'Signal'" in problems
              and any("still named 'Signal'" in w for w in bad.get("warnings", [])),
              str(bad.get("warnings"))[:90])

        # An absent field is the same failure as a wrong one: nothing says
        # which runtime to ask, how to read the variable, or how much of it.
        empty = Path(tmp) / "empty-fields.tcscopex"
        stripped = (text.replace("<DataType>REAL64</DataType>", "<DataType></DataType>")
                        .replace("<VariableSize>8</VariableSize>", "<VariableSize></VariableSize>")
                        .replace("<TargetPort>501</TargetPort>", "<TargetPort></TargetPort>"))
        empty.write_bytes(b"\xef\xbb\xbf" + stripped.encode("utf-8"))
        blank = run("checkscope", empty, expect_ok=False)
        check("checkscope rejects fields that are simply absent",
              blank.get("ok") is False
              and sum(any(w in p for w in ("no TargetPort", "no DataType",
                                           "no VariableSize"))
                      for p in blank.get("problems", [])) == 3,
              str(blank.get("problems"))[:90])

        # Names must stay unique however the paths collide, or the export has
        # two columns with one heading - the thing the names exist to prevent.
        collide = Path(tmp) / "collide.tcscopex"
        clashing = run("newscope", tpl, "-o", collide, "--netid", "1.2.3.4.1.1",
                       "--channels", "MAIN.a.NcToPlc.Val,MAIN.a.PlcToNc.Val,"
                                     "MAIN.a.Val_2,MAIN.a.Status.Val_2")
        clashed = [c["name"] for c in clashing["channels"]]
        check("colliding paths still get distinct names",
              len(set(clashed)) == 4 and run("checkscope", collide).get("ok") is True,
              str(clashed))
        # Dropping the wrapper is what made them collide, so put it back rather
        # than separate a setpoint from a measurement by an ordinal.
        check("a wrapper struct comes back when it is the only difference",
              "NcToPlc" in clashed[0] and "PlcToNc" in clashed[1], str(clashed[:2]))

        # The escape hatch from the Axes. rule, and the way to reach a second
        # PLC runtime per channel.
        ported = run("newscope", tpl, "-o", Path(tmp) / "ported.tcscopex",
                     "--netid", "1.2.3.4.1.1",
                     "--channels", "Axes.NotAnAxis.Val:LREAL:852,MAIN.b:BOOL")
        check("an explicit port overrides the namespace rule",
              [(c["port"], c["port_source"]) for c in ported["channels"]]
              == [(852, "declared"), (851, "derived")],
              str([(c["port"], c["port_source"]) for c in ported["channels"]]))

        # Bad input answers in the tool's own JSON, not with a traceback.
        for label, args_in in (
                ("a window that is not a number", ("--record-time", "nan")),
                ("a window that rounds to nothing", ("--record-time", "0.00000001")),
                ("an entry with no symbol", ("--channels", ":BOOL")),
                ("an unknown type name", ("--channels", "MAIN.a:LREALX")),
                ("one symbol declared two ways", ("--channels", "MAIN.a:BOOL,MAIN.a:LREAL")),
                ("a channel list that names nothing", ("--channels", ",,,")),
                ("a port outside the ADS range", ("--port", "99999")),
                ("a per-channel port outside it", ("--channels", "MAIN.a:BOOL:0"))):
            refused = run("newscope", tpl, "-o", Path(tmp) / "refused.tcscopex",
                          "--netid", "1.2.3.4.1.1", *args_in, expect_ok=False)
            check(f"newscope refuses {label}, in JSON",
                  refused.get("ok") is False and bool(refused.get("error")),
                  str(refused.get("error"))[:70])

        # A width that does not match its type reads the wrong bytes off the
        # target - a recording of something, just not of this variable.
        mismatched = Path(tmp) / "mismatched.tcscopex"
        # The BIT channel is the only 1-byte one, so widening every 1 widens it.
        wrong_size = text.replace("<VariableSize>1</VariableSize>",
                                  "<VariableSize>8</VariableSize>")
        mismatched.write_bytes(b"\xef\xbb\xbf" + wrong_size.encode("utf-8"))
        size_check = run("checkscope", mismatched, expect_ok=False)
        check("checkscope rejects a width that contradicts the type",
              any("VariableSize says 8" in p for p in size_check.get("problems", [])),
              str(size_check.get("problems"))[:90])

        # 85 for 851 is one keystroke, looks like a port, and records nothing.
        # Neither verb used to say anything about it at all.
        typo = Path(tmp) / "typo.tcscopex"
        mistyped = run("newscope", tpl, "-o", typo, "--netid", "1.2.3.4.1.1",
                       "--port", "85", "--channels", "MAIN.fbIO.Value:LREAL")
        typo_chk = run("checkscope", typo)
        check("a PLC port below the first runtime is called out by both verbs",
              mistyped.get("ports_suspect") == ["MAIN.fbIO.Value"]
              and any("port 85 is below" in w for w in typo_chk.get("warnings", [])),
              str(mistyped.get("ports_note"))[:70])

        # And the other direction: a channel really called Signal is not a
        # leftover, because Signal is the alias newscope derives for it.
        own_leaf = Path(tmp) / "own-leaf.tcscopex"
        run("newscope", tpl, "-o", own_leaf, "--netid", "1.2.3.4.1.1",
            "--channels", "MAIN.fbIO.Signal:BOOL")
        leaf_chk = run("checkscope", own_leaf)
        check("a symbol whose own leaf is Signal is not called a leftover",
              leaf_chk.get("ok") is True
              and not any("placeholder" in w for w in leaf_chk.get("warnings", [])),
              str(leaf_chk.get("warnings"))[:70])

        # Nameless acquisitions all share one key, so only the first used to be
        # reported - fix it, rerun, meet the next one.
        blanked = Path(tmp) / "nameless.tcscopex"
        unnamed_text = text
        for leaf in names:
            unnamed_text = unnamed_text.replace(f"<Name>{leaf}</Name>", "<Name></Name>")
        blanked.write_bytes(b"\xef\xbb\xbf" + unnamed_text.encode("utf-8"))
        nameless = run("checkscope", blanked, expect_ok=False)
        check("every nameless acquisition is reported, not just the first",
              any(p.startswith(f"{len(names)} acquisition(s) have no Name")
                  for p in nameless.get("problems", [])),
              str(nameless.get("problems"))[:90])

        # The two type tables have to stay in step: an IEC name checkscope
        # suggests must be one newscope accepts, and a type that is not a real
        # number belongs in a state band rather than on a shared axis - bits in
        # one, integers in another.
        iec = ("BOOL", "SINT", "USINT", "BYTE", "INT", "UINT", "WORD", "DINT",
               "UDINT", "DWORD", "LINT", "ULINT", "LWORD", "REAL", "LREAL")
        typed = Path(tmp) / "every-type.tcscopex"
        all_types = run("newscope", tpl, "-o", typed, "--netid", "1.2.3.4.1.1",
                        "--channels",
                        ",".join(f"MAIN.fbT.v{i}:{name}"
                                 for i, name in enumerate(iec)))
        typed_chk = run("checkscope", typed)
        check("every IEC type name newscope takes maps to one checkscope knows",
              all_types.get("ok") is True and typed_chk.get("ok") is True
              and not any("not one this tool recognises" in w
                          for w in typed_chk.get("warnings", [])),
              str(typed_chk.get("warnings"))[:70])
        by_band = {b["band"]: b["channels"] for c in all_types.get("charts", [])
                   for b in c.get("bands", [])}
        integers = [s for band, chans in by_band.items()
                    if band.startswith("Step / count") for s in chans]
        check("bits band as state, and every other integer type beside them",
              [s.rsplit(":", 1)[0] for s in by_band.get("Digital / state", [])]
              == ["MAIN.fbT.v0"]
              and len(integers) == len(iec) - 3
              and not any(s in ("MAIN.fbT.v13", "MAIN.fbT.v14") for s in integers),
              str([(c["chart"], [b["band"] for b in c["bands"]])
                   for c in all_types.get("charts", [])])[:90])

    # The templates ship what everyone copies, so they have to be right too.
    for name in ("axis-diagnosis.tcscopex", "minimal-single-channel.tcscopex"):
        path = ROOT / "templates" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig")
        check(f"{name} declares types in Scope's vocabulary",
              "<DataType>LREAL<" not in text and "<DataType>REAL64<" in text,
              name)

    # A channel named Signal exports as a column called Signal. The
    # single-channel template is the exception on purpose: its symbol is
    # PLACEHOLDER.Symbol, so its name is a placeholder for the same reason and
    # checkscope says so when anyone generates from it unchanged.
    axis_tpl = (ROOT / "templates" / "axis-diagnosis.tcscopex")
    if axis_tpl.exists():
        check("the worked template carries no placeholder channel name",
              "<Name>Signal</Name>" not in axis_tpl.read_text(encoding="utf-8-sig"),
              "axis-diagnosis.tcscopex")
    placeholder_tpl = (ROOT / "templates" / "minimal-single-channel.tcscopex")
    if placeholder_tpl.exists():
        text = placeholder_tpl.read_text(encoding="utf-8-sig")
        check("the placeholder template is a placeholder throughout",
              "PLACEHOLDER" in text and "<Name>Signal</Name>" in text,
              "minimal-single-channel.tcscopex")


def prefix_house_checks():
    """A 32-channel function-block recording in a prefix-style house.

    The shape of a real follow-up session's channel list, every name a
    stand-in: one step enum per nested block, so the leaf `seStep` repeats;
    seven bits and two integers in one block; counters beside flags; and a
    length whose name contains "Loading". On the version before this check it
    put a step number on the same axis as seven 0/1 flags, filed the length
    under torque, and wrote a band its own checkscope called crowded.
    """
    import xml.etree.ElementTree as ET

    tpl = ROOT / "templates" / "axis-diagnosis.tcscopex"
    if not tpl.exists():
        check("prefix-style house layout", True, "skipped: no template")
        return

    ctl = "GVL.fbCell.fbControl"
    startup = [f"{ctl}.fbStartup.{leaf}" for leaf in (
        "seStep:INT", "sbReady1:BOOL", "sbReady2:BOOL", "sbHold1:BOOL",
        "sbHold2:BOOL", "sbCheckOk:BOOL", "sbIdle:BOOL", "sbSingle:BOOL",
        "onIndex:INT", "sfLoadingOffset:LREAL")]
    tracks = [f"{ctl}.fbTrack{n}.{leaf}" for n in (1, 2) for leaf in (
        "seStep:INT", "snCount:INT", "sbAtMark:BOOL", "sbInWindow:BOOL",
        "sfTravelActual:LREAL", "sfEdgeFront:LREAL", "sfTarget1:LREAL",
        "seDir1:INT", "ofPos1:LREAL", "ofPos2:LREAL")]
    entries = [f"{ctl}.seStep:INT", *startup, *tracks, "GVL.fbRecipe.bUpdating:BOOL"]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "house.tcscopex"
        made = run("newscope", tpl, "-o", out, "--netid", "1.2.3.4.1.1",
                   "--channels", ",".join(entries))
        names = [c["name"] for c in made.get("channels", [])]
        check("32 channels sharing leaves still get 32 names",
              len(names) == 32 and len(set(names)) == 32, str(len(set(names))))

        types = {c["symbol"]: c["data_type"] for c in made.get("channels", [])}
        charts = {c["chart"]: {b["band"]: b["channels"] for b in c["bands"]}
                  for c in made.get("charts", [])}
        # A step number running 0..200 flattens every 0/1 trace on its axis.
        mixed = [f"{chart}/{band}" for chart, bands in charts.items()
                 for band, chans in bands.items()
                 if {types.get(s) == "BIT" for s in chans} == {True, False}
                 and any(types.get(s) != "BIT" and types.get(s, "").startswith(("INT", "UINT"))
                         for s in chans)]
        check("bits never share an axis with multi-valued integers", not mixed,
              str(mixed))
        startup_bands = charts.get("fbStartup", {})
        check("a length named ...Loading... is not filed as a load",
              not any("sfLoadingOffset" in s
                      for s in startup_bands.get("Torque / current", [])),
              str({b: len(c) for b, c in startup_bands.items()}))
        check("step enums and counters get a band of their own",
              startup_bands.get("Step / count", [])
              == [f"{ctl}.seStep", f"{ctl}.fbStartup.seStep",
                  f"{ctl}.fbStartup.onIndex"]
              and f"{ctl}.fbTrack1.snCount" in charts.get("fbTrack1", {}).get(
                  "Step / count", []),
              str({b: len(c) for b, c in startup_bands.items()}))

        chk = run("checkscope", out)
        check("checkscope has nothing to say about newscope's own layout",
              chk.get("ok") is True
              and not any("one value axis" in w or "stacks" in w
                          or "twice in one tab" in w
                          for w in chk.get("warnings", [])),
              str([w[:60] for w in chk.get("warnings", [])]))

        # A step is read against what it drives. The parent sequencer's lone
        # step got a tab to itself in the field; it belongs in each child
        # block's tab, first in its band - drawn three times, recorded once.
        parent = f"{ctl}.seStep"
        with_parent = sorted(c for c, bands in charts.items()
                             if any(parent in chans for chans in bands.values()))
        check("a lone parent step is drawn in each child block's tab, not its own",
              "fbControl" not in charts
              and with_parent == ["fbStartup", "fbTrack1", "fbTrack2"]
              and all(charts[t]["Step / count"][0] == parent for t in with_parent),
              f"tabs {sorted(charts)}, parent in {with_parent}")
        house = ET.fromstring(out.read_text(encoding="utf-8-sig"))
        parent_guid = next(a.findtext("Guid") for a in house.iter("AdsAcquisition")
                           if a.findtext("SymbolName") == parent)
        drawn = [c for c in house.iter("Channel")
                 if c.findtext(".//AcquisitionGUID") == parent_guid]
        check("the parent step is recorded once and drawn three times",
              len(drawn) == 3 and chk.get("acquisitions") == 32
              and chk.get("acquisitions_in_several_tabs") == 1,
              f"drawn {len(drawn)}, acquisitions {chk.get('acquisitions')}")
        # Nothing below it to give context to, so it keeps its own tab.
        check("a lone channel with no child blocks keeps its tab",
              list(charts.get("fbRecipe", {}).values()) == [["GVL.fbRecipe.bUpdating"]],
              str(charts.get("fbRecipe")))

        # A program or a global list is a namespace, not a block that drives
        # anything: its lone flag is not copied into every block beneath it.
        ns = Path(tmp) / "namespace.tcscopex"
        spaced = run("newscope", tpl, "-o", ns, "--netid", "1.2.3.4.1.1",
                     "--channels", "GVL.bFlag:BOOL,GVL.fbA.bX:BOOL,GVL.fbA.bY:BOOL")
        ns_tabs = {c["chart"]: [s for b in c["bands"] for s in b["channels"]]
                   for c in spaced.get("charts", [])}
        check("a namespace's lone flag keeps its tab rather than spreading",
              ns_tabs.get("GVL") == ["GVL.bFlag"]
              and "GVL.bFlag" not in ns_tabs.get("fbA", []), str(ns_tabs))

        # The same acquisition twice in one tab is not context, it is a slip.
        twice = ET.fromstring(out.read_text(encoding="utf-8-sig"))
        band = next(twice.iter("AxisGroup")).find("SubMember")
        copy_of = ET.fromstring(ET.tostring(band.find("Channel")))
        for guid in copy_of.iter("Guid"):
            guid.text = str(__import__("uuid").uuid4())
        band.append(copy_of)
        doubled = Path(tmp) / "doubled.tcscopex"
        doubled.write_bytes(b"\xef\xbb\xbf" + ET.tostring(twice, encoding="utf-8"))
        check("checkscope warns when one acquisition is drawn twice in one tab",
              any("twice in one tab" in w
                  for w in run("checkscope", doubled).get("warnings", [])),
              "")

        # Past the crowding threshold on bits alone, the band is split rather
        # than written in a shape checkscope would then warn about.
        flags = Path(tmp) / "flags.tcscopex"
        many = run("newscope", tpl, "-o", flags, "--netid", "1.2.3.4.1.1",
                   "--channels", ",".join(f"GVL.fbIO.ib{i}:BOOL" for i in range(11)))
        sizes = [len(b["channels"]) for c in many.get("charts", []) for b in c["bands"]]
        check("eleven flags are split into balanced bands, none crowded",
              sizes == [6, 5]
              and not any("one value axis" in w
                          for w in run("checkscope", flags).get("warnings", [])),
              str(sizes))

        # A disabled band was the other thing that came back from the field:
        # every AxisGroup Enabled=false, nothing shown until someone clicked.
        # Disabling is a real Scope View feature, so this warns, never fails.
        text = out.read_text(encoding="utf-8-sig")
        root = ET.fromstring(text)
        for group in root.iter("AxisGroup"):
            group.find("Enabled").text = "false"
        next(root.iter("AdsAcquisition")).find("Enabled").text = "false"
        off = Path(tmp) / "disabled.tcscopex"
        off.write_bytes(b"\xef\xbb\xbf" + ET.tostring(root, encoding="utf-8"))
        disabled = run("checkscope", off)
        warned = " | ".join(disabled.get("warnings", []))
        bands_total = sum(1 for _ in root.iter("AxisGroup"))
        check("checkscope warns about disabled bands and acquisitions, and still passes",
              disabled.get("ok") is True
              and f"{bands_total} of {bands_total} bands are disabled" in warned
              and "1 of 32 acquisitions are disabled" in warned,
              warned[:120])


def second_field_session_checks():
    """What the second field session (evals/field-review-1fa0e9b-rounds.md) added.

    Scope turns a type it cannot read into VOID and saves it that way; NC axis
    fields have fixed types; and a generated chart in a dark IDE was a panel of
    light grey with no axis styling at all.
    """
    import xml.etree.ElementTree as ET

    tpl = ROOT / "templates" / "axis-diagnosis.tcscopex"
    if not tpl.exists():
        check("second field session checks", True, "skipped: no template")
        return

    axis = "Axes.Axis 1 (Drive1_ChA)"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "nc.tcscopex"
        made = run("newscope", tpl, "-o", out, "--netid", "1.2.3.4.1.1",
                   "--channels", f"{axis}.ActPos,{axis}.PosDiff,{axis}.ErrorCode,"
                                 f"{axis}.SomethingNew,MAIN.fbStation.fLevel")
        reported = {c["symbol"]: c for c in made.get("channels", [])}
        written = {(a.findtext("SymbolName") or "").strip():
                   (a.findtext("DataType"), a.findtext("VariableSize"))
                   for a in ET.fromstring(out.read_text(encoding="utf-8-sig")
                                          ).findall(".//AdsAcquisition")}
        check("an NC status field is written as the 4-byte type it is",
              written.get(f"{axis}.ErrorCode") == ("UINT32", "4")
              and reported[f"{axis}.ErrorCode"]["type_source"] == "nc-field",
              str(written.get(f"{axis}.ErrorCode")))
        # The table is what has been seen, not a licence to guess the rest.
        check("an NC field outside the table, and any PLC symbol, is still a default",
              made.get("types_defaulted") == [f"{axis}.SomethingNew",
                                              "MAIN.fbStation.fLevel"],
              str(made.get("types_defaulted")))

        # Scope parses a type name it does not know to VOID and saves that. The
        # file then fails to connect every such channel, and used to pass here.
        text = out.read_text(encoding="utf-8-sig")
        void = Path(tmp) / "void.tcscopex"
        void.write_bytes(b"\xef\xbb\xbf" + text.replace(
            "<DataType>REAL64</DataType>", "<DataType>VOID</DataType>").encode("utf-8"))
        rejected = run("checkscope", void, expect_ok=False)
        check("checkscope refuses VOID and says Scope wrote it",
              rejected.get("ok") is False
              and any("DataType is VOID" in p and "Scope writes back" in p
                      for p in rejected.get("problems", [])),
              str(rejected.get("problems"))[:90])

        # The table describes Axes.<axis>.<field> on the NC port and nothing
        # else. A PLC struct with the same leaf, a declared type, a symbol sent
        # to another port and a deeper path all keep their own.
        lookalike = Path(tmp) / "lookalike.tcscopex"
        looks = run("newscope", tpl, "-o", lookalike, "--netid", "1.2.3.4.1.1",
                    "--channels", "MAIN.fbAxis.NcToPlc.ErrorCode,"
                                  "Axes.Axis2.ErrorCode:LREAL,"
                                  "Axes.Axis3.ErrorCode:852,"
                                  "Axes.Axis4.Enc.ErrorCode")
        sources = {c["symbol"]: c["type_source"] for c in looks.get("channels", [])}
        check("the NC table stays out of symbols it does not describe",
              sources == {"MAIN.fbAxis.NcToPlc.ErrorCode": "default",
                          "Axes.Axis2.ErrorCode": "declared",
                          "Axes.Axis3.ErrorCode": "default",
                          "Axes.Axis4.Enc.ErrorCode": "default"}, str(sources))
        # checkscope has to know the table too, or a file from an older
        # newscope with ErrorCode 8 bytes wide passes in silence.
        looked = run("checkscope", lookalike, expect_ok=False)
        check("checkscope warns about an NC field declared as the wrong type",
              any(w.startswith("Axes.Axis2.ErrorCode: DataType REAL64")
                  and "UINT32" in w for w in looked.get("warnings", []))
              and not any(w.startswith("MAIN.fbAxis.NcToPlc.ErrorCode: DataType")
                          for w in looked.get("warnings", [])),
              str([w[:50] for w in looked.get("warnings", []) if "DataType" in w]))

        # Theme, value by value. Three traces share the Position band so the
        # palette order is exercised past its first slot; a template with no
        # AxisStyle anywhere, and one axis with no SubMember at all, makes
        # newscope build them rather than recolour the template's own.
        def signed(argb):
            return str(argb - 2 ** 32)

        palettes = {
            "dark": (0xFF252526, 0xFFF1F1F1, 0xFF3E3E42,
                     (0xFF3987E5, 0xFF008300, 0xFFD55181)),
            "light": (0xFFFCFCFB, 0xFF52514E, 0xFFE1E0D9,
                      (0xFF2A78D6, 0xFF008300, 0xFFE87BA4)),
        }
        unstyled_tpl = Path(tmp) / "unstyled-template.tcscopex"
        plain = ET.fromstring(tpl.read_text(encoding="utf-8-sig"))
        for sub in plain.iter("SubMember"):
            for style in sub.findall("AxisStyle"):
                sub.remove(style)
        first_time_axis = plain.find(".//AxisGroup/SubMember/TimeAxis")
        first_time_axis.remove(first_time_axis.find("SubMember"))
        unstyled_tpl.write_bytes(b"\xef\xbb\xbf" + ET.tostring(plain, encoding="utf-8"))

        trio = f"{axis}.ActPos,{axis}.SetPos,{axis}.Position"
        for theme, (bg, fg, grid, traces) in palettes.items():
            styled = Path(tmp) / f"{theme}.tcscopex"
            made_theme = run("newscope", unstyled_tpl, "-o", styled,
                             "--netid", "1.2.3.4.1.1", "--theme", theme,
                             "--channels", trio)
            root = ET.fromstring(styled.read_text(encoding="utf-8-sig"))
            panels = [node.findtext("DisplayColor") for tag in
                      ("YTChart", "AxisGroup", "OverviewChart") for node in root.iter(tag)]
            axes = [a for tag in ("TimeAxis", "ValueAxis") for a in root.iter(tag)]
            styles = [a.find("SubMember/AxisStyle") for a in axes]
            # Guarded: a missing style must fail a check, not abort the run.
            style_guids = {s.findtext("Guid") for s in styles if s is not None}
            check(f"--theme {theme}: every panel, axis and grid in its colours",
                  panels and set(panels) == {signed(bg)}
                  and axes and all(s is not None for s in styles)
                  and {a.findtext("DisplayColor") for a in axes} == {signed(fg)}
                  and {s.findtext("DisplayColor") for s in styles} == {signed(fg)}
                  and {s.findtext("GridColor") for s in styles} == {signed(grid)}
                  and {s.findtext("ColorMode") for s in styles} == {"CustomColor"},
                  f"{len(axes)} axes, panels {set(panels)}")
            check(f"--theme {theme}: every axis has its own AxisStyle, where real "
                  "files keep it",
                  len(style_guids) == len(axes)
                  and all("SubMember" in [c.tag for c in a]
                          and [c.tag for c in a].index("SubMember")
                          < [c.tag for c in a].index("Guid") for a in axes),
                  f"{len(style_guids)} of {len(axes)}")
            band = next((g for g in root.iter("AxisGroup")
                         if g.findtext("Name") == "Position"), None)
            chans = band.findall("SubMember/Channel") if band is not None else []
            check(f"--theme {theme}: traces take the palette in order, both "
                  "colour fields",
                  [c.findtext("DisplayColor") for c in chans]
                  == [signed(t) for t in traces]
                  and [c.findtext("SubMember/ChannelStyle/DisplayColor")
                       for c in chans] == [signed(t) for t in traces],
                  str([c.findtext("DisplayColor") for c in chans]))
            back = run("checkscope", styled)
            check(f"--theme {theme}: reported, and read back by checkscope",
                  made_theme.get("theme") == theme and back.get("theme") == theme
                  and back.get("axes_without_style") == 0,
                  f"{made_theme.get('theme')} / {back.get('theme')}")

        # A file from before this change, or from a real project without axis
        # styling, is fine to record with; it is only told about.
        bare = Path(tmp) / "bare.tcscopex"
        stripped = ET.fromstring(text)
        for sub in stripped.iter("SubMember"):
            for style in sub.findall("AxisStyle"):
                sub.remove(style)
        bare.write_bytes(b"\xef\xbb\xbf" + ET.tostring(stripped, encoding="utf-8"))
        unstyled = run("checkscope", bare)
        check("an axis with no AxisStyle is a warning, not a broken file",
              unstyled.get("ok") is True
              and any("have no AxisStyle" in w for w in unstyled.get("warnings", [])),
              str(unstyled.get("axes_without_style")))

    for name in ("axis-diagnosis.tcscopex", "minimal-single-channel.tcscopex"):
        path = ROOT / "templates" / name
        if path.exists():
            chk = run("checkscope", path, expect_ok=False)
            check(f"{name} is styled for the default theme on every axis",
                  chk.get("theme") == "dark" and chk.get("axes_without_style") == 0,
                  f"theme={chk.get('theme')} unstyled={chk.get('axes_without_style')}")


def shareability_checks():
    """No real machine address anywhere in the tracked tree.

    An allowlist rather than a list of things to avoid, so the check itself
    names nothing. The reader was validated against a customer's machine and the
    obvious way to leak that is to paste its net ID in as the worked example -
    which is exactly what had happened, in five files including SKILL.md.
    """
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                            capture_output=True, text=True)
    if listed.returncode != 0:
        check("tracked files carry no real AMS net ID", True, "skipped: no git")
        return

    offenders = {}
    for name in listed.stdout.split():
        path = ROOT / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for found in set(NET_ID.findall(text)) - ALLOWED_NET_IDS:
            offenders.setdefault(found, []).append(name)
    check("tracked files carry no real AMS net ID", not offenders,
          "; ".join(f"{k} in {v[0]}" for k, v in list(offenders.items())[:3]))


def layout_checks():
    """Where a channel lands on screen, which is not the same as being wired.

    The complaint this answers came from a real session: twenty channels arrived
    as twenty traces in one chart, every one of them the same colour and sharing
    one auto-scaled axis. The file was flawlessly built and unreadable.
    """
    import xml.etree.ElementTree as ET

    tpl = ROOT / "templates" / "axis-diagnosis.tcscopex"
    if not tpl.exists():
        check("newscope groups channels into tabs", True, "skipped: no template")
        return

    symbols = [
        "MAIN.fbAxis1.NcToPlc.ActPos", "MAIN.fbAxis1.NcToPlc.SetPos",
        "MAIN.fbAxis1.NcToPlc.PosDiff", "MAIN.fbAxis1.NcToPlc.ActVelo",
        "MAIN.fbAxis1.NcToPlc.ActTorque",
        "MAIN.fbAxis2.NcToPlc.ActPos", "MAIN.fbAxis2.NcToPlc.SetPos",
        "MAIN.fbAxis2.NcToPlc.PosDiff", "MAIN.fbAxis2.NcToPlc.ActVelo",
        "MAIN.fbAxis2.NcToPlc.ActTorque",
        "GVL.Axes[3].fActPos", "GVL.Axes[3].fSetPos",
        "GVL.Axes[3].fFollowingError", "GVL.Axes[3].bEnabled",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        grouped = Path(tmp) / "grouped.tcscopex"
        made = run("newscope", tpl, "-o", grouped, "--netid", "1.2.3.4.1.1",
                   "--channels", ",".join(symbols))
        charts = made.get("charts") or []
        titles = [c["chart"] for c in charts]
        check("newscope gives each device its own chart tab",
              titles == ["fbAxis1", "fbAxis2", "Axes[3]"], str(titles))

        bands = {c["chart"]: [b["band"] for b in c["bands"]] for c in charts}
        check("bands are stacked in reading order, position first",
              bands.get("fbAxis1") == ["Position", "Following error",
                                       "Velocity", "Torque / current"],
              str(bands.get("fbAxis1")))

        by_band = {b["band"]: b["channels"] for b in charts[0]["bands"]}
        check("set and actual position share one axis, being one comparison",
              by_band.get("Position") == ["MAIN.fbAxis1.NcToPlc.ActPos",
                                          "MAIN.fbAxis1.NcToPlc.SetPos"],
              str(by_band.get("Position")))
        # The whole point of the split: a following error of a few microns on
        # the position axis is a flat line on zero.
        check("the following error is not left on the position axis",
              by_band.get("Following error") == ["MAIN.fbAxis1.NcToPlc.PosDiff"],
              str(by_band.get("Following error")))
        check("a name that only looks like a position is read as a state",
              by_band.get("Digital / state") is None
              and bands.get("Axes[3]", [])[-1] == "Digital / state",
              str(bands.get("Axes[3]")))

        # Wiring has to survive the regrouping: every trace still has to reach
        # its acquisition, or the project opens and plots nothing.
        chk = run("checkscope", grouped)
        check("a multi-chart project is still fully wired",
              chk.get("ok") is True
              and chk.get("display_channels_wired") == len(symbols),
              f"wired={chk.get('display_channels_wired')} {chk.get('problems')}")
        check("checkscope reports the layout it would draw",
              [c["chart"] for c in chk.get("charts", [])] == titles,
              str([c["chart"] for c in chk.get("charts", [])]))

        root = ET.fromstring(grouped.read_text(encoding="utf-8-sig"))
        first_band = root.find("SubMember/YTChart/SubMember/AxisGroup")
        colours = [c.findtext("DisplayColor")
                   for c in first_band.findall("SubMember/Channel")]
        check("channels sharing an axis are drawn in different colours",
              len(set(colours)) == len(colours) and len(colours) == 2, str(colours))
        stacked = root.findtext("SubMember/YTChart/SubMember/ChartStyle/StackedAxes")
        check("a chart with several bands asks for them to be stacked",
              stacked == "true", str(stacked))

        # The escape hatch, for channels that genuinely share a scale.
        flat = Path(tmp) / "flat.tcscopex"
        made_flat = run("newscope", tpl, "-o", flat, "--netid", "1.2.3.4.1.1",
                        "--layout", "flat", "--channels", ",".join(symbols))
        check("--layout flat keeps every channel on one axis",
              len(made_flat.get("charts", [])) == 1
              and len(made_flat["charts"][0]["bands"]) == 1,
              str([c["chart"] for c in made_flat.get("charts", [])]))
        crowded = run("checkscope", flat)
        check("checkscope says when one axis is carrying too much",
              any("one value axis" in w for w in crowded.get("warnings", [])),
              str(crowded.get("warnings"))[:80])
        check("an overloaded axis is a warning, not a broken file",
              crowded.get("ok") is True, str(crowded.get("problems")))

        # A symbol listed twice is one signal, not two claims on the target's
        # bandwidth.
        twice = Path(tmp) / "twice.tcscopex"
        dup = run("newscope", tpl, "-o", twice, "--netid", "1.2.3.4.1.1",
                  "--channels", "MAIN.fbAxis.NcToPlc.ActPos,MAIN.fbAxis.NcToPlc.ActPos")
        check("a symbol asked for twice is recorded once",
              len(dup.get("channels", [])) == 1
              and run("checkscope", twice).get("acquisitions") == 1,
              str(dup.get("channels")))


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
    layout_checks()
    recordability_checks()
    second_field_session_checks()
    prefix_house_checks()
    shareability_checks()

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
