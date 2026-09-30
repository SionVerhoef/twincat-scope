# Field review -- v1.0.0 (first round after the release)

Run by an agent on the same commissioning workstation as the rounds before (Windows 10, decimal-comma
locale, TwinCAT 3.1 build 4024.55, TcXaeShell 15.0, Python 3.12.10, Windows PowerShell 5.1 and
PowerShell 7.5). The subject: the `v1.0.0` tag (`a6cf947`), installed the way a user would.

**Anonymised.** Symbol paths, channel names, NetIDs and file names are replaced; counts and
kinds are measured. Setpoints, positions, cycle times and tuning values are left out. Part C's
values are normalised as described there. Wall-clock times appear only as offsets; index groups
and offsets are never given. Axes are `axis1`-`axis3` as in the reviews before; the PLC INT16
sequence variables are `seq1`-`seq4`. Recordings stayed on the machine.

## Verdict

| Item | Result | Bug or observation |
|---|---|---|
| Setup -- README install | ✅ worked exactly as written | -- |
| Setup -- tests | ✅ 343/343 on Windows (348 less the same 5), grader passes | -- |
| A1 -- `update-skill.ps1`, latest | ✅ v1.0.0, `SKILL.md` at the top, temp zip and unpack folder gone | -- |
| A2 -- `-Version v1.0.0` over an install | ✅ replaced cleanly (a stray file in the target was gone) | -- |
| A3 -- no network | ✅ clear error, exit 1, target untouched | -- |
| A -- a mistyped `-Version` | ⚠️ reported as "Could not reach the GitHub API" with proxy advice | **bug** (minor), fixed in the patch |
| A -- execution policy | ✅ not blocked from a clone; ⚠️ blocked when the script carries Mark-of-the-Web | **doc bug**, fixed in the patch |
| A4 -- `doctor` from the installed copy | ✅ all checks ok; the script's closing hint is `py -3 …\scripts\tcscope.py doctor` | -- |
| B1 -- parked at a software limit | ✅ no clipping; SetPos at its max 81.7 % of the time is a `hold` | -- |
| B1b -- parked against a physical end stop (extra) | ✅ no clipping; ⚠️ a 27 s standing following error ranks only as 2 ramps | observation |
| B2 -- genuine saturation | ⏸ not produced: the axis has no torque signal, no limit reached | -- |
| C -- shape of the #40 SetAcc spike | ✅ captured, normalised (table below) | data for bead mez |
| D -- where XAE keeps its theme | ✅ **found**: one `HKCU` registry value, no admin needed | data for bead 8ln |
| E -- integer state channels, capped 20 | ✅ tables below; no slot is a machine defect | data for bead 99j |

Tests: **343/343** on v1.0.0 and with the patch (the patch touches only `tools/update-skill.ps1`,
`README.md` and this file).

## Setup: pass

In a scratch repository, `git submodule add https://github.com/SionVerhoef/twincat-scope
.claude/skills/twincat-scope`, then `git -C .claude/skills/twincat-scope checkout v1.0.0` and
`git add`. HEAD is `a6cf947`. The only output besides the clone was git's usual *LF will be
replaced by CRLF* warning for `.gitmodules`.

From the pinned folder: `make_fixture.py` and `make_real_fixtures.py` run, `test_verbs.py` ends
**343/343 checks passed**, `evals/test_grader.py` ends "grader separates good from trapped answers
on every eval."

## Part A -- `tools/update-skill.ps1`

Target: a scratch folder. `%TEMP%` held no `twincat-scope*` entry before any run.

**Execution policy.** `Get-ExecutionPolicy -List`: `LocalMachine RemoteSigned`, everything else
`Undefined` (the agent's own shell also had `Process Bypass`, so every run below was repeated in a
child `powershell.exe`/`pwsh` with that removed). A script from a git clone carries no
Mark-of-the-Web, so `RemoteSigned` **runs it with nothing extra needed**. A copy marked as
downloaded (`Zone.Identifier` `ZoneId=3`, what a browser writes) is refused, verbatim (5.1):

