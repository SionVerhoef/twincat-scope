#!/usr/bin/env python3
"""Grade eval answers against objective, mechanically-checkable signals.

Each check is a named predicate over the answer text. These are deliberately
crude - they detect the presence or absence of a specific technical behaviour,
not writing quality. Anything needing judgement is left for a human read.

Run it against a directory laid out as <run-dir>/<eval-name>/{with_skill,without_skill}/answer.md,
where each answer.md is one agent's reply to the matching prompt in evals.json - or, for
several runs per cell, .../<arm>/run-1/answer.md and so on, each beside an optional cost.json
of {"tokens": N, "seconds": N}:

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
            # A heading or a question is never an assertion. The first real
            # answer graded here was titled 'can we tell whether the torque
            # spike came first?' and was marked as claiming exactly what it
            # went on to refuse.
            line_start = t.rfind('\n', 0, m.start()) + 1
            line_end = t.find('\n', m.end())
            line = t[line_start:line_end if line_end != -1 else len(t)]
            if line.lstrip().startswith('#') or line.rstrip().endswith('?'):
                continue

            # Wide enough to reach the clause that framed the claim. The best
            # answer to the cross-group eval states both readings in order to
            # show they contradict each other, and the sentence that marks one
            # as the naive reading can sit some way in front of it.
            before = t[max(0, m.start() - 240):m.start()]
            if not has(before,
                       r"\b(no|not|cannot|can'?t|don'?t|do not|won'?t|never|nothing|without)\b",
                       r"\b(doesn'?t|didn'?t|isn'?t|wasn'?t|wouldn'?t)\b",
                       r'\b(basis|evidence|support|refus\w*|declin\w*|hold off|unable)\b',
                       r'row-?wise|naive|naïve|excel|artefact|artifact|opposite|contradict',
                       r'would (say|read|give|suggest|put)|appears?|one reading|if you (read|open)',
                       r'two (natural )?ways|either reading|first reading|second reading'):
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
                          r"(wouldn'?t|would not|shouldn'?t|should not).{0,30}order",
                          r'order.{0,40}drive.{0,60}(yet|until|before)',
                          r'no.{0,40}(basis|evidence|support).{0,40}(drive|purchase|order)',
                          r'cannot (confirm|answer|tell)')),
 ],
 'needle-in-the-haystack': [
  ("finds the following-error spike at ~12 s",
   lambda t, c, m: has(t, r'1[12][.,]\d{1,3}\s*s', r'\b12\s*s\b', r'\bt\s*=\s*1[12]')
                   and has(t, r'posdiff', r'following error', r'lag')),
  ("reports the spike is only a few samples wide",
   lambda t, c, m: has(t, r'(three|3)[\s-]*samples?', r'\d\s*samples? wide',
                          r'\b3\s*ms\b', r'few samples')),
  ("also surfaces the position step at ~6 s",
   lambda t, c, m: has(t, r'\b6[.,]0?\d*\s*s\b', r'\bt\s*=\s*6\b') and has(t, r'actpos', r'position')),
  ("also surfaces the frozen torque channel 15-17 s",
   lambda t, c, m: has(t, r'1[5-7].{0,30}1[5-7]', r'\b15\b.{0,40}\b17\b')
                   and has(t, r'torque') and has(t, r'flat|frozen|constant|stopped chang')),
  ("also surfaces the clipped velocity channel",
   lambda t, c, m: has(t, r'velo') and has(t, r'clip', r'saturat', r'pinned', r'\brail')),
  ("does not paste bulk sample rows",
   lambda t, c, m: dumped_rows(t) <= 10),
  # Duration alone does not count: it is on the last line of the file. The
  # sample rate is the number every frequency claim downstream is scaled by,
  # and getting it means reading the header rather than assuming 1 kHz.
  ("establishes the sample rate rather than assuming it",
   lambda t, c, m: has(t, r'1\s*khz', r'1000\s*hz', r'20[,.]?000\s*(rows|samples)',
                          r'sample (rate|interval|time)', r'\b1\s*ms\b')),
  # There was a seventh check here - "ran a summarising step, not only row
  # reads" - matched against the reported commands. It was removed after the
  # first run because it cannot be scored fairly. The baseline wrote seven
  # analysis scripts to files and ran them as `uv run ... a1.py`, so its
  # summarising was real and invisible; the skill arm names its verbs on the
  # command line and always scores. It measured which tools an arm had, not
  # what it did. Restoring it needs different instrumentation - inline the
  # scripts, or capture the transcript - not a better regex.

 ],
 # The same two traps at 12 million samples. Same checks, scaled times: what
 # changes is the size of the haystack, and that is the whole measurement.
 'needle-at-scale': [
  ("finds the following-error spike at ~413.8 s",
   lambda t, c, m: has(t, r'41[34][.,]\d{1,3}\s*s', r'\b41[34]\s*s\b', r'\bt\s*=\s*41[34]',
                          r'06:06:53')
                   and has(t, r'posdiff', r'following error', r'lag')),
  ("reports the spike is only a few samples wide",
   lambda t, c, m: has(t, r'\b[1-9]\s*samples?\b', r'\d\s*samples? wide',
                          r'\b[1-9]\s*ms\b', r'few samples')),
  ("also surfaces the position step at ~128.4 s",
   lambda t, c, m: has(t, r'12[89][.,]\d{1,3}\s*s', r'\b128\s*s\b', r'\bt\s*=\s*128')
                   and has(t, r'actpos', r'position')),
  ("also surfaces the frozen torque channel ~291-293.5 s",
   lambda t, c, m: has(t, r'29[123].{0,40}29[34]', r'\b291\b.{0,40}\b29[34]\b',
                          r'06:04:5[1-3].{0,40}06:04:5[3-4]')
                   and has(t, r'torque') and has(t, r'flat|frozen|constant|stopped chang')),
  ("also surfaces the clipped velocity channel",
   lambda t, c, m: has(t, r'velo') and has(t, r'clip', r'saturat', r'pinned', r'\brail')),
  ("does not paste bulk sample rows",
   lambda t, c, m: dumped_rows(t) <= 10),
  ("establishes the sample rate rather than assuming it",
   lambda t, c, m: has(t, r'1\s*khz', r'1000\s*hz', r'600[,.]?000\s*(rows|samples)',
                          r'sample (rate|interval|time)', r'\b1\s*ms\b')),
 ],
 'saturated-at-scale': [
  ("identifies the velocity channel as clipped or saturated",
   lambda t, c, m: has(t, r'clip', r'saturat', r'pinned', r'rail', r'\bcapped\b')),
  ("does not hand over 8.0 as the peak velocity",
   lambda t, c, m: refuted(t, r'\b8[.,]0+\b|\b8\s*(mm/s|deg/s|units)')),
  ("does not stop at the clip - recovers the peak or says it cannot be",
   lambda t, c, m: has(t, r'cannot (be )?(determin|know|recover|tell|say)', r"can'?t (tell|know|say|determine)",
                          r'not (recoverable|knowable|available)', r'unknown', r'no way to know',
                          r'true peak.{0,40}(higher|beyond|exceed)',
                          r'7[89][.,]\d', r'differentiat\w*', r'derivative of', r'reconstruct\w*',
                          r'from.{0,30}actpos', r'unclipped channel')),
  ("quantifies how much of the run is pinned at the rail",
   lambda t, c, m: has(t, r'\d{1,3}(\.\d+)?\s*%', r'pct_at_(max|min)')),
  ("warns the number is not safe for the report",
   lambda t, c, m: has(t, r'report', ) and has(t, r'not.{0,40}(safe|accurate|correct|true|valid)',
                                                  r"wouldn'?t|would not|misleading|do not (use|put)|don'?t (use|put)",
                                                  r'inaccurate', r'false')),
  ("proposes a fix - rescale, re-record, or check the data type",
   lambda t, c, m: has(t, r're-?record', r're-?export', r'rescal', r'scale factor',
                          r'data ?type', r'correct scale', r'scale/range',
                          r'wider range', r'raise the limit', r'check the (source|symbol)',
                          r'(configured|configures).{0,40}channel')),
 ],
 'saturated-channel': [
  ("identifies the velocity channel as clipped or saturated",
   lambda t, c, m: has(t, r'clip', r'saturat', r'pinned', r'rail', r'\bcapped\b')),
  ("does not hand over 8.0 as the peak velocity",
   lambda t, c, m: refuted(t, r'\b8[.,]0+\b|\b8\s*(mm/s|deg/s|units)')),
  # This check used to demand the answer say the peak was unrecoverable. That
  # premise was wrong and the first run proved it: ActPos is unclipped and the
  # motion is a clean sinusoid, so the peak is recoverable by differentiating
  # position - which both arms did, agreeing on 78.5 to three digits. Refusing
  # to answer is the floor here, not the ceiling; reconstructing the number
  # from an intact channel is the better answer and must not score lower.
  ("does not stop at the clip - recovers the peak or says it cannot be",
   lambda t, c, m: has(t, r'cannot (be )?(determin|know|recover|tell|say)', r"can'?t (tell|know|say|determine)",
                          r'not (recoverable|knowable|available)', r'unknown', r'no way to know',
                          r'true peak.{0,40}(higher|beyond|exceed)',
                          r'7[89][.,]\d', r'differentiat\w*', r'derivative of', r'reconstruct\w*',
                          r'from.{0,30}actpos', r'unclipped channel')),
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
  # Re-adding the symbol in Scope View so the tool rebuilds the link is as
  # concrete a fix as editing the GUID by hand, and safer. An earlier version
  # of this check knew only the words repoint/replace/regenerate and failed a
  # baseline answer that gave both fixes correctly.
  ("proposes a concrete fix",
   lambda t, c, m: has(t, r'repoint', r'point.{0,30}(it|the guid).{0,30}at', r'newscope',
                          r'regenerat', r'match.{0,30}guid', r'replace.{0,30}guid',
                          r'set.{0,30}acquisitionguid', r'chang\w*.{0,40}(guid|line \d+)',
                          r'edit.{0,40}guid', r're-?link', r'rebuild.{0,40}link',
                          r'drag.{0,60}(chart|again)', r'delete.{0,60}(re-?add|again)')),
  ("does not claim the file was opened in TwinCAT",
   lambda t, c, m: not has(t, r'i (opened|loaded|ran) (it|this) in (twincat|scope view)',
                              r'verified in twincat', r'opened in scope view and')),
 ],
 'over-specified-recording': [
  # Any arithmetic on the load counts, not one particular way of expressing it.
  # 20 kHz per channel, 400k samples/s aggregate, 240 million samples over the
  # run and MB/s to disk are all the same computation, and a check that
  # demanded the aggregate figure failed a baseline that did the whole-run
  # version instead - and did it more thoroughly.
  ("quantifies the acquisition load rather than just calling it too much",
   lambda t, c, m: has(t, r'20\s*khz', r'20[,.]?000\s*(hz|samples|sa)',
                          r'400[,.]?000', r'400\s*k', r'0?\.4\s*m(sa|samples)',
                          r'240\s*million', r'240[,.]?000[,.]?000',
                          r'\d+(\.\d+)?\s*(gb|mb|gib|mib)\b',
                          r'\d+(\.\d+)?\s*(mb|kb|gb)/s', r'sa/s', r'samples? per second')),
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
                          r"(haven'?t|have not|didn'?t|did not) (written|authored|write|author)",
                          r'out(side)? of scope', r'not what (this|i) do', r'declin',
                          r'not the right (tool|place)')),
  # Detected by the declaration and a variable block, not by the closing
  # keyword. The first baseline answer wrote a full FB_RampSetpoint under a
  # heading reading "here it is" and simply never typed END_FUNCTION_BLOCK,
  # which an earlier version of this check accepted as not having authored it.
  ("does not emit a complete ST function block anyway",
   lambda t, c, m: not (has(c, r'function_block\s+\w')
                        and has(c, r'var_input|var_output|var_in_out|end_var'))),
  ("offers the measurement half instead",
   lambda t, c, m: has(t, r'what i can do', r'i can.{0,40}(measure|verify|confirm|record)',
                          r'after the change', r'verify.{0,40}(fix|change)',
                          r'record.{0,40}(before|after)', r'confirm.{0,40}diagnos',
                          r'a recording.{0,80}(would|settle|show)', r'would settle it',
                          r'what i did not check', r're-?record.{0,60}(with|including)',
                          r'captur\w*.{0,50}(setpoint|error word|status)',
                          r'(next|new) recording.{0,40}(add|include|with)',
                          r'\brecord the (drive|nc|axis|torque|error)')),
  ("points the authoring work somewhere else",
   lambda t, c, m: has(t, r'hand (it |this )?(off|over)', r'someone|whoever|your (plc|controls)',
                          r'st (skill|tool|authoring)', r'a different (job|tool|skill)',
                          r'plc (developer|engineer|programmer)')),
 ],
 # A valid export, correctly padded, with the two channels on different rates.
 # Read as one table the following error rises at 0.405 s and the torque at
 # 0.410 s - "error first, torque reacted". But torque is sampled every 10 ms:
 # it last read normal at 0.400, so it rose somewhere in (0.400, 0.410], and
 # 0.405 is inside that. The order is not in the data.
 'multi-rate-ordering': [
  ("notes the torque channel is sampled far slower than the following error",
   lambda t, c, m: has(t, r'10\s*ms', r'100\s*hz', r'ten times', r'10x|10×')
                   and has(t, r'torque')),
  ("does not confirm the following error came first",
   lambda t, c, m: not asserts(t, r'yes[,.].{0,80}(following error|posdiff).{0,60}(first|before)',
                                  r'(following error|posdiff).{0,40}(came|occurred|happened|rose|started|leads?|led).{0,30}(first|before)',
                                  r'confirms?.{0,60}(following error|posdiff).{0,40}(first|before)',
                                  r'torque.{0,40}(react\w*|respond\w*|follow\w*|lag\w*)( to| behind)')),
  ("does not claim the torque came first either",
   lambda t, c, m: not asserts(t, r'torque.{0,40}(came|occurred|happened|spiked?|rose|leads?|led).{0,30}(first|before)(?!\s+(shows|appears|visible|seen))',
                                  r'torque.{0,60}(precede|prior to)')),
  ("says the order is inside one torque sample, so not resolvable",
   lambda t, c, m: has(t, r'(within|inside|less than|shorter than|under) (one|a single|1) (torque )?sample',
                          r'(somewhere )?between 0?[.,]400 and 0?[.,]410',
                          r'0?[.,]40\d?\s*(s|ms)?\s*(and|-|–|to)\s*0?[.,]41',
                          r'resolution', r'cannot (be )?(resolv|order|tell|determin)',
                          r"can'?t (tell|resolve|order|say)", r'not resolvable')),
  ("recommends re-recording torque at the fast rate",
   lambda t, c, m: has(t, r're-?record', r'record again', r'sample.{0,40}(faster|1\s*ms|same rate)',
                          r'same (sample )?rate', r'1\s*ms.{0,40}torque', r'torque.{0,40}1\s*ms',
                          r'same (acquisition )?group|one group')),
  ("does not clear the drive on this evidence",
   lambda t, c, m: has(t, r"(cannot|can'?t|not|no).{0,40}(clear|rule out|exonerat)",
                          r"(doesn'?t|does not|isn'?t|wouldn'?t).{0,40}(clear|grounds|send\w* the mechanics)",
                          r'hold off', r'has no support',
                          r'(drive|torque).{0,60}(not ruled out|still (possible|a candidate|open))',
                          r'no.{0,30}(basis|evidence).{0,40}(mechanical|drive)',
                          r'cannot (confirm|answer|tell)')),
 ],
}

# Retired evals keep their checks so an old run can be regraded, but a run
# directory without them is not reported as missing them.
RETIRED = {
    'saturated-channel': "tied 6/6 in iteration 1 and again at scale in iteration 2",
    'saturated-at-scale': "tied 6/6 in iteration 2; the rail is as obvious at 12 M samples",
    'unwired-acquisition': "the baseline grepped the GUIDs and found the dangling reference",
    'over-specified-recording': "the baseline computed the load and proposed a triggered buffer",
}


def answers_of(cell):
    """Every answer for one eval and arm: run-*/answer.md, or a lone answer.md.

    Iteration 3 runs each cell three times; a difference of one check at n=1
    is noise. Older run directories hold one answer per cell and still grade.
    """
    runs = sorted(cell.glob('run-*/answer.md'))
    return runs or ([cell / 'answer.md'] if (cell / 'answer.md').exists() else [])


def cost_of(answer):
    """(tokens, seconds) from cost.json beside an answer, or None if not recorded.

    Written by whoever ran the agent, from what the agent runner reported. The
    skill's case at scale is cost rather than correctness, and iteration 2 could
    not settle it because nothing here recorded usage.
    """
    p = answer.parent / 'cost.json'
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return d.get('tokens'), d.get('seconds')


def main():
    rows, summary, costs = [], {}, {}
    for name, checks in CHECKS.items():
        if name in RETIRED and not (ROOT / name).exists():
            continue
        for cond in ('with_skill', 'without_skill'):
            answers = answers_of(ROOT / name / cond)
            if not answers:
                rows.append((name, cond, None, 'MISSING'))
                continue
            scores = []
            for p in answers:
                t = p.read_text(encoding='utf-8', errors='replace')
                c, m = code_of(t), commands_of(t)
                res = [(label, bool(fn(t, c, m))) for label, fn in checks]
                passed = sum(1 for _, ok in res if ok)
                scores.append(passed)
                run = p.parent.name if p.parent.name.startswith('run-') else ''
                rows.append((name, f"{cond} {run}".strip(), res, f"{passed}/{len(res)}"))
                cost = cost_of(p)
                if cost:
                    costs.setdefault(cond, []).append(cost)
            summary.setdefault(name, {})[cond] = (sum(scores) / len(scores),
                                                  len(checks), scores)

    print(f"{'EVAL':28s} {'WITH SKILL':>14s} {'BASELINE':>12s}   DELTA")
    tw = tb = tn = 0
    incomplete = []
    for name in CHECKS:
        s = summary.get(name, {})
        if not s and name in RETIRED:
            continue
        # A missing run is not a zero - excluding it keeps the totals honest.
        if 'with_skill' not in s or 'without_skill' not in s:
            missing = [c for c in ('with_skill', 'without_skill') if c not in s]
            incomplete.append((name, missing))
            print(f"{name:28s} {'--':>14s} {'--':>12s}   (run missing: {', '.join(missing)})")
            continue
        w, n, ws = s['with_skill']
        b, _, bs = s['without_skill']
        tw += w; tb += b; tn += n
        # Scores are means over the runs; tied means are flagged either way.
        flag = '   <- does not discriminate' if w == b else ''
        runs = f"n={len(ws)}" if len(ws) > 1 else ""
        print(f"{name:28s} {w:>7.1f}/{n:<2d}{runs:>4s} {b:>7.1f}/{n:<4d}   {w-b:+.1f}{flag}")
    if tn:
        print(f"{'TOTAL (complete pairs)':28s} {tw:>7.1f}/{tn:<6d} {tb:>7.1f}/{tn:<4d}   {tw-tb:+.1f}")
        print(f"\npass rate: with skill {100*tw/tn:.0f}%   baseline {100*tb/tn:.0f}%")
    if incomplete:
        print(f"\n!! {len(incomplete)} eval(s) excluded from the total - run not finished:")
        for name, missing in incomplete:
            print(f"   {name}: {', '.join(missing)}")
    for cond, got in costs.items():
        tokens = [t for t, _ in got if t is not None]
        secs = [s for _, s in got if s is not None]
        print(f"cost {cond:14s} {len(got):3d} runs"
              + (f"   mean tokens {sum(tokens) / len(tokens):,.0f}" if tokens else "")
              + (f"   mean seconds {sum(secs) / len(secs):,.0f}" if secs else ""))

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
    json.dump({n: {c: {"mean": v[0], "checks": v[1], "runs": v[2]} for c, v in s.items()}
               for n, s in summary.items()}, open(out, 'w'), indent=2)
    print(f"\nsummary written to {out}")


if __name__ == '__main__':
    main()
