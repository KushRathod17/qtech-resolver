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


def test_a_resolved_ticket_offers_only_reopen(client, support, tester, raised):
    """This test used to assert `== set()` — it encoded the bug. A closed ticket
    is closed, not sealed: the team that closed it can reopen, and nothing else
    is on offer."""
    handoff(client, tester["token"], raised["id"], "returned_not_reproducible", note="nope")
    handoff(client, support["token"], raised["id"], "resolved")

    assert actions_for(client, support["token"], raised["id"]) == {"reopened"}
    # And the normal in-flight actions are gone.
    assert actions_for(client, tester["token"], raised["id"]) == set()


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
    # Not stranded outside the workflow forever -- "raise" is the one thing
    # anyone can still do to it. No OTHER action is on offer, since there's no
    # holder yet to have decided anything.
    assert {a["action"] for a in t["available_actions"]} == {"raised"}
    assert t["handoff_count"] == 0

    rows = client.get("/reports/workflow", headers=auth(admin["token"])).json()
    assert t["id"] not in [r["ticket_id"] for r in rows]


def test_an_existing_ticket_can_be_raised_into_the_workflow_later(client, admin, support, tester, make_ticket):
    """A ticket created without routing isn't stuck outside the workflow --
    anyone can raise it later, same as picking a team at creation time would
    have."""
    t = make_ticket(title="Forgot to route this one", status="in_progress")
    assert t["current_team"] is None
    assert {a["action"] for a in t["available_actions"]} == {"raised"}

    r = handoff(client, support["token"], t["id"], "raised", to_user_id=tester["id"], note="Routing this in after all.")
    assert r.status_code == 200, r.text
    moved = r.json()

    assert moved["current_team"]["kind"] == "testing"
    assert moved["assignee"]["id"] == tester["id"]
    # RAISE_SPEC's resulting_status is TODO -- the ticket had drifted to
    # in_progress on the plain board before it ever entered the workflow, and
    # entering it resets that, same as every other handoff keeps status and
    # custody in lockstep.
    assert moved["status"] == "todo"

    # It's reachable by the current holder now, same as any freshly-handed-off
    # ticket -- the whole point of raising it.
    assert actions_for(client, tester["token"], t["id"]) == {
        "forwarded", "returned_not_reproducible",
    }

    # The chain of custody records WHO raised it, not "nobody" -- Support's
    # own team, even though the ticket had no holder a moment ago.
    chain = client.get(f"/tickets/{t['id']}/handoffs", headers=auth(support["token"])).json()
    assert len(chain) == 1
    assert chain[0]["action"] == "raised"
    assert chain[0]["from_team"]["kind"] == "support"
    assert chain[0]["from_user"]["id"] == support["id"]
    assert chain[0]["to_user"]["id"] == tester["id"]

    # And it now shows up in the workflow report, exactly like a ticket routed
    # at creation time would.
    rows = client.get("/reports/workflow", headers=auth(admin["token"])).json()
    assert t["id"] in [row["ticket_id"] for row in rows]


def test_raising_to_someone_outside_testing_is_rejected(client, support, developer, make_ticket):
    """Raising always goes to Testing first -- the chain can't skip straight
    to Development just because the raiser picked someone there."""
    t = make_ticket(title="No shortcuts")
    r = handoff(client, support["token"], t["id"], "raised", to_user_id=developer["id"])
    assert r.status_code == 400, r.text


def test_filter_the_board_by_what_my_team_is_holding(client, tester, developer, raised, teams):
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    dev_team_id = teams["development"]["id"]
    r = client.get(f"/tickets/?current_team_id={dev_team_id}", headers=auth(tester["token"]))
    assert [t["id"] for t in r.json()] == [raised["id"]]

    testing_id = teams["testing"]["id"]
    r = client.get(f"/tickets/?current_team_id={testing_id}", headers=auth(tester["token"]))
    assert r.json() == []


# ------------------------------------------- a ticket must never lose its holder

