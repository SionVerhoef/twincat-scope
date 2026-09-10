# Working on this repository

These rules apply to anyone — human or agent — **editing this repository**. They are not
instructions for using the skill on your own machine, where your data is your own.

## This repository is public

`github.com/SionVerhoef/twincat-scope` is world-readable, mirrored by anyone who clones it,
and installed as a submodule into other people's projects. Assume every commit is permanent
and already read by a stranger.

## Treat every measurement as if it were under NDA

Scope recordings come from real machines belonging to real customers. Handle all of it as
confidential by default — not only the files someone explicitly marked as such.

**Never commit anything that identifies a customer, a site, a machine or a controller.**
That includes, in files *and* in commit messages, changelog entries, test fixtures, eval
transcripts, field reviews and issue text:

- **`AmsNetId` values, IP addresses, hostnames** — these name one controller on one network
- **`IndexGroup` / `IndexOffset`** — memory addresses from one specific build
- **Customer, site or end-user names**, machine numbers, serial numbers, project codes —
  including inside channel names, symbol paths, file names and the CSV preamble
- **Setpoints, recipes, cycle times, tuning parameters** — commercially sensitive
- Screenshots and plots, which carry all of the above in their axis labels and legends

## Anonymise by substitution, not by deletion

The point is to remove identity while keeping the evidence. Rename
`Klant_A_Vulmachine.Axis3.ActPos` to `Line1.Axis3.ActPos` and replace the NetID with
`1.2.3.4.1.1`: every structural signal survives, nothing identifies anyone.

**Names are stand-ins; numbers are real.** Sample rates, row counts, skews, column layouts
and timings are the evidence and should be reported as measured. The names are not evidence,
so they get replaced. `evals/field-review-af54888.md` is the worked example of this — read it
before writing up any work done against real recordings.

Naming a *product* is fine and often necessary: "AX8000-series drives", "TC3.1", "linear-motor
transport" describe hardware anyone can buy. Naming *whose* machine it is, is not.

## Everything here must apply to everybody

This is a general-purpose skill. Every reference, rule, threshold and example must make sense
to a reader who has never seen the machine it was derived from. If a sentence only makes sense
to someone with access to one specific installation, it is wrong for this repo — generalise it
or leave it out. A finding learned from one machine is welcome; the machine's identity is not
part of the finding.

## Before adding any real file

`examples/README.md` carries the full redaction checklist and is the authority for files
dropped into `examples/`. Read it first. Recorded data itself (`*.svdx`, `*.csv` fixtures,
`*.png`) is gitignored on purpose — do not add exceptions to `.gitignore` to force one in.

## If something private has already been committed

**Stop and tell the maintainer.** Do not quietly delete it in a follow-up commit: on a public
repo the old blob stays reachable in history and on every clone and fork. Removing it needs a
history rewrite and a force-push, which is a decision for the maintainer, not for an agent.
