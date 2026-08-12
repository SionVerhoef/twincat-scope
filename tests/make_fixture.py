#!/usr/bin/env python3
"""Generate synthetic scope exports with known defects planted in them.

Two things make this worth having. First, `events` and `plot` need ground truth
to be tested against, and a real recording gives you no ground truth - you only
have an opinion about what is in it. Second, real recordings carry customer
machine behaviour and must never be committed; synthetic ones can be.

Writes two files with identical content but different locale conventions,
because Beckhoff tooling on a Dutch or German Windows exports ';' separated with
',' decimals, and a reader that assumes otherwise fails silently.

Stdlib only, on purpose - generating fixtures must not require the analysis
dependencies, or CI cannot bootstrap itself.

Usage:  python3 tests/make_fixture.py [--out DIR]
"""

import argparse
import json
import math
import random
from pathlib import Path

RATE_HZ = 1000.0
DURATION_S = 20.0

# Planted defects. The tests assert these exact positions are found.
STEP_TIME = 6.0          # ActPos jumps
SPIKE_TIME = 12.0        # 3 samples wide - invisible to naive decimation
SPIKE_WIDTH = 3
FLAT_START, FLAT_END = 15.0, 17.0   # Torque frozen
CLIP_LIMIT = 8.0         # Velocity saturates


def build():
    n = int(RATE_HZ * DURATION_S)
    rng = random.Random(20260811)
    rows = []
    for i in range(n):
        t = i / RATE_HZ

        pos = 50.0 * math.sin(2 * math.pi * 0.25 * t) + rng.gauss(0, 0.02)
        if t >= STEP_TIME:
            pos += 12.0

        vel = 78.5 * math.cos(2 * math.pi * 0.25 * t) + rng.gauss(0, 0.05)
        vel = max(-CLIP_LIMIT, min(CLIP_LIMIT, vel))

        torque = 1.5 + 0.4 * math.sin(2 * math.pi * 3.0 * t) + rng.gauss(0, 0.01)
        if FLAT_START <= t <= FLAT_END:
            torque = 1.5

        lag = 0.05 * math.sin(2 * math.pi * 0.25 * t) + rng.gauss(0, 0.002)
        if abs(t - SPIKE_TIME) < (SPIKE_WIDTH / 2) / RATE_HZ:
            lag += 4.0

        rows.append((t, pos, vel, torque, lag))
    return rows


HEADER = ["Time", "Axis1.ActPos", "Axis1.ActVelo", "Axis1.ActTorque", "Axis1.PosDiff"]

# A Scope export states time in milliseconds. The tool converts on read and
# reports seconds, so the ground truth below stays in seconds.
MS_PER_S = 1000.0


def write(path, rows, delimiter, decimal):
    def fmt(value):
        text = f"{value:.6f}"
        return text.replace(".", ",") if decimal == "," else text

    lines = [
        "Name" + delimiter + "Synthetic scope export",
        "File" + delimiter + path.name,
        "StartTime" + delimiter + "2026-08-11 09:00:00",
        "SampleTime" + delimiter + fmt(1.0 / RATE_HZ),
        "",
        delimiter.join(HEADER),
    ]
    lines.extend(
        delimiter.join(fmt(v * MS_PER_S if i == 0 else v) for i, v in enumerate(row))
        for row in rows
    )
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "fixtures"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = build()

    write(out / "planted.csv", rows, ",", ".")
    write(out / "planted_eu.csv", rows, ";", ",")

    truth = {
        "rate_hz": RATE_HZ,
        "duration_s": DURATION_S,
        "rows": len(rows),
        "channels": HEADER[1:],
        "planted": {
            "step": {"channel": "Axis1.ActPos", "time": STEP_TIME, "delta": 12.0},
            "spike": {"channel": "Axis1.PosDiff", "time": SPIKE_TIME,
                      "width_samples": SPIKE_WIDTH, "amplitude": 4.0},
            "flatline": {"channel": "Axis1.ActTorque",
                         "start": FLAT_START, "end": FLAT_END},
            "clipping": {"channel": "Axis1.ActVelo", "limit": CLIP_LIMIT},
        },
    }
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(json.dumps({"ok": True, "written": [p.name for p in sorted(out.iterdir())]}, indent=2))


if __name__ == "__main__":
    main()
