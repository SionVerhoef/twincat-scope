# twincat-scope

> **Status: no tagged release yet.** The submodule install below tracks `main`;
> `tools/update-skill.ps1` needs a release to download and starts working at the first tag.

An agent skill for recording **TwinCAT 3 Scope** measurements and making sense of the data
they produce. Works with GitHub Copilot in VS Code and with Claude Code, from the same files.

Companion skill: **[twincat-st](https://github.com/SionVerhoef/twincat-st)** writes and reviews
the Structured Text. This one measures what that code does on the machine. They are independent
— install either alone.

> **Not affiliated with or endorsed by Beckhoff Automation GmbH & Co. KG.**
> "TwinCAT" and "Beckhoff" are trademarks of Beckhoff Automation GmbH & Co. KG, used here
> nominatively to describe what this skill works with. "EtherCAT" is a registered trademark
> and patented technology, licensed by Beckhoff Automation GmbH, Germany.

## What it is

Recording is the easy half. A ten-minute recording of twenty channels at 1 kHz is twelve
million samples — too large to read, and the thing you are looking for is usually three
samples wide.

So this skill never returns samples. It gives an agent a ladder of verbs — `manifest`,
`stats`, `events`, `plot`, `correlate`, `window` — each returning a few hundred bytes or one
picture, narrowing the question until real rows are worth looking at.

`references/data-triage.md` is the file that does the work, and the reason to use this rather
than ask a model directly. Its central claim: **plots must use a min/max envelope per pixel
bucket, never decimation.** At 22 samples per pixel, decimation gives a 3-sample spike about a
1-in-7 chance of appearing — so six times out of seven you get a clean-looking chart of a
machine that faulted.

It also builds recordings: `newscope` writes a `.tcscopex` with fresh GUIDs, laid out as a
chart tab per device and a stacked band per quantity rather than every trace on one axis, and
`checkscope` catches the failure that looks like success — a display channel wired to nothing,
which opens perfectly and plots an empty chart.

## Install

```bash
# GitHub Copilot in VS Code
git submodule add https://github.com/SionVerhoef/twincat-scope .github/skills/twincat-scope

# Claude Code
git submodule add https://github.com/SionVerhoef/twincat-scope .claude/skills/twincat-scope
```

Submodules have one sharp edge worth knowing: a plain `git clone` of your repository leaves
the folder **empty**. Everyone who clones afterwards needs

```bash
git clone --recurse-submodules <your-repo>
# or, in an existing clone
git submodule update --init
```

If your team would rather not use submodules, `tools/update-skill.ps1` downloads a release
zip into the same location instead.

### Requirements

**[uv](https://docs.astral.sh/uv/)** — that is all. It fetches Python and the analysis
dependencies on first run, needs no administrator rights, and installs into your user
profile:

```powershell
winget install --id=astral-sh.uv -e
```

Behind a corporate proxy, two settings save a lot of time:

```powershell
$env:UV_NATIVE_TLS = "true"                        # use the Windows certificate store
$env:UV_DEFAULT_INDEX = "https://nexus.example/repository/pypi/simple"
```

Without `UV_NATIVE_TLS`, an intercepting proxy breaks TLS with an opaque error.

The acquisition half — `doctor`, `newscope`, `checkscope` — needs nothing but Python, so it
works on a locked-down machine before uv exists.

```bash
py -3 scripts/tcscope.py doctor        # tells you exactly what is missing, and the fix
                                       # (py -3 on Windows; python3 elsewhere)
```

## Layout

```
twincat-scope/
├── SKILL.md                        entry point — rules, workflow, routing
├── references/
│   ├── data-triage.md              CORE — the method, the envelope rule
│   ├── recording-load.md           CORE — why a recording is not free
│   ├── scope-configuration.md      VENDOR — .tcscopex schema, GUID linkage
│   └── export-tool.md              VENDOR — TC3ScopeExportTool.exe, CSV traps
├── scripts/tcscope.py              every verb
├── templates/                      known-good .tcscopex
├── examples/                       real recordings — empty by design
├── tests/                          synthetic fixtures with planted defects
└── tools/update-skill.ps1          zip install, for teams avoiding submodules
```

## Status

**A generated `.tcscopex` has recorded on a real machine** — five NC axis channels, on the
third round of a field session (`evals/field-review-1fa0e9b-rounds.md`). The first two rounds,
and an earlier session (`evals/field-review-1fa0e9b.md`), found the type, port and name
defects that stood in the way. Those rounds ran patches to an older version. This one writes
the same type, name, port and addressing fields, plus an `AxisStyle` per axis and new colours
that Scope has never read — no file from it has been opened yet. Bit, integer and PLC-side
channels and triggers have not been seen working either. Specifically:

- The `.tcscopex` schema was derived by reading real Beckhoff sample projects, and the
  templates validate against it. `checkscope` has been run against 7 real Beckhoff-authored
  projects, which shows it can *read* one — not that it can write an equivalent.
- The CSV reader **was** measured against 19 genuine `TC3ScopeExportTool.exe` exports from a
  Beckhoff CX/AX8000 machine (TwinCAT 3.1, EU locale), covering both the TAB and `,`
  dialects and all three sample-rate alignment states. Those recordings carry customer
  machine behaviour and are not in this repo; `tests/make_real_fixtures.py` regenerates
  structural copies of all five layouts instead.
- The analysis verbs are tested against those structural fixtures and against synthetic ones
  with planted defects — a step, a 3-sample spike, a flatline, a clipped channel. No `.svdx`
  has been converted by the real export tool here.

`SKILL.md` rule 3 tells the agent never to claim something is verified when it is not. The
same honesty applies to the skill itself.

**The most useful contribution now is a recording from a generated file with bit, integer and
PLC channels in it**, a look at the `--theme` colours in real Scope View, and a confirmation
that `.svdx` export behaves as documented.

## Tests

```bash
py -3 tests/make_fixture.py       # synthetic recordings, US and EU locale
py -3 tests/test_verbs.py         # end-to-end checks; a script, not a pytest suite,
                                  # so `pytest` collects nothing from it
                                  # (py -3 on Windows; python3 elsewhere, as CI runs them)
```

## Licence

MIT — see `LICENSE`.
