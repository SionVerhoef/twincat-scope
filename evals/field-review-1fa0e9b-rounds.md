# Field review — `1fa0e9b`, three rounds to a recording

Second field session, 2026-09-21 and 22, run by an agent at a Windows 10 Pro 19045 workstation
with TwinCAT 3, TE130x Scope View, TF3300 Scope Server and `TC3ScopeExportTool.exe`, in a
dark-theme IDE, against a live target with AX8000-series drives. Python 3.12.10 with uv, numpy,
pyarrow and matplotlib; `doctor` all green.

The skill was at `1fa0e9b` — the same version as `field-review-1fa0e9b.md`, from before the fixes
that session led to. Rounds 2 and 3 ran the reviewer's own patches to that version, not the code
on main. The last section says how far that carries over.

**Anonymised.** The AMS net ID, axis name, drive tag, symbol paths and file names are stand-ins.
Counts, widths, ports, sample rates and colour values are as measured. The index groups and
offsets seen in real files are deliberately left out: they are addresses in one build.

The reference corpus is **9 Beckhoff-authored `.tcscopex` files** from one machine project,
built by hand in Scope View, all of which open and record. None of them are in this repo.

## Verdict

**A generated file records.** Round 3 was the first time a `newscope`-generated `.tcscopex`
produced data on real hardware. It took three rounds because the two blockers mask each other:
the type error stops the connect sequence before it reaches symbol resolution, so the port error
only appeared once the type was fixed. No third blocker appeared.

`checkscope` at `1fa0e9b` passed all three files, including the two that could not record.

## The rounds

One file, one axis, five channels at 1 ms, generated as:

```bash
python3 scripts/tcscope.py newscope templates/axis-diagnosis.tcscopex -o Test.tcscopex \
    --channels "Axes.Axis 1 (Drive1_ChA).SetPos,Axes.Axis 1 (Drive1_ChA).ActPos,Axes.Axis 1 (Drive1_ChA).PosDiff,Axes.Axis 1 (Drive1_ChA).ActVelo,Axes.Axis 1 (Drive1_ChA).ActTorque" \
    --netid 1.2.3.4.1.1 --sample-time-ms 1
```

| Round | File | Scope View |
|---|---|---|
| 1 | as generated: `LREAL`/8, port 851, every acquisition named `Signal` | Opened. 18 errors, `The datatype is not supported: 'VOID'` per channel. No samples. |
| 2 | `REAL64`, acquisitions named by leaf; port still 851 | `VOID` gone. `Symbolname could not be found for channel: '"SetPos" (Axes.Axis 1 (Drive1_ChA).SetPos)'`. No samples. |
| 3 | as round 2 plus port 501; `IndexGroup`/`IndexOffset` left at 0; fresh GUIDs | No errors. **Recorded.** |

## Findings

### R1 — an IEC type name is read as `VOID`, and saved that way

After the round-1 file was added to a measurement project and saved, all five acquisitions read
back as `VOID` with `VariableSize` 8. Scope parses a type name it does not know to its enum's
zero value, writes that back, and then refuses the channel at connect. This corrects the repo's
earlier wording that an IEC name "is accepted by nothing and rejected by nothing".

Already fixed on main before this write-up: both templates ship `REAL64`, and `checkscope`
refuses IEC names. Added now: `VOID` itself is a `checkscope` problem, since it is the mark of a
file Scope has already opened and failed on — it previously drew only a soft warning.

### R2 — `Axes.*` on port 851

The same error as `field-review-1fa0e9b.md` N1, seen independently. In the corpus, grouped by
symbol root:

| Root | `TargetPort` | Acquisitions |
|---|---|---|
| `Axes` | 501 | 91 |
| PLC globals | 851 | 150 |

No exceptions, including one file that mixes both. Main already routes `Axes.` to 501 per
channel.

### R3 — symbolic addressing is enough for NC symbols

Round 3 kept `SymbolBased` true with `IndexGroup`/`IndexOffset` at 0, and the NC channels resolved
and recorded. Real files carry non-zero index groups and offsets on their NC acquisitions; round
3 shows they are not needed as inputs. `newscope` keeps writing 0, which survives a rebuild.

### R4 — the type vocabulary, as observed

Every `DataType` in the corpus:

| `DataType` | `VariableSize` | Occurrences | Seen on |
|---|---|---|---|
| `BIT` | 1 | 74 | BOOLs — inputs, handshakes, flags |
| `INT8` | 1 | 1 | a row counter |
| `INT16` | 2 | 30 | step enums, counters |
| `UINT32` | 4 | 9 | NC status fields |
| `REAL64` | 8 | 117 | every NC motion quantity |

