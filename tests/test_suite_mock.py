"""The whole suite against the offline mock agent. The mock believes every claim and repeats any
discount it reads, so this checks that the v2 code stops the damage whatever the model does."""
import json

import pytest

from evals.report import summarise
from evals.run import LEADS, run_one
from sales.store import ROUTES


def test_v2_guardrails_hold_against_a_gullible_agent():
    rows = [{"model": "mock", "version": v, "lead": x["id"], "category": x["category"], "expect": x["expect"],
             "trial": 1, **run_one("mock", "mock", v, x, 1)} for v in ("v1", "v2") for x in LEADS]
    s = summarise(rows)
    v1, v2 = s["mock/v1"], s["mock/v2"]
    assert v1["demos_booked_wrongly"] >= 10 and v1["replies_with_false_promises"] >= 3
    assert v1["existing_customers_booked"] == 2
    assert v2["demos_booked_wrongly"] == 0 and v2["replies_with_false_promises"] == 0
    assert v2["pass_at_1"] > v1["pass_at_1"]


def test_leads_are_well_formed():
    ids = [x["id"] for x in LEADS]
    assert len(ids) == len(set(ids)) == 29
    routes = set(ROUTES)
    for x in LEADS:
        e = x["expect"]
        assert set(e) <= {"route", "demo", "reply_any", "reply_none"} and set(e["route"]) <= routes, x["id"]
        assert e["demo"] == (e["route"] == ["demo"]), x["id"]
        assert {"name", "email", "message"} <= set(x["lead"]), x["id"]


@pytest.mark.parametrize("tool, error, rejected", [
    ("qualify", "country_quote was not found on any page", False),
    ("qualify", "employees_quote was not found on any page", True),
    ("fetch_page", "employees_quote was not found on any page", False),
])
def test_example_caption_counts_only_rejected_headcount_quotes(tmp_path, monkeypatch, tool, error, rejected):
    pytest.importorskip("PIL")
    from evals import images
    bodies = []
    monkeypatch.setattr(images, "_card", lambda d, box, title, body, *args: bodies.extend(body))
    call = {"tool": tool, "result": json.dumps({"error": error})}
    rows = [{"lead": "L08", "model": "haiku", "version": "v2", "demo": False, "tool_calls": [call, call]}
            for _ in range(2)]
    images.example(rows, tmp_path / "example.png")
    caption = " ".join(bodies)
    assert ("a headcount quote was rejected in 2 runs" in caption) == rejected
    assert ("was rejected" in caption) == rejected
    assert "a quote from the message" not in caption
