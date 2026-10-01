#!/usr/bin/env python3
"""Stage a round of eval runs, file the answers back, and run the judge read blind.

Iteration 4 staged and filed by hand and learned two things the hard way: every
run needs a stage of its own (a shared data/ let baselines read another eval's
file), and the arm must not show in anything the orchestrator reads before
grading. Iteration 6 added three more: an agent told to read prompts/<id>.txt
can list the other prompts, a run can report "written" without its answer on
disk, and the judge packets were built by a script that lived nowhere. So:

  stage          One directory per (eval, arm, run) under --root, named by a
                 shuffled neutral id (s01, s02...). Each holds a copy of
                 fixtures/stages/<eval>/data/ and, for the skill arm only,
                 skill/ (from `git archive HEAD`). Each run's prompt goes alone
                 into prompts/<id>-<random>/task.txt, and prompts/ is made
                 unlistable, so an agent given its own path cannot find
                 another. launch.tsv lists, per id, the one line to give a
                 fresh agent. The id-to-arm map is written to --keys, a
                 directory outside --root: nothing an agent or the
                 orchestrator reads before grading says which arm a run is.

  collect        Files <root>/answers/<id>.md as runs/<name>/<eval>/<arm>/
                 run-<n>/answer.md, with cost.json from <root>/cost.tsv (id,
                 tokens, seconds, tool uses; tab-separated) where given. Names
                 every run with no answer on disk and exits 1: recover or
                 re-run those before grading.

  judge-stage    One packet per eval under <root>/judge/<eval>/packet.md: the
                 prompt, expected_output, ground truth and that eval's answers
                 shuffled as A, B, C..., with `## Commands` stripped and the
                 tool's name, the skill's paths and the word "skill" replaced.
                 The letter key goes to --keys. A fresh agent per packet writes
                 <root>/judge/<eval>/scores.json:
                 {"A": {"score": 0|1|2, "why": "..."}, ...}

  judge-collect  Files each score as judge.json beside the answer it scored,
                 where grade.py reads it.

Stdlib only. Run from the repository root, and **not from a session isolated in
a git worktree**: in iteration 6 such a session's guard refused 32 of the
agents' shell commands and four answer files were never written.

Usage:
    python3 evals/make_eval_fixture.py
    python3 evals/stage_runs.py stage --root /tmp/evalround --keys /tmp/evalround-keys --runs 3 --seed 1
    ... give each line of launch.tsv to a fresh agent, logging cost.tsv ...
    python3 evals/stage_runs.py collect --root /tmp/evalround --keys /tmp/evalround-keys --name iteration-7
    python3 evals/stage_runs.py judge-stage --root /tmp/evalround --keys /tmp/evalround-keys --name iteration-7
    ... give each packet to a fresh agent ...
    python3 evals/stage_runs.py judge-collect --root /tmp/evalround --keys /tmp/evalround-keys
    python3 evals/grade.py evals/runs/iteration-7
"""
import argparse
import io
import json
import os
import random
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ARMS = ("with_skill", "without_skill")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

LAUNCH = ("Your whole task is written in one file: {task}\n\n"
          "Read that file and do exactly what it says, as if its text had been given to you "
          "directly as the request. Do not look at any other directory under {root} except the "
          "ones that task text names.")

JUDGE = ("You are judging the answers in one file: {packet} - it holds the request, the expected "
         "output, the ground truth and the answers, lettered. Read no other file and run nothing.\n\n"
         "Score each answer on its own, against the expected output and ground truth only:\n"
         "- 0 - falls into the trap the expected output describes, or states something the "
         "ground truth contradicts.\n"
         "- 1 - avoids the trap but misses part of the expected output, or hedges where the data "
         "is clear.\n"
         "- 2 - reaches the expected output and states nothing the ground truth contradicts.\n\n"
         "The answers come from conditions you are not told; some words were replaced by [tool], "
         "[doc] or <stage>. Do not guess the condition, and do not reward or penalise style, "
         "length or method - only whether the answer is right.\n\n"
         "Write the scores as JSON to {scores}, one entry per letter, `why` one sentence: "
         '{{"A": {{"score": 2, "why": "..."}}, ...}}. Check the file exists, then reply with only '
         "the word: judged")


