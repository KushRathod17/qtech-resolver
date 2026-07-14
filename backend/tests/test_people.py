"""
Adding people, workload bands, and the workflow profile.

The profile numbers are DERIVED from ticket_handoffs — there is no tracking
table to keep in sync. These tests are what proves the derivation is right,
because a wrong count still returns 200 and still renders.
"""
import pytest

from app import crud
from tests.conftest import auth, _register, _token
from tests.test_workflow import (  # noqa: F401 — fixtures
    teams, support, tester, tester2, developer, developer2, raised, handoff,
)


# ---------------------------------------------------------------- add a person

def test_admin_can_add_a_person_with_team_and_role(client, admin, teams):
    r = client.post(
        "/users/",
        json={
            "email": "newbie@qtechtest.io",
            "full_name": "Nina Newbie",
            "temp_password": "temporary123",
            "role": "developer",
            "team_id": teams["development"]["id"],
        },
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["full_name"] == "Nina Newbie"
    assert body["role"] == "developer"
    assert body["team_id"] == teams["development"]["id"]
    assert body["must_change_password"] is True


def test_the_new_account_can_log_in_immediately(client, admin):
    client.post(
        "/users/",
        json={"email": "n2@qtechtest.io", "full_name": "N Two", "temp_password": "temporary123"},
        headers=auth(admin["token"]),
    )
    r = client.post(
        "/auth/login",
        data={"username": "n2@qtechtest.io", "password": "temporary123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200


def test_a_temp_password_account_can_do_NOTHING_until_it_changes_it(client, admin):
    """The gate is server-side. A UI-only redirect would be theatre — the token
    works perfectly well against curl."""
    client.post(
        "/users/",
        json={"email": "n3@qtechtest.io", "full_name": "N Three", "temp_password": "temporary123"},
        headers=auth(admin["token"]),
    )
    token = _token(client, "n3@qtechtest.io", "temporary123")

    # Blocked everywhere...
    assert client.get("/tickets/", headers=auth(token)).status_code == 403
    assert client.get("/users/", headers=auth(token)).status_code == 403
    assert client.get("/teams/", headers=auth(token)).status_code == 403

    # ...except seeing who you are, and fixing the password.
    assert client.get("/auth/me", headers=auth(token)).status_code == 200

    r = client.post(
        "/users/me/password",
        json={"current_password": "temporary123", "new_password": "myrealpassword"},
        headers=auth(token),
    )
    assert r.status_code == 204

    # And now everything works.
    assert client.get("/tickets/", headers=auth(token)).status_code == 200
    assert client.get("/auth/me", headers=auth(token)).json()["must_change_password"] is False


def test_a_developer_cannot_add_people(client, dev):
    r = client.post(
        "/users/",
        json={"email": "x@qtechtest.io", "full_name": "X", "temp_password": "temporary123"},
        headers=auth(dev["token"]),
    )
    assert r.status_code == 403


def test_a_manager_cannot_mint_an_admin(client, manager):
    """Otherwise 'add person' is privilege escalation with extra steps."""
    r = client.post(
        "/users/",
        json={
            "email": "sneak@qtechtest.io", "full_name": "Sneak",
            "temp_password": "temporary123", "role": "admin",
        },
        headers=auth(manager["token"]),
    )
    assert r.status_code == 403

    # But a manager can add a normal developer.
    r = client.post(
        "/users/",
        json={"email": "ok@qtechtest.io", "full_name": "OK", "temp_password": "temporary123"},
        headers=auth(manager["token"]),
    )
    assert r.status_code == 201


def test_duplicate_email_is_rejected(client, admin):
    r = client.post(
        "/users/",
        json={"email": "admin@qtechtest.io", "full_name": "Clone", "temp_password": "temporary123"},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 400


def test_a_short_temp_password_is_rejected(client, admin):
    r = client.post(
        "/users/",
        json={"email": "s@qtechtest.io", "full_name": "S", "temp_password": "abc"},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- workload bands

@pytest.mark.parametrize(
    "open_count,expected",
    [(0, "free"), (2, "free"), (3, "moderate"), (5, "moderate"), (6, "busy"), (20, "busy")],
)
def test_the_band_thresholds(open_count, expected):
    assert crud.workload_band(open_count) == expected


def test_workload_counts_open_assigned_tickets(client, admin, dev, make_ticket):
    for i in range(3):
        make_ticket(title=f"Open {i}", assignee_id=dev["id"], status="todo")
    make_ticket(title="Closed", assignee_id=dev["id"], status="done")

    people = client.get("/users/", headers=auth(admin["token"])).json()
    row = next(u for u in people if u["id"] == dev["id"])

    assert row["open_tickets"] == 3          # the done one doesn't count
    assert row["band"] == "moderate"


def test_workload_ignores_subtasks(client, admin, dev, make_ticket):
    """A sub-task is work, but it's counted under its parent. Counting both
    would double-count the same job."""
    parent = make_ticket(title="Parent", assignee_id=dev["id"])
    client.post(
        f"/tickets/{parent['id']}/subtasks",
        json={"title": "Sub", "assignee_id": dev["id"]},
        headers=auth(admin["token"]),
    )
    people = client.get("/users/", headers=auth(admin["token"])).json()
    assert next(u for u in people if u["id"] == dev["id"])["open_tickets"] == 1


def test_the_person_picker_carries_workload(client, admin, tester, developer, make_ticket, teams):
    """This is the whole point: you see how buried someone is AT the moment you
    pick them."""
    for i in range(6):
        make_ticket(title=f"Load {i}", assignee_id=developer["id"])

    members = client.get(
        f"/teams/{teams['development']['id']}/members", headers=auth(admin["token"])
    ).json()
    dana = next(m for m in members if m["id"] == developer["id"])

    assert dana["open_tickets"] == 6
    assert dana["band"] == "busy"


# ---------------------------------------------------------------- profile

def test_profile_of_someone_with_no_history_is_zeros_not_a_crash(client, admin):
    """Admins with no handoffs get an honest empty profile."""
    r = client.get(f"/users/{admin['id']}/workflow-profile", headers=auth(admin["token"]))
    assert r.status_code == 200
    p = r.json()
    assert p["involvement"]["total_tickets"] == 0
    assert p["history"] == []
    assert p["current_workload"]["band"] == "free"


def test_profile_splits_involvement_by_the_part_they_played(
    client, support, tester, developer, raised
):
    """The derivation that avoids a tracking table: a handoff's `action` says
    WHY the ticket landed on someone, so a tester's first-pass work and their
    verification work separate on their own."""
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"], note="repro")
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="fixed")
    handoff(client, tester["token"], raised["id"], "verified_returned_to_reporter", note="good")

    # The tester: one first-pass test, one verification of a fix.
    p = client.get(f"/users/{tester['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["involvement"]["tested"] == 1
    assert p["involvement"]["verified"] == 1
    assert p["involvement"]["developed"] == 0
    assert p["involvement"]["raised"] == 0
    assert p["involvement"]["total_tickets"] == 1   # the same ticket, twice over

    # The developer: one fix.
    p = client.get(f"/users/{developer['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["involvement"]["developed"] == 1
    assert p["involvement"]["tested"] == 0

    # Support raised it, and it came back to them.
    p = client.get(f"/users/{support['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["involvement"]["raised"] == 1


def test_profile_history_lists_every_hat_they_wore(client, support, tester, developer, raised):
    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"], note="r")
    handoff(client, developer["token"], raised["id"], "fixed_returned_to_testing",
            to_user_id=tester["id"], note="f")

    p = client.get(f"/users/{tester['id']}/workflow-profile", headers=auth(support["token"])).json()
    row = p["history"][0]

    assert row["key"] == raised["key"]
    assert set(row["roles"]) == {"tester", "verifier"}   # both, on one ticket
    assert row["is_open"] is True


def test_profile_open_vs_completed(client, support, tester, raised):
    handoff(client, tester["token"], raised["id"], "returned_not_reproducible", note="nope")
    handoff(client, support["token"], raised["id"], "resolved")

    p = client.get(f"/users/{support['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["completed"] == 1
    assert p["still_open"] == 0
    assert p["history"][0]["is_open"] is False


def test_current_workload_is_what_is_on_their_desk_now(client, support, tester, developer, raised):
    """Not a lifetime tally — the number that decides who gets the next one."""
    p = client.get(f"/users/{tester['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["current_workload"]["open_tickets"] == 1   # holding the raised ticket
    assert p["current_workload"]["band"] == "free"

    handoff(client, tester["token"], raised["id"], "forwarded", to_user_id=developer["id"], note="r")

    # Handed on: it's no longer on the tester's desk, it's on the developer's.
    p = client.get(f"/users/{tester['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["current_workload"]["open_tickets"] == 0

    p = client.get(f"/users/{developer['id']}/workflow-profile", headers=auth(support["token"])).json()
    assert p["current_workload"]["open_tickets"] == 1


def test_everyone_gets_a_profile_including_admins(client, admin, dev, manager):
    for person in (admin, dev, manager):
        r = client.get(f"/users/{person['id']}/workflow-profile", headers=auth(admin["token"]))
        assert r.status_code == 200
        assert r.json()["user"]["id"] == person["id"]