```
File …\motw.ps1 cannot be loaded. The file …\motw.ps1 is not digitally signed. You cannot run
this script on the current system. For more information about running scripts and setting
execution policy, see about_Execution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
    + FullyQualifiedErrorId : UnauthorizedAccess
```

That matters, because the script exists for people who do not clone: the natural way to get it
without git is to save it from the browser. `Unblock-File`, or `-ExecutionPolicy Bypass -File`,
runs it. The README said neither (fixed in the patch).

**1. Latest: pass.** Run from PowerShell 7.5:

```
Looking up latest release of SionVerhoef/twincat-scope...
Downloading v1.0.0...

Installed twincat-scope v1.0.0 into <scratch>\twincat-scope
Check the environment with:  py -3 <scratch>\twincat-scope\scripts\tcscope.py doctor
```

`SKILL.md` is at the top of the target, not one folder down. Afterwards `%TEMP%` holds no
`twincat-scope-v1.0.0.zip` and no `twincat-scope-unpack-*`. The content matches the submodule
checkout file for file; the only difference is line endings: the zip is LF, the clone CRLF by
`core.autocrlf`. The `.tcscopex` templates are `-text` and identical either way. *(Observation.)*
The zip also carries `tests/`, `evals/` and `.github/`. *(Observation.)*

**2. `-Version v1.0.0` over the install: pass.** From Windows PowerShell 5.1.19041 under
`RemoteSigned`. It printed `Replacing existing <scratch>\twincat-scope`; a marker file put into
the target beforehand was gone, `SKILL.md` was there, nothing nested, `%TEMP%` clean.

**3. No network: pass.** A dead proxy (`127.0.0.1:9`) in the child process only. Verbatim, 5.1:

```
update-skill.ps1 : Could not reach the GitHub API: Unable to connect to the remote server
Behind a corporate proxy you may need:
    [System.Net.WebRequest]::DefaultWebProxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials
If the repository has no releases yet, this script has nothing to download -
use the git submodule install from README.md instead.
    + CategoryInfo          : NotSpecified: (:) [Write-Error], WriteErrorException
```

PowerShell 7: `Write-Error: Could not reach the GitHub API: No connection could be made because
the target machine actively refused it. (127.0.0.1:9)` and the same advice. Process exit code 1
both times, and the marker file in the target survived: **the existing install is untouched.**

**Also tried: a tag that does not exist (`-Version v9.9.9`). Bug, minor.** Verbatim, PowerShell 7:

```
Write-Error: …\tools\update-skill.ps1:44
Line |
  44 |  Could not reach the GitHub API: $($_.Exception.Message)
     | Could not reach the GitHub API: Response status code does not indicate success: 404 (Not Found).  Behind a
     | corporate proxy you may need: …
```

The API was reached; the tag was wrong. The message sends the user to their proxy settings. Two
smaller points in the same block: under `$ErrorActionPreference = "Stop"` the `Write-Error`
throws, so the `exit 1` after it never runs (the exit code is still 1, by the terminating error),
and PowerShell 7 frames the text in a source-line box that flattens its line breaks.
**Fixed in the patch:** a 404 says `No release 'v9.9.9' in SionVerhoef/twincat-scope (GitHub
answered 404)` and points at the releases page; anything else keeps the network message; both
print plainly, end `Nothing was changed in <target>.` and reach `exit 1`. Re-run on 5.1 and 7:
404, dead proxy and a real install all behave, target untouched on both failures.

**Doc, observation.** The README said the script installs "into the same location" as the
submodule, but its default `-Target` is `.github/skills/twincat-scope` (Copilot). A Claude Code
user running it bare gets the skill where Claude Code does not look. The patch says to pass
`-Target .claude\skills\twincat-scope`.

**4. `doctor` from the installed copy: pass.** `py -3 scripts\tcscope.py doctor` → `"ok": true`,
all seven checks ok (Python 3.12.10, uv, numpy, pyarrow, matplotlib, the TF3300 export tool, the
cache at `%LOCALAPPDATA%\tcscope\cache`), exit 0. With nothing failing it prints no fix line; the
hint the user sees is the script's own closing line, and that is **`py -3`**.

