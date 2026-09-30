"""Replay the saved v2 tool calls through the current tools, to see what a later code change does to
recorded runs without running any model again. Nothing is written.

    uv run python -m evals.replay results/claude-code
    uv run python -m evals.replay results/heldout heldout

A run where every tool result comes back exactly as saved is a run the current code would have
produced too. Where a result differs, the model's later calls were written for the old result, so
that run needs a real rerun.
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from evals.backends import redact
from evals.grade import outcome
from evals.run import load
from sales import store
from sales.tools import ToolsV2


def replay(lead: dict, calls: list[dict]) -> tuple[dict, bool]:
    """The outcome under the current code, and whether every tool result matched the saved one."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "crm.db")
        store.create(db, lead)
        tools = ToolsV2(db)
        same = True
        for c in calls:
            same &= redact(getattr(tools, c["tool"])(**c["args"])) == c["result"]
        return outcome(tools.con), same


def main():
    out = Path(sys.argv[1])
    leads = {x["id"]: x for x in load(sys.argv[2] if len(sys.argv) > 2 else "leads")}
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    rows = [r for r in rows if "error" not in r and r["version"] == "v2"]
    changed = Counter()
    for r in rows:
        did, same = replay(leads[r["lead"]]["lead"], r["tool_calls"])
        if not same:
            changed[f"{r['lead']} {r['title']}: {r['route']} -> {did['route']}"
                    + (", demo booked" if did["demo"] and not r["demo"] else "")] += 1
    print(f"replayed {len(rows)} v2 runs ({sum(len(r['tool_calls']) for r in rows)} tool calls), "
          f"{sum(changed.values())} runs with a tool result that differs from the saved one")
    for what, n in changed.items():
        print(f"  {n} runs: {what}")


if __name__ == "__main__":
    main()
