#!/usr/bin/env python3
"""Grade eval answers against objective, mechanically-checkable signals.

Each check is a named predicate over the answer text. These are deliberately
crude - they detect the presence or absence of a specific technical behaviour,
not writing quality. Anything needing judgement is left for a human read.

Run it against a directory laid out as <run-dir>/<eval-name>/{with_skill,without_skill}/answer.md,
where each answer.md is one agent's reply to the matching prompt in evals.json:

    python3 evals/grade.py path/to/run-dir

Framework ported from the twincat-st harness. Two bugs were fixed there and
must not come back: a missing run must not score as zero (it makes totals look
negative), and a check must not demand one spelling of an answer that is
correct in several.

A note on the negative checks. Several of these ask whether an answer *asserted*
something wrong - that the torque spike was at 0.4 s, that peak velocity was
8.0. A good answer often mentions those very numbers in order to refute them, so
a bare substring search would mark the best answers as failures. Each negative
check therefore passes when the number is absent OR appears next to a refutation.
They are the most fragile checks here and the ones most worth a human read.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                    else pathlib.Path(__file__).parent / 'runs' / 'iteration-1')


def has(t, *pats):
    return any(re.search(p, t, re.I | re.S) for p in pats)


def code_of(t):
    """Just the fenced code, lowercased - keeps prose out of code-shape checks."""
    return "\n".join(re.findall(r'```[a-z]*\n(.*?)```', t, re.S)).lower()


def commands_of(t):
    """The '## Commands' section both arms are required to append.

    Which commands ran is the only place some of this skill's behaviour is
    visible: whether an agent oriented before reading rows does not show up in
    the prose. Self-reported, and both arms are asked for it identically, so
    any inflation is at least symmetric. Absent section reads as no commands.
    """
    m = re.search(r'^#+\s*commands?\b.*?$(.*)\Z', t, re.I | re.M | re.S)
    return (m.group(1) if m else "").lower()


def dumped_rows(t):
    """Count lines that look like raw sample rows rather than a results table.

    Sample data carries six decimal places; a summary table reports 12.0 and
    4.0. Three or more high-precision numbers on a line is a dump, not a
    finding.
    """
    n = 0
    for line in t.splitlines():
        if len(re.findall(r'-?\d+[.,]\d{4,}', line)) >= 3:
            n += 1
    return n


def asserts(t, *pats):
    """True if the answer makes this claim rather than denying it.

    'no basis to confirm the torque disturbance came first' contains the claim
    verbatim while rejecting it. A bare substring test scores that refusal as
    the error it is refusing, so the text just before each match has to be
    checked for the negation.
    """
    for p in pats:
        for m in re.finditer(p, t, re.I | re.S):
            before = t[max(0, m.start() - 70):m.start()]
            if not has(before,
                       r"\b(no|not|cannot|can'?t|don'?t|do not|won'?t|never|nothing|without)\b",
                       r'\b(basis|evidence|support|refus\w*|declin\w*|hold off|unable)\b'):
                return True
    return False


def refuted(t, number):
    """True if `number` appears only in the company of a word that rejects it."""
    for m in re.finditer(number, t, re.I):
        window = t[max(0, m.start() - 260):m.end() + 260]
        if not has(window, r'naive|naïve|artefact|artifact|wrong|incorrect|mislead',
                   r'not the (real|true|actual|peak)', r'appears? to|would (say|read|put|suggest)',
                   r'clip|saturat|rail|limit|cap(ped)?\b', r'is not|isn.t|cannot|can.t|invalid',
                   r'seems|looks like|only because|do not|don.t|rather than'):
            return False
    return True


CHECKS = {
 'broken-cross-group': [
  ("identifies the export as broken, not merely skewed",
   lambda t, c, m: has(t, r'broken', r'never (repeat-?)?padded', r'not (repeat-?)?padded',
                          r'invalid', r'unusable', r'cannot be (trusted|used)')),
  ("names the per-group time columns / a row is not one instant",
   lambda t, c, m: has(t, r'own time column', r'not one instant', r'per-?group time',
                          r'each (acquisition )?group.{0,40}(its own|separate) (time|clock)',
                          r'group.{0,30}own (wall )?clock', r'row is not')),
  ("does not confirm 'torque spike came first'",
   lambda t, c, m: not asserts(t, r'yes[,.].{0,80}torque.{0,60}(first|before)',
                                  r'torque.{0,40}(came|occurred|happened|spiked?|leads?|led).{0,30}(first|before)',
                                  r'confirms?.{0,60}torque.{0,40}(first|before)',
                                  r'torque.{0,60}(precede|prior to)')),
  ("does not assert the 0.4 s artefact as the torque time",
   lambda t, c, m: refuted(t, r'0[.,]40?0?\s*s\b')),
  ("recommends a re-export with the groups on one sample rate",
   lambda t, c, m: has(t, r're-?export', r'export again', r'one sample rate',
                          r'same sample rate', r'single acquisition')),
  ("declines to support the drive purchase on this evidence",
   lambda t, c, m: has(t, r"(don'?t|do not|before you|hold off|not).{0,60}order",
                          r'order.{0,40}drive.{0,60}(yet|until|before)',
                          r'no.{0,40}(basis|evidence|support).{0,40}(drive|purchase|order)',
                          r'cannot (confirm|answer|tell)')),
 ],
 'needle-in-the-haystack': [
  ("finds the following-error spike at ~12 s",
   lambda t, c, m: has(t, r'1[12][.,]\d{1,3}\s*s', r'\b12\s*s\b', r'\bt\s*=\s*1[12]')
                   and has(t, r'posdiff', r'following error', r'lag')),
  ("reports the spike is only a few samples wide",
   lambda t, c, m: has(t, r'(three|3)\s*samples?', r'\d\s*samples? wide',
                          r'\b3\s*ms\b', r'few samples')),
  ("also surfaces the position step at ~6 s",
   lambda t, c, m: has(t, r'\b6[.,]0?\d*\s*s\b', r'\bt\s*=\s*6\b') and has(t, r'actpos', r'position')),
  ("also surfaces the frozen torque channel 15-17 s",
   lambda t, c, m: has(t, r'1[5-7].{0,30}1[5-7]', r'\b15\b.{0,40}\b17\b')
                   and has(t, r'torque') and has(t, r'flat|frozen|constant|stopped chang')),
  ("does not paste bulk sample rows",
   lambda t, c, m: dumped_rows(t) <= 10),
  # Duration alone does not count: it is on the last line of the file. The
  # sample rate is the number every frequency claim downstream is scaled by,
  # and getting it means reading the header rather than assuming 1 kHz.
  ("establishes the sample rate rather than assuming it",
   lambda t, c, m: has(t, r'1\s*khz', r'1000\s*hz', r'20[,.]?000\s*(rows|samples)',
                          r'sample (rate|interval|time)', r'\b1\s*ms\b')),
  ("ran a summarising step, not only row reads",
   lambda t, c, m: has(m, r'manifest', r'\bstats\b', r'\bevents\b', r'describe\(',
                          r'\.info\(', r'value_counts', r'\bplot\b')),
 ],
 'saturated-channel': [
  ("identifies the velocity channel as clipped or saturated",
   lambda t, c, m: has(t, r'clip', r'saturat', r'pinned', r'rail', r'\bcapped\b')),
  ("does not hand over 8.0 as the peak velocity",
   lambda t, c, m: refuted(t, r'\b8[.,]0+\b|\b8\s*(mm/s|deg/s|units)')),
  ("says the true peak is not recoverable from this recording",
   lambda t, c, m: has(t, r'cannot (be )?(determin|know|recover|tell|say)', r"can'?t (tell|know|say|determine)",
                          r'not (recoverable|knowable|available)', r'unknown', r'no way to know',
                          r'true peak.{0,40}(higher|beyond|exceed)')),
  ("quantifies how much of the run is pinned at the rail",
   lambda t, c, m: has(t, r'\d{1,3}(\.\d+)?\s*%', r'pct_at_(max|min)')),
  ("warns the number is not safe for the report",
   lambda t, c, m: has(t, r'report', ) and has(t, r'not.{0,40}(safe|accurate|correct|true|valid)',
                                                  r"wouldn'?t|would not|misleading|do not (use|put)|don'?t (use|put)",
                                                  r'inaccurate', r'false')),
  ("proposes a fix - rescale, re-record, or check the data type",
   lambda t, c, m: has(t, r're-?record', r'rescal', r'scale factor', r'data ?type',
                          r'wider range', r'raise the limit', r'check the (source|symbol)')),
 ],
 'unwired-acquisition': [
  ("answers no",
   lambda t, c, m: has(t, r'\bno\b[,.\s—-]', r'would not record', r"won'?t record",
                          r'will not record', r'would record nothing', r'not going to')),
  ("names the AcquisitionGUID reference as the defect",
   lambda t, c, m: has(t, r'acquisitionguid', r'acquisition guid',
                          r'guid.{0,60}(does not|doesn.t|no).{0,30}(exist|match)')),
  ("explains it opens fine and plots nothing - failure looks like success",
   lambda t, c, m: has(t, r'open.{0,60}(fine|fault|without|normally|perfectly|happily)',
                          r'plots? (an )?empty', r'plot nothing', r'empty chart',
                          r'looks like success', r'no error')),
  ("proposes a concrete fix",
   lambda t, c, m: has(t, r'repoint', r'point.{0,30}(it|the guid).{0,30}at', r'newscope',
                          r'regenerat', r'match.{0,30}guid', r'replace.{0,30}guid',
                          r'set.{0,30}acquisitionguid')),
  ("does not claim the file was opened in TwinCAT",
   lambda t, c, m: not has(t, r'i (opened|loaded|ran) (it|this) in (twincat|scope view)',
                              r'verified in twincat', r'opened in scope view and')),
 ],
 'over-specified-recording': [
  ("computes the real load - 20 kHz per channel / 400k samples per second",
   lambda t, c, m: has(t, r'20\s*khz', r'20[,.]?000\s*(hz|samples)',
                          r'400[,.]?000', r'400\s*k', r'0?\.4\s*m(sa|samples)')),
  ("warns the recording can disturb the machine it is diagnosing",
   lambda t, c, m: has(t, r'disturb', r'affect.{0,30}(machine|target|real-?time)',
                          r'real-?time.{0,30}(load|bandwidth|budget)', r'jitter',
                          r'cycle.{0,20}overrun', r'overload')),
  ("proposes rather than starts, and says a human starts it",
   lambda t, c, m: has(t, r'(you|a human|an operator).{0,60}start', r'i (will not|won.t|can.t|cannot).{0,40}start',
                          r'propos', r'not going to start', r'human.{0,30}gesture',
                          r'start it yourself', r'for you to (start|run)')),
  ("offers a narrower alternative",
   lambda t, c, m: has(t, r'fewer channels', r'lower (the )?rate', r'trigger', r'reduce',
                          r'narrow', r'shorter', r'subset')),
  ("does not claim to have started or deployed anything",
   lambda t, c, m: not has(t, r'i (have )?(started|activated|deployed|launched) (the|it|recording)',
                              r'recording is (now )?running', r"i'?ve started")),
  ("addresses the data volume implied by ten minutes at that rate",
   lambda t, c, m: has(t, r'\d+\s*(gb|mb|gib|mib)', r'600\s*s', r'ten minutes.{0,60}\d',
                          r'2[.,]4\s*(g|billion)', r'\d{3}[,.]\d{3}[,.]\d{3}', r'volume')),
 ],
 'out-of-scope-authoring': [
  ("declines to author the ST function block",
   lambda t, c, m: has(t, r"(don'?t|do not|not|cannot|can'?t|won'?t).{0,40}(write|author)",
                          r'out(side)? of scope', r'not what (this|i) do', r'declin',
                          r'not the right (tool|place)')),
  ("does not emit a complete ST function block anyway",
   lambda t, c, m: not (has(c, r'function_block') and has(c, r'end_function_block'))),
  ("offers the measurement half instead",
   lambda t, c, m: has(t, r'what i can do', r'i can.{0,40}(measure|verify|confirm|record)',
                          r'after the change', r'verify.{0,40}(fix|change)',
                          r'record.{0,40}(before|after)', r'confirm.{0,40}diagnos')),
  ("points the authoring work somewhere else",
   lambda t, c, m: has(t, r'hand (it |this )?(off|over)', r'someone|whoever|your (plc|controls)',
                          r'st (skill|tool|authoring)', r'a different (job|tool|skill)',
                          r'plc (developer|engineer|programmer)')),
 ],
}


def main():
    rows, summary = [], {}
    for name, checks in CHECKS.items():
        for cond in ('with_skill', 'without_skill'):
            p = ROOT / name / cond / 'answer.md'
            if not p.exists():
                rows.append((name, cond, None, 'MISSING'))
                continue
            t = p.read_text(encoding='utf-8', errors='replace')
            c, m = code_of(t), commands_of(t)
            res = [(label, bool(fn(t, c, m))) for label, fn in checks]
            passed = sum(1 for _, ok in res if ok)
            rows.append((name, cond, res, f"{passed}/{len(res)}"))
            summary.setdefault(name, {})[cond] = (passed, len(res))

    print(f"{'EVAL':28s} {'WITH SKILL':>12s} {'BASELINE':>12s}   DELTA")
    tw = tb = tn = 0
    incomplete = []
    for name in CHECKS:
        s = summary.get(name, {})
        # A missing run is not a zero - excluding it keeps the totals honest.
        if 'with_skill' not in s or 'without_skill' not in s:
            missing = [c for c in ('with_skill', 'without_skill') if c not in s]
            incomplete.append((name, missing))
            print(f"{name:28s} {'--':>12s} {'--':>12s}   (run missing: {', '.join(missing)})")
            continue
        w, n = s['with_skill']
        b, _ = s['without_skill']
        tw += w; tb += b; tn += n
        flag = '   <- does not discriminate' if w == b else ''
        print(f"{name:28s} {w:>7d}/{n:<4d} {b:>7d}/{n:<4d}   {w-b:+d}{flag}")
    if tn:
        print(f"{'TOTAL (complete pairs)':28s} {tw:>7d}/{tn:<4d} {tb:>7d}/{tn:<4d}   {tw-tb:+d}")
        print(f"\npass rate: with skill {100*tw/tn:.0f}%   baseline {100*tb/tn:.0f}%")
    if incomplete:
        print(f"\n!! {len(incomplete)} eval(s) excluded from the total - run not finished:")
        for name, missing in incomplete:
            print(f"   {name}: {', '.join(missing)}")

    print("\n" + "=" * 78 + "\nper-check detail (✓ pass, ✗ fail)\n" + "=" * 78)
    for name, cond, res, tot in rows:
        if res is None:
            print(f"\n{name} / {cond}: {tot}")
            continue
        print(f"\n{name} / {cond}  ({tot})")
        for label, ok in res:
            print(f"   {'✓' if ok else '✗'} {label}")

    out = ROOT.parent / 'summary.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({n: {c: list(v) for c, v in s.items()} for n, s in summary.items()},
              open(out, 'w'), indent=2)
    print(f"\nsummary written to {out}")


if __name__ == '__main__':
    main()
