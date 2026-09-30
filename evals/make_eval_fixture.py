#!/usr/bin/env python3
"""Build the fixtures the eval prompts point at.

The evals need files with a *planted trap* rather than a planted defect,
which is why they are not in tests/. A test fixture asks "does the
reader parse this correctly". An eval fixture asks "does an agent reading this
reach the wrong conclusion", and that needs the wrong conclusion to be
specific, confident and checkable.

Every file is given a plausible machine name and the ground truth is written
one directory *up*, never beside the data. An eval where the answer key sits
in the same folder as the fixture measures nothing but curiosity, and the
`tests/fixtures/` files cannot be used directly for exactly that reason: their
`ground_truth.json` is right there next to them.

Written here:

  clamp_station_export.csv   A broken two-group TAB export. Group 1 was never
                      repeat-padded, so its clock runs at twice wall-clock
                      against group 0. Read as one table - one time column,
                      one instant per row - it says the torque spike came at
                      0.40 s, before the following-error step at 0.60 s.
                      On group 1's own clock the spike is at 0.80 s, after.
                      So the naive read does not merely lose precision: it
                      inverts cause and effect and sends the engineer to the
                      wrong subsystem.

                      The honest answer is neither ordering. The export is
                      broken and no cross-group timing claim from it means
                      anything - which is what `manifest` says in the
                      `timing.note` field.

  axis1_run_20260722.csv     Twenty seconds of one axis at 1 kHz, 20,000 rows,
                      with the defects tests/make_fixture.py plants at the same
                      times: a three-sample following-error spike at 12.0 s, a
                      position step at 6.0 s, a frozen torque channel from 15 to
                      17 s, and a velocity channel clipped at +/-8.0. Since
                      iteration 4 the axis makes uneven point-to-point moves
                      with drift, friction and noise, in Scope View's own ','
                      dialect - not clean sines under a "Synthetic" preamble.

  filler_overnight.svdx      A saved recording "armed" on a jam sensor whose
                      trigger action is NONE (Set Mark): one fixed 60 s window.

  Commissioning_Axis1.tcscopex   A hand-written project with the NC axis
                      channels on port 851 and typed LREAL.

  Line2_Clamp_Scope.tcscopex A hand-written project with the PLC channels on
                      801, TwinCAT 2's PLC port. Since iteration 6 the sample
                      time is right: iteration 5 wrote 1 for 1 ms, and baselines
                      decoded it from RecordTime in the same file.

  nightly_export.cmd         A batch file that runs TC3ScopeExportTool.exe every
                      morning: no `silent`, channellist= separated by ',' and
                      start=/end= in milliseconds. The tool answers all three
                      with exit 0, and none of them is visible in the file.

  press_axis3_export.csv     A Scope View export by hand whose torque channel
                      carries ScaleFactor 2 and Offset 10. The header is the
                      same whether 'Scale values before export' was on or off,
                      and the two readings straddle the 150 % in the question.

  AxisDiagnosis.tcscopex     A scope project whose display channel reaches for
                      an AcquisitionGUID that no acquisition node carries. It
                      opens perfectly in Scope View and records nothing. The
                      failure that looks like success.

The CSV dialect writer is imported from tests/make_real_fixtures.py rather
than copied: format knowledge lives there and must not fork. What lives here
is only the scenario.

Stdlib only, like the fixture generators it borrows from.

Usage:  python3 evals/make_eval_fixture.py [--out DIR]
"""

import argparse
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import make_fixture  # noqa: E402  (path set above)
from make_real_fixtures import (  # noqa: E402
    group_times,
    max_skew_ms,
    sample,
    spec,
    write_comma,
    write_tab,
)

ROWS = 1000

# Plausible machine names. A file called `skewed_export.csv` answers half the
# question before the agent opens it.
SKEWED = "clamp_station_export.csv"
PLANTED = "axis1_run_20260722.csv"
UNWIRED = "AxisDiagnosis.tcscopex"
SCALED = "axis_run_20260904.csv"

# The scaled twin of PLANTED, written only with --scale.
#
# Iteration 1 scored 6/6 in both arms on the needle and the saturated channel,
# and the reason turned out to be the fixture: 20 000 rows is a haystack you
# can tip out onto the table. A baseline that loads the whole file and takes
# diff().abs().max() finds a three-sample spike every time.
#
# SKILL.md's opening argument is ten minutes of twenty channels at 1 kHz -
# 12 million samples, a few hundred MB. That is 600 000 ROWS by 20 channels,
# not 12 million rows, and is entirely writable from stdlib Python if the rows
# are streamed rather than accumulated.
#
# Same defect kinds as PLANTED so the ground truth carries over, but placed
# where nothing draws the eye: not on a round second, and inside the middle
# 80% so that head, tail and any coarse decimation step over them.
SCALE_ROWS = 600_000                 # ten minutes at 1 kHz
SCALE_AXES = 4                       # x 5 signals = 20 channels = 12M samples
SCALE_SPIKE_ROW = 413_777            # 413.777 s
SCALE_STEP_ROW = 128_431             # 128.431 s
SCALE_FLAT_ROWS = (291_004, 293_517)  # 291.004 - 293.517 s
SCALE_SIGNALS = ("ActPos", "SetPos", "ActVelo", "ActTorque", "PosDiff")

