#!/usr/bin/env python3
"""Drive stage_runs.py through a whole round with fake answers.

Every step of this harness has failed once in a real round: prompts an agent
could list, an answer reported and never written, a redaction that turned
`Commissioning_Axis1.tcscopex` into `[tool]x`. A round is 40-odd agent runs, so
those are found here, not there.

Run from the repository root:  python3 evals/test_stage_runs.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
NAME = f"selftest-{os.getpid()}"
failures = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def run(*args):
    p = subprocess.run([sys.executable, str(EVALS / "stage_runs.py"), *map(str, args)],
                       capture_output=True, text=True, cwd=EVALS.parent)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, {"raw": p.stdout + p.stderr}


def main():
    if not (EVALS / "fixtures" / "stages").is_dir():
        subprocess.run([sys.executable, str(EVALS / "make_eval_fixture.py")], check=True,
                       capture_output=True, cwd=EVALS.parent)
    evals = json.loads((EVALS / "evals.json").read_text())["evals"]
    tmp = Path(tempfile.mkdtemp(prefix="stage-selftest-"))
    root, keys = tmp / "round", tmp / "keys"
    try:
        code, out = run("stage", "--root", root, "--keys", root / "keys", "--runs", 1)
        check("stage refuses a --keys inside --root", code != 0, str(out)[:120])

        code, out = run("stage", "--root", root, "--keys", keys, "--runs", 1, "--seed", 3)
        check("stage writes one run per eval and arm",
              code == 0 and out.get("runs") == 2 * len(evals), str(out)[:200])
        launch = [l.split("\t") for l in (root / "launch.tsv").read_text().splitlines()]
        check("launch.tsv has one line per run, each naming a task file that exists",
              len(launch) == 2 * len(evals)
              and all(Path(l[1].split("one file: ")[1].split("\\n")[0]).is_file() for l in launch))
        # root is not stopped by permission bits, so there this proves nothing.
        try:
            listed = bool(os.listdir(root / "prompts"))
        except PermissionError:
            listed = False
        check("the prompts directory cannot be listed", not listed or os.geteuid() == 0)
        check("the arm map is not under the root agents work in",
              (keys / "map.json").is_file() and not list(root.rglob("map.json")))
        task = Path(launch[0][1].split("one file: ")[1].split("\\n")[0]).read_text()
        check("a prompt asks for a file-writing tool and a check that the answer exists",
              "file-writing tool" in task and "check that the file exists" in task)

        mapping = json.loads((keys / "map.json").read_text())
        sids = sorted(mapping)
        for sid in sids[1:]:
            m = mapping[sid]
            (root / "answers" / f"{sid}.md").write_text(
                f"The file Commissioning_Axis1.tcscopex is wrong. I ran the skill's checker at "
                f"{root}/stage/{sid}/skill/scripts/tcscope.py and read SKILL.md.\n\n"
                f"## Commands\nuv run tcscope.py manifest x  # {m['arm']}\n")
        (root / "cost.tsv").write_text("".join(f"{s}\t1000\t10.5\t3\n" for s in sids))
        code, out = run("collect", "--root", root, "--keys", keys, "--name", NAME)
        check("collect names a run with no answer on disk and fails",
              code == 1 and out.get("missing") == [sids[0]], str(out)[:200])
        (root / "answers" / f"{sids[0]}.md").write_text("Nothing wrong.\n\n## Commands\nls\n")
        code, out = run("collect", "--root", root, "--keys", keys, "--name", NAME)
        check("collect files every answer with its cost",
              code == 0 and out.get("filed") == len(sids) and out.get("costs") == len(sids),
              str(out)[:200])

        code, out = run("judge-stage", "--root", root, "--keys", keys, "--name", NAME, "--seed", 5)
        check("judge-stage writes one packet per eval",
              code == 0 and len(out.get("packets", [])) == len(evals), str(out)[:200])
        packets = [(root / "judge" / e["name"] / "packet.md").read_text() for e in evals]
        answers = "\n".join(p.split("## Answer A", 1)[1] for p in packets)
        check("a packet's answers carry no Commands section, tool name, skill path or arm",
              "## Commands" not in answers and "tcscope.py" not in answers
              and "/skill" not in answers and "with_skill" not in answers
              and "without_skill" not in answers and "SKILL.md" not in answers,
              answers[:200])
        check("a .tcscopex file name survives the redaction",
              "Commissioning_Axis1.tcscopex" in answers and "[tool]x" not in answers)

        for e in evals:
            key = json.loads((keys / f"judge-{e['name']}.json").read_text())
            (root / "judge" / e["name"] / "scores.json").write_text(
                json.dumps({letter: {"score": 2, "why": "test"} for letter in key}))
        first = root / "judge" / evals[0]["name"] / "scores.json"
        good = first.read_text()
        first.write_text(json.dumps({"A": {"score": 5, "why": "out of range"}}))
        code, out = run("judge-collect", "--root", root, "--keys", keys)
        check("judge-collect refuses scores that do not match the packet",
              code == 1 and out.get("problems"), str(out)[:200])
        first.write_text(good)
        code, out = run("judge-collect", "--root", root, "--keys", keys)
        judged = list((EVALS / "runs" / NAME).rglob("judge.json"))
        check("judge-collect files a judge.json beside every answer",
              code == 0 and len(judged) == len(sids), f"{len(judged)} of {len(sids)}")
    finally:
        os.chmod(root / "prompts", 0o755) if (root / "prompts").exists() else None
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(EVALS / "runs" / NAME, ignore_errors=True)

    if failures:
        print(f"\n!! {len(failures)} failed")
        return 1
    print("\nstage_runs.py carries a round from staging to judged answers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
