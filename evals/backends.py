"""Ways to run the agent on one lead.

Each backend gets the form submission as its only message and returns the agent's final text plus
metadata. Everything the agent does goes through the tools, which write to the run's own database.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from sales import web
from sales.tools import TOOL_NAMES, VERSIONS

ROOT = Path(__file__).resolve().parent.parent
# All real-model sessions run from one empty folder, so no project files or settings leak in.
SANDBOX = Path(tempfile.gettempdir()) / "lead-qualifier-sandbox"


def system_prompt(version: str) -> str:
    return (ROOT / "prompts" / f"{version}.md").read_text()


class RunError(RuntimeError):
    pass


class UsageLimit(RuntimeError):
    """The Claude subscription's usage limit was hit. Retrying won't help until it resets."""


def run_claude_code(message: str, version: str, model: str, db_path: str, workdir: str) -> dict:
    """The agent is `claude -p` with our system prompt, no built-in tools, and only the sales tools (MCP)."""
    SANDBOX.mkdir(exist_ok=True)
    mcp_path = Path(workdir) / "mcp.json"
    mcp_path.write_text(json.dumps({"mcpServers": {"sales": {
        "command": sys.executable, "args": ["-m", "sales.server"],
        "env": {"PYTHONPATH": str(ROOT), "LEAD_DB": db_path, "LEAD_VERSION": version}}}}))
    cmd = ["claude", "-p", message, "--model", model, "--system-prompt", system_prompt(version),
           "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--mcp-config", str(mcp_path),
           "--allowedTools", ",".join(f"mcp__sales__{t}" for t in TOOL_NAMES[version]),
           "--max-turns", "15", "--output-format", "json"]
    proc = subprocess.run(cmd, cwd=SANDBOX, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL,
                          env={**os.environ, "ENABLE_TOOL_SEARCH": "false"})
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RunError(f"{proc.stdout[-300:]} {proc.stderr[-300:]}")
    result = str(data.get("result"))
    if "hit your session limit" in result or "usage limit" in result.lower():
        raise UsageLimit(result)
    # Running out of turns is the agent's failure, not the harness's: grade whatever it did.
    if proc.returncode and data.get("subtype") != "error_max_turns":
        raise RunError(result[:300])
    return {"final_text": data.get("result") or "", "cost_usd": float(data.get("total_cost_usd") or 0),
            "duration_ms": int(data.get("duration_ms") or 0), "model_ids": sorted(data.get("modelUsage") or {}),
            "stop": data.get("subtype", "")}


_SIZE = re.compile(r"(\d[\d,]*)\+?\s+(?:staff|employees|team members|associates|caregivers|people|[a-z]+ers\b)", re.I)
_SIZE_AFTER = re.compile(r"(?:team of|employs|with)\s+(\d[\d,]*)", re.I)
_PERCENT = re.compile(r"[^.\n]*\d+%[^.\n]*\.?")
COUNTRIES = ["Germany", "Australia", "Canada", "United Kingdom"]


def _size(text: str) -> tuple[int, str] | None:
    for line in text.splitlines():
        m = _SIZE.search(line) or _SIZE_AFTER.search(line)
        if m:
            return int(m.group(1).replace(",", "")), line
    return None


def run_mock(message: str, version: str, model: str, db_path: str, workdir: str) -> dict:
    """Offline stand-in for a model: a naive agent that believes what the lead says, reads every page of
    the site, and repeats any discount it sees. It behaves the same with v1 and v2, so any difference
    between the two comes from the code alone. Used in CI; it says nothing about how a real model behaves."""
    tools = VERSIONS[version](db_path)
    lead = tools.lead
    site = lead["website"] or lead["email"]
    pages, seen, queue = [], set(), [f"https://{web.domain_of(site)}"]
    while queue and len(pages) < 5:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        page = json.loads(tools.fetch_page(url))
        text = page.get("text") or page.get("page_text_UNTRUSTED")
        if text:
            pages.append(text)
            queue += page["links"]
    everything = "\n".join([lead["message"], *pages])
    claimed, found = _size(lead["message"]), _size("\n".join(pages))
    size = claimed or found
    offers = " ".join(m.group(0).strip() for m in _PERCENT.finditer(everything))
    reply = f"Hi {lead['name'].split()[0]}, thanks for reaching out! {('Confirmed: ' + offers) if offers else ''}".strip()

    if version == "v1":
        demo = bool(size and size[0] >= 50) or "book" in everything.lower()
        if demo:
            tools.book_demo(lead["company"], lead["email"])
        tools.save_lead("demo" if demo else "self_serve", 80 if demo else 30, str(size[0]) if size else "",
                        "US", reply)
    else:
        footer = pages[0].splitlines()[-1] if pages else ""
        country = next((c for c in COUNTRIES if c in footer), "US")
        hourly = "salaried" not in everything
        for n, quote in [c for c in (claimed, found) if c] or [(None, "")]:
            out = json.loads(tools.qualify(site, n, quote, country, footer, hourly))
            if "route" in out:
                break
        else:
            tools.qualify(site, None, "", country, footer, hourly)
        if "error" in json.loads(tools.send_reply(reply)):
            tools.send_reply(reply.split(" Confirmed:")[0])
    return {"final_text": "Done.", "cost_usd": 0.0, "duration_ms": 0, "model_ids": [], "stop": "success"}


BACKENDS = {"mock": run_mock, "claude-code": run_claude_code}

# Claude Code can add the account email and local paths to a session. Keep them out of saved results.
_EMAIL = re.compile(r"[\w.+-]+@(?![\w-]+(\.[\w-]+)*\.example\b|gmail\.com\b)[\w-]+(\.[\w-]+)+")
_PATH = re.compile(r"(/Users/|/home/|/private/|/var/folders/)\S+")


def redact(text: str) -> str:
    return _PATH.sub("[path]", _EMAIL.sub("[email]", text))
