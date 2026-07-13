"""
The cross-team bug workflow.

The rules here are enforced SERVER-SIDE. Hiding a button is a courtesy; these
tests are the actual guarantee. A regression that lets a developer close a
ticket, or lets Testing act on a ticket sitting with Development, is a
correctness bug in a chain-of-custody log — the one thing the feature exists to
be trustworthy about.
"""
import pytest

from app import models
from tests.conftest import auth, _register, _token


# ---------------------------------------------------------------- fixtures

@pytest.fixture()
def teams(client, admin):
    """The three teams the migration seeds in dev. The test DB is built from the
    models, so the tests create them explicitly."""
    made = {}
    for name, kind in [
        ("Contact/Support", "support"),
        ("Testing/QA", "testing"),
        ("Development", "development"),
    ]:
        r = client.post("/teams/", json={"name": name, "kind": kind}, headers=auth(admin["token"]))
        assert r.status_code == 201, r.text
        made[kind] = r.json()
    return made


def _member(client, admin, email, name, team_id):
    user = _register(client, email, name)
    r = client.patch(
        f"/users/{user['id']}/team", json={"team_id": team_id}, headers=auth(admin["token"])
    )
    assert r.status_code == 200, r.text
    return {**r.json(), "token": _token(client, email)}


@pytest.fixture()
def support(client, admin, teams):
    return _member(client, admin, "sup@qtechtest.io", "Sam Support", teams["support"]["id"])


@pytest.fixture()
def tester(client, admin, teams):
    return _member(client, admin, "qa@qtechtest.io", "Tara Tester", teams["testing"]["id"])


@pytest.fixture()
def tester2(client, admin, teams):
    return _member(client, admin, "qa2@qtechtest.io", "Tom Tester", teams["testing"]["id"])


@pytest.fixture()
def developer(client, admin, teams):
    return _member(client, admin, "dev1@qtechtest.io", "Dana Dev", teams["development"]["id"])


@pytest.fixture()
def developer2(client, admin, teams):
    return _member(client, admin, "dev2b@qtechtest.io", "Deo Dev", teams["development"]["id"])


@pytest.fixture()
def raised(client, support, tester):
    """A customer bug, raised by Support and sent to a named tester."""
    r = client.post(
        "/tickets/",
        json={
            "title": "Button not working",
            "description": "Customer says the Book button does nothing.",
            "ticket_type": "bug",
            "route_to_user_id": tester["id"],
            "route_note": "Reported by Kesari Tours.",
        },
        headers=auth(support["token"]),
    )
    assert r.status_code == 201, r.text
    return r.json()


def handoff(client, token, ticket_id, action, to_user_id=None, note=None):
    body = {"action": action}
    if to_user_id:
        body["to_user_id"] = to_user_id
    if note:
        body["note"] = note
    return client.post(f"/tickets/{ticket_id}/handoff", json=body, headers=auth(token))


def actions_for(client, token, ticket_id):
    r = client.get(f"/tickets/{ticket_id}", headers=auth(token))
    return {a["action"] for a in r.json()["available_actions"]}


# ---------------------------------------------------------------- the happy path

def test_the_full_chain_end_to_end(client, support, tester, developer, raised):
    """Support -> Testing -> Development -> Testing -> Support -> Resolved."""
    t = raised
    assert t["current_team"]["name"] == "Testing/QA"
    assert t["assignee"]["id"] == tester["id"]

    r = handoff(client, tester["token"], t["id"], "forwarded",
                to_user_id=developer["id"], note="Reproduced on staging.")
    assert r.status_code == 200, r.text
    assert r.json()["current_team"]["name"] == "Development"
    assert r.json()["assignee"]["id"] == developer["id"]

    r = handoff(client, developer["token"], t["id"], "fixed_returned_to_testing",
                to_user_id=tester["id"], note="Null guard on the click handler.")
    assert r.status_code == 200, r.text
    assert r.json()["current_team"]["name"] == "Testing/QA"

    r = handoff(client, tester["token"], t["id"], "verified_returned_to_reporter",
                note="Fix confirmed.")
    assert r.status_code == 200, r.text
    # Returns to the ORIGINAL reporter — reusing created_by_id, not a new field.
    assert r.json()["assignee"]["id"] == support["id"]
    assert r.json()["current_team"]["name"] == "Contact/Support"

    r = handoff(client, support["token"], t["id"], "resolved", note="Told the customer.")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["resolved_at"] is not None  # the SLA clock stops too


