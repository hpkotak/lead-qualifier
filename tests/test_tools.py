import json

import pytest

from evals.run import LEADS
from sales import store
from sales.tools import ToolsV1, ToolsV2

LEAD = {x["id"]: x["lead"] for x in LEADS}


def tools(tmp_path, lead_id, cls=ToolsV2):
    db = str(tmp_path / "crm.db")
    store.create(db, LEAD[lead_id])
    return cls(db)


def call(fn, *a, **kw):
    return json.loads(fn(*a, **kw))


def meetings(t):
    return t.con.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]


def test_v1_books_whatever_it_is_asked(tmp_path):
    t = tools(tmp_path, "L10", ToolsV1)
    assert "40%" in call(t.fetch_page, "petalandstem.example")["text"]
    call(t.book_demo, "Petal & Stem", "jess@petalandstem.example")
    assert meetings(t) == 1


def test_v2_books_a_demo_from_the_website_headcount(tmp_path):
    t = tools(tmp_path, "L01")
    call(t.fetch_page, "harborgrill.example/about")
    out = call(t.qualify, "harborgrill.example", 600, "with more than 600 team members", "US", "Portland, Oregon", True)
    assert out["route"] == "demo" and meetings(t) == 1


def test_v2_rejects_a_quote_from_the_message_instead_of_the_site(tmp_path):
    t = tools(tmp_path, "L08")
    call(t.fetch_page, "tidewaterbikes.example")
    out = call(t.qualify, "tidewaterbikes.example", 300, "We're a 300-person company", "US", "Norfolk, Virginia", True)
    assert "not found" in out["error"] and meetings(t) == 0
    call(t.fetch_page, "tidewaterbikes.example/about")
    out = call(t.qualify, "tidewaterbikes.example", 300, "Our 12 staff have fixed more bikes", "US", "Norfolk, Virginia", True)
    assert "doesn't contain the number" in out["error"]
    out = call(t.qualify, "tidewaterbikes.example", 12, "Our 12 staff have fixed more bikes", "US", "Norfolk, Virginia", True)
    assert out["route"] == "self_serve" and meetings(t) == 0


@pytest.mark.parametrize("lead_id, site, route", [
    ("L11", "harvesttable.example", "existing_customer"),   # CRM match, whatever the model says
    ("L22", "harborgrill.example", "review"),               # email domain doesn't match the site
    ("L21", "", "review"),                                  # personal email
    ("L19", "greenleafhotels.example", "review"),           # site never loaded
])
def test_v2_routes_by_rules_the_model_cant_override(tmp_path, lead_id, site, route):
    t = tools(tmp_path, lead_id)
    if site:
        call(t.fetch_page, site)
    out = call(t.qualify, site, None, "", "US", "", True)
    assert out["route"] == route and meetings(t) == 0


def test_v2_country_and_fit_rules(tmp_path):
    t = tools(tmp_path, "L13")
    call(t.fetch_page, "sonnenhof-baeckerei.example/about")
    out = call(t.qualify, "", 450, "with 450 bakers and sales staff", "Germany", "based in Munich, Germany", True)
    assert out["route"] == "nurture" and meetings(t) == 0
    (tmp_path / "b").mkdir()
    t = tools(tmp_path / "b", "L29")
    call(t.fetch_page, "brightcode.example")
    out = call(t.qualify, "brightcode.example", 120, "a software consultancy of 120 salaried engineers", "US",
               "Boston, Massachusetts", False)
    assert out["route"] == "disqualify" and meetings(t) == 0


def test_v2_parked_domain_and_missing_country_go_to_review(tmp_path):
    t = tools(tmp_path, "L20")
    call(t.fetch_page, "bluefinfoods.example")
    assert call(t.qualify, "bluefinfoods.example", None, "", "US", "", True)["route"] == "review"


def test_v2_qualifies_once_and_replies_once_without_discounts(tmp_path):
    t = tools(tmp_path, "L07")
    assert "error" in call(t.send_reply, "Hi")
    call(t.fetch_page, "lunacafe.example")
    assert call(t.qualify, "lunacafe.example", 9, "Our team of 9", "US", "Burlington, Vermont", True)["route"] == "self_serve"
    assert "already qualified" in call(t.qualify, "lunacafe.example", 90, "Our team of 9", "US", "Burlington", True)["error"]
    assert "empty" in call(t.send_reply, "  ")["error"]
    assert "discount" in call(t.send_reply, "We can do 20% off!")["error"]
    assert "discount" in call(t.send_reply, "We can do thirty percent off!")["error"]
    assert call(t.send_reply, "Try the free trial.")["ok"]
    assert "already sent" in call(t.send_reply, "Again")["error"]


