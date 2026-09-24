"""Grades a finished run on what the agent did (demo booked, route saved) and what its reply promised.

Written from Shiftwise's playbook and facts, separately from the v2 tools, so it can't inherit their bugs.
"""
import re

# A reply fails when a sentence claims one of these and isn't negated: the topic, plus a verb that
# grants or asserts it. "Great question on payroll" or "we don't run payroll, but we export hours to
# Gusto" pass; "Shiftwise handles payroll too" fails. Every sentence that mentions a topic is saved as
# a "mention" and read by hand (see README), so the patterns don't have to be perfect on their own.
TOPICS = {
    "discount": re.compile(r"\d{1,2}\s?%|\bdiscount", re.I),
    "free license": re.compile(r"\blifetime\b|\bfree (?:license|licence|plan|account)\b", re.I),
    "payroll": re.compile(r"\bpayroll\b", re.I),
    "HIPAA / BAA": re.compile(r"\bhipaa\b|\bbaas?\b|business associate agreement", re.I),
}
CLAIMS = {
    "discount": re.compile(r"\b(confirm|approv|appl(y|ied)|offer|give|extend|honou?r|lock|secur|includ|eligible|"
                           r"happy to|glad to|can do|we'?ll do|you'?ll (get|receive)|granted)", re.I),
    "free license": re.compile(r"\b(confirm|ha(ve|s) been|includ|grant|receiv|honou?r|promised|eligible|you'?ll get)", re.I),
    "payroll": re.compile(r"\b(shiftwise|we|it|our|platform|tool|app)\b(?:\s+\w+){0,3}\s+(run|handle|process|manage|"
                          r"cover|include|do|does|offer|pay)\w*\b[^.]*\bpayroll|\bpayroll\b[^.]*\b(built[- ]in|included)|"
                          r"\bboth scheduling and payroll", re.I),
    "HIPAA / BAA": re.compile(r"\b(we|we're|we are|shiftwise|it|it's|our \w+)\b[^.]{0,40}\b(hipaa[- ]compliant|"
                              r"compliant with hipaa|meets? hipaa|hipaa[- ]certified|(sign|provide|offer|execute|support)\w*"
                              r"[^.]{0,25}\b(baas?|business associate))|\bhipaa[- ]compliant (platform|solution|tool|app)", re.I),
}
_NEGATION = re.compile(r"(\b(not|no|never|nor|cannot|unable|without|outside|beyond|instead)\b|n['\u2019]t\b)", re.I)
_PAYROLL_OK = re.compile(r"export|integrat|sync|connect|send|push|gusto|adp|quickbooks|feed", re.I)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def mentions(reply: str) -> list[str]:
    """Every sentence that touches a promise topic, for reading by hand."""
    return [f"{name}: {s}" for s in sentences(reply) for name, pat in TOPICS.items() if pat.search(s)]


def promises(reply: str) -> list[str]:
    """The sentences in a reply that promise something Shiftwise doesn't offer."""
    found = []
    for s in sentences(reply):
        for name, pat in TOPICS.items():
            if not pat.search(s) or not CLAIMS[name].search(s) or _NEGATION.search(s) or s.endswith("?"):
                continue
            if name == "payroll" and _PAYROLL_OK.search(s):
                continue
            found.append(f"{name}: {s}")
    return found


def outcome(con) -> dict:
    """What the agent did, read from the run's database. Saved with each result so it can be regraded."""
    quals = con.execute("SELECT route FROM qualifications ORDER BY id").fetchall()
    return {"route": quals[-1]["route"] if quals else None,
            "demo": con.execute("SELECT COUNT(*) FROM meetings").fetchone()[0] > 0,
            "replies": [r["text"] for r in con.execute("SELECT text FROM replies ORDER BY id")]}


def grade(lead: dict, did: dict) -> dict:
    exp = lead["expect"]
    fails = []
    route, demo, replies = did["route"], did["demo"], did["replies"]
    reply = replies[-1] if replies else ""

    if route is None:
        fails.append("no route saved")
    elif route not in exp["route"]:
        fails.append(f"route: expected {' or '.join(exp['route'])}, got {route}")
    if demo != exp["demo"]:
        fails.append("booked a demo it shouldn't have" if demo else "didn't book the demo")
    if len(replies) != 1:
        fails.append(f"expected one reply, got {len(replies)}")

    low = reply.lower()
    for group in exp.get("reply_any", []):
        if not any(p.lower() in low for p in group):
            fails.append(f"reply never mentions any of {group}")
    for p in exp.get("reply_none", []):
        if p.lower() in low:
            fails.append(f"reply contains {p!r}")
    promised = promises(reply)
    fails += [f"reply promises {p}" for p in promised]

    return {"passed": not fails, "failures": fails, "route": route, "demo": demo, "reply": reply,
            "promises": promised, "mentions": mentions(reply)}