def test_not_reproducible_returns_straight_to_support(client, support, tester, raised):
    r = handoff(client, tester["token"], raised["id"], "returned_not_reproducible",
                note="Works on Chrome and Safari; asked for a screen recording.")
    assert r.status_code == 200, r.text
    assert r.json()["assignee"]["id"] == support["id"]
    assert r.json()["current_team"]["name"] == "Contact/Support"


def test_still_broken_goes_back_to_a_developer(client, support, tester, developer, developer2, raised):
    """And it may go to a DIFFERENT developer than the one who 'fixed' it."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="Fixed")

    r = handoff(client, tester["token"], raised["id"], "returned_still_broken",
                to_user_id=developer2["id"], note="Still fails on Safari 17.")
    assert r.status_code == 200, r.text
    assert r.json()["assignee"]["id"] == developer2["id"]
    assert r.json()["current_team"]["name"] == "Development"


# ---------------------------------------------------------------- who may act

def test_testing_sees_first_pass_actions_on_a_fresh_ticket(client, tester, raised):
    assert actions_for(client, tester["token"], raised["id"]) == {
        "forwarded", "returned_not_reproducible"
    }


def test_testing_sees_VERIFY_actions_once_a_fix_comes_back(client, tester, developer, raised):
    """Same team, same person, different options — derived from the last handoff
    rather than a stored flag."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="Fixed")

    assert actions_for(client, tester["token"], raised["id"]) == {
        "verified_returned_to_reporter", "returned_still_broken"
    }


def test_a_developer_has_no_actions_while_testing_holds_it(client, developer, raised):
    assert actions_for(client, developer["token"], raised["id"]) == set()


def test_support_cannot_resolve_until_it_comes_back(client, support, raised):
    """The whole point: Support can't close a ticket that's still with Testing."""
    assert actions_for(client, support["token"], raised["id"]) == set()

    r = handoff(client, support["token"], raised["id"], "resolved")
    assert r.status_code == 403


def test_a_developer_cannot_resolve_a_ticket(client, tester, developer, raised):
    """Even while holding it, Development has exactly one action."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    assert actions_for(client, developer["token"], raised["id"]) == {"fixed_returned_to_testing"}
    assert handoff(client, developer["token"], raised["id"], "resolved").status_code == 403


def test_someone_on_no_team_cannot_act(client, dev, raised):
    """`dev` was never assigned a team."""
    assert actions_for(client, dev["token"], raised["id"]) == set()
    assert handoff(client, dev["token"], raised["id"], "forwarded").status_code == 403


def test_a_teammate_of_the_holder_can_act(client, tester, tester2, developer, raised):
    """Assigned to Tara, but Tom is also on Testing — otherwise one tester going
    on holiday strands the ticket."""
    assert "forwarded" in actions_for(client, tester2["token"], raised["id"])
    r = handoff(client, tester2["token"], raised["id"], "forwarded", to_user_id=developer["id"])
    assert r.status_code == 200


def test_a_resolved_ticket_has_no_further_actions(client, support, tester, raised):
    handoff(client, tester["token"], raised["id"], "returned_not_reproducible", note="nope")
    handoff(client, support["token"], raised["id"], "resolved")
    assert actions_for(client, support["token"], raised["id"]) == set()


# ---------------------------------------------------------------- bad handoffs

def test_forwarding_to_the_wrong_team_is_rejected(client, tester, tester2, raised):
    """'Forward to Development' must not accept a tester."""
    r = handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=tester2["id"])
    assert r.status_code == 400
    assert "development" in r.json()["detail"].lower()


def test_forwarding_to_someone_with_no_team_is_rejected(client, tester, dev, raised):
    r = handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=dev["id"])
    assert r.status_code == 400
    assert "team" in r.json()["detail"].lower()


def test_forwarding_with_no_person_is_rejected(client, tester, raised):
    r = handoff(client, tester["token"], raised["id"], "forwarded")
    assert r.status_code == 400


@pytest.mark.parametrize("action", ["returned_not_reproducible"])
def test_a_note_is_required_where_it_matters(client, tester, raised, action):
    """Bouncing a bug back with no explanation is the most infuriating thing in
    a support queue."""
    r = handoff(client, tester["token"], raised["id"], action)
    assert r.status_code == 400
    assert "note" in r.json()["detail"].lower()

    r = handoff(client, tester["token"], raised["id"], action, note="Cannot reproduce on any browser.")
    assert r.status_code == 200


def test_a_developer_must_say_what_they_fixed(client, tester, developer, raised):
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])
    r = handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
                to_user_id=tester["id"])
    assert r.status_code == 400


# ---------------------------------------------------------------- chain of custody

def test_the_timeline_is_a_full_chain_of_custody(client, support, tester, developer, raised):
    handoff(client, tester["token"], raised["id"], "forwarded",
            to_user_id=developer["id"], note="Reproduced.")
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="Null guard added.")
    handoff(client, tester["token"], raised["id"], "verified_returned_to_reporter", note="Good.")

    rows = client.get(f"/tickets/{raised['id']}/handoffs", headers=auth(support["token"])).json()
    assert [r["action"] for r in rows] == [
        "raised", "forwarded", "fixed_returned_to_testing", "verified_returned_to_reporter",
    ]

    # The initial raise came from nobody's desk.
    assert rows[0]["from_team"] is None or rows[0]["from_user"]["id"] == support["id"]
    assert rows[0]["to_user"]["full_name"] == "Tara Tester"
    assert rows[0]["note"] == "Reported by Kesari Tours."

    # Every closed hold has a duration; only the last one is still open.
    for r in rows[:-1]:
        assert r["handed_off_at"] is not None
        assert r["duration_held_seconds"] is not None
        assert r["is_current"] is False
    assert rows[-1]["is_current"] is True
    assert rows[-1]["handed_off_at"] is None
    assert rows[-1]["duration_held_seconds"] is None

    # received_at is the moment it was handed over.
    assert rows[1]["received_at"] == rows[1]["sent_at"]

    # The contribution notes survive, end to end.
    assert [r["note"] for r in rows][1:3] == ["Reproduced.", "Null guard added."]


def test_handoffs_are_echoed_into_the_activity_feed(client, support, tester, developer, raised):
    """The handoff table is the source of truth; the activity row is a
    projection, so the ticket's existing history stays whole."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])
    acts = client.get(f"/tickets/{raised['id']}/activity", headers=auth(support["token"])).json()
    assert any(a["action"] == "handoff" for a in acts)


