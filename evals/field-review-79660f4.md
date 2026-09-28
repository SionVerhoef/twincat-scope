# Field review — main @ 79660f4

Run by an agent on the same Beckhoff commissioning workstation as the 8bf9230 round
(Windows 10, Dutch locale, TwinCAT 3.1 build 4024.55, Scope 3.4.3147.18 incl. the TF3300
export tool, Python 3.12.10, `uv` 0.12.7). The subject: the G1-G6 fixes that followed the
8bf9230 review. The skill was reinstalled from `79660f4` first.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; every number
is the measured one. Recordings, projects and CSVs stayed on the machine. NC axis fields
(`ActPos`, `SetPos`, …) are named because they are the same on every NC axis.

The same material as last round:
- **R1, R2.** 60 s `.svdx` recordings, each with a 2 ms group (one NC position) and a 4 ms
  group (one PLC flag). R1's axis stands still; R2's moves.
- **R3.** 600 s, 33 channels (10 `REAL64`, 10 `BIT`, 8 `INT16`, 5 `UINT32`), in 5 time groups.
- Scope View CSV exports of R2 with one option changed each.
- A scratch copy of a project, for the trigger tests.

## Verdict

Every G fix holds on real files: G1, G2, G3, G4, G5 and G6, including every trigger setting
Scope View was made to save (11 saves). Nothing was refused that should have been read. Two new
defects were found and fixed:
- **a Parquet recording was loaded at twice its size** (H1);
- **`checkscope` called every ring-buffer recording a fixed window** (H4), 4 of 25 real files.

Also described, not fixed:
- a detector-design problem: clean command trajectories describe their moves as flatlines (H2);
- the Stop Subsave pre-trigger is not checked (H3);
- an open question about Start Subsave (H5).

Tests: **276/276** on `79660f4` with `py -3 tests/test_verbs.py` (the first Windows run of the
G fixes). **280/280** with the patch.

## Results, by handoff step

### 1. G1 — headerless exports, from Scope View: pass

| File (Scope View, R2) | Result |
|---|---|
| Header None + Include trigger info (TAB, `.`) | refused: "has no header row naming its columns" |
| Header None alone (`,`, `.`) | same refusal |
| Header None, `;` with `,` | same refusal |
| Header None, from the tool | same refusal |
| Header **Full** + trigger info | `ok`: 29 999 / 15 000, `REAL64`/`BIT`, ports 501/851 |

The trigger table in the headerless file, first 6 lines, with only the separator shown:

```
(blank line)
TriggerGroup<TAB>Count<TAB>ReleaseTime<TAB>Comment<TAB>
Trigger Group<TAB>0<TAB>18648<TAB><TAB>
Trigger Group<TAB>1<TAB>54276<TAB><TAB>
Trigger Group<TAB>2<TAB>58204<TAB><TAB>
0<TAB>50.0001220703125<TAB>0<TAB>1
```

The header cell is exactly `TriggerGroup`, so the fix's assumption holds. The rows below it say
`Trigger Group`, with a space. The file starts with one empty line.

### 2. G2 — Timelines None: pass

Both Scope View's *Timelines None* export and *Timelines None + Fill with previous value* are
refused: "group 0's time column (column 0) runs backwards … so it is not a time column". The fix
asks whether the file was made with Timelines None. Fill does not add a time column.

### 3. No false refusals: pass

All `ok`, with no `time_backsteps` field and no `malformed_rows`:

| Export | Delimiter / decimal | Samples |
|---|---|---|
| Scope View defaults | `,` / `.` | 29 999 / 15 000 |
| Scope View `;` / `,` | `;` / `,` | 29 999 / 15 000 |
| Scope View Fill with previous value | `,` / `.` | 29 999 / 15 000 |
| Scope View Shift value | `,` / `.` | 29 999 / 15 000 |
| Scope View trigger info, Name header | TAB / `.` | 29 999 / 15 000 |
| The tool | TAB / `,` | 29 999 / 15 000 |
| The tool, trigger info | TAB / `,` | 29 999 / 15 000 |
| R3 through the tool | TAB / `,` | 300 003, 150 002, 299 996, 149 999, 50 002 |

### 4. G3 — `ingest` without `-o`: pass

R2 went to `%LOCALAPPDATA%\tcscope\cache\<stem>-d225322a.parquet`. The same file name copied
into a second folder went to `<stem>-63506e82.parquet`. `manifest` on each path reads
29 999 / 15 000.

### 5. G4 — argument errors: pass

`ingest` with no input returns `{"ok": false, "error": "…the following arguments are required:
input", "fix": "usage: …"}`, with exit code 2 and nothing on stderr.

### 6. G5 — `time_columns`: pass

`ingest` on R3 reports `time_columns: 33` and no `groups` key. `manifest` lists 5 groups.

### 7. G6 — trigger actions, on a scratch copy: pass

Each row is a separate save in Scope View, read by `checkscope`:

