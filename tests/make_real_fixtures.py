#!/usr/bin/env python3
"""Regenerate structural copies of the real TC3ScopeExportTool.exe dialects.

Nineteen genuine exports from a Beckhoff CX/AX8000 machine (TwinCAT 3.1, EU
locale) were measured, then thrown away - recorded data carries real machine
behaviour and never belongs in git. What survives is their *structure*: row
order, metadata keys, delimiters, decimal separators, group layout and
time-column behaviour, shrunk to 200 rows and filled with synthetic signal.

Every name below is invented. Symbol paths, net IDs and hardware tags are
generic stand-ins chosen to keep the *shape* that matters - the spaces, dots,
brackets and the unbalanced parenthesis - without carrying anything that
identifies the machine they were measured on.

A Scope CSV is not `time,ch1,ch2,...`. It is a horizontal concatenation of
independent acquisition groups, each carrying its own time column:

    <t0> <a0> <a1> | <t1> <b0> <b1> <b2> | <t2> <c0>
    ^ group 0      ^ group 1             ^ group 2

so a physical row is not one instant in time. Every fixture here exists to hold
some part of that invariant in place.

Times are written in milliseconds, because that is what Scope exports contain.
The reader converts to seconds on the way in; the ground truth below is in
seconds, matching what the tool reports.

Stdlib only, like make_fixture.py - CI has to bootstrap itself before numpy
exists.

Usage:  python3 tests/make_real_fixtures.py [--out DIR]
"""

import argparse
import json
import math
import random
from pathlib import Path

ROWS = 200
STEP_MS = 200.0      # planted step, on each group's own time axis
STEP_DELTA = 25.0

# The 17 keys a TAB-dialect export writes, in file order. Reconstructed from the
# real files: the exact spelling matters because the group parser finds group
# boundaries by looking for the key token repeating along a metadata row.
TAB_KEYS = [
    "Name", "SymbolName", "SymbolComment", "NetId", "Port",
    "IndexGroup", "IndexOffset", "Data-Type", "SampleTime[ms]", "SymbolBased",
    "VariableSize", "Offset", "ScaleFactor", "BitMask", "Unit",
    "StartTime", "EndTime",
]


# --------------------------------------------------------------------------
# signal
# --------------------------------------------------------------------------

def sample(rng, group_id, channel_id, t_ms, stepped):
    """One synthetic sample. Smooth enough that a planted step stands out."""
    t = t_ms / 1000.0
    base = (10.0 + 3.0 * group_id + channel_id)
    value = base + 5.0 * math.sin(2 * math.pi * 1.5 * t + channel_id) + rng.gauss(0, 0.01)
    if stepped:
        value += STEP_DELTA
    return value


def step_channel(n_channels):
    """Channel index 3 carries the planted step, or index 0 in 1-channel groups."""
    return 3 if n_channels > 3 else 0


# --------------------------------------------------------------------------
# group timing
# --------------------------------------------------------------------------

