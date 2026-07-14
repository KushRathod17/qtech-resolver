"""
"Tickets I solved" — GET /users/{id}/contributions.

Everything here is derived from the handoff chain, so these tests are what prove
the derivation is right: fixed ≠ verified, a reopened fix doesn't count as
solved, and the actor's own view is honest.
"""
from tests.conftest import auth
from tests.test_workflow import (  # noqa: F401 — fixtures
    teams, support, tester, tester2, developer, developer2, raised, handoff,
)


def contributions(client, token, user_id):
    return client.get(f"/users/{user_id}/contributions", headers=auth(token)).json()


def _run_to_resolved(client, support, tester, developer, ticket):
    """Push a raised ticket all the way to DONE: dev fixes, tester verifies,
    support closes."""
    handoff(client, tester["token"], ticket["id"], "forwarded",
            to_user_id=developer["id"], note="reproduced")
    handoff(client, developer["token"], ticket["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="added a null guard")
    handoff(client, tester["token"], ticket["id"], "verified_returned_to_reporter",
            note="confirmed fixed")
    r = handoff(client, support["token"], ticket["id"], "resolved", note="told the customer")
    assert r.json()["status"] == "done"


def test_a_resolved_fix_shows_under_fixed(client, support, tester, developer, raised):
    _run_to_resolved(client, support, tester, developer, raised)

    c = contributions(client, developer["token"], developer["id"])
    assert [t["key"] for t in c["fixed"]] == [raised["key"]]
    assert c["fixed_reopened"] == []
    # The developer did NOT verify it — that must not leak into their verified list.
    assert c["verified"] == []


def test_the_verifier_shows_under_verified_not_fixed(client, support, tester, developer, raised):
    """The whole point: 'I fixed it' and 'I tested it' are different, and the
    same ticket must not appear as both for the same person."""
    _run_to_resolved(client, support, tester, developer, raised)

    c = contributions(client, tester["token"], tester["id"])
    assert [t["key"] for t in c["verified"]] == [raised["key"]]
    assert c["fixed"] == []


def test_a_fix_that_was_reopened_is_not_counted_as_solved(
    client, support, tester, developer, raised
):
    """A fix that didn't hold hasn't solved anything — it moves to
    fixed_reopened rather than silently inflating the solved count."""
    _run_to_resolved(client, support, tester, developer, raised)
    # Customer comes back; Support reopens.
    handoff(client, support["token"], raised["id"], "reopened",
            to_user_id=tester["id"], note="still broken on Safari")

    c = contributions(client, developer["token"], developer["id"])
    assert c["fixed"] == []                                   # no longer "solved"
    assert [t["key"] for t in c["fixed_reopened"]] == [raised["key"]]  # but still visible


def test_a_developer_who_fixed_it_twice_counts_the_ticket_once(
    client, support, tester, developer, raised
):
    """Fix → still broken → fix again. Two fix handoffs, ONE ticket solved."""
    handoff(client, tester["token"], raised["id"], "forwarded",
            to_user_id=developer["id"], note="repro")
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="attempt 1")
    handoff(client, tester["token"], raised["id"], "returned_still_broken",
            to_user_id=developer["id"], note="nope")
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="attempt 2")
    handoff(client, tester["token"], raised["id"], "verified_returned_to_reporter", note="ok")
    handoff(client, support["token"], raised["id"], "resolved", note="done")

    c = contributions(client, developer["token"], developer["id"])
    assert len(c["fixed"]) == 1


def test_open_assigned_is_what_is_on_your_desk_now(client, support, tester, developer, raised):
    """The actionable list — assigned and not done."""
    # `raised` is currently sitting with the tester.
    c = contributions(client, tester["token"], tester["id"])
    assert [t["key"] for t in c["open_assigned"]] == [raised["key"]]
    assert c["workload"]["open_tickets"] == 1
    assert c["workload"]["band"] == "free"

    # Forward it away — no longer on the tester's desk.
    handoff(client, tester["token"], raised["id"], "forwarded",
            to_user_id=developer["id"], note="repro")
    c = contributions(client, tester["token"], tester["id"])
    assert c["open_assigned"] == []
    c = contributions(client, developer["token"], developer["id"])
    assert [t["key"] for t in c["open_assigned"]] == [raised["key"]]


def test_someone_with_no_contributions_gets_empty_lists_not_a_crash(client, admin):
    c = contributions(client, admin["token"], admin["id"])
    assert c["fixed"] == []
    assert c["verified"] == []
    assert c["open_assigned"] == []
    assert c["workload"]["open_tickets"] == 0


def test_open_assigned_excludes_subtasks(client, admin, dev, make_ticket):
    """A sub-task is counted under its parent, not as its own desk item."""
    parent = make_ticket(assignee_id=dev["id"])
    client.post(f"/tickets/{parent['id']}/subtasks",
                json={"title": "sub", "assignee_id": dev["id"]}, headers=auth(admin["token"]))

    c = contributions(client, dev["token"], dev["id"])
    assert [t["key"] for t in c["open_assigned"]] == [parent["key"]]


# ---------------------------------------------------------------- raised scoping

def test_raised_counts_only_workflow_tickets_not_board_authorship(
    client, support, tester, make_ticket
):
    """The audit bug: 'raised' counted every ticket where you were the author,
    sweeping in board cards you never routed anywhere."""
    # Support authors three board tickets (no routing) and raises one real bug.
    for i in range(3):
        make_ticket(title=f"Board card {i}", token=support["token"])
    client.post(
        "/tickets/",
        json={"title": "A real bug", "route_to_user_id": tester["id"]},
        headers=auth(support["token"]),
    )

    profile = client.get(f"/users/{support['id']}/workflow-profile",
                         headers=auth(support["token"])).json()
    # Only the routed one counts as "raised", not the three board cards.
    assert profile["involvement"]["raised"] == 1
