# Real recordings — intentionally empty

**Adding one real, redacted export is the highest-value single improvement available to this
skill.**

The reference files describe the CSV format in prose. Prose is a weak signal. The reader
currently *sniffs* the delimiter, the decimal separator and the preamble layout, because it
has never seen genuine `TC3ScopeExportTool.exe` output. One real file turns all of that from
inference into fact.

The same applies to diagnosis. A model reading "look for saturation" produces generic advice.
A model that has seen what your machine's torque channel looks like when the drive is
healthy produces advice about *your* machine.

## What to put here

- **One CSV export**, from any short recording. Even ten seconds of two channels settles the
  format questions.
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
