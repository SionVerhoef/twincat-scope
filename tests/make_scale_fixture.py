#!/usr/bin/env python3
"""Generate a Scope export at the scale the skill actually claims to handle.

SKILL.md opens on a 400 MB, 12-million-sample recording. Every fixture in this
repo is 200 to 1500 rows, so nothing here has ever tested that claim - which a
field review named its first priority, and which is a fair charge: three or four
orders of magnitude is not a detail.

The file is generated, never committed. At the default size it is ~180 MB.

The signal is the at-rest shape from make_real_fixtures.py, repeated: an axis
parked, one commanded move, one planted disturbance, per period. That matters
for the benchmark - a synthetic sine would let `events` finish without doing the
work it does on a real recording, and would make the numbers a lie.

Two groups at different rates, the slow one repeat-padded, because that is what
forces the reader to de-duplicate at scale rather than on 200 rows.

Stdlib only, like the other generators.

Usage:  python3 tests/make_scale_fixture.py --rows 500000 -o /tmp/scale.csv
"""

import argparse
import math
import random
import time
from pathlib import Path

TAB_KEYS = [
    "Name", "SymbolName", "SymbolComment", "NetId", "Port",
    "IndexGroup", "IndexOffset", "Data-Type", "SampleTime[ms]", "SymbolBased",
    "VariableSize", "Offset", "ScaleFactor", "BitMask", "Unit",
    "StartTime", "EndTime",
]

# One period of machine behaviour, in rows of the fast group: park, move, park,
# fault. 10 000 rows at 2 ms is 20 s, so a default-size file holds 50 cycles.
PERIOD = 10_000
MOVE_START, CRUISE_START, CRUISE_END, MOVE_END = 3000, 3500, 6000, 6500
FAULT_INDEX = 8000
CRUISE_VELO = 250.0
FAULT_DELTA = 40.0


def period_values(channel_index, rows, step_ms):
    """One period of formatted values for one channel.

    Formatted once and reused: at ten million samples the cost of str-formatting
    every value dominates generation, and the point of this file is to measure
    the reader, not the writer.
    """
    rng = random.Random(1000 + channel_index)
    role = channel_index % 4
    out, pos = [], 0.0
    for i in range(rows):
        if i < MOVE_START or i >= MOVE_END:
            velo = 0.0
        elif i < CRUISE_START:
            velo = CRUISE_VELO * (i - MOVE_START) / (CRUISE_START - MOVE_START)
        elif i < CRUISE_END:
            velo = CRUISE_VELO
        else:
            velo = CRUISE_VELO * (MOVE_END - i) / (MOVE_END - CRUISE_END)
        pos += velo * step_ms / 1000.0

        if role == 0:                                   # position, at rest
            value = round(pos, 4) + rng.uniform(-1e-9, 1e-9)
        elif role == 1:                                 # velocity, at rest
            value = round(velo, 4) + rng.uniform(-1e-9, 1e-9)
        elif role == 2:                                 # torque, never at rest
            value = 2.0 * math.sin(2 * math.pi * 3.0 * i * step_ms / 1000.0)
            value += rng.gauss(0, 0.05)
            if MOVE_START <= i < MOVE_END:
                value += 12.0
            if i >= FAULT_INDEX:
                value += FAULT_DELTA
        else:                                           # digital
            value = 1.0 if MOVE_START - 50 <= i < MOVE_END + 50 else 0.0
        out.append(f"{value:.9f}".replace(".", ","))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=500_000)
    ap.add_argument("--channels", type=int, default=20,
                    help="split evenly between a 2 ms and a 4 ms group")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    fast = args.channels // 2
    slow = args.channels - fast
    started = time.time()

    # Per-channel period tables. The slow group advances every other row, which
    # is repeat-padding: Scope prints the held sample again so both groups end
    # on the same timestamp.
    fast_cols = [period_values(c, PERIOD, 2.0) for c in range(fast)]
    slow_cols = [period_values(100 + c, PERIOD // 2, 4.0) for c in range(slow)]

    def metadata(key, value_for):
        row = ["Name" if key == "Name" else key]
        row = []
        for gid, count in ((0, fast), (1, slow)):
            row.append(key)
            for c in range(count):
                row.append(value_for(gid, c))
        return "\t".join(row)

    types = ["REAL64", "REAL64", "REAL64", "BIT"]
    meta = {
        "Name": lambda g, c: ["ActPos", "ActVelo", "ActTorque", "bEnable"][c % 4],
        "SymbolName": lambda g, c: (
            f"Axes.Smarttrak M{c + 1} (E1_1{c + 1:02d}U2_ChA."
            f"{['ActPos', 'ActVelo', 'ActTorque', 'bEnable'][c % 4]}"),
        "SymbolComment": lambda g, c: "scale fixture",
        "NetId": lambda g, c: "5.68.118.43.1.1",
        "Port": lambda g, c: "501" if g == 0 else "851",
        "IndexGroup": lambda g, c: "16448",
        "IndexOffset": lambda g, c: str(1000 + c * 8),
        "Data-Type": lambda g, c: types[c % 4],
        "SampleTime[ms]": lambda g, c: "2,000000" if g == 0 else "4,000000",
        "SymbolBased": lambda g, c: "True",
        "VariableSize": lambda g, c: "8",
        "Offset": lambda g, c: "0",
        "ScaleFactor": lambda g, c: "1,000000",
        "BitMask": lambda g, c: "0",
        "Unit": lambda g, c: "(None)",
        "StartTime": lambda g, c: "0",
        "EndTime": lambda g, c: "0",
    }

    out = Path(args.output)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write("TwinCAT Scope Export\r\n")
        fh.write(f"File\t{out.name}\r\n")
        fh.write("StartTime\t17-8-2026 09:14:03\r\nEndTime\t17-8-2026 09:47:31\r\n")
        fh.write("Version\t3.1.4024.35\r\n\r\n")
        for key in TAB_KEYS:
            fh.write(metadata(key, meta[key]) + "\r\n")

        chunk = []
        for i in range(args.rows):
            p, half = i % PERIOD, (i // 2) % (PERIOD // 2)
            row = [f"{i * 2.0:.6f}".replace(".", ",")]
            row += [col[p] for col in fast_cols]
            # The slow group's own time column, repeat-padded to the fast rows.
            row.append(f"{(i // 2) * 4.0:.6f}".replace(".", ","))
            row += [col[half] for col in slow_cols]
            chunk.append("\t".join(row))
            if len(chunk) >= 20_000:
                fh.write("\r\n".join(chunk) + "\r\n")
                chunk = []
        if chunk:
            fh.write("\r\n".join(chunk) + "\r\n")

    size = out.stat().st_size
    print(f"wrote {out}")
    print(f"  {args.rows} rows x {args.channels} channels "
          f"= {args.rows * args.channels / 1e6:.1f}M samples")
    print(f"  {size / 1e6:.1f} MB in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
