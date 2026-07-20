"""Epics, sub-tasks, and the rules that keep the ticket tree sane."""
from tests.conftest import auth


def test_subtask_inherits_its_parents_context(client, admin, make_ticket):
    """A sub-task nobody can be bothered to fill in is a sub-task that doesn't
    get filed — so it inherits rather than asking."""
    parent = make_ticket(product="OTRAMS-Booking", client_name="Kesari Tours", priority="highest")
    r = client.post(
        f"/tickets/{parent['id']}/subtasks",
        json={"title": "Write the migration"},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201
    st = r.json()

    assert st["ticket_type"] == "subtask"
    assert st["parent_id"] == parent["id"]
    assert st["product"] == "OTRAMS-Booking"
    assert st["client_name"] == "Kesari Tours"
    assert st["priority"] == "highest"


def test_subtasks_are_hidden_from_the_board(client, admin, make_ticket):
    """Showing them as loose cards would double-count the work."""
    parent = make_ticket()
    client.post(
        f"/tickets/{parent['id']}/subtasks", json={"title": "Sub"}, headers=auth(admin["token"])
    )

    board = client.get("/tickets/", headers=auth(admin["token"])).json()
    assert [t["key"] for t in board] == [parent["key"]]

    everything = client.get("/tickets/?include_subtasks=true", headers=auth(admin["token"])).json()
    assert len(everything) == 2


def test_parent_carries_its_subtasks(client, admin, make_ticket):
    parent = make_ticket()
    for title in ("One", "Two"):
        client.post(
            f"/tickets/{parent['id']}/subtasks", json={"title": title}, headers=auth(admin["token"])
        )
    fresh = client.get(f"/tickets/{parent['id']}", headers=auth(admin["token"])).json()
    assert {s["title"] for s in fresh["subtasks"]} == {"One", "Two"}


def test_a_subtask_cannot_have_subtasks(client, admin, make_ticket):
    parent = make_ticket()
    st = client.post(
        f"/tickets/{parent['id']}/subtasks", json={"title": "Sub"}, headers=auth(admin["token"])
    ).json()

    r = client.post(
        f"/tickets/{st['id']}/subtasks", json={"title": "Nope"}, headers=auth(admin["token"])
    )
    assert r.status_code == 400


def test_deleting_a_parent_cascades_to_its_subtasks(client, admin, make_ticket):
    parent = make_ticket()
    client.post(
        f"/tickets/{parent['id']}/subtasks", json={"title": "Sub"}, headers=auth(admin["token"])
    )
    client.delete(f"/tickets/{parent['id']}", headers=auth(admin["token"]))

    everything = client.get("/tickets/?include_subtasks=true", headers=auth(admin["token"])).json()
    assert everything == []


# The Epic feature (progress rollups, /convert-to-epic, epics blocking their
# own subtasks) was deliberately replaced by Parent Tags -- see the TicketType
# enum comment in models.py ("the one epic became a parent tag"). TicketType.EPIC
# stays in the enum only so old rows keep parsing; nothing new creates one, and
# the progress block / convert route were removed along with the rest of the
# feature. NOTE: Parent Tags itself has no test coverage yet -- worth adding,
# but that's new coverage to write, not a regression in what used to be tested
# here.
