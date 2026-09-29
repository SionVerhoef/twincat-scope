# twincat-scope

An agent skill for **TwinCAT 3 Scope**: build scope projects that actually record, and read
the recordings they produce without drowning in samples. Built and tested with Claude Code;
the same files follow the skill layout GitHub Copilot in VS Code reads, which is untested.

Companion skill: **[twincat-st](https://github.com/SionVerhoef/twincat-st)** writes and reviews
the Structured Text. This one measures what that code does on the machine. Install either
alone.

> **Not affiliated with or endorsed by Beckhoff Automation GmbH & Co. KG.**
> "TwinCAT" and "Beckhoff" are trademarks of Beckhoff Automation GmbH & Co. KG, used here
> nominatively to describe what this skill works with. "EtherCAT" is a registered trademark
> and patented technology, licensed by Beckhoff Automation GmbH, Germany.

## Why

Two things go wrong when you hand a model a scope problem without help.

**The configuration looks right and records nothing.** NC axis symbols live on port 501, not
851. Scope wants `REAL64`, not `LREAL`, and reads the IEC name as `VOID`. A display channel
wired to a stale GUID opens perfectly and plots an empty chart. None of this is guessable, and
a model without the skill confidently calls such a file "sound".

**The recording is too big to read.** Ten minutes of twenty channels at 1 kHz is twelve million
samples, and the fault is usually three of them. Decimate it for a plot and a 3-sample spike
shows up about one time in seven. Read a multi-rate export as one table and cause and effect
can come out reversed.

This skill gives the agent the Scope-specific facts and a small tool that answers questions
about a recording in a few hundred bytes or one picture, instead of returning samples.

**What it has shown so far.** In the latest blinded evals (`evals/results-iteration-4.md`:
five evals, three runs each, the same model with and without the skill) answers with the skill
scored 28.3 of 29 against 20.7 without, and an independent judge ranked the two the same way on
every eval. The widest gap was a hand-written `.tcscopex` that would record nothing: all three
answers without the skill called it sound. On a planted-fault recording both scored full marks.
The skill does not save tokens; it used about 9% more. On real machines, files it generates
open and record unedited, and `checkscope --tmc` caught every planted symbol error against a
real compiled program (see *Status*).

## Features

**Build and check a recording**

- **`newscope`** — writes a `.tcscopex` from a template for the symbols you name: fresh GUIDs
  with every display channel still wired to its acquisition, Scope's own data types, NC axis
  symbols routed to port 501, sample and record time set.
- **Readable layout by default** — one chart tab per device, one stacked band per quantity,
  at most eight traces per band, so a following error of microns is not flattened by a
  position of a metre. Dark or light theme.
- **`checkscope`** — catches the files that open fine and record nothing: unwired or dangling
  channels, duplicate GUIDs, wrong ports, IEC type names, size/type mismatches, placeholder
  names and NetIDs. Also reads the project stored inside a `.svdx`.
- **Recording-plan warnings** — sample load against the target, a fixed window that will
  probably miss an intermittent fault, ring-buffer and trigger behaviour.
- **`--tmc`** — checks every PLC symbol against the compiled program: typos, renamed
  variables, types read at the wrong width.
- **No dependencies** — `doctor`, `newscope` and `checkscope` run on plain Python, so they work
  on a locked-down engineering PC.

**Read a recording**

- **`ingest`** — converts a `.svdx` (through Beckhoff's `TC3ScopeExportTool.exe`) or a Scope CSV
  to Parquet once, so every later question takes seconds instead of minutes.
- **`manifest`** — channels, units, sample rates, duration, gaps, and whether timing across
  acquisition groups can be trusted at all.
- **`stats`** — per-channel health: time pinned at a rail, flat stretches, quantisation,
  outlier-heavy distributions.
- **`events`** — steps, spikes, ramps, flatlines, holds, clipping, digital transitions and
  threshold crossings, ranked worst-first and spread across the recording. Tells a setpoint at
  rest from a frozen sensor.
- **`plot`** — a PNG drawn as a min/max envelope per pixel, so a 3-sample spike is always
  visible.
- **`correlate`** — which channel moved first, with the lag and its sign spelled out; refuses
  channels on different clocks unless you ask it to resample.
- **`window`** — the actual numbers for a short time range, capped so a broad question cannot
  flood the conversation.
- **Real export formats** — both TAB and European `;`/`,` dialects, multi-rate groups,
  repeat-padded or truncated slow groups, channels exported several times. Layouts it cannot
  read correctly are refused by name rather than misread.

**Guidance for the agent**

- A diagnosis method that walks from summary to raw rows, with how to read each result.
- How to size a recording so it does not disturb the machine it is measuring.
- Four hard rules: no safety logic, no writes to a live machine, no unverified claims, and a
  human starts every recording.

## Install

```bash
# Claude Code
git submodule add https://github.com/SionVerhoef/twincat-scope .claude/skills/twincat-scope

# GitHub Copilot in VS Code (untested)
git submodule add https://github.com/SionVerhoef/twincat-scope .github/skills/twincat-scope
```

Pin a release rather than following `main`, and commit the pin:

```bash
git -C .claude/skills/twincat-scope checkout v1.0.0
git add .claude/skills/twincat-scope
```

A plain `git clone` of your repository leaves a submodule folder **empty**. Everyone who clones
afterwards needs `git clone --recurse-submodules <your-repo>`, or `git submodule update --init`
in an existing clone.

If your team would rather not use submodules, `tools/update-skill.ps1` downloads a release zip
into the same location instead (`-Version v1.0.0`, or the latest release by default).

### Requirements

**[uv](https://docs.astral.sh/uv/)**. It fetches Python and the analysis dependencies on first
run, needs no administrator rights, and installs into your user profile:

```powershell
winget install --id=astral-sh.uv -e
```

Behind a corporate proxy:

```powershell
$env:UV_NATIVE_TLS = "true"                        # use the Windows certificate store
$env:UV_DEFAULT_INDEX = "https://nexus.example/repository/pypi/simple"
```

Without `UV_NATIVE_TLS`, an intercepting proxy breaks TLS with an opaque error.

`doctor` tells you what is missing and how to fix it:

```bash
py -3 scripts/tcscope.py doctor        # python3 on Linux or macOS
```

`doctor`, `newscope` and `checkscope` need no packages, but they do need **Python 3** itself.
A fresh Windows PC may have none: `python.exe` there can be a 0-byte Microsoft Store stub, and
`py` missing. Install it for your user only, no administrator rights needed:

```powershell
winget install --id=Python.Python.3.12 -e --scope user
```

or run the python.org installer with *Install for all users* unticked.

## Layout

```
twincat-scope/
├── SKILL.md                        entry point — rules, workflow, routing
├── references/
│   ├── data-triage.md              the method for reading a recording
│   ├── recording-load.md           sizing a recording safely
│   ├── scope-configuration.md      .tcscopex schema, ports, types, layout
│   └── export-tool.md              TC3ScopeExportTool.exe and the CSV traps
├── scripts/tcscope.py              every verb
├── templates/                      known-good .tcscopex
├── examples/                       real recordings — empty by design
├── tests/                          synthetic fixtures with planted defects
├── evals/                          skill evals and field-test write-ups
└── tools/update-skill.ps1          zip install, for teams avoiding submodules
```

## Status

There is no TwinCAT installation where this skill is developed. Everything below was checked
on real machines in field sessions, written up in `evals/field-review-*.md`.

**Verified**

- Files generated by `newscope`, unedited, open and **record** in Scope View: NC axis
  channels on 501 and PLC `BIT`/`INT16`/`REAL64` channels on 851, several tabs, both themes.
- The whole path once end to end: generate, record with a trigger, convert the `.svdx` with
  the real export tool, `ingest`, `manifest`.
- The CSV reader against 19 genuine export-tool CSVs and every CSV option in Scope View's
  export dialog. Each layout either reads correctly or is refused by name.
- `checkscope` against 25 real project files, and eight of Scope View's eleven trigger actions.
  A ring-buffer recording keeps exactly its record time, ending at the stop.
- Both templates, loaded as shipped: they open with the documented layout, and refuse to
  record until the NetId and symbols are set, as intended.
- `--tmc` against a real 862-symbol `.tmc`: known-good symbols resolve, a misspelled symbol
  and a wrongly-sized type are both caught.
- NC channels by every path `newscope` types — direct axis fields and `ToPlc`/`FromPlc`
  members, as `UINT32`, `UINT16`, `INT32` and `REAL64` — record on a moving axis and keep their
  types.
- Timelines *All* on a 10-channel group reads correctly.
- `events` on a real 600 s, 33-channel recording, over several rounds of fixes.
- The test suite on Windows and Linux.

**Not yet verified**

- The analysis verbs across a wide variety of real recordings — most real data so far comes
  from one machine.
- An axis parked exactly at a limit, a genuine saturation, and marker tables in an export.
- What a *Subsave* trigger records: it needs a Scope View Professional licence, which no test
  machine had.
- A Scope View CSV exported with *Scale values* on cannot be told from a raw one: `manifest`
  warns that its values *may* be scaled, and with a Name-only header cannot see the scaling at
  all. `ingest` on the `.svdx` reads raw values.
- Installation through GitHub Copilot in VS Code.

`SKILL.md` rule 3 tells the agent never to claim something is verified when it is not. The
same applies to this list.

The most useful contribution is a redacted recording of a **known fault** — see
`examples/README.md` — or a run of `evals/field-test-brief.md` on a machine with TwinCAT.

## Tests

```bash
py -3 tests/make_fixture.py && py -3 tests/make_real_fixtures.py
py -3 tests/test_verbs.py              # end-to-end checks of every verb
py -3 evals/test_grader.py             # the eval grader against known answers
```

Both test files are plain scripts, not pytest suites. `evals/README.md` explains how the skill
itself is evaluated against a no-skill baseline.

## Licence

MIT — see `LICENSE`.