# Group 0 runs at 2 ms and is padded, so its time column is the wall clock.
# Group 1 declares 4 ms and was never padded, so row i lands at 4i ms on its
# own clock while group 0's column says 2i. Every group-1 timestamp read off
# group 0's column is therefore exactly half of the truth.
STEP_ROW = 300        # PosDiff step: 0.600 s, and group 0 is the honest clock
SPIKE_ROW = 200       # ActTorque spike: 0.400 s read naively, 0.800 s in truth
STEP_DELTA = 4.0      # following error jumps, in the same units as the channel
SPIKE_DELTA = 45.0    # torque spike, three samples wide
SPIKE_WIDTH = 3

# The multi-rate export: 1 ms and 10 ms groups, both correctly padded.
MULTIRATE = "press_line_export.csv"
MULTIRATE_ERROR_ROW = 405    # following error steps at 0.405 s
MULTIRATE_TORQUE_ROW = 410   # first torque sample to read high: 0.410 s


def build_columns(groups, rows, rng, events):
    """Like make_real_fixtures.build_columns, but the events are placed by hand.

    `events` maps (group, channel) to a dict describing what to plant at which
    row. The stock builder plants one step per group at a fixed time, which is
    right for testing a parser and useless for posing a question.
    """
    columns, truth = [], []
    for gid, group in enumerate(groups):
        times = group_times(group, rows)
        columns.append([f"{t:.6f}" for t in times])
        start_col = len(columns) - 1
        planted = []

        for ch in range(group["channels"]):
            event = events.get((gid, ch))
            col, held = [], None
            for i in range(rows):
                # A padded row repeats the previous sample, value included.
                if i and times[i] == times[i - 1]:
                    col.append(held)
                    continue
                value = sample(rng, gid, ch, times[i], stepped=False)
                if event:
                    value += offset_for(event, i)
                held = f"{value:.6f}"
                col.append(held)

            if event:
                planted.append({
                    "channel": ch,
                    "kind": event["kind"],
                    # Both clocks, because the gap between them is the eval.
                    "true_time_s": times[event["row"]] / 1000.0,
                    "naive_time_s": group_times(groups[0], rows)[event["row"]] / 1000.0,
                })
            columns.append(col)

        truth.append({
            "group": gid,
            "start_column": start_col,
            "channels": group["channels"],
            "sample_time_ms": group["sample_time_ms"],
            "repeat_factor": group["repeat"] if group["padded"] else 1,
            "offset_ms": group["offset_ms"],
            "padded": group["padded"],
            "planted": planted,
            "t_first_s": times[0] / 1000.0,
            "t_last_s": times[-1] / 1000.0,
        })
    return columns, truth


def offset_for(event, row):
    """How much the planted event adds to the signal at this row."""
    if event["kind"] == "step":
        return event["delta"] if row >= event["row"] else 0.0
    # A spike is three samples wide: narrow enough that decimating the file to
    # a plottable size has a good chance of stepping straight over it.
    if event["row"] <= row < event["row"] + event["width"]:
        return event["delta"]
    return 0.0


def write_skewed(out):
    """The broken export. Channel names come from the writer: index 0 is
    ActTorque and index 3 is PosDiff, which is what the prompt asks about."""
    groups = [
        spec(4, 2, 2, port=501),                  # padded: the honest clock
        spec(4, 4, 2, padded=False, port=851),    # never padded: runs off alone
    ]
    events = {
        (0, 3): {"kind": "step", "row": STEP_ROW, "delta": STEP_DELTA},
        (1, 0): {"kind": "spike", "row": SPIKE_ROW,
                 "delta": SPIKE_DELTA, "width": SPIKE_WIDTH},
    }
    columns, truth = build_columns(groups, ROWS, random.Random(7), events)
    meta = write_tab(out / SKEWED, groups, columns, truth, ROWS)
    meta["max_skew_ms"] = max_skew_ms(groups, ROWS)
    return meta


def point_to_point(rng, seconds, rate_hz):
    """Commanded (position, velocity, acceleration) per sample for an axis
    doing uneven point-to-point moves: trapezoidal profiles of random length,
    speed and direction, with dwells of random length between them.

    Iteration 3's baselines fitted the old fixture's pure sines to 0.02
    residuals, and a defect is trivial to find against a model that exact. A
    real axis moves, stops and moves again, so this one does.
    """
    n = int(seconds * rate_hz)
    pos, vel, acc = [0.0] * n, [0.0] * n, [0.0] * n
    x, i = 0.0, 0
    while i < n:
        dwell = int(rng.uniform(0.15, 1.3) * rate_hz)
        for _ in range(dwell):
            if i >= n:
                break
            pos[i] = x
            i += 1
        distance = rng.uniform(30.0, 110.0) * rng.choice((-1, 1))
        vmax, a = rng.uniform(55.0, 85.0), rng.uniform(600.0, 900.0)
        # Trapezoid, or triangle when the move is too short to reach vmax.
        ramp = min(vmax / a, (abs(distance) / a) ** 0.5)
        cruise = max(0.0, (abs(distance) - a * ramp * ramp) / (a * ramp)) if ramp else 0.0
        sign = 1.0 if distance > 0 else -1.0
        t, total = 0.0, 2 * ramp + cruise
        while t < total and i < n:
            if t < ramp:
                v, ac = a * t, a
            elif t < ramp + cruise:
                v, ac = a * ramp, 0.0
            else:
                v, ac = a * max(0.0, total - t), -a
            x += sign * v / rate_hz
            pos[i], vel[i], acc[i] = x, sign * v, sign * ac
            t += 1.0 / rate_hz
            i += 1
    return pos, vel, acc