def group_times(spec, rows):
    """Time column for one group, in milliseconds.

    Repeat-padding is what Scope does when groups run at different rates: each
    slow sample is printed on consecutive rows so every group ends on the same
    timestamp. `padded=False` reproduces the broken exports where it did not.
    """
    step_ms, offset, padded = spec["sample_time_ms"], spec["offset_ms"], spec["padded"]
    base = spec["repeat"] if padded else 1
    return [((i // base) * step_ms if padded else i * step_ms) + offset
            for i in range(rows)]


def build_columns(groups, rows, rng):
    """Return (columns, ground_truth_groups). columns[j] is one file column."""
    columns, truth = [], []
    for gid, spec in enumerate(groups):
        times = group_times(spec, rows)
        columns.append([f"{t:.6f}" for t in times])
        start_col = len(columns) - 1
        target = step_channel(spec["channels"])
        step_time = None
        for ch in range(spec["channels"]):
            col, held = [], None
            for i in range(rows):
                stepped = ch == target and times[i] >= STEP_MS
                if stepped and step_time is None:
                    step_time = times[i]
                # Repeat-padding repeats the sample, not just the timestamp:
                # a padded row is the previous value printed again.
                if i and times[i] == times[i - 1]:
                    col.append(held)
                    continue
                held = f"{sample(rng, gid, ch, times[i], stepped):.6f}"
                col.append(held)
            columns.append(col)
        truth.append({
            "group": gid,
            "start_column": start_col,
            "channels": spec["channels"],
            "sample_time_ms": spec["sample_time_ms"],
            "repeat_factor": spec["repeat"] if spec["padded"] else 1,
            "offset_ms": spec["offset_ms"],
            "padded": spec["padded"],
            "step_channel": target,
            # seconds, because that is the unit every verb reports
            "step_time_s": (step_time or 0.0) / 1000.0,
            "t_first_s": times[0] / 1000.0,
            "t_last_s": times[-1] / 1000.0,
        })
    return columns, truth


def max_skew_ms(groups, rows):
    """Largest disagreement between the groups' first or last timestamps -
    judged per group, the way the reader does, never row by row."""
    times = [group_times(g, rows) for g in groups]
    firsts, lasts = [t[0] for t in times], [t[-1] for t in times]
    return max(max(firsts) - min(firsts), max(lasts) - min(lasts))


# --------------------------------------------------------------------------
# writers
# --------------------------------------------------------------------------

def decimal_comma(text):
    return text.replace(".", ",")


def write_comma(path, groups, columns, truth, rows, blanks=False, names=None):
    """COMMA dialect: ',' delimiter, '.' decimals, a Name row and nothing else.

    Short channel names only, disambiguated with (1)/(2)/(3) suffixes that say
    nothing about which instance is which - so the qualified path a report would
    want simply is not in the file.
    """
    delim = ","
    lines = [
        "TwinCAT Scope Export",
        f"File,{path.name}",
        "StartTime,2026-07-22 09:14:03",
        "EndTime,2026-07-22 09:14:04",
        "Version,3.1.4024.35",
        "",
    ]

    name_row = []
    seen = {}
    for gid, spec in enumerate(groups):
        name_row.append("Name")
        for ch in range(spec["channels"]):
            # `names` is one list for every group, or one list per group.
            given = names[gid] if names and isinstance(names[0], list) else names
            short = (given[ch] if given else COMMA_NAMES[ch % len(COMMA_NAMES)])
            seen[short] = seen.get(short, 0) + 1
            suffix = f" ({seen[short]})" if seen[short] > 1 else ""
            name_row.append(short + suffix)
    lines.append(delim.join(name_row))

    ncols = len(columns)
    rng = random.Random(4242)
    blank_cells = 0
    time_blanks = []
    for i in range(rows):
        row = [columns[j][i] for j in range(ncols)]
        if blanks:
            # Real exports drop cells inside the data block, time columns
            # included - 7 of 19 files had between 3 and 132 of them.
            if i in (37, 118):
                row[0] = ""
                time_blanks.append(i)
                blank_cells += 1
            if i % 17 == 5:
                victim = rng.randrange(1, ncols)
                if row[victim]:
                    row[victim] = ""
                    blank_cells += 1
        lines.append(delim.join(row))

    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return {
        "delimiter": ",", "decimal": ".", "columns": ncols,
        "data_line": len(lines) - rows + 1, "rows": rows,
        "groups": truth, "blank_cells": blank_cells,
        "time_column_blanks": time_blanks,
        "max_skew_ms": max_skew_ms(groups, rows),
    }


COMMA_NAMES = ["ActPos", "ActVelo", "ActTorque", "PosDiff", "SetPos",
               "SetVelo", "CtrlOutput", "ActCurrent", "FollowErr", "Status"]

TAB_SHORT = ["ActTorque", "ActPos", "ActVelo", "PosDiff", "CtrlOut",
             "rActual", "rSetpoint", "bEnable", "nState", "rCurrent"]


def tab_symbol(gid, spec, ch):
    """A qualified symbol path, with the spaces, dots and parentheses that make
    splitting on '.' the wrong way to derive a short name.

    Names are invented; the *shape* is copied, and the shape is the whole point.
    Every NC symbol here is truncated mid-parenthesis, because that is what
    Beckhoff's own exporter writes - in the measured files every symbol under
    one axis had lost its closing bracket, identically. The reader is being
    faithful, so nothing here should ever balance it.
    """
    short = TAB_SHORT[ch % len(TAB_SHORT)]
    if spec["port"] == 501:
        return f"Axes.Linear Axis {ch + 1} (DRV_1{ch + 1:02d}_ChA.{short}"
    return f"gPlc.emTransport.fbCtrl[{ch}].{short}"


def write_tab(path, groups, columns, truth, rows, wrap_comments=False, symbols=None):
    """TAB dialect: '\\t' delimiter, EU decimal comma, 17 metadata rows.

    The decimal comma is the trap: on a TAB file every row holds exactly as many
    ',' as '\\t', so a delimiter vote decided on consistency alone elects ','.

    `symbols` is one list of SymbolNames per group. A None cell in `columns`
    ends that row there: the export writes shorter rows once a group has run
    out of samples.
    """
    delim = "\t"
    lines = [
        "TwinCAT Scope Export",
        f"File\t{path.name}",
        "StartTime\t22-7-2026 09:14:03",
        "EndTime\t22-7-2026 09:14:04",
        "Version\t3.1.4024.35",
        "",
    ]

    def metadata_row(key, value_for):
        row, idx = [], 0
        for gid, spec in enumerate(groups):
            row.append(key)
            for ch in range(spec["channels"]):
                row.append(value_for(gid, spec, ch, idx))
                idx += 1
        return row

    types = ["REAL64", "INT16", "BIT"]
    values = {
        "Name": lambda g, s, c, i: (symbols[g][c].rsplit(".", 1)[-1] if symbols
                                    else TAB_SHORT[c % len(TAB_SHORT)]),
        "SymbolName": lambda g, s, c, i: (symbols[g][c] if symbols
                                          else tab_symbol(g, s, c)),
        "SymbolComment": lambda g, s, c, i: comment_for(i, wrap_comments),
        "NetId": lambda g, s, c, i: "192.168.1.10.1.1",
        "Port": lambda g, s, c, i: str(s["port"]),
        "IndexGroup": lambda g, s, c, i: "16448",
        "IndexOffset": lambda g, s, c, i: str(1000 + c * 8),
        "Data-Type": lambda g, s, c, i: types[c % len(types)],
        "SampleTime[ms]": lambda g, s, c, i: decimal_comma(f"{s['sample_time_ms']:.6f}"),
        "SymbolBased": lambda g, s, c, i: "True",
        "VariableSize": lambda g, s, c, i: "8",
        "Offset": lambda g, s, c, i: "0",
        "ScaleFactor": lambda g, s, c, i: decimal_comma("1.000000"),
        "BitMask": lambda g, s, c, i: "0",
        # The literal string TwinCAT writes when a symbol carries no unit. It is
        # not a null and must not be coerced into one - round-tripping what the
        # source says beats guessing what it meant.
        "Unit": lambda g, s, c, i: "(None)",
        "StartTime": lambda g, s, c, i: "0",
        "EndTime": lambda g, s, c, i: "0",
    }
    for key in TAB_KEYS:
        lines.append(delim.join(metadata_row(key, values[key])))

    ncols = len(columns)
    for i in range(rows):
        row = [columns[j][i] for j in range(ncols)]
        if None in row:
            row = row[:row.index(None)]
        lines.append(delim.join(decimal_comma(cell) for cell in row))

    text = "\r\n".join(lines) + "\r\n"
    path.write_text(text, encoding="utf-8")

    physical = text.splitlines()
    data_line = len(physical) - rows + 1
    return {
        "delimiter": "\t", "decimal": ",", "columns": ncols,
        "data_line": data_line, "rows": rows, "groups": truth,
        "blank_cells": 0, "time_column_blanks": [],
        "max_skew_ms": max_skew_ms(groups, rows),
    }


def comment_for(idx, wrap):
    """Structured Text comments carry embedded newlines, so one logical metadata
    row lands across many physical lines - none of them ncols wide.

    Sixteen newlines spread across the row, reproducing the real 120-column
    file where SymbolComment alone occupied physical lines 7 to 23.
    """
    if not wrap:
        return "torque feedback"
    if idx == 0:
        return "(* torque feedback\nscaled in the drive\nsee DRV_103 *)"
    if idx % 4 == 0:
        return "(* torque feedback\nscaled in the drive *)"
    return "torque feedback"


# --------------------------------------------------------------------------
# an axis that is at rest for most of the recording
# --------------------------------------------------------------------------

AT_REST_ROWS = 1500
AT_REST_STEP_MS = 2.0
AT_REST_NAMES = ["ActPos", "ActVelo", "ActTorque", "bEnable"]
# One commanded move: park, accelerate, cruise, decelerate, park again.
MOVE_START, CRUISE_START, CRUISE_END, MOVE_END = 450, 500, 1000, 1050
CRUISE_VELO = 250.0                 # mm/s
DISTURBANCE_INDEX = 1200            # the one genuine fault, well after the move
DISTURBANCE_DELTA = 40.0            # Nm


def at_rest_columns():
    """A linear axis doing one move, plus a planted torque disturbance.

    This is the shape that made `events` unusable on real machine data, and no
    fixture had it. An axis is at rest for most of a recording, so over half its
    first differences are the encoder's quantisation floor - MAD collapses to
    ~1e-9, which is non-zero, so a threshold of 6*MAD*1.4826 flagged every
    sample of the move. One real 5000-row export produced 1199 "steps" from a
    position channel that moved exactly once.

    The dither below is what keeps MAD non-zero rather than exactly zero. That
    distinction is the whole defect: a zero MAD was already handled.
    """
    rng = random.Random(97)
    pos, cols = 0.0, {name: [] for name in AT_REST_NAMES}
    truth = {"step_time_s": None, "move_time_s": None}
    for i in range(AT_REST_ROWS):
        if i < MOVE_START or i >= MOVE_END:
            velo = 0.0
        elif i < CRUISE_START:
            velo = CRUISE_VELO * (i - MOVE_START) / (CRUISE_START - MOVE_START)
        elif i < CRUISE_END:
            velo = CRUISE_VELO
        else:
            velo = CRUISE_VELO * (MOVE_END - i) / (MOVE_END - CRUISE_END)
        pos += velo * AT_REST_STEP_MS / 1000.0

        # Torque: never at rest, so it is the control - the detector always
        # worked on channels like this one.
        t_s = i * AT_REST_STEP_MS / 1000.0
        torque = 2.0 * math.sin(2 * math.pi * 3.0 * t_s) + rng.gauss(0, 0.05)
        if MOVE_START <= i < MOVE_END:
            torque += 12.0
        if i >= DISTURBANCE_INDEX:
            torque += DISTURBANCE_DELTA
            if truth["step_time_s"] is None:
                truth["step_time_s"] = t_s
        if i == MOVE_START:
            truth["move_time_s"] = t_s

        dither = rng.uniform(-1e-9, 1e-9)
        cols["ActPos"].append(f"{round(pos, 4) + dither:.9f}")
        cols["ActVelo"].append(f"{round(velo, 4) + dither:.9f}")
        cols["ActTorque"].append(f"{torque:.9f}")
        cols["bEnable"].append(f"{1.0 if MOVE_START - 50 <= i < MOVE_END + 50 else 0.0:.6f}")

    times = [i * AT_REST_STEP_MS for i in range(AT_REST_ROWS)]
    columns = [[f"{t:.6f}" for t in times]] + [cols[n] for n in AT_REST_NAMES]
    gt = [{
        "group": 0, "start_column": 0, "channels": len(AT_REST_NAMES),
        "sample_time_ms": AT_REST_STEP_MS, "repeat_factor": 1, "offset_ms": 0.0,
        "padded": True, "step_channel": AT_REST_NAMES.index("ActTorque"),
        "step_time_s": truth["step_time_s"], "move_time_s": truth["move_time_s"],
        "step_delta": DISTURBANCE_DELTA,
        "at_rest_fraction": 1.0 - (MOVE_END - MOVE_START) / AT_REST_ROWS,
        "t_first_s": 0.0, "t_last_s": times[-1] / 1000.0,
    }]
    return columns, gt


# --------------------------------------------------------------------------
# a 2 ms and a 4 ms group over 60 s, in both layouts a real export uses
# --------------------------------------------------------------------------

TWO_RATE_SPAN_MS = 60_000
TWO_RATE_SYMBOLS = [["Axes.Axis1.ActPos"], ["MAIN.bFlag"]]
TWO_RATE_LAG_S = 0.1     # bFlag follows ActPos's sign this much later


def two_rate_columns(layout):
    """Two groups, one channel each, both covering the same 60 s.

    'padded': the 4 ms group repeats each sample on the next row - times
    0,0,4,4,... - so every row is full, 30001 of them.
    'truncated': the 4 ms group writes its 15001 samples on the first 15001
    rows, and every row after that carries the 2 ms group alone.

    In both a row is not one instant, and in both the two groups start and end
    together - which is what makes the file sound for cross-group timing. The
    truncated layout disagrees row by row by up to 30 s.
    """
    rng = random.Random(61)
    fast = [i * 2.0 for i in range(TWO_RATE_SPAN_MS // 2 + 1)]
    rows = len(fast)
    if layout == "padded":
        slow = [(i // 2) * 4.0 for i in range(rows)]
    else:
        slow = [i * 4.0 for i in range(TWO_RATE_SPAN_MS // 4 + 1)]
        slow += [None] * (rows - len(slow))

    def pos(t_ms):
        return 100.0 * math.sin(2 * math.pi * 0.5 * t_ms / 1000.0)

    act_pos = [f"{pos(t) + rng.gauss(0, 0.01):.6f}" for t in fast]
    flag = [None if t is None else
            f"{1.0 if pos(t - TWO_RATE_LAG_S * 1000.0) > 0 else 0.0:.6f}" for t in slow]
    columns = [[f"{t:.6f}" for t in fast], act_pos,
               [None if t is None else f"{t:.6f}" for t in slow], flag]
    samples = len({t for t in slow if t is not None})
    truth = [
        {"group": 0, "start_column": 0, "channels": 1, "sample_time_ms": 2.0,
         "repeat_factor": 1, "n_samples": rows,
         "t_first_s": 0.0, "t_last_s": TWO_RATE_SPAN_MS / 1000.0},
        {"group": 1, "start_column": 2, "channels": 1, "sample_time_ms": 4.0,
         "repeat_factor": 2 if layout == "padded" else 1, "n_samples": samples,
         "t_first_s": 0.0, "t_last_s": TWO_RATE_SPAN_MS / 1000.0},
    ]
    return columns, truth, rows


# --------------------------------------------------------------------------

def spec(channels, sample_time_ms, base_ms, offset_ms=0.0, padded=True, port=851):
    return {"channels": channels, "sample_time_ms": sample_time_ms,
            "repeat": int(sample_time_ms / base_ms), "offset_ms": offset_ms,
            "padded": padded, "port": port}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "fixtures" / "real"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    truth = {}

    # 34 columns, 3 groups at 2/4/12 ms, repeat 1/2/6. Skew reaches 10 ms, which
    # is one PLC cycle - enough to invert a cause-and-effect ordering.
    groups = [spec(14, 2, 2), spec(15, 4, 2), spec(2, 12, 2)]
    cols, gt = build_columns(groups, ROWS, random.Random(1))
    truth["real_comma_3group.csv"] = write_comma(
        out / "real_comma_3group.csv", groups, cols, gt, ROWS)

    # 37 columns, negative start offsets, blank cells including two in time
    # column 0 - which is what poisons a median taken over np.diff.
    groups = [spec(14, 2, 2), spec(18, 2, 2, offset_ms=-2.0), spec(2, 4, 2, offset_ms=-8.0)]
    cols, gt = build_columns(groups, ROWS, random.Random(2))
    truth["real_comma_blanks.csv"] = write_comma(
        out / "real_comma_blanks.csv", groups, cols, gt, ROWS, blanks=True)

    # 56 columns, two groups: NC task on port 501, PLC task on port 851.
    groups = [spec(24, 2, 2, port=501), spec(30, 4, 2, port=851)]
    cols, gt = build_columns(groups, ROWS, random.Random(3))
    truth["real_tab_2group.csv"] = write_tab(
        out / "real_tab_2group.csv", groups, cols, gt, ROWS)

    # 76 columns, 38 one-channel groups, and the slow half never repeat-padded:
    # the 4 ms groups are stretched over twice the wall-clock span of the 2 ms
    # ones. No conclusion about their relative timing is valid.
    groups = ([spec(1, 2, 2, padded=False, port=501) for _ in range(24)] +
              [spec(1, 4, 2, padded=False, port=851) for _ in range(14)])
    cols, gt = build_columns(groups, ROWS, random.Random(4))
    truth["real_tab_pergroup_skewed.csv"] = write_tab(
        out / "real_tab_pergroup_skewed.csv", groups, cols, gt, ROWS)

    # 120 columns, 60 one-channel groups, one rate, multi-line comments.
    groups = [spec(1, 4, 4, port=851) for _ in range(60)]
    cols, gt = build_columns(groups, ROWS, random.Random(5))
    truth["real_tab_pergroup_single.csv"] = write_tab(
        out / "real_tab_pergroup_single.csv", groups, cols, gt, ROWS,
        wrap_comments=True)

    # One axis, at rest for 60% of the recording, with one commanded move and
    # one planted torque disturbance. Signal shape rather than dialect: this is
    # the file that says whether `events` is usable on real machine data.
    groups = [spec(len(AT_REST_NAMES), AT_REST_STEP_MS, AT_REST_STEP_MS)]
    cols, gt = at_rest_columns()
    truth["real_comma_atrest.csv"] = write_comma(
        out / "real_comma_atrest.csv", groups, cols, gt, AT_REST_ROWS,
        names=AT_REST_NAMES)

    # A 2 ms and a 4 ms group over 60 s, in the two layouts real exports use
    # for a slow group: repeat-padded, and truncated into shorter rows.
    for layout in ("padded", "truncated"):
        groups = [spec(1, 2, 2, port=501), spec(1, 4, 2, padded=layout == "padded")]
        cols, gt, rows = two_rate_columns(layout)
        name = f"real_tab_2rate_{layout}.csv"
        meta = write_tab(out / name, groups, cols, gt, rows, symbols=TWO_RATE_SYMBOLS)
        meta["max_skew_ms"] = 0.0     # both groups span exactly 0 to 60 s
        meta["lag_s"] = TWO_RATE_LAG_S
        truth[name] = meta

    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(json.dumps(
        {"ok": True,
         "written": [name for name in sorted(truth)],
         "summary": {name: {"columns": t["columns"], "groups": len(t["groups"]),
                            "channels": sum(g["channels"] for g in t["groups"]),
                            "data_line": t["data_line"],
                            "max_skew_ms": t["max_skew_ms"]}
                     for name, t in sorted(truth.items())}},
        indent=2))


if __name__ == "__main__":
    main()
