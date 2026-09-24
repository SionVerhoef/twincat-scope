#!/usr/bin/env python3
"""Build the fixtures the eval prompts point at.

Two of the six evals need a file with a *planted trap* rather than a planted
defect, which is why they are not in tests/. A test fixture asks "does the
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
                      carrying the defects tests/make_fixture.py plants: a
                      three-sample following-error spike at 12.0 s, a position
                      step at 6.0 s, a frozen torque channel from 15 to 17 s,
                      and a velocity channel clipped at +/-8.0 while the signal
                      underneath it reaches 78.5. Two traps in one file - a
                      needle too narrow to survive decimation, and a saturated
                      channel whose maximum is not its maximum.

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
import random
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


def write_planted(out):
    """The 20-second single-axis recording, borrowed wholesale from the test
    generator. Only the name changes: nothing about `planted.csv` should be
    visible to an agent being asked what is wrong with it."""
    rows = make_fixture.build()
    make_fixture.write(out / PLANTED, rows, ",", ".")
    return {
        "rows": len(rows),
        "rate_hz": make_fixture.RATE_HZ,
        "duration_s": make_fixture.DURATION_S,
        "planted": {
            "step": {"channel": "Axis1.ActPos", "time_s": make_fixture.STEP_TIME},
            "spike": {"channel": "Axis1.PosDiff", "time_s": make_fixture.SPIKE_TIME,
                      "width_samples": make_fixture.SPIKE_WIDTH, "amplitude": 4.0},
            "flatline": {"channel": "Axis1.ActTorque",
                         "start_s": make_fixture.FLAT_START, "end_s": make_fixture.FLAT_END},
            "clipping": {"channel": "Axis1.ActVelo", "limit": make_fixture.CLIP_LIMIT,
                         "true_amplitude": 78.5,
                         "note": "the recorded maximum is the clip, not the peak"},
        },
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
        for line in ("Name,Synthetic scope export",
                     f"File,{SCALED}",
                     "StartTime,2026-09-04 06:00:00",
                     f"SampleTime,{1.0 / rate_hz:.6f}",
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
                      "<AmsNetId>192.168.1.10.1.1</AmsNetId>")

    target = "<AcquisitionGUID>"
    start = src.index(target) + len(target)
    end = src.index("</AcquisitionGUID>", start)
    original = src[start:end]
    if original.strip() in ("", NULL_GUID):
        raise SystemExit("template's AcquisitionGUID is already unset - nothing to break")
    dst = src[:start] + DANGLING + src[end:]
    (out / UNWIRED).write_text(dst, encoding="utf-8")
    return {"was": original, "now": DANGLING}


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
    }
    if scaled is not None:
        truth[SCALED] = scaled
    # One directory up, deliberately: see the module docstring.
    (Path(__file__).parent / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(json.dumps({"ok": True, "out": str(out),
                      "written": sorted(p.name for p in out.iterdir())}, indent=2))


if __name__ == "__main__":
    main()