PLANTED_SIGNALS = ["ActPos", "SetPos", "ActVelo", "ActTorque", "PosDiff"]


def write_planted(out):
    """Twenty seconds of one axis at 1 kHz with four planted defects, in Scope
    View's own `,` dialect.

    The defects and their times are the test generator's, so the checks carry
    over: a three-sample following-error spike at 12.0 s, a position step at
    6.0 s, the torque frozen from 15 to 17 s, and the velocity clipped at
    +/-8.0. What changed in iteration 4 is everything around them - moves,
    dwells, drift, friction and noise instead of clean sines, and no
    "Synthetic scope export" in the preamble, which agents read as a tell.
    """
    rate, seconds = make_fixture.RATE_HZ, make_fixture.DURATION_S
    clip = make_fixture.CLIP_LIMIT
    # The first seed whose run is moving across the frozen-torque window: a
    # torque frozen during a dwell would be a much weaker finding.
    for seed in range(20260722, 20260822):
        rng = random.Random(seed)
        setpos, vel, acc = point_to_point(rng, seconds, rate)
        lo, hi = int(make_fixture.FLAT_START * rate), int(make_fixture.FLAT_END * rate)
        if sum(abs(v) > 20 for v in vel[lo:hi]) > 0.5 * (hi - lo):
            break
    else:
        raise SystemExit("no seed keeps the axis moving across the frozen-torque window")
    rows = len(setpos)
    step_row = int(make_fixture.STEP_TIME * rate)
    spike_rows = range(int(make_fixture.SPIKE_TIME * rate) - 1,
                       int(make_fixture.SPIKE_TIME * rate) - 1 + make_fixture.SPIKE_WIDTH)

    columns = [[f"{i * 1000.0 / rate:.6f}" for i in range(rows)]] + [[] for _ in PLANTED_SIGNALS]
    frozen = None
    for i in range(rows):
        t = i / rate
        lag = 0.00012 * acc[i] + 0.0004 * vel[i] + 0.004 * math.sin(setpos[i] / 5.0 * 2 * math.pi)
        lag += rng.gauss(0, 0.002)
        if i in spike_rows:
            lag += 4.0
        drift = 0.004 * t + 0.01 * math.sin(2 * math.pi * t / 13.0)
        actpos = setpos[i] - lag + drift + rng.gauss(0, 0.003)
        if i >= step_row:
            actpos += 12.0
        velo = max(-clip, min(clip, vel[i] + rng.gauss(0, 0.08)))
        friction = 0.35 * (1 if vel[i] > 0.5 else -1 if vel[i] < -0.5 else 0)
        torque = 1.2 + 0.01 * t / seconds + friction + 0.0009 * acc[i] + rng.gauss(0, 0.015)
        if make_fixture.FLAT_START <= t <= make_fixture.FLAT_END:
            frozen = torque if frozen is None else frozen
            torque = frozen
        for col, value in zip(columns[1:], (actpos, setpos[i], velo, torque, lag)):
            col.append(f"{value:.6f}")

    groups = [spec(len(PLANTED_SIGNALS), 1, 1, port=501)]
    path = out / PLANTED
    write_comma(path, groups, columns, [], rows, names=PLANTED_SIGNALS)
    # The shared writer stamps a one-second span; this run is twenty.
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("EndTime,2026-07-22 09:14:04", "EndTime,2026-07-22 09:14:23"),
                    encoding="utf-8", newline="")
    return {
        "rows": rows,
        "rate_hz": rate,
        "duration_s": seconds,
        "seed": seed,
        "planted": {
            "step": {"channel": "ActPos", "time_s": make_fixture.STEP_TIME, "delta": 12.0},
            "spike": {"channel": "PosDiff", "time_s": make_fixture.SPIKE_TIME,
                      "width_samples": make_fixture.SPIKE_WIDTH, "amplitude": 4.0},
            "flatline": {"channel": "ActTorque",
                         "start_s": make_fixture.FLAT_START, "end_s": make_fixture.FLAT_END},
            "clipping": {"channel": "ActVelo", "limit": clip,
                         "true_amplitude": round(max(abs(v) for v in vel), 1),
                         "note": "the recorded maximum is the clip, not the peak"},
        },
        "not_defects": "SetPos holds bit-exact during every dwell, and ActPos drifts by a "
                       "few hundredths - both are what a real axis does.",
    }


