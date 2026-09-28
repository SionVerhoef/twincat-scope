#!/usr/bin/env python3
"""Stage a round of eval runs, and file the answers back where grade.py reads them.

Iteration 4 did both by hand and learned two things the hard way: every run
needs a stage of its own (a shared data/ let baselines read another eval's
file), and the arm must not show in anything the orchestrator reads before
grading. So:

  stage    One directory per (eval, arm, run) under --root, named by a shuffled
           neutral id (s01, s02...). Each holds a copy of
           fixtures/stages/<eval>/data/ and, for the skill arm only, skill/ (from
           `git archive HEAD`). Writes prompts/<id>.txt - the eval's prompt with
           the iteration-4 additions for both arms - and map.json, the only place
           that ties an id to its eval and arm. Keep map.json out of the agents'
           reach: --root is outside the repository.

  collect  Files <root>/answers/<id>.md as runs/<name>/<eval>/<arm>/run-<n>/
           answer.md, with cost.json from <root>/cost.tsv (id, tokens, seconds,
           tool uses; tab-separated) where given.

Stdlib only. Run from the repository root.

Usage:
    python3 evals/make_eval_fixture.py
    python3 evals/stage_runs.py stage --root /tmp/evalround --runs 3 --seed 1
    ... run each prompts/<id>.txt in a fresh agent, logging cost.tsv ...
    python3 evals/stage_runs.py collect --root /tmp/evalround --name iteration-5
    python3 evals/grade.py evals/runs/iteration-5
"""
import argparse
import io
import json
import random
import shutil
import subprocess
import tarfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ARMS = ("with_skill", "without_skill")


def stage(root, runs, seed):
    stages = EVALS / "fixtures" / "stages"
    if not stages.is_dir():
        raise SystemExit("no fixtures/stages - run evals/make_eval_fixture.py first")
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"{root} is not empty - stage each round into a fresh directory")
    skill = subprocess.run(["git", "archive", "HEAD", "SKILL.md", "references", "scripts",
                            "templates"], check=True, capture_output=True).stdout
    evals = json.loads((EVALS / "evals.json").read_text())["evals"]
    cells = [(e, arm, run) for e in evals for arm in ARMS for run in range(1, runs + 1)]
    random.Random(seed).shuffle(cells)

    (root / "prompts").mkdir(parents=True)
    (root / "answers").mkdir()
    mapping = {}
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
                f"give it, to {root}/answers/{sid}.md, and reply with only the word: written")
        (root / "prompts" / f"{sid}.txt").write_text(lead + body + tail)
        mapping[sid] = {"eval": e["name"], "arm": arm, "run": run}
    (root / "map.json").write_text(json.dumps(mapping, indent=2))
    print(json.dumps({"ok": True, "root": str(root), "runs": len(mapping),
                      "prompts": str(root / "prompts")}, indent=2))


def collect(root, name):
    mapping = json.loads((root / "map.json").read_text())
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
        if not answer.exists():
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


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--runs", type=int, default=3)
    s.add_argument("--seed", type=int, default=1)
    c = sub.add_parser("collect")
    c.add_argument("--root", type=Path, required=True)
    c.add_argument("--name", required=True)
    args = ap.parse_args()
    if args.cmd == "stage":
        stage(args.root, args.runs, args.seed)
    else:
        collect(args.root, args.name)


if __name__ == "__main__":
    main()
