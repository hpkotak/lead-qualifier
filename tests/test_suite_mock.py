"""The whole suite against the offline mock agent. The mock believes every claim and repeats any
discount it reads, so this checks that the v2 code stops the damage whatever the model does."""
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
