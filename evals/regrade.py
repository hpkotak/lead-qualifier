"""Regrade saved results with the current grader and lead file, without running any model again.

    uv run python -m evals.regrade results/claude-code
    uv run python -m evals.regrade results/heldout heldout
"""
import json
import sys
from pathlib import Path

from evals import report
from evals.grade import grade
from evals.run import load


def main():
    out = Path(sys.argv[1])
    name = sys.argv[2] if len(sys.argv) > 2 else "leads"
    leads = {x["id"]: x for x in load(name)}
    path = out / "results.jsonl"
    rows, changed = [], 0
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if "error" not in r:
            lead = leads[r["lead"]]
            new = grade(lead, {"route": r["route"], "demo": r["demo"], "replies": r["replies"]})
            changed += new["passed"] != r["passed"]
            r.update(new, expect=lead["expect"], category=lead["category"], title=lead["title"])
        rows.append(r)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    report.write(out, list(leads.values()), name)
    print(f"regraded {len(rows)} runs, {changed} changed pass/fail")


if __name__ == "__main__":
    main()