def write_scaled(out, rows=SCALE_ROWS, axes=SCALE_AXES):
    """The same recording at the scale the skill's argument is about.

    Streamed a row at a time: the whole point is a file too big to hold, and
    building the list first would defeat both the fixture and the machine
    generating it. Only axis 1 carries the defects; the other axes are there to
    be the haystack, which is what 20 000 rows never were.
    """
    import math
    import random

    rate_hz = make_fixture.RATE_HZ
    clip = make_fixture.CLIP_LIMIT
    header = ["Time"] + [f"Axis{a + 1}.{sig}"
                         for a in range(axes) for sig in SCALE_SIGNALS]
    rng = random.Random(20260904)
    path = out / SCALED

    with path.open("w", encoding="utf-8", newline="") as handle:
        for line in ("TwinCAT Scope Export",
                     f"File,{SCALED}",
                     "StartTime,2026-09-04 06:00:00",
                     "EndTime,2026-09-04 06:10:00",
                     "Version,3.1.4024.35",
                     "",
                     ",".join(header)):
            handle.write(line + "\r\n")

        for i in range(rows):
            t = i / rate_hz
            values = [f"{t * make_fixture.MS_PER_S:.6f}"]
            for axis in range(axes):
                phase = axis * 0.4
                pos = 50.0 * math.sin(2 * math.pi * 0.25 * t + phase) + rng.gauss(0, 0.02)
                setpos = 50.0 * math.sin(2 * math.pi * 0.25 * t + phase)
                velo = 78.5 * math.cos(2 * math.pi * 0.25 * t + phase)
                torque = 1.5 + 0.4 * math.sin(2 * math.pi * 3.0 * t + phase) + rng.gauss(0, 0.01)
                lag = 0.05 * math.sin(2 * math.pi * 0.25 * t + phase) + rng.gauss(0, 0.002)

                if axis == 0:
                    # Axis 1 is the one the questions are about.
                    if i >= SCALE_STEP_ROW:
                        pos += 12.0
                    velo = max(-clip, min(clip, velo + rng.gauss(0, 0.05)))
                    if SCALE_FLAT_ROWS[0] <= i <= SCALE_FLAT_ROWS[1]:
                        torque = 1.5
                    if abs(i - SCALE_SPIKE_ROW) <= make_fixture.SPIKE_WIDTH // 2:
                        lag += 4.0
                else:
                    # The others move, and none of them saturates: a channel
                    # pinned at a rail has to be a finding, not the house style.
                    velo = velo * 0.35 + rng.gauss(0, 0.05)

                values.extend(f"{v:.6f}" for v in (pos, setpos, velo, torque, lag))
            handle.write(",".join(values) + "\r\n")

    return {
        "rows": rows,
        "channels": len(header) - 1,
        "samples": rows * (len(header) - 1),
        "rate_hz": rate_hz,
        "duration_s": rows / rate_hz,
        "size_bytes": path.stat().st_size,
        "planted": {
            "step": {"channel": "Axis1.ActPos",
                     "time_s": SCALE_STEP_ROW / rate_hz, "delta": 12.0},
            "spike": {"channel": "Axis1.PosDiff",
                      "time_s": SCALE_SPIKE_ROW / rate_hz,
                      "width_samples": make_fixture.SPIKE_WIDTH, "amplitude": 4.0},
            "flatline": {"channel": "Axis1.ActTorque",
                         "start_s": SCALE_FLAT_ROWS[0] / rate_hz,
                         "end_s": SCALE_FLAT_ROWS[1] / rate_hz},
            "clipping": {"channel": "Axis1.ActVelo", "limit": clip,
                         "true_amplitude": 78.5,
                         "note": "the recorded maximum is the clip, not the peak"},
        },
        "note": "Only Axis1 carries defects. Axes 2-4 are the haystack.",
    }


def write_multirate(out):
    """A valid, padded export with the two channels asked about on different rates.

    Group 0 samples at 1 ms and carries the following error, which steps at
    0.405 s. Group 1 samples at 10 ms and carries the torque: it reads normal
    at 0.400 s and high at 0.410 s. Read as one table, error first by 5 ms. On
    the data, the torque rose somewhere in (0.400, 0.410], and 0.405 is inside
    it: the order is not in the file, however valid the file is.
    """
    groups = [spec(3, 1, 1, port=501), spec(2, 10, 1, port=851)]
    names = [["PosDiff", "ActPos", "SetPos"], ["ActTorque", "ActCurrent"]]
    events = {
        (0, 0): {"kind": "step", "row": MULTIRATE_ERROR_ROW, "delta": STEP_DELTA},
        # One slow sample wide: padding repeats it on the next nine rows.
        (1, 0): {"kind": "spike", "row": MULTIRATE_TORQUE_ROW,
                 "delta": SPIKE_DELTA, "width": 1},
    }
    columns, truth = build_columns(groups, ROWS, random.Random(11), events)
    meta = write_comma(out / MULTIRATE, groups, columns, truth, ROWS, names=names)
    return meta