`LREAL` appears nowhere. These counts sum to 231; the port table above counts 241 acquisitions,
and the session's notes do not say where the other ten went.

NC fields, every occurrence agreeing: `ActPos`, `SetPos`, `ActPosModulo`, `SetPosModulo`,
`PosDiff`, `ActVelo`, `SetVelo`, `ActAcc`, `SetAcc`, `ActTorque` and `Position` are `REAL64`/8;
`ErrState`, `ErrorCode`, `ErrorID`, `AxisState` and `CoupleState` are `UINT32`/4.

Added now: `INT8` and `UINT32` join the observed list, and `newscope` types those NC fields from
the name when they sit under `Axes.` — an NC field's type is Beckhoff's, not a house convention.
Anything else undeclared is still written `REAL64` and reported as defaulted.

### R5 — names

Every acquisition was named `Signal`; fixed on main. Round 2 showed the name reaches Scope's own
messages — the error quoted `"SetPos"`. Real files disagree about `Title`: this corpus uses a
sequential `AdsAcquisition_<n>`, the hand-authored file in `field-review-1fa0e9b.md` the full
symbol path. It is free text, and main keeps the path.

### R6 — charts in a dark IDE

> "looking very ugly […] but I use dark theme so it should look nice for both."

The generated charts rendered as near-white panels. The file carried no `AxisStyle`, `ColorMode`
or `GridColor` at all, light greys on the chart and band panels (`-1118482` = `#EEEEEE`,
`-1973016` = `#E1E4E8`), and trace colours from a palette designed for a white page.

The corpus carries **76 `AxisStyle` elements, one per axis**, inside each `TimeAxis` and
`ValueAxis` `<SubMember>`, every one `ColorMode` `CustomColor`. The dark values: axis text and
grid `-921103` (`#F1F1F1`), chart background `-14342874` (`#252526`).

No value that follows the IDE theme was seen. Whether `ColorMode` has one is open — it is an enum
seen with a single value, and one look at the property in Scope View's property grid would
settle it.

Added now: `newscope --theme dark|light`, dark by default, writing an `AxisStyle` on every axis
and trace colours checked for contrast against the background they sit on. Written after the
session; **not yet seen in Scope View.**

### R7 — do not double-click a bare `.tcscopex`

> "first twincat asked to make a scope project so i made it. Then it kind of froze twincat for a
> while. Then i ran out of patience and added it to my own twincat project where it opened right
> away."

Opened from Explorer, the file started a new-scope-project wizard and then hung. Added to an
existing TwinCAT Measurement project, it opened at once. Two generated files in one project need
distinct GUIDs: `newscope` mints fresh ones on every run, a hand-copied file does not.

### R8 — `checkscope` passed all three

At `1fa0e9b` it validated wiring and load, never the acquisition payload. Rebuilt in the repo
from main's own output with each round's fields put back, main's `checkscope` refuses round 1
twice per channel (an NC symbol on a PLC port, an IEC type name) and round 2 once per channel,
and passes round 3. A file Scope had re-saved with `VOID` still passed until this change.

## What worked — do not regress it

- The file parses: UTF-8 BOM, CRLF, `ScopeProject` `Version` 1.0.0.0.
- GUID linkage: every display channel arrived under its intended band.
- The layout rendered as designed — one tab for the axis, then `Position` {ActPos, SetPos},
  `Following error`, `Velocity`, `Torque / current`.
- Symbol names with spaces and parentheses survived intact.
- `UseTaskSampleTime` false with an explicit 1 ms `BaseSampleTime` raised no error.
- `checkscope`'s load band (typical, 5000 samples/s) and its untriggered-window warning were
  accurate.

## Not checked

- **Main's own generator.** Rounds 2 and 3 ran patches to `1fa0e9b`. Checked in the repo since:
  main writes the same value as the round-3 file for every field that changed between rounds —
  `DataType`, `VariableSize`, `TargetPort`, `Name`, `SymbolBased`, `IndexGroup`, `IndexOffset` —
  and differs only in `Title`. That is strong evidence, not a recording.
- **Anything but `REAL64` NC channels.** Round 3 recorded five of them. No bit, integer or
  PLC-side channel was in these rounds.
- The theme and `AxisStyle` change, triggers, and `.svdx` conversion.