def stage(root, keys, runs, seed):
    stages = EVALS / "fixtures" / "stages"
    if not stages.is_dir():
        raise SystemExit("no fixtures/stages - run evals/make_eval_fixture.py first")
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"{root} is not empty - stage each round into a fresh directory")
    if root.resolve() in keys.resolve().parents or keys.resolve() == root.resolve():
        raise SystemExit("--keys must be outside --root, or the agents can read the arms")
    skill = subprocess.run(["git", "archive", "HEAD", "SKILL.md", "references", "scripts",
                            "templates"], check=True, capture_output=True).stdout
    evals = json.loads((EVALS / "evals.json").read_text())["evals"]
    cells = [(e, arm, run) for e in evals for arm in ARMS for run in range(1, runs + 1)]
    random.Random(seed).shuffle(cells)

    prompts = root / "prompts"
    prompts.mkdir(parents=True)
    (root / "answers").mkdir()
    keys.mkdir(parents=True, exist_ok=True)
    mapping, launch = {}, []
    for i, (e, arm, run) in enumerate(cells, 1):
        sid = f"s{i:02d}"
        here = root / "stage" / sid
        shutil.copytree(stages / e["name"] / "data", here / "data")
        lead = ""
        if arm == "with_skill":
            with tarfile.open(fileobj=io.BytesIO(skill)) as tar:
                tar.extractall(here / "skill", filter="data")
            lead = (f"A skill for this work is in {here}/skill. Read {here}/skill/SKILL.md "
                    f"first and follow it; its tool runs as `uv run "
                    f"{here}/skill/scripts/tcscope.py`.\n\n")
        body = e["prompt"].replace("{FIXTURES}", str(here / "data"))
        tail = (f"\n\nWork from {here} (cd there before any command). Do not read anything "
                "under the repository checkout or under ~/.claude. Do not send any "
                "notifications. End your answer with a `## Commands` section listing verbatim "
                "every shell command you ran, in order.\n\n"
                f"When you are done, write your complete final answer, exactly as you would "
                f"give it, to {root}/answers/{sid}.md with your file-writing tool rather than "
                "a shell redirect, check that the file exists, and reply with only the word: "
                "written")
        task = prompts / f"{sid}-{secrets.token_hex(6)}" / "task.txt"
        task.parent.mkdir()
        task.write_text(lead + body + tail)
        launch.append(f"{sid}\t" + LAUNCH.format(task=task, root=root).replace("\n", "\\n"))
        mapping[sid] = {"eval": e["name"], "arm": arm, "run": run}
    # Enter by exact name, no listing: an agent holding its own path cannot
    # enumerate the rest.
    os.chmod(prompts, 0o311)
    (root / "launch.tsv").write_text("\n".join(launch) + "\n")
    (keys / "map.json").write_text(json.dumps(mapping, indent=2))
    print(json.dumps({"ok": True, "root": str(root), "runs": len(mapping),
                      "launch": str(root / "launch.tsv"), "keys": str(keys)}, indent=2))


def collect(root, keys, name):
    mapping = json.loads((keys / "map.json").read_text())
    costs = {}
    tsv = root / "cost.tsv"
    if tsv.exists():
        for line in tsv.read_text().splitlines():
            sid, tokens, seconds, tools = line.split("\t")
            costs[sid] = {"tokens": int(tokens), "seconds": float(seconds),
                          "tool_uses": int(tools)}
    out, missing = EVALS / "runs" / name, []
    for sid, m in sorted(mapping.items()):
        answer = root / "answers" / f"{sid}.md"
        if not answer.exists() or not answer.read_text().strip():
            missing.append(sid)
            continue
        cell = out / m["eval"] / m["arm"] / f"run-{m['run']}"
        cell.mkdir(parents=True, exist_ok=True)
        shutil.copy2(answer, cell / "answer.md")
        (cell / "stage_id").write_text(sid)
        if sid in costs:
            (cell / "cost.json").write_text(json.dumps(costs[sid]))
    print(json.dumps({"ok": not missing, "filed": len(mapping) - len(missing),
                      "missing": missing, "costs": len(costs), "out": str(out)}, indent=2))
    return 1 if missing else 0


def blind(text, root):
    """An answer with what gives its arm away taken out, as far as text allows.

    The `## Commands` section goes whole: it names the tool on every line. What
    stays is the prose, where the verbs an answer ran and the method it used
    still show. That limit is real and is stated in every results file.
    """
    stage_dir = re.escape(str(root)) + r"/stage/\w+"
    text = re.split(r"\n##+\s*Commands\b", text)[0]
    text = re.sub(stage_dir + r"/skill/scripts/tcscope\.py", "[tool]", text)
    text = re.sub(stage_dir + r"/skill\S*", "[doc]", text)
    text = re.sub(stage_dir, "<stage>", text)
    # \b on both sides: Commissioning_Axis1.tcscopex is a file name, not the tool.
    text = re.sub(r"(uv run\s+)?(\S*/)?\btcscope(\.py)?\b", "[tool]", text)
    text = re.sub(r"SKILL\.md", "[doc]", text)
    text = re.sub(r"\b[Ss]kill\b", "[tool]", text)
    return text.rstrip() + "\n"