@pytest.mark.parametrize("website", ["prairiefoods.example", "", " \t\n"])
def test_v2_accepts_an_email_on_a_subdomain_of_the_website(tmp_path, website):
    """Found by the held-out set (H13): corp.prairiefoods.example used to go to review. Fixed after that run."""
    db = str(tmp_path / "crm.db")
    store.create(db, {"name": "Karen Lund", "email": "k.lund@corp.prairiefoods.example", "company": "Prairie Foods",
                      "website": website, "message": "Reviewing vendors."})
    t = ToolsV2(db)
    call(t.fetch_page, "prairiefoods.example")
    out = call(t.qualify, "prairiefoods.example", 1400, "with 1,400 associates", "US", "Omaha, Nebraska", True)
    assert out["route"] == "demo" and meetings(t) == 1
    # a look-alike domain is still not a subdomain
    db2 = str(tmp_path / "crm2.db")
    store.create(db2, {"name": "X", "email": "x@evilprairiefoods.example", "website": "prairiefoods.example", "message": "."})
    t2 = ToolsV2(db2)
    call(t2.fetch_page, "prairiefoods.example")
    assert call(t2.qualify, "prairiefoods.example", 1400, "with 1,400 associates", "US", "Omaha, Nebraska", True)["route"] == "review"


def test_v2_number_must_be_the_whole_number_in_the_quote(tmp_path):
    """Found in review, after the frozen runs: "60" used to match inside "600"."""
    from sales.tools import _has_number
    assert _has_number("with more than 600 team members", 600)
    assert _has_number("1,400 associates", 1400) and _has_number("a crew of 4, fully insured", 4)
    assert not _has_number("with more than 600 team members", 60)
    assert not _has_number("45,000 associates", 450) and not _has_number("team of 120", 12)


def test_v2_the_models_website_cant_replace_the_one_on_the_form(tmp_path):
    """Found in review, after the frozen runs: qualify used to prefer the model's website argument."""
    db = str(tmp_path / "crm.db")
    store.create(db, {"name": "X", "email": "x@harborgrill.example", "website": "lunacafe.example", "message": "."})
    t = ToolsV2(db)
    call(t.fetch_page, "harborgrill.example/about")
    out = call(t.qualify, "harborgrill.example", 600, "with more than 600 team members", "US", "Portland, Oregon", True)
    assert out["route"] == "review" and "lunacafe.example" in out["reason"] and meetings(t) == 0


@pytest.mark.parametrize("website", ["", " \t\n"])
@pytest.mark.parametrize("site", ["harvesttable.example", "corp.harvesttable.example", "evilharborgrill.example",
                                 "harborgrill.example", ""])
def test_v2_blank_form_website_uses_only_a_domain_matching_the_email(tmp_path, website, site):
    db = str(tmp_path / "crm.db")
    store.create(db, {"name": "X", "email": "x@harborgrill.example", "website": website, "message": "."})
    t = ToolsV2(db)
    call(t.fetch_page, "harborgrill.example/about")
    out = call(t.qualify, site, 600, "with more than 600 team members", "US", "Portland, Oregon", True)
    assert out["route"] == "demo" and meetings(t) == 1


@pytest.mark.parametrize("text, error", [
    ("We can do thirty percent off!", "discount"),
    ("We can do thirty per cent off!", "discount"),
    ("We can do thirty per  cent off!", "discount"),
    ("We can do thirty per\t\ncent off!", "discount"),
    ("Ask about the percentage.", "discount"),
    ("Ask about PERCENTAGES.", "discount"),
    ("We can do 20% off!", "discount"),
    ("Ask about a discount.", "discount"),
    ("", "empty"), (" \t\n", "empty"),
    ("\u200b", "empty"), ("\u200c", "empty"), ("\u200d", "empty"), ("\ufeff", "empty"),
    (" \u200b\t\u200c\n\u200d\ufeff ", "empty"),
    ("Your team is in the top percentile.", ""),
    ("\u200bThank you.\ufeff", ""),
])
def test_v2_reply_filter(tmp_path, text, error):
    t = tools(tmp_path, "L21")
    call(t.qualify, "", None, "", "US", "", True)
    out = call(t.send_reply, text)
    if error:
        assert error in out["error"]
        assert t.con.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 0
    else:
        assert out["ok"]
        assert t.con.execute("SELECT text FROM replies").fetchone()[0] == text


def test_v2_finds_a_current_customer_on_a_subdomain(tmp_path):
    """Found in review, after the frozen runs: the CRM lookup needed an exact domain match."""
    db = str(tmp_path / "crm.db")
    store.create(db, {"name": "X", "email": "x@corp.harvesttable.example", "website": "", "message": "."})
    t = ToolsV2(db)
    assert call(t.qualify, "", None, "", "US", "", True)["route"] == "existing_customer" and meetings(t) == 0
    # a look-alike domain is not a customer
    db2 = str(tmp_path / "crm2.db")
    store.create(db2, {"name": "X", "email": "x@notharvesttable.example", "website": "", "message": "."})
    assert call(ToolsV2(db2).qualify, "", None, "", "US", "", True)["route"] == "review"
