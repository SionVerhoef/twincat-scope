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
    write_tab,
)

ROWS = 1000

# Plausible machine names. A file called `skewed_export.csv` answers half the
# question before the agent opens it.
SKEWED = "clamp_station_export.csv"
PLANTED = "axis1_run_20260722.csv"
UNWIRED = "AxisDiagnosis.tcscopex"

# Group 0 runs at 2 ms and is padded, so its time column is the wall clock.
# Group 1 declares 4 ms and was never padded, so row i lands at 4i ms on its
# own clock while group 0's column says 2i. Every group-1 timestamp read off
# group 0's column is therefore exactly half of the truth.
STEP_ROW = 300        # PosDiff step: 0.600 s, and group 0 is the honest clock
SPIKE_ROW = 200       # ActTorque spike: 0.400 s read naively, 0.800 s in truth
STEP_DELTA = 4.0      # following error jumps, in the same units as the channel
SPIKE_DELTA = 45.0    # torque spike, three samples wide
SPIKE_WIDTH = 3


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
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    skewed = write_skewed(out)
    planted = write_planted(out)
    unwired = write_unwired(out)

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
    }
    # One directory up, deliberately: see the module docstring.
    (Path(__file__).parent / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(json.dumps({"ok": True, "out": str(out),
                      "written": sorted(p.name for p in out.iterdir())}, indent=2))


if __name__ == "__main__":
    main()