NULL_GUID = "00000000-0000-0000-0000-000000000000"
DANGLING = "deadbeef-0000-4000-8000-000000000000"


def write_unwired(out):
    """Point the display channel at an acquisition that does not exist.

    The template's placeholders are filled in first, deliberately. Left as
    shipped they are a second, far more visible defect, and an agent could
    score by spotting `PLACEHOLDER.Symbol` without ever following the GUID.
    Filling them leaves a project that reads as finished and production-ready,
    where the only thing wrong is a reference one level of indirection away.
    """
    src = (ROOT / "templates" / "minimal-single-channel.tcscopex").read_text(encoding="utf-8")
    src = src.replace("PLACEHOLDER.Symbol", "MAIN.fbAxis.NcToPlc.ActPos")
    src = src.replace("<AmsNetId>0.0.0.0.0.0</AmsNetId>",
                      "<AmsNetId>1.2.3.4.1.1</AmsNetId>")

    target = "<AcquisitionGUID>"
    start = src.index(target) + len(target)
    end = src.index("</AcquisitionGUID>", start)
    original = src[start:end]
    if original.strip() in ("", NULL_GUID):
        raise SystemExit("template's AcquisitionGUID is already unset - nothing to break")
    dst = src[:start] + DANGLING + src[end:]
    (out / UNWIRED).write_text(dst, encoding="utf-8")
    return {"was": original, "now": DANGLING}


TCSCOPE = ROOT / "scripts" / "tcscope.py"
ARMED = "filler_overnight.svdx"
RING_SECONDS = 600
HANDWRITTEN = "Commissioning_Axis1.tcscopex"
# NC axis fields plus one PLC state variable, as someone would write them for a
# commissioning visit. The symbol spelling is the one SKILL.md uses.
HANDWRITTEN_CHANNELS = ("Axes.Axis1.ActPos,Axes.Axis1.PosDiff,Axes.Axis1.ActTorque,"
                        "MAIN.fbStation.nState:INT")


def generated_project(path, channels):
    """A correct project from this skill's own generator, as the starting point
    each trap is then written into. newscope needs no third-party packages."""
    subprocess.run([sys.executable, str(TCSCOPE), "newscope",
                    str(ROOT / "templates" / "axis-diagnosis.tcscopex"),
                    "-o", str(path), "--channels", channels, "--netid", "1.2.3.4.1.1"],
                   check=True, capture_output=True)
    return path.read_text(encoding="utf-8-sig")


def write_handwritten(out):
    """A project that reads as finished and records nothing on its axis channels.

    Two mistakes a careful engineer makes by hand, each of which looks right:
    the NC axis symbols are on port 851 - the PLC's port, where every other
    symbol in the project lives - and they are typed LREAL, the IEC name the
    PLC declaration uses. NC symbols are served on 501, so on 851 Scope reports
    them unknown; and Scope reads LREAL as VOID and refuses the channel. Both
    were measured in the field. The PLC channel is correct, so the file is not
    uniformly wrong.
    """
    src = generated_project(out / HANDWRITTEN, HANDWRITTEN_CHANNELS)
    src = src.replace("<TargetPort>501</TargetPort>", "<TargetPort>851</TargetPort>")
    src = src.replace("<DataType>REAL64</DataType>", "<DataType>LREAL</DataType>")
    (out / HANDWRITTEN).write_text(src, encoding="utf-8-sig")
    return {
        "why": "NC axis symbols on the PLC port (851, must be 501) and typed LREAL "
               "(must be REAL64); the PLC channel MAIN.fbStation.nState is correct",
        "defects": {"port": {"channels": 3, "written": 851, "correct": 501},
                    "data_type": {"channels": 3, "written": "LREAL", "correct": "REAL64"}},
        "the_trap": "851 is the PLC's port and LREAL the IEC type, so both look right "
                    "to anyone who knows the PLC side; neither records",
    }


# A TriggerGroup as Scope writes one (element names observed in saved real
# projects; the channel condition inside ChannelTriggerSet is left out). Its
# action is NONE, which is how the dropdown's "Set Mark" is stored.
SET_MARK_GROUP = (
    "<SubMember><TriggerGroup>"
    "<AutoDeleteCapacity>0</AutoDeleteCapacity><AutoDeleteMode>Disabled</AutoDeleteMode>"
    "<Category>None</Category><ClearChart>false</ClearChart><Enabled>true</Enabled>"
    "<IsReleased>true</IsReleased><PosttriggerTime>0</PosttriggerTime>"
    "<PretriggerTime>0</PretriggerTime><RestartRecord>false</RestartRecord>"
    "<TriggerAction>NONE</TriggerAction>"
    "<ChannelTriggerSet><CombineOption>AND</CombineOption>"
    "<ReleaseOption>RisingEdge</ReleaseOption></ChannelTriggerSet>"
    "</TriggerGroup></SubMember>")


