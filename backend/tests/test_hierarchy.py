"""Epics, sub-tasks, and the rules that keep the ticket tree sane."""
from tests.conftest import auth


def test_subtask_inherits_its_parents_context(client, admin, component, make_ticket):
    """A sub-task nobody can be bothered to fill in is a sub-task that doesn't
    get filed — so it inherits rather than asking."""
    parent = make_ticket(component_id=component["id"], client_name="Kesari Tours", priority="highest")
    r = client.post(
        f"/tickets/{parent['id']}/subtasks",
        json={"title": "Write the migration"},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201
    st = r.json()

    assert st["ticket_type"] == "subtask"
    assert st["parent_id"] == parent["id"]
    assert st["component"]["name"] == "OTRAMS-Booking"
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


def test_an_epic_cannot_own_subtasks(client, admin, make_ticket):
    """Epics group tickets. That's a different relationship."""
    epic = make_ticket(ticket_type="epic")
    r = client.post(
        f"/tickets/{epic['id']}/subtasks", json={"title": "Nope"}, headers=auth(admin["token"])
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


# ---------------------------------------------------------------- epic progress

def test_epic_progress_prefers_points_over_ticket_count(client, admin, make_ticket):
    """A 13-point story finishing is more progress than a 1-point one, and a
    raw count hides that."""
    epic = make_ticket(title="Epic", ticket_type="epic")
    make_ticket(title="Big", epic_id=epic["id"], story_points=9, status="done")
    make_ticket(title="Small", epic_id=epic["id"], story_points=1, status="todo")

    fresh = client.get(f"/tickets/{epic['id']}", headers=auth(admin["token"])).json()
    p = fresh["progress"]

    assert p["done"] == 1 and p["total"] == 2
    assert p["points_done"] == 9 and p["points_total"] == 10
    assert p["percent"] == 90  # points, not the 50% a ticket count would give


def test_epic_with_no_children_is_zero_not_a_crash(client, admin, make_ticket):
    epic = make_ticket(ticket_type="epic")
    assert epic["progress"]["percent"] == 0
    assert epic["progress"]["total"] == 0


def test_a_non_epic_has_no_progress_block(client, admin, make_ticket):
    assert make_ticket(ticket_type="task")["progress"] is None


# ---------------------------------------------------------------- convert

def test_convert_to_epic_promotes_subtasks_rather_than_deleting_them(client, admin, make_ticket):
    """An epic can't own sub-tasks, and parent_id cascades on delete — so a
    naive conversion would silently destroy them."""
    parent = make_ticket(title="Grew too big")
    st = client.post(
        f"/tickets/{parent['id']}/subtasks", json={"title": "Survivor"}, headers=auth(admin["token"])
    ).json()

    converted = client.post(
        f"/tickets/{parent['id']}/convert-to-epic", headers=auth(admin["token"])
    ).json()
    assert converted["ticket_type"] == "epic"
    assert converted["subtasks"] == []

    everything = client.get("/tickets/?include_subtasks=true", headers=auth(admin["token"])).json()
    survivor = next(t for t in everything if t["key"] == st["key"])
    assert survivor["parent_id"] is None
    assert survivor["epic_id"] == converted["id"]
    assert survivor["ticket_type"] == "task"


def test_converting_an_epic_again_is_rejected(client, admin, make_ticket):
    epic = make_ticket(ticket_type="epic")
    r = client.post(f"/tickets/{epic['id']}/convert-to-epic", headers=auth(admin["token"]))
    assert r.status_code == 400