## Part B -- clipping on a parked axis and a real saturation

One axis (not one of R3's `axis1`-`axis3`), recorded with a file from `newscope` (ActPos, SetPos,
PosDiff, ActVelo, SetVelo, ActTorque; NC port 501, all typed `nc-field`; 2 ms; 40 s window;
3 000 samples/s, `checkscope` no problems). The user moved the axis and started and stopped both
recordings; nothing was written to the controller. Both recorded without an error: 20 000 rows,
39.998 s, no gaps, `cross_group_timing_valid: true`. Values below are normalised: positions by
the stroke of SetPos in that recording, velocities by the largest |SetVelo|.

**ActTorque is constant 0 in both** (`manifest` `constant: true`; `stats` 100 % at min and max).
On this axis the NC's torque field is not fed by the drive. `events` reports **nothing** for it,
which is right: a channel at one value throughout is not clipping.

**1. Parked at a software limit: pass.** The user moved the axis to its software limit and left it
there. The move ran from about 4.2 s to 7.3 s; the axis then stood for 32.7 s.

| Channel | kinds and counts | clipping | at max / min (`stats`) |
|---|---|---|---|
| SetPos | 2 hold, 1 ramp | **none** | 81.7 % / 10.4 % |
| SetVelo | 3 hold, 2 ramp | none | 7.7 % / 92.1 % |
| ActPos | none | none | 0.07 % / 0.005 % |
| PosDiff | 22 ramp, 7 spike | none | -- |
| ActVelo | 16 ramp, 3 step | none | -- |
| ActTorque | none (constant) | none | 100 % / 100 % |

SetPos sits exactly at its maximum for 81.7 % of the recording, the case a naive rail detector
calls clipping, and it is reported as a `hold` of 16 344 samples from 7.31 s: **the expectation is
met.** ActPos parks with encoder quantisation (7 distinct values over the last 10 s, following
error within 2e-5 of the stroke), so it never sits at one maximum and is not a candidate either.
The 7 PosDiff spikes (23-34 samples wide, severity 12-31) and the ActVelo steps all fall in the
move, 5.0-7.0 s; none in the parked part. *(Observation: whether those PosDiff bumps during the
move are tuning or normal was not checked.)*

**1b. Parked against a physical end stop (not asked for; done by the user).** The same move,
driven onto a mechanical stop.

| Channel | kinds and counts | clipping |
|---|---|---|
| SetPos | 2 hold, 1 ramp | **none** (at max 66.9 %) |
| SetVelo | 3 hold, 2 ramp | none |
| ActPos | none | none |
| PosDiff | **2 ramp** | none |
| ActVelo | 36 ramp, 11 step, **4 spike** | none |
| ActTorque | none (constant) | none |

What the data shows: ActPos stops about **0.10 of the stroke short** of the target from about
12.3 s, while SetPos runs on to the target at 13.24 s and holds there. PosDiff then **stands at
about 0.10-0.11 of the stroke for the remaining 27 s**. Twice (15.844 s and 31.172 s) ActPos
**springs back** a further ~0.012 of the stroke within 7 samples (14 ms), and in between creeps
back towards the stop. Those two are the ActVelo spikes of severity 538 and 534, the only
high-severity events in the file, peaking at 5.9× the largest commanded velocity. The recording
cannot say why: the mechanism yielding, or the drive easing off, are both consistent with it, and
no torque, error code or axis state was recorded to tell them apart.

What `events` did not say *(observations, not bugs; no kind promises them)*:
- **The standing following error is reported only as 2 PosDiff ramps.** 27 s of a following error
  at a tenth of the stroke is the headline of this recording; `stats` shows it (the mean), `events`
  describes only the ramp into it. A "stands away from zero" kind, or a hold on a noisy channel,
  would be needed to rank it.
- **The stall is not a frozen sensor.** For ~0.9 s (12.3-13.24 s) ActPos stood almost still while
  SetPos moved, but with quantisation noise, so #39's exact-flatline `while_moving` check does not
  fire. That is correct for "frozen sensor", and it means a blocked axis has no event of its own.