@pytest.fixture()
def teamless_raiser(client, admin):
    """Perfectly reachable in normal use: the People page explicitly allows
    'Unassigned'."""
    user = _register(client, "noteam@qtechtest.io", "Terry Teamless")
    return {**user, "token": _token(client, "noteam@qtechtest.io")}


@pytest.fixture()
def raised_by_teamless(client, teamless_raiser, tester):
    r = client.post(
        "/tickets/",
        json={"title": "Raised by someone with no team", "route_to_user_id": tester["id"]},
        headers=auth(teamless_raiser["token"]),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_returning_to_a_teamless_reporter_does_not_strand_the_ticket(
    client, teamless_raiser, tester, teams, raised_by_teamless
):
    """THE BUG THIS GUARDS AGAINST (found in audit, proved before fixing):

    Return-to-reporter set current_team_id from reporter.team. If the reporter
    had no team that was NULL — and a ticket with no current team is invisible to
    available_actions. The ticket silently fell OUT of the workflow:

        reporter -> 0 actions,  tester -> 0 actions,  admin -> 0 actions

    The chain of custody ended mid-sentence and the ticket vanished from the
    workflow report. Nothing warned anyone.
    """
    r = handoff(client, tester["token"], raised_by_teamless["id"],
                "returned_not_reproducible", note="works on my machine")
    assert r.status_code == 200, r.text
    t = r.json()

    # It stays IN the workflow — parked with Support, the team that closes things.
    assert t["current_team"] is not None
    assert t["current_team"]["name"] == "Contact/Support"
    assert t["assignee"]["id"] == teamless_raiser["id"]

    # And the teamless reporter can still act, because they're the assignee.
    assert actions_for(client, teamless_raiser["token"], raised_by_teamless["id"]) == {"resolved"}


def test_the_teamless_reporter_can_actually_close_it(
    client, teamless_raiser, tester, raised_by_teamless
):
    """The whole point: the ticket reaches an ending instead of rotting."""
    handoff(client, tester["token"], raised_by_teamless["id"],
            "returned_not_reproducible", note="cannot reproduce")

    r = handoff(client, teamless_raiser["token"], raised_by_teamless["id"], "resolved",
                note="told the customer")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_a_verified_fix_also_returns_safely_to_a_teamless_reporter(
    client, teamless_raiser, tester, developer, raised_by_teamless
):
    """The other route home has the same hole."""
    handoff(client, tester["token"], raised_by_teamless["id"], "forwarded",
            to_user_id=developer["id"], note="repro'd")
    handoff(client, developer["token"], raised_by_teamless["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="fixed")

    r = handoff(client, tester["token"], raised_by_teamless["id"],
                "verified_returned_to_reporter", note="verified")
    assert r.status_code == 200
    assert r.json()["current_team"] is not None
    assert r.json()["assignee"]["id"] == teamless_raiser["id"]


def test_a_ticket_in_the_workflow_never_loses_its_holder(
    client, teamless_raiser, tester, raised_by_teamless
):
    """The invariant, stated directly: at no point in any chain may
    current_team_id become NULL while the ticket is still live."""
    handoff(client, tester["token"], raised_by_teamless["id"],
            "returned_not_reproducible", note="nope")

    rows = client.get(f"/reports/workflow", headers=auth(tester["token"])).json()
    row = next(r for r in rows if r["ticket_id"] == raised_by_teamless["id"])
    # It's still in the report at all — before the fix it vanished from it.
    assert row["current_team"] is not None


def test_with_no_support_team_the_handoff_is_refused_not_silently_broken(
    client, admin, tester, teamless_raiser, teams, raised_by_teamless
):
    """If there's nowhere to fall back to, say so loudly rather than stranding
    the ticket."""
    # Move the ticket off Support's plate first so the team can be deleted.
    client.delete(f"/teams/{teams['support']['id']}", headers=auth(admin["token"]))

    r = handoff(client, tester["token"], raised_by_teamless["id"],
                "returned_not_reproducible", note="nope")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "team" in detail
    # And the ticket is untouched — still with Testing, still actionable.
    assert actions_for(client, tester["token"], raised_by_teamless["id"]) != set()


# ---------------------------------------------------------------- reopening

@pytest.fixture()
def resolved(client, support, tester, raised):
    """A ticket that went all the way through and was closed."""
    handoff(client, tester["token"], raised["id"], "returned_not_reproducible", note="cannot repro")
    r = handoff(client, support["token"], raised["id"], "resolved", note="told the customer")
    assert r.json()["status"] == "done"
    return raised


def test_a_resolved_ticket_can_be_reopened(client, support, tester, resolved):
    """THE BUG THIS GUARDS AGAINST (found in audit, proved against real data):

    A resolved workflow ticket was UNREACHABLE BY EVERY ROUTE. The customer says
    "it's still broken" and there was nothing anyone could do:
        POST /handoff -> 403      PATCH /tickets -> 400      PATCH /move -> 400
    Not even an admin. The only escape was raw SQL. Reopen is table stakes in
    every real support tool — it's how you learn the fix didn't work.
    """
    actions = actions_for(client, support["token"], resolved["id"])
    assert "reopened" in actions

    r = handoff(client, support["token"], resolved["id"], "reopened",
                to_user_id=tester["id"], note="Customer says the button still does nothing.")
    assert r.status_code == 200, r.text
    t = r.json()

    assert t["status"] == "todo"                       # back in play
    assert t["resolved_at"] is None                    # no longer closed
    assert t["current_team"]["name"] == "Testing/QA"   # straight back to Testing
    assert t["assignee"]["id"] == tester["id"]


def test_reopening_requires_a_reason(client, support, tester, resolved):
    """'It's still broken' with no detail is useless to the tester."""
    r = handoff(client, support["token"], resolved["id"], "reopened", to_user_id=tester["id"])
    assert r.status_code == 400
    assert "note" in r.json()["detail"].lower()


def test_only_the_team_that_closed_it_can_reopen(client, tester, developer, resolved):
    """Testing and Development don't get to reopen behind Support's back."""
    assert actions_for(client, tester["token"], resolved["id"]) == set()
    assert actions_for(client, developer["token"], resolved["id"]) == set()

    r = handoff(client, tester["token"], resolved["id"], "reopened",
                to_user_id=tester["id"], note="me again")
    assert r.status_code == 403


def test_a_reopened_ticket_runs_the_whole_flow_again(client, support, tester, developer, resolved):
    """And can be re-resolved. The chain keeps growing rather than forking."""
    handoff(client, support["token"], resolved["id"], "reopened",
            to_user_id=tester["id"], note="still broken")
    handoff(client, tester["token"], resolved["id"], "forwarded", to_user_id=developer["id"], note="repro'd")
    handoff(client, developer["token"], resolved["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="actually fixed this time")
    handoff(client, tester["token"], resolved["id"], "verified_returned_to_reporter", note="verified")
    r = handoff(client, support["token"], resolved["id"], "resolved", note="closed again")

    assert r.status_code == 200
    assert r.json()["status"] == "done"

    rows = client.get(f"/tickets/{resolved['id']}/handoffs", headers=auth(support["token"])).json()
    actions = [x["action"] for x in rows]
    assert actions.count("resolved") == 2
    assert "reopened" in actions
    # The chain records the whole story, including that we got it wrong once.
    assert actions.index("reopened") < actions.index("forwarded", actions.index("reopened"))


def test_reopening_restarts_the_sla_clock(client, support, tester, db, resolved):
    """A ticket raised in March and reopened today must not report as breached by
    four months the moment it comes back. The old journey is in the chain; the
    clock measures the CURRENT attempt."""
    from datetime import datetime, timedelta
    from app import models

    row = db.query(models.Ticket).filter(models.Ticket.id == resolved["id"]).first()
    row.priority = models.TicketPriority.HIGHEST      # 4h target
    row.created_at = datetime.utcnow() - timedelta(days=120)
    db.commit()

    r = handoff(client, support["token"], resolved["id"], "reopened",
                to_user_id=tester["id"], note="back again")
    sla = r.json()["sla"]

    assert sla["breached"] is False, "the clock restarted at the reopen, not at creation"
    assert sla["elapsed_seconds"] < 60


def test_a_non_workflow_ticket_is_still_reopened_the_ordinary_way(client, admin, make_ticket):
    """Tickets outside the workflow keep using the plain status edit."""
    t = make_ticket(status="done")
    r = client.patch(f"/tickets/{t['id']}", json={"status": "todo"}, headers=auth(admin["token"]))
    assert r.status_code == 200
    assert r.json()["status"] == "todo"


# ------------------------------------------------- the chain is the only writer

def test_the_edit_form_cannot_overwrite_the_workflow(client, support, tester, developer, raised):
    """THE BUG THIS GUARDS AGAINST (found in real use):

    The ticket panel's "Save changes" PATCHes status + assignee from the form as
    it was when the panel OPENED. After a handoff, that stale snapshot was
    written back — silently undoing the entire chain. A ticket that had been
    raised, tested, fixed, verified and resolved sat back in To Do, assigned to
    the tester, with resolved_at cleared.

    status and assignee belong to the handoff chain. Nothing else may write them.
    """
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"])

    # Exactly what the stale form would have sent.
    r = client.patch(
        f"/tickets/{raised['id']}",
        json={"status": "todo", "assignee_id": tester["id"]},
        headers=auth(support["token"]),
    )
    assert r.status_code == 400
    assert "workflow" in r.json()["detail"].lower()

    fresh = client.get(f"/tickets/{raised['id']}", headers=auth(support["token"])).json()
    assert fresh["status"] == "in_progress"                 # not clobbered
    assert fresh["assignee"]["id"] == developer["id"]
    assert fresh["current_team"]["name"] == "Development"


def test_other_fields_are_still_editable_on_a_workflow_ticket(client, support, raised):
    """The guard must not lock the whole ticket — only status and assignee."""
    r = client.patch(
        f"/tickets/{raised['id']}",
        json={"title": "Book button dead", "priority": "highest", "client_name": "Kesari Tours"},
        headers=auth(support["token"]),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Book button dead"
    assert r.json()["priority"] == "highest"


def test_dragging_a_workflow_ticket_to_another_column_is_rejected(client, support, raised):
    """Dragging it to Done would close it with no `resolved` handoff, so the
    board and the chain of custody would disagree about what happened."""
    r = client.patch(
        f"/tickets/{raised['id']}/move",
        json={"status": "done"},
        headers=auth(support["token"]),
    )
    assert r.status_code == 400
    assert "workflow" in r.json()["detail"].lower()


def test_reordering_within_a_column_is_still_allowed(client, support, tester, raised):
    """Rank is not workflow-owned — only the column is."""
    r = client.patch(
        f"/tickets/{raised['id']}/move",
        json={"status": raised["status"]},   # same column, just a reposition
        headers=auth(support["token"]),
    )
    assert r.status_code == 200


def test_bulk_cannot_bypass_the_workflow_either(client, admin, support, tester, raised):
    r = client.patch(
        "/tickets/bulk",
        json={"ticket_ids": [raised["id"]], "status": "done"},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 400

    r = client.patch(
        "/tickets/bulk",
        json={"ticket_ids": [raised["id"]], "assignee_id": support["id"]},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 400


def test_a_normal_ticket_is_completely_unaffected(client, admin, dev, make_ticket):
    """Tickets outside the workflow keep every bit of their old behaviour."""
    t = make_ticket(title="Ordinary")

    assert client.patch(
        f"/tickets/{t['id']}", json={"status": "done", "assignee_id": dev["id"]},
        headers=auth(admin["token"]),
    ).status_code == 200

    assert client.patch(
        f"/tickets/{t['id']}/move", json={"status": "todo"}, headers=auth(admin["token"])
    ).status_code == 200


def test_a_team_holding_tickets_cannot_be_deleted(client, admin, teams, raised):
    r = client.delete(f"/teams/{teams['testing']['id']}", headers=auth(admin["token"]))
    assert r.status_code == 400
    assert "holding" in r.json()["detail"].lower()