| Saved | `trigger_groups` (action, enabled, pre-trigger s) | `fixed_window` | Warning |
|---|---|---|---|
| Set Mark | `NONE`, true, 0 | true | "TriggerAction is NONE (Set Mark)…" |
| Stop Display | `STOP_DISPLAY`, true, 0 | true | fixed-window, names Stop Display |
| Export | `EXPORT`, true, 0 | true | fixed-window, names Export |
| Reporting Trigger | `REPORT_TRIGGER`, true, 5 | true | fixed-window, names Reporting Trigger |
| Start Record | `START_RECORD`, true, 0 | false | none |
| Stop Record | `STOP_RECORD`, true, 0 | false | none |
| Stop Record + pre-trigger `00:00:05:00` (60 s window) | `STOP_RECORD`, true, **300** | false | "The pre-trigger (300 s, TriggerAction STOP_RECORD) is longer than the 60 s record window" |
| Then Set Mark | `NONE`, true, **300** | true | fixed-window only; no pre-trigger warning |
| Start Record, group disabled | `START_RECORD`, **false**, 300 | true | "…every trigger group is disabled…" |
| Two groups: Start Record + Stop Record | both listed | false | none |

The Reporting Trigger row is last round's snapshot of that setting, re-read with 79660f4. It
carried a 5 s pre-trigger from an earlier edit. The first group of the two-group save still
carries its hidden 300 s pre-trigger; with Start Record no warning fires, as designed.

`trigger_groups` against every real file with a trigger, 22 in all: the 3 files that
contain a `TriggerGroup` element list it, and the 19 without one list none. So the element path
`TriggerModule/SubMember/TriggerGroup` is right. Two projects report `ok: false`, the same as on
8bf9230, and both correctly: one has 21 acquisitions named `Signal`, the other is a template with
a placeholder symbol.

**Start and Stop Subsave** were saved too (one trigger group, 60 s window, a 300 s pre-trigger
left over from row 7):

| Saved | Written | `fixed_window` | What Scope View shows for it |
|---|---|---|---|
| Start Subsave | `START_SUBSAVE` | false | **Record Time `00:00:01:00`** |
| Stop Subsave | `STOP_SUBSAVE` | false | Pre-/Post-Trigger, Save Path, File Name Mask, auto-delete, "Connected charts subsave only" |

The Subsave settings were in the trigger group all along, not added on switching:
- `SubSaveLength` 600 000 000 (= 60 s, the Record Time above);
- `SubSavePath` `$ScopeProject$\SubSaves`;
- `SubSaveNameMask` `{ScopeProject}({I:4})_{yyyyMMdd_HH'h'mm'm'ss's'}`;
- `SubSaveOnlyConnectedCharts` true.

Switching the action changed only `TriggerAction`. So a subsave **writes a separate file**
(Start: `SubSaveLength` from the trigger on; Stop: the pre-trigger up to the event). The main
recording keeps its own window. Nothing was recorded with either, so what lands in the file is
still inferred. See H3 and H5.

**Ringbuffer** (a project property in Scope View, with *Restart Record*, *Start Mode* User Start
and *File Store*) is saved as `/ScopeProject/StopMode`: `AutoStop` when off, `ClientStop` when on.
Nothing else changes. See H4.

### 8. `.svdx`: pass

`checkscope` on R1 and R2 is `ok` and lists one group (`NONE`, enabled, pre/post 0). R3 lists
none; its project has no `TriggerGroup`, and the warning says "no trigger configured".

## Beyond the handoff

**The tool's arguments.** `channel=<name>` and `channellist=<name>` export that one channel.
`start=`/`end=` take **absolute FILETIME ticks**; a 10 s range gave 5 001 + 2 501 samples,
with both ends included. Milliseconds, `24-9-2026 hh:mm:ss` and `hh:mm:ss` are ignored with
exit 0 and the full range. Now in `references/export-tool.md`.

**`SymbolComment` carries a hand-written comment.** A copy of R2 with a marker in the PLC
acquisition's `<Comment>` exports that marker in the `SymbolComment` row, where the 85-character
declaration comment used to be. So a marker kept there costs the declaration comment in every
export too. Now in `references/scope-configuration.md`.

**R3's 13 882 events** (bead item). The busiest channel is an NC axis's following error
(`PosDiff`): 2 447 events, of which 1 414 are ramps, 1 027 spikes, 4 flatlines and 2 steps. For
the same axis, counting SetPos's moving segments directly gives 656 moves in 600 s (moving 28%
of the time). Against that:

| Field | Real moves | `events` |
|---|---|---|
| SetPos | 656 | 655 flatline, 2 clipping, **0 ramp** |
| SetVelo | 651 | 652 flatline, **0 ramp** |
| SetAcc | — | 333 flatline, 58 step, 21 spike |
| ActPos | 656 | 1 156 ramp (1.76 per move) |
| ActVelo | — | 1 806 ramp |
| PosDiff | — | 1 414 ramp, 1 027 spike (≈3.7 per move) |
| AxisState | — | 1 041 step, 135 spike |
| CoupleState | — | 435 transition |

The counts follow real activity, so this is not random over-firing. See H2.

## Findings

### H1 — a Parquet recording was loaded at twice its size (fixed)

