# Real recordings — intentionally empty

**A real, redacted recording of a known fault is the most valuable thing this folder can
hold.**

The format questions are answered: the reader was measured against 19 genuine
`TC3ScopeExportTool.exe` exports covering both dialects, and `tests/make_real_fixtures.py`
reproduces the five layouts they use. Another clean export adds little.

Diagnosis is the gap. A model reading "look for saturation" produces generic advice.
A model that has seen what your machine's torque channel looks like when the drive is
healthy produces advice about *your* machine.

## What to put here

- **One CSV export**, from any short recording, if it comes from an installation whose export
  looks unlike the five layouts already reproduced — a different locale or tool version.
- **A `.tcscopex` from a project that works**, so the templates can be checked against
  something Scope View has actually opened.
- **A recording with a known fault**, plus a one-line note saying what the fault was. These
  are worth the most and are the rarest.

## Before you commit anything

A scope recording carries more identifying detail than people expect. Check for:

- **`AmsNetId` values** — these appear in `.tcscopex` files and identify a specific
  controller on a specific network
- **`IndexGroup` / `IndexOffset`** — memory addresses from a specific build
- **Customer or site names, machine numbers, project codes** inside channel names, symbol
  paths, file names and the CSV preamble
- **Setpoints, recipes and cycle times** that are commercially sensitive
- **IP addresses and hostnames** in the export metadata
- Anything under NDA

Redaction costs nothing here. Renaming `Klant_A_Vulmachine.Axis3.ActPos` to
`Line1.Axis3.ActPos` and replacing the NetID with `1.2.3.4.1.1` preserves every structural
signal that matters and removes everything that identifies anyone.

Values can be scaled or scrambled too, as long as the *shape* survives — the format questions
only need the header, and the diagnosis questions only need the waveform.

## If a file needs context

Leave a note beside it:

```
examples/
├── axis3-following-error.csv
├── axis3-following-error.md   <- "Filling machine, servo on a cam profile.
│                                  Drive tripped F220 at ~12 s. Root cause was a
│                                  loose coupling, found after the recording."
└── axis3-scope.tcscopex
```

That note is what turns a file into a teaching example.

## Why this folder is in git but empty

So the redaction rules above are read *before* someone drops a file in, not after.