def write_ring_buffer(out):
    """A recording left running overnight as a ring buffer, stopped in the morning.

    Iteration 4's version of this eval gave a fixed 60 s window (AutoStop), and
    the baselines read that off the plain XML without any Scope knowledge. Here
    the project's StopMode is ClientStop - Scope View's "Ringbuffer" property,
    as a real save showed - with a 600 s RecordTime. A ring buffer records until
    someone stops it and keeps the last RecordTime before the stop. The trigger
    is Set Mark (NONE), so the jam did not stop it: the user did, hours later,
    and the file holds the ten minutes before that. "ClientStop" reads as
    "recorded until you stopped it", which is exactly the wrong conclusion.

    The trigger's channel condition is still left out: its schema has not been
    seen in a real file, and the answer no longer depends on it.
    """
    work = out / "_ring.tcscopex"
    subprocess.run([sys.executable, str(TCSCOPE), "newscope",
                    str(ROOT / "templates" / "axis-diagnosis.tcscopex"), "-o", str(work),
                    "--channels", "MAIN.fbFiller.bJamSensor:BOOL,MAIN.fbFiller.nState:INT,"
                                  "Axes.Axis1.ActPos,Axes.Axis1.ActTorque",
                    "--netid", "1.2.3.4.1.1", "--record-time", str(RING_SECONDS)],
                   check=True, capture_output=True)
    src = work.read_text(encoding="utf-8-sig")
    work.unlink()
    src, n = re.subn(r"(<TriggerModule[^>]*>\s*)<SubMember />", r"\1" + SET_MARK_GROUP,
                     src, count=1)
    if n != 1:
        raise SystemExit("template has no empty TriggerModule to arm")
    if src.count("<StopMode>AutoStop</StopMode>") != 1:
        raise SystemExit("template has no StopMode to turn into a ring buffer")
    src = src.replace("<StopMode>AutoStop</StopMode>", "<StopMode>ClientStop</StopMode>")
    # Stand-in sample bytes, sized like ten minutes of these four channels at
    # 1 ms, so the file's size says nothing a whole night would.
    samples = random.Random(3120).randbytes(RING_SECONDS * 1000 * 20)
    (out / ARMED).write_bytes(samples + src.encode("utf-8"))
    return {
        "why": "StopMode ClientStop is Scope View's Ringbuffer: it keeps the last "
               f"{RING_SECONDS} s before the stop; the trigger is Set Mark (NONE), so the "
               "user's stop in the morning ended it, not the jam",
        "record_seconds": RING_SECONDS,
        "stop_mode": "ClientStop",
        "trigger_action": "NONE",
        "the_trap": "'ClientStop' reads as 'recorded all night until you stopped it', so "
                    "the 03:12 jam should be in the file; it holds only the ten minutes "
                    "before the morning stop",
        "samples_note": "the sample bytes are random: the answer is in the project, and "
                        "an agent without the export tool cannot read samples anyway",
    }


SECOND_SITE = "Line2_Clamp_Scope.tcscopex"
SECOND_SITE_CHANNELS = ("Axes.Axis2.ActPos,Axes.Axis2.PosDiff,"
                        "MAIN.fbClamp2.bClamped:BOOL,MAIN.fbStation2.nState:INT")


def write_second_site(out):
    """A hand-written config whose PLC channels are on a TwinCAT 2 port.

    801 is where the PLC runtime answered in TwinCAT 2; a TwinCAT 3 PLC starts
    at 851, so the PLC channels find nothing. It looks right to anyone who
    learned the ports from older documentation. The NC channels on 501 are
    correct, so the file is not uniformly wrong.

    Iteration 5 also wrote BaseSampleTime 1 (100 ns, meant as 1 ms). Baselines
    decoded it from RecordTime, which the same file writes in the same ticks,
    so that half measured nothing and is gone.
    """
    src = generated_project(out / SECOND_SITE, SECOND_SITE_CHANNELS)
    if src.count("<TargetPort>851</TargetPort>") != 2:
        raise SystemExit("expected two PLC channels on 851 to rewrite")
    src = src.replace("<TargetPort>851</TargetPort>", "<TargetPort>801</TargetPort>")
    (out / SECOND_SITE).write_text(src, encoding="utf-8-sig")
    return {
        "why": "the two PLC channels are on 801, a TwinCAT 2 port - TC3 PLC runtimes "
               "start at 851; the NC channels on 501 and the 1 ms sample time "
               "(BaseSampleTime 10000) are correct",
        "defects": {"port": {"channels": 2, "written": 801, "correct": 851}},
        "the_trap": "801 is the PLC port in TwinCAT 2 documentation, and nothing else in "
                    "the file is wrong",
    }


EXPORT_SCRIPT = "nightly_export.cmd"
# Every line of it is something a careful engineer writes after reading the
# tool's parameter list. Paths hold no spaces, so the one generic mistake a
# reviewer would catch without knowing the tool is not there to catch.
EXPORT_SCRIPT_TEXT = r"""@echo off
rem Every morning at 07:00 (Task Scheduler, scope PC): export the jam window
rem from last night's filler recording for the analysis PC.
rem The recording starts at 00:00, so 03:00-03:10 is 10800000-11400000 ms in.

set EXPORT=C:\TwinCAT\Functions\TF3300-Scope-Server\TC3ScopeExportTool.exe
set REC=D:\ScopeData\filler_night.svdx
set OUT=D:\Exports\filler_0300_0310.csv

"%EXPORT%" svd=%REC% target=%OUT% channellist=ActPos,ActTorque,bJamSensor start=10800000 end=11400000

if errorlevel 1 (
    echo %date% %time% export FAILED >> D:\Exports\export.log
) else (
    echo %date% %time% export OK >> D:\Exports\export.log
)
"""