`load_parquet` called `pq.read_table` and kept the table while `to_numpy(...).astype(float)`
copied every column out of it. On R3:

| | Arrow pool peak | RSS after load | `manifest` / `stats` / `events` peak |
|---|---|---|---|
| 79660f4 | 200.5 MB | 517 MB | 518 / 527 / 534 MB |
| patch | 9.6 MB | 309 MB | 304 / 328 / 334 MB |
| CSV path, for comparison | — | — | 326 / 335 / 340 MB |

The time is unchanged: 0.9-1.2 s on Parquet against 9.8-10.5 s on the CSV. The output is
**byte-identical** for all three verbs on R3.

**Done:** `ParquetFile.read(columns=[name])` one column at a time, and each copied into a
writable float array (zero-copy arrays come back read-only). Regression check
`parquet_memory_checks`:
- It builds a 40 000-row, 20-channel scale fixture, ingests it, and loads it in a subprocess.
- It fails if `pyarrow.default_memory_pool().max_memory()` reaches a third of the table. On
  that fixture 79660f4 gives 1.30× and the patch 0.22×.

**Merged differently.** The same defect had been fixed on the development machine in the
meantime (PR #29): one column at a time too, but handed to NumPy without a copy, on the system
allocator. Zero-copy arrays are views on Arrow's buffers, so there the pool *is* the data and a
pool-only limit cannot pass. The field round's check was kept, renamed `parquet_pool_checks`,
and now counts Arrow's pool and NumPy's allocations together, against 2.5× the table: 79660f4
gives 4.42×, the field round's fix 1.87×, the merged zero-copy fix 1.71×. The R3 figures above
are for the field round's version; the merged one was not measured on R3.

### H2 — a clean command trajectory reports its rests and none of its moves (not fixed)

On a noise-free setpoint (SetPos, SetVelo), the first difference is constant during a move. So
the MAD threshold never sees an excursion and no ramp is reported. Every standstill then comes
out as a `flatline` ("stopped updating"), which is the wrong description for a setpoint at
rest. The same axis's noisy ActPos reports 1.76 ramps per real move instead. The rest-count
itself is right (655 rests between 656 moves).

This is a detector-design question, and needs someone to choose. Options:
- a `rest` kind for exact standstills on non-BIT channels;
- detecting ramps on a clean channel from runs of constant non-zero slope;
- merging ramps closer than a settling time.

Not attempted here.

### H3 — the Stop Subsave pre-trigger is not checked (not fixed)

With Stop Subsave and a 300 s pre-trigger on a 60 s window, `checkscope` gives no "longer than
the record window" warning; 79660f4 checks that for `STOP_RECORD` only. Scope View shows the
Pre-Trigger for Stop Subsave exactly as for Stop Record. The data a subsave keeps comes from the
running recording, so the same limit very likely applies. Recording with it would confirm that
before the warning is widened.

### H4 — a ring buffer was called a fixed window (fixed)

`checkscope` never read `StopMode`. The 4 real files with `ClientStop` each got "records a
fixed 3540 / 600 / 300 / 600 s window (no trigger configured, and the recording does not
restart)", with the advice about the chance of catching an intermittent fault. A ring buffer
runs until someone stops it and keeps the last `RecordTime`, so that advice is wrong for it.

**Done:**
- `checkscope` reports `ring_buffer`, and a ring buffer is never a fixed window.
- When no trigger starts or stops the recording, it says: "runs as a ring buffer … records until
  someone stops it and keeps the last N s before the stop. Stop it soon after the fault, or add a
  Stop Record trigger".
- All 4 real files now get that. The 21 `AutoStop` files are unchanged.
- The Ringbuffer on/off saves read `ring_buffer` true / false.
- Three regression checks: ring buffer not fixed; ring buffer explained; AutoStop not a ring
  buffer.

### H5 — does a Start Subsave trigger mean "not a fixed window"? (open)

79660f4 counts Start/Stop Subsave as recording actions, so `fixed_window` is false for them. But
a subsave only copies a slice into its own file (H3's evidence), and it can only fire while the
main recording runs. With `AutoStop`, the main recording still ends after its fixed window. So
"not a fixed window" may promise more than a subsave delivers. This needs a recording with a
subsave trigger to decide.

### Smaller observations

- Scope View's export dialog **remembers the last-used settings** again: `SV-full-trig`
  came out `;`/`,` because the export before it used `;`. So a file someone sends
  says nothing about the defaults.
- In XAE, **Ctrl+S did not reach the scope editor** after its Properties grid was edited: 7
  settings were changed and none was written until *File → Save <name>.tcscopex* was used.
  A tester, or an agent's instructions to a user, should name the menu item.

## Still untested

- 4.9: an axis parked at a limit, and a genuine saturation.
- A scaled channel with *Scale values* on.
- Marker windows on a recording that has markers.
- Timelines All on a group of several channels.
- Recording with Start/Stop Subsave, and with Ringbuffer on (H3, H5).
- `channellist=` with several names, and `svdx=`.

Nothing was written to or activated on any controller. Only the scratch copy of one project was
modified, and only through Scope View.