def judge_stage(root, keys, name, seed):
    runs = EVALS / "runs" / name
    spec = json.loads((EVALS / "evals.json").read_text())["evals"]
    truth_file = EVALS / "ground_truth.json"
    truth = json.loads(truth_file.read_text()) if truth_file.exists() else {}
    rng, staged, launch = random.Random(seed), [], []
    for e in spec:
        cells = sorted(p.parent for arm in ARMS
                       for p in (runs / e["name"] / arm).glob("run-*/answer.md"))
        if not cells:
            continue
        rng.shuffle(cells)
        files = {f: truth[Path(f).name] for f in e.get("files", []) if Path(f).name in truth}
        parts = [f"# Judge packet: {e['name']}\n",
                 "## The request the answers were given\n",
                 e["prompt"].replace("{FIXTURES}", "<stage>/data"), "",
                 "## Expected output\n", e["expected_output"], "",
                 "## Ground truth (the eval's own)\n",
                 json.dumps(e.get("ground_truth"), indent=2, ensure_ascii=False), "",
                 "## Ground truth (how the fixture was built)\n",
                 json.dumps(files, indent=2, ensure_ascii=False), ""]
        key = {}
        for letter, cell in zip(LETTERS, cells):
            key[letter] = str(cell)
            parts += [f"\n---\n\n## Answer {letter}\n",
                      blind((cell / "answer.md").read_text(encoding="utf-8"), root)]
        d = root / "judge" / e["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "packet.md").write_text("\n".join(parts), encoding="utf-8")
        (keys / f"judge-{e['name']}.json").write_text(json.dumps(key, indent=2))
        launch.append(f"{e['name']}\t" + JUDGE.format(packet=d / "packet.md",
                                                       scores=d / "scores.json").replace("\n", "\\n"))
        staged.append(e["name"])
    (root / "judge" / "launch.tsv").write_text("\n".join(launch) + "\n")
    print(json.dumps({"ok": bool(staged), "packets": staged,
                      "launch": str(root / "judge" / "launch.tsv")}, indent=2))
    return 0 if staged else 1


def judge_collect(root, keys):
    filed, problems = 0, []
    for k in sorted(keys.glob("judge-*.json")):
        name = k.stem[len("judge-"):]
        scores_file = root / "judge" / name / "scores.json"
        if not scores_file.exists():
            problems.append(f"{name}: no scores.json")
            continue
        scores, key = json.loads(scores_file.read_text()), json.loads(k.read_text())
        if set(scores) != set(key):
            problems.append(f"{name}: scored {sorted(scores)}, packet had {sorted(key)}")
            continue
        for letter, cell in key.items():
            s = scores[letter]
            if s.get("score") not in (0, 1, 2):
                problems.append(f"{name} {letter}: score {s.get('score')!r} is not 0, 1 or 2")
                continue
            (Path(cell) / "judge.json").write_text(
                json.dumps({"score": s["score"], "why": s.get("why", "")}))
            filed += 1
    print(json.dumps({"ok": not problems, "filed": filed, "problems": problems}, indent=2))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("stage", "collect", "judge-stage", "judge-collect"):
        p = sub.add_parser(cmd)
        p.add_argument("--root", type=Path, required=True)
        p.add_argument("--keys", type=Path, required=True,
                       help="where the id-to-arm map and the judge's letter keys are kept; "
                            "outside --root")
        if cmd == "stage":
            p.add_argument("--runs", type=int, default=3)
        if cmd in ("stage", "judge-stage"):
            p.add_argument("--seed", type=int, default=1)
        if cmd in ("collect", "judge-stage"):
            p.add_argument("--name", required=True)
    args = ap.parse_args()
    if args.cmd == "stage":
        return stage(args.root, args.keys, args.runs, args.seed)
    if args.cmd == "collect":
        return collect(args.root, args.keys, args.name)
    if args.cmd == "judge-stage":
        return judge_stage(args.root, args.keys, args.name, args.seed)
    return judge_collect(args.root, args.keys)


if __name__ == "__main__":
    sys.exit(main())
