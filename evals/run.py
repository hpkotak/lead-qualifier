"""Run the lead suite: every lead x version x model, repeated --trials times.

    uv run python -m evals.run                                   # offline mock agent, a few seconds
    uv run python -m evals.run --backend claude-code --models haiku,opus --trials 5
    uv run python -m evals.run --backend claude-code --models haiku,opus --leads heldout --out results/heldout
    uv run python -m evals.run --backend claude-code --models haiku --versions v1b --out results/ablation

Results are appended to <out>/results.jsonl as each run finishes, so an interrupted run continues
where it stopped when started again with the same --out.
"""
import argparse
import json
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from evals import report
from evals.backends import BACKENDS, ROOT, RunError, UsageLimit, redact
from evals.grade import grade, outcome
from sales import store


def load(name: str = "leads") -> list[dict]:
    return yaml.safe_load((ROOT / "evals" / f"{name}.yaml").read_text())


LEADS = load()


def run_one(backend: str, model: str, version: str, lead: dict, trial: int, attempts: int = 3) -> dict:
    for attempt in range(1, attempts + 1):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "crm.db")
            store.create(db, lead["lead"])
            try:
                out = BACKENDS[backend](store.form_message(lead["lead"]), version, model, db, tmp)
            except (RunError, subprocess.TimeoutExpired, OSError) as e:
                if attempt == attempts:
                    return {"error": redact(str(e))}
                print(f"retrying {model} {version} {lead['id']} #{trial} after: {redact(str(e))[:200]}", flush=True)
                time.sleep(30 * attempt)  # usually a rate limit; start again on a fresh database
                continue
            con = store.connect(db)
            crash = con.execute("SELECT error FROM harness_errors").fetchone()
            if crash:
                con.close()
                return {"error": "tool crashed: " + redact(crash[0][-500:])}
            did = outcome(con)
            did["replies"] = [redact(t) for t in did["replies"]]
            result = grade(lead, did)
            calls = [{"tool": r["tool"], "args": json.loads(r["args"]), "result": redact(r["result"])}
                     for r in con.execute("SELECT * FROM tool_calls ORDER BY id")]
            con.close()
            return {**result, "replies": did["replies"], "tool_calls": calls, "final_text": redact(out["final_text"]),
                    "stop": out["stop"], "cost_usd": out["cost_usd"], "duration_ms": out["duration_ms"], "model_ids": out["model_ids"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="mock", choices=BACKENDS)
    ap.add_argument("--models", default="haiku", help="comma-separated Claude model aliases (ignored by mock)")
    ap.add_argument("--versions", default="v1,v2")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--leads", default="leads", help="which lead file in evals/ (leads or heldout)")
    ap.add_argument("--only", default="", help="comma-separated lead ids")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    models = ["mock"] if a.backend == "mock" else a.models.split(",")
    leads = [x for x in load(a.leads) if not a.only or x["id"] in a.only.split(",")]
    out = Path(a.out or ROOT / "results" / a.backend)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "results.jsonl"
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line)
            if "error" not in r:
                done.add((r["model"], r["version"], r["lead"], r["trial"]))

    jobs = [(m, v, x, t) for m in models for v in a.versions.split(",") for x in leads
            for t in range(1, a.trials + 1) if (m, v, x["id"], t) not in done]
    print(f"{len(jobs)} runs to do ({len(done)} already done) -> {path}")
    lock = threading.Lock()
    with ThreadPoolExecutor(a.workers) as pool, path.open("a") as f:
        futures = {pool.submit(run_one, a.backend, m, v, x, t): (m, v, x, t) for m, v, x, t in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            m, v, x, t = futures[fut]
            try:
                result = fut.result()
            except UsageLimit as e:
                print(f"Stopping: {e}. Run the same command again after it resets to continue.", flush=True)
                for other in futures:
                    other.cancel()
                break
            row = {"model": m, "version": v, "lead": x["id"], "category": x["category"], "title": x["title"],
                   "trial": t, "expect": x["expect"], **result}
            with lock:
                f.write(json.dumps(row) + "\n")
                f.flush()
            status = "ERROR" if "error" in row else ("pass" if row["passed"] else "FAIL " + "; ".join(row["failures"]))
            print(f"[{n}/{len(jobs)}] {m} {v} {x['id']} #{t}: {status}", flush=True)

    report.write(out, load(a.leads), a.leads)


if __name__ == "__main__":
    main()