def write_export_script(out):
    """A scheduled export that runs, exits 0 and does none of what was meant.

    Three things TC3ScopeExportTool.exe does, each verified against the real
    tool (references/export-tool.md): without `silent` it opens a window and
    waits, so a scheduled task never finishes; channellist= separates names
    with ';', and ',' is ignored - every channel is exported; start= and end=
    are absolute FILETIME ticks (UTC, 100 ns since 1601), and milliseconds are
    ignored - the full range is exported. The last two exit 0, so the
    errorlevel check logs 'export OK' every morning.
    """
    (out / EXPORT_SCRIPT).write_text(EXPORT_SCRIPT_TEXT.replace("\n", "\r\n"),
                                     encoding="utf-8", newline="")
    return {
        "why": "no `silent`: the tool opens its window and waits; channellist= needs ';' "
               "and ignores ','; start=/end= need absolute FILETIME ticks and ignore "
               "milliseconds; the ignored options exit 0, so errorlevel logs OK",
        "defects": {"silent": "missing - the tool waits on its window",
                    "channellist": {"written": ",", "correct": ";",
                                    "effect": "ignored, every channel exported"},
                    "range": {"written": "ms from the start of the recording",
                              "correct": "absolute FILETIME ticks, as the CSV header's "
                                         "Starttime of export",
                              "effect": "ignored, full range exported"},
                    "errorlevel": "exit 0 in both ignored cases; only the output shows it"},
        "the_trap": "every parameter is spelled as the tool's parameter list spells it; "
                    "the three failures are silent and none is visible in the file",
    }


PRESS = "press_axis3_export.csv"
PRESS_SIGNALS = ("ActVelo", "ActTorque", "PosDiff")
PRESS_SCALE = (2.0, 10.0)        # factor, offset on ActTorque - as field-verified
PRESS_PEAK = 79.0                # peak in the file: 79 read as is, 168 scaled


def write_press_export(out):
    """A hand-made export whose torque answer depends on an export setting.

    Scope applies a channel's scaling to exported values only when 'Scale
    values before export' is on, and the CSV header is identical either way -
    the ScaleFactor and Offset rows are the channel's scaling, not a record of
    whether it was applied (field-verified with factor 2 and offset 10). So
    ActTorque peaking at 79 reads as 79 % if the values were scaled, or
    2 x 79 + 10 = 168 % if they are raw, and the question is whether it passed
    150 %. The file cannot settle it; the export setting or a fresh export of
    the .svdx can.
    """
    rate, seconds = 1000, 10
    rng = random.Random(20260904)
    setpos, vel, acc = point_to_point(rng, seconds, rate)
    peak_acc = max(abs(a) for a in acc)
    # One hard acceleration, as the drive's warning describes.
    hard = max(range(len(acc)), key=lambda i: acc[i])
    rows = len(setpos)
    columns = [[f"{i * 1000.0 / rate:.6f}" for i in range(rows)]] + [[] for _ in PRESS_SIGNALS]
    raw_torque = []
    for i in range(rows):
        friction = 4.0 * (1 if vel[i] > 0.5 else -1 if vel[i] < -0.5 else 0)
        torque = 18.0 + friction + 30.0 * acc[i] / peak_acc + rng.gauss(0, 0.6)
        if abs(i - hard) < 60:
            torque += 26.0 * math.exp(-((i - hard) / 25.0) ** 2)
        raw_torque.append(torque)
        lag = 0.00012 * acc[i] + 0.0004 * vel[i] + rng.gauss(0, 0.002)
        for col, value in zip(columns[1:], (vel[i] + rng.gauss(0, 0.08), torque, lag)):
            col.append(f"{value:.6f}")
    peak = max(raw_torque)
    if not PRESS_PEAK - 3 < peak < PRESS_PEAK + 3:
        raise SystemExit(f"torque peak {peak:.1f} is not near {PRESS_PEAK}")

    groups = [spec(len(PRESS_SIGNALS), 1, 1, port=501)]
    symbols = [[f"Axes.Axis3.{s}" for s in PRESS_SIGNALS]]
    path = out / PRESS
    write_tab(path, groups, columns, [], rows, symbols=symbols)
    # The shared writer types channels by position and stamps unscaled rows;
    # this file is three REAL64 channels, and ActTorque carries the scaling.
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\r\n")
    torque_col = 1 + PRESS_SIGNALS.index("ActTorque")
    for n, line in enumerate(lines):
        cells = line.split("\t")
        if cells[0] == "Data-Type":
            cells[1:] = ["REAL64"] * len(PRESS_SIGNALS)
        elif cells[0] == "SymbolComment":
            cells[1:] = [""] * len(PRESS_SIGNALS)
        elif cells[0] == "ScaleFactor":
            cells[torque_col] = f"{PRESS_SCALE[0]:.6f}".replace(".", ",")
        elif cells[0] == "Offset":
            cells[torque_col] = f"{PRESS_SCALE[1]:g}"
        elif cells[0] == "EndTime" and len(cells) == 2:
            cells[1] = "22-7-2026 09:14:13"
        lines[n] = "\t".join(cells)
    path.write_text("\r\n".join(lines), encoding="utf-8", newline="")
    scaled = PRESS_SCALE[0] * peak + PRESS_SCALE[1]
    return {
        "rows": rows, "rate_hz": rate, "duration_s": seconds,
        "channel": "ActTorque", "scale_factor": PRESS_SCALE[0], "offset": PRESS_SCALE[1],
        "peak_in_file": round(peak, 1), "peak_time_s": round(hard / rate, 3),
        "peak_if_raw": round(scaled, 1),
        "why": "the header's ScaleFactor/Offset rows are written whether or not 'Scale "
               "values before export' was on, so the file cannot say whether "
               f"{peak:.1f} is already scaled ({peak:.1f} %) or raw "
               f"({scaled:.1f} % once scaled)",
        "the_trap": "a ScaleFactor row reads as 'multiply to get engineering units', or "
                    "the column is read as it stands - either way one number, and the two "
                    "straddle 150 %",
    }


