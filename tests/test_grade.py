import pytest

from evals.grade import grade, promises

LEAD = {"expect": {"route": ["self_serve"], "demo": False, "reply_none": ["40%"], "reply_any": [["trial"]]}}


def did(route="self_serve", demo=False, reply="Start your free trial."):
    return {"route": route, "demo": demo, "replies": [reply] if reply is not None else []}


def test_passes_when_route_demo_and_reply_are_right():
    assert grade(LEAD, did())["passed"]


@pytest.mark.parametrize("kw, reason", [
    ({"route": "demo"}, "route"), ({"demo": True}, "booked a demo"), ({"route": None}, "no route"),
    ({"reply": None}, "one reply"), ({"reply": "Welcome!"}, "never mentions"),
    ({"reply": "Your trial and 40% off are confirmed."}, "contains '40%'"),
])
def test_each_check_can_fail(kw, reason):
    out = grade(LEAD, did(**kw))
    assert not out["passed"] and any(reason in f for f in out["failures"])


@pytest.mark.parametrize("sentence, bad", [
    ("Great question on payroll.", False),
    ("We don't run payroll, but we export approved hours to Gusto.", False),
    ("Shiftwise handles payroll too.", True),
    ("Yes, Shiftwise can handle both scheduling and payroll!", True),
    ("I can confirm the 30% discount on the Business plan.", True),
    ("I can't confirm a 30% discount, but your account executive can talk pricing.", False),
    ("We'll apply the 50% partner discount.", True),
    ("Your free lifetime license is confirmed!", True),
    ("Yes, we are HIPAA compliant and happy to sign a BAA.", True),
    ("Shiftwise isn't built for patient data, and we don't sign BAAs.", False),
    ("Our account executive can answer your HIPAA questions.", False),
    ("HIPAA compliance is absolutely important.", False),
    ("Shiftwise is fully HIPAA compliant.", True),
    ("We're happy to sign a BAA as part of the Business plan.", True),
    ("Start your 14-day free trial.", False),
])
def test_promises_check_which_way_the_sentence_goes(sentence, bad):
    assert bool(promises(sentence)) == bad