**2. A genuine saturation: not produced.** The axis has no torque signal (above), and no torque or
velocity limit was reached on it. Not pushed for one, per the brief. The end stop is a mechanical
block, not a signal at a rail: no channel sits at a limit value, and `clipping` correctly stays
silent.

## Part C -- the shape of the #40 SetAcc spike (bead mez)

R3 re-ingested from the `.svdx` with v1.0.0 (600 s, 33 channels, 2 ms). `events` in full: 27 360
events, the same total as last round with its patch. axis1.SetAcc: 3 367 ramp, 333 hold, 57 step,
22 spike, unchanged.

The #40 event is the **only SetAcc spike with `width_samples: 2`**; the other 21 are 3 or 4 wide
and all `recurring`. It sits 131.258 s into the recording.

| Field | Value |
|---|---|
| kind | `spike` |
| delta | **0.186** (normalised as below) |
| width_samples | 2 |
| severity | 1.022 |
| recurring | true |
| detection threshold | **not reported** by `events`. Since severity is "multiple of each detector's own threshold", it is implied: delta / severity ≈ 0.182 normalised |

**Normalisation:** every value divided by the largest absolute SetAcc in the whole recording
(from `stats`; the channel's min and max are symmetric, so they normalise to -1.000 and +1.000),
rounded to 3 decimals. Time is the sample index relative to the event (0 = the event's index).
`window` returned 42 rows from -20 to +21.

| i | SetAcc | | i | SetAcc | | i | SetAcc |
|---:|---:|---|---:|---:|---|---:|---:|
| -20 | -0.707 | | -6 | -0.892 | | 8 | -0.975 |
| -19 | -0.749 | | -5 | -0.801 | | 9 | -0.974 |
| -18 | -0.787 | | -4 | -0.679 | | 10 | -0.968 |
| -17 | -0.822 | | -3 | -0.533 | | 11 | -0.959 |
| -16 | -0.854 | | -2 | -0.367 | | 12 | -0.946 |
| -15 | -0.883 | | -1 | -0.188 | | 13 | -0.929 |
| -14 | -0.907 | | **0** | **-0.001** | | 14 | -0.908 |
| -13 | -0.929 | | 1 | -0.185 | | 15 | -0.883 |
| -12 | -0.946 | | 2 | -0.365 | | 16 | -0.855 |
| -11 | -0.959 | | 3 | -0.531 | | 17 | -0.823 |
| -10 | -0.968 | | 4 | -0.678 | | 18 | -0.788 |
| -9 | -0.974 | | 5 | -0.799 | | 19 | -0.749 |
| -8 | -0.975 | | 6 | -0.892 | | 20 | -0.708 |
| -7 | -0.951 | | 7 | -0.951 | | 21 | -0.663 |

**What the shape is.** Mirror-symmetric about sample 0. The acceleration eases down to about
-0.975, then climbs in steps that grow and level off (0.024, 0.059, 0.091, 0.122, 0.146, 0.166, 0.179, **0.187**)
to just short of zero, and goes back down the same steps. It is the acceleration command turning round just short of zero at close to its full rate of
change (jerk), not a sample that jumps out and back.

**Why #40 calls it a spike.** The event's delta (0.186) is the **last flank step**, not an
excursion: the step into sample 0 (0.187) and out of it (0.184) are the same size as the step
before them (0.179). One sample is "out", its two neighbours flank it, and the threshold (≈0.182)
sits just under the flank step. A test that would separate it: in a real spike the step into the
peak is much larger than the step before it; here the ratio is 0.187 / 0.179 ≈ 1.04. Equally, the
second difference is small everywhere except at the apex, where it is about 2× the flank step and
no more. *(Data for a fix; no fix in this round.)*

## Part D -- where TwinCAT keeps its colour theme (bead 8ln)

**1. The IDE:** the standalone **TcXaeShell** (`C:\Program Files (x86)\Beckhoff\TcXaeShell\
Common7\IDE\TcXaeShell.exe`, file and product version 15.0.0.0; `Profile\BuildNum` 15.0.28010,
the Visual Studio 2017 isolated shell). No Visual Studio `devenv` was running.

**2. What changed.** Theme switched by the user through Tools > Options > Environment > General >
Color Theme, read by the agent after each switch, XAE left running; then back to Dark and XAE
closed and reopened.

| Location | Dark (start) | → Light | → Blue | → Dark, XAE restarted |
|---|---|---|---|---|
| `HKCU\Software\Beckhoff\TcXaeShell\15.0_IsoShell\ApplicationPrivateSettings\Microsoft\VisualStudio` → `ColorTheme` | Dark | **Light, at once** | **Blue, at once** | Dark |
| same key → `ColorThemeNew` | Dark | Light | Blue | Dark |
| `HKCU\Software\Microsoft\VisualStudio` /s /f ColorTheme | 0 matches | 0 | 0 | 0 |
| `…\15.0_IsoShell_Config\Settings\Microsoft.VisualStudio.ColorTheme(New)` | flags only (`IsRoamed` etc.), no theme | unchanged | unchanged | unchanged |
| the live `.vssettings` (`Profile\AutoSaveFile` → `%LOCALAPPDATA%\Beckhoff\TcXaeShell\15.0_IsoShell\Settings\TcXaeShell\CurrentSettings-<date>.vssettings`), `<Theme Id="{…}"/>` | Dark | **unchanged** (same hash) | **unchanged** | rewritten **on exit**, 6 s before the new process started; Dark |
| three older `CurrentSettings-*.vssettings` in the same folder | Blue | unchanged | unchanged | unchanged |
| `privateregistry.bin` under `%LOCALAPPDATA%\Microsoft\VisualStudio\*` or `%LOCALAPPDATA%\Beckhoff\*` | **does not exist** | -- | -- | -- |

The value's format is `0*System.String*<guid>` for `ColorTheme` and `0*System.String*{<guid>}`
for `ColorThemeNew`, matching the three GUIDs in the brief.

**3. Result: found.** The reliable source is

```
HKCU\Software\Beckhoff\TcXaeShell\15.0_IsoShell\ApplicationPrivateSettings\Microsoft\VisualStudio
    ColorTheme    REG_SZ    0*System.String*<theme GUID>
```

It changes the moment the user presses OK and is **readable without admin rights** (the user has
full control of the key; nothing outside `HKCU` is involved). The `.vssettings` file is
unreliable: it lags the IDE until it closes, and the folder holds several stale copies with other
themes. Scope of the finding: TcXaeShell 15.0 on one PC. Where TwinCAT integrated into a full
Visual Studio keeps it was not checked (none here; a `privateregistry.bin` there is plausible but
unverified). A custom theme would carry a GUID not in the table and should fall back to the default.

## Part E -- integer state channels and the capped 20 (bead 99j)

R3 with v1.0.0. Pair counts come from `events` (`from`/`to` of every step), and a direct count of
value changes in the Parquet agrees with them exactly on every channel.

| Channel | changes | distinct from→to pairs | ×1 | ×2-4 | ×5-19 | ×20+ | `recurring` | at 0 | error-code-like? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| seq1 (INT16) | 3 269 | 14 | 3 | 6 | 0 | 5 | 3 254 | 0 % | no: never 0, most common value 45 % |
| seq2 (INT16) | 1 568 | 19 | 5 | 2 | 0 | 12 | 1 559 | 0 % | no: never 0, 39 % |
| seq3 (INT16) | 1 558 | 19 | 5 | 2 | 0 | 12 | 1 549 | 0 % | no: never 0, 39 % |
| seq4 (INT16) | 7 | 5 | 3 | 2 | 0 | 0 | 0 | 0 % | no: never 0, 61 % |
| axis2.AxisState | 2 603 | 5 | 1 | 0 | 0 | 4 | 2 602 | 56 % | no: 0 is the most common value but at 56 %, not "rarely non-zero" |
| axis2.CoupleState | 435 | 2 | 0 | 0 | 0 | 2 | 435 | 41 % | no: two-valued, 59/41 |

The recording's two genuinely error-code-like channels, the axis's `ErrState` and `ErrorCode`,
sit at 0 for all 600 s and report nothing. So R3 has **no** channel that looks like an error
code *and* changes: option 2 of last round (a state change is a defect only on error-code-like
channels) would demote every integer state change here to descriptive.

Worth noting for the design: the 5-19 band is empty on every state channel. A pair is either a
one-off / handful (sequence start, stop, a branch taken twice) or routine (20+).

**The capped 20** (`events --max-events 20`, 1.45 s):

| # | kind | channel | severity | recurring | defect? |
|---:|---|---|---:|---|---|
| 1 | clipping (max, 57.8 %) | PLC REAL64 rate | 57.8 | -- | **no** -- a filtered rate sitting at one of its values; 6 distinct values, two of them 98.7 % of the time. Clipping is the wrong kind for a near-two-valued channel (tool) |
| 2 | clipping (min, 40.9 %) | the same | 40.9 | -- | no, same |
| 3 | step | seq2 | 200 | no | no -- sequence start |
| 4 | step | seq3 | 280 | no | no -- start, first branch |
| 5 | step | seq2 | 210 | no | no -- start, first branch |
| 6 | flatline (19 847 samples) | the PLC REAL64 rate | 396.9 | -- | no -- the same rate standing still |
| 7 | step | PLC INT product count | 14 | no | no -- products leaving (the count drops) |
| 8 | step | the same | 14 | no | no -- same |
| 9 | step | the same | 14 | no | no -- same |
| 10 | step | the same | 8 | no | no -- a smaller drop |
| 11 | step (2 wide) | axis1.SetAcc | 2.09 | no | no -- routine on a command channel |
| 12 | step (2 wide) | axis1.SetAcc | 2.09 | no | no -- same |
| 13 | flatline (114 062 samples) | axis1.PosDiff | 2 281 | -- | no -- the axis idle after the stop |
| 14 | step | seq1 | 1 580 | no | no -- **the stop**, 14 ms after PosDiff froze |
| 15 | step | seq2 | 1 380 | no | no -- the stop |
| 16 | step | seq3 | 1 380 | no | no -- the stop |
| 17 | step | seq2 | 200 | no | no -- the restart |
| 18 | step | seq3 | 200 | no | no -- the restart |
| 19 | step | seq2 | 264 | no | no -- restart, branch |
| 20 | step | seq3 | 210 | no | no -- restart, branch |

**None of the 20 is a machine defect.** The stop (14-16) and the frozen following error (13)
are what a diagnosis of this recording wants to see first. New against last round's list: the
**product count takes 4 slots** (7-10). It is a counter, not a state: 14 distinct pairs, and
its most common drop occurs 10 times, below the 20-alike line, so none is `recurring`. That is
the risk the capped-20 design has to answer: the 5-19 band, empty on the state channels, is where
a counter lives.

*Note added on the development machine:* this round ran v1.0.0. PR #48, merged after it, makes a
change between states a channel visits anyway a descriptive `transition`, and keeps a `step` only
for a jump into a state entered once or a change on an error code. Under #48 the sequence start
and branches (3-5, 17-20) and the product count (7-10) are transitions; the stop (14-16) stays a
step only where its state is entered once. Not yet re-run on R3.

## For the beads

- **mez:** Part C's table. The flank-step ratio (≈1.04 here) separates a jerk reversal from a
  spike.
- **8ln:** the registry value in Part D; `0*System.String*` prefix, GUID after it; TcXaeShell 15.0
  only.
- **99j:** Part E's tables. No state channel here is error-code-like; a counter (not a state)
  took 4 capped slots with pairs in the 5-19 band.
- **a4z:** passed; the patch fixes the 404 message and documents Mark-of-the-Web and `-Target`.
- **56p:** the parked half passes, on a software limit and on an end stop. The saturation half
  stays open: it needs an axis whose drive feeds a torque value and reaches its limit in normal
  work. New from the end stop: a blocked axis (large, noisy, standing following error) has no
  event kind of its own.

## Still untested

- a genuine saturation (B2);
- Subsave with a Professional licence;
- the 19 original exports;
- `correlate` on a broken multi-group export;
- the theme location under TwinCAT integrated into a full Visual Studio.