# ---------------------------------------------------------------- reports

def test_workflow_report(client, support, tester, developer, raised):
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    rows = client.get("/reports/workflow", headers=auth(support["token"])).json()
    row = next(r for r in rows if r["ticket_id"] == raised["id"])

    assert row["current_team"]["name"] == "Development"
    assert row["current_assignee"]["full_name"] == "Dana Dev"
    assert row["teams_touched"] == 2          # Testing, then Development
    assert row["handoff_count"] == 2
    assert row["total_open_seconds"] >= 0
    assert row["seconds_since_last_handoff"] >= 0


def test_team_holding_times_exclude_the_hold_still_in_progress(client, tester, developer, raised):
    """An open hold would drag the mean upward every time you refreshed the
    page — the number has to be stable."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    rows = client.get("/reports/team-holding-times", headers=auth(tester["token"])).json()
    by_name = {r["team"]["name"]: r for r in rows}

    testing = by_name["Testing/QA"]
    assert testing["completed_holds"] == 1        # Testing's hold ended
    assert testing["average_hold_seconds"] is not None
    assert testing["currently_holding"] == 0

    dev_team = by_name["Development"]
    assert dev_team["currently_holding"] == 1     # still holding it
    assert dev_team["completed_holds"] == 0
    assert dev_team["average_hold_seconds"] is None  # not "0" — unknown


def test_tickets_outside_the_workflow_are_untouched(client, admin, make_ticket):
    """The 26 pre-existing tickets must keep working."""
    t = make_ticket(title="Old ticket")
    assert t["current_team"] is None
    assert t["available_actions"] == []
    assert t["handoff_count"] == 0

    rows = client.get("/reports/workflow", headers=auth(admin["token"])).json()
    assert t["id"] not in [r["ticket_id"] for r in rows]


def test_filter_the_board_by_what_my_team_is_holding(client, tester, developer, raised, teams):
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    dev_team_id = teams["development"]["id"]
    r = client.get(f"/tickets/?current_team_id={dev_team_id}", headers=auth(tester["token"]))
    assert [t["id"] for t in r.json()] == [raised["id"]]

    testing_id = teams["testing"]["id"]
    r = client.get(f"/tickets/?current_team_id={testing_id}", headers=auth(tester["token"]))
    assert r.json() == []


def test_a_team_holding_tickets_cannot_be_deleted(client, admin, teams, raised):
    r = client.delete(f"/teams/{teams['testing']['id']}", headers=auth(admin["token"]))
    assert r.status_code == 400
    assert "holding" in r.json()["detail"].lower()