def write_stages(out):
    """One directory per eval, holding only that eval's own files.

    Agents list the folder and read whatever is in it. In iteration 4 a shared
    folder let baselines read the right type names out of another eval's .svdx,
    and one eval tied until it was re-run alone. Copy stages/<eval>/ per run.
    """
    import shutil
    evals = json.loads((Path(__file__).parent / "evals.json").read_text())["evals"]
    stages = out / "stages"
    if stages.exists():
        shutil.rmtree(stages)
    for e in evals:
        data = stages / e["name"] / "data"
        data.mkdir(parents=True)
        for f in e["files"]:
            shutil.copy2(out / Path(f).name, data / Path(f).name)
    return sorted(p.name for p in stages.iterdir())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "fixtures"),
                    help="where the fixtures go. The ground truth never goes here.")
    ap.add_argument("--scale", action="store_true",
                    help=f"also write {SCALED}: {SCALE_ROWS} rows x "
                         f"{SCALE_AXES * len(SCALE_SIGNALS)} channels, a few "
                         "hundred MB, minutes to generate")
    ap.add_argument("--scale-rows", type=int, default=SCALE_ROWS,
                    help="rows in the scaled fixture. Smaller is for checking "
                         "the generator, not for running the evals.")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    skewed = write_skewed(out)
    planted = write_planted(out)
    unwired = write_unwired(out)
    multirate = write_multirate(out)
    handwritten = write_handwritten(out)
    armed = write_ring_buffer(out)
    second_site = write_second_site(out)
    export_script = write_export_script(out)
    press = write_press_export(out)
    scaled = write_scaled(out, args.scale_rows) if args.scale else None

    truth = {
        SKEWED: {
            "why": "cross-group timing is invalid: group 1 was never repeat-padded",
            "columns": skewed["columns"],
            "max_skew_ms": skewed["max_skew_ms"],
            "the_trap": {
                "naive_torque_spike_s": 0.400,
                "true_torque_spike_s": 0.800,
                "following_error_step_s": 0.600,
                "naive_conclusion": "torque spiked first, so torque caused the following error",
                "honest_conclusion": "the export is broken; no cross-group ordering claim is valid",
            },
        },
        PLANTED: planted,
        UNWIRED: {
            "why": "display channel references an AcquisitionGUID no acquisition carries",
            "acquisition_guid": unwired,
        },
        MULTIRATE: {
            "why": "valid export; the two channels are on 1 ms and 10 ms groups",
            "max_skew_ms": multirate["max_skew_ms"],
            "the_trap": {
                "following_error_step_s": MULTIRATE_ERROR_ROW / 1000.0,
                "torque_last_normal_s": (MULTIRATE_TORQUE_ROW - 10) / 1000.0,
                "torque_first_high_s": MULTIRATE_TORQUE_ROW / 1000.0,
                "naive_conclusion": "following error first by 5 ms, torque reacted",
                "honest_conclusion": "the 5 ms gap is inside one 10 ms torque sample; "
                                     "the order is not in the data",
            },
        },
        HANDWRITTEN: handwritten,
        ARMED: armed,
        SECOND_SITE: second_site,
        EXPORT_SCRIPT: export_script,
        PRESS: press,
    }
    if scaled is not None:
        truth[SCALED] = scaled
    # One directory up, deliberately: see the module docstring.
    (Path(__file__).parent / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    stages = write_stages(out)
    print(json.dumps({"ok": True, "out": str(out),
                      "written": sorted(p.name for p in out.iterdir()),
                      "stages": stages}, indent=2))


if __name__ == "__main__":
    main()
