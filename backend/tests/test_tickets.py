"""Ticket CRUD, drag-and-drop ranking, filters, and bulk actions."""
from tests.conftest import auth


def test_ticket_keys_are_sequential(client, admin, make_ticket):
    a = make_ticket(title="First")
    b = make_ticket(title="Second")
    assert a["key"] == "QTR-1"
    assert b["key"] == "QTR-2"


def test_ticket_carries_nested_assignee_and_labels(client, admin, dev, label, make_ticket):
    t = make_ticket(assignee_id=dev["id"], label_ids=[label["id"]])
    assert t["assignee"]["full_name"] == "Dev Developer"
    assert t["reporter"]["full_name"] == "Ada Admin"
    assert [l["name"] for l in t["labels"]] == ["Payments"]


def test_new_tickets_land_at_the_top_of_their_column(client, admin, make_ticket):
    first = make_ticket(title="Older")
    second = make_ticket(title="Newer")
    assert second["rank"] < first["rank"]


# ---------------------------------------------------------------- move / rank

def test_move_between_columns_changes_status(client, admin, make_ticket):
    t = make_ticket(status="todo")
    r = client.patch(
        f"/tickets/{t['id']}/move", json={"status": "in_progress"}, headers=auth(admin["token"])
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_move_between_two_neighbours_interpolates_the_rank(client, admin, make_ticket):
    """The whole point of float ranks: a reorder writes ONE row instead of
    renumbering the column."""
    top = make_ticket(title="Top", status="todo")
    bottom = make_ticket(title="Bottom", status="todo")
    mover = make_ticket(title="Mover", status="done")

    # Put them in a known order: top above bottom.
    if top["rank"] > bottom["rank"]:
        top, bottom = bottom, top

    r = client.patch(
        f"/tickets/{mover['id']}/move",
        json={"status": "todo", "before_id": top["id"], "after_id": bottom["id"]},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 200
    moved = r.json()
    assert top["rank"] < moved["rank"] < bottom["rank"]


def test_move_into_an_empty_column(client, admin, make_ticket):
    t = make_ticket(status="todo")
    r = client.patch(
        f"/tickets/{t['id']}/move",
        json={"status": "code_review", "before_id": None, "after_id": None},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "code_review"


def test_moving_to_done_stamps_resolved_at(client, admin, make_ticket):
    t = make_ticket(status="todo")
    r = client.patch(f"/tickets/{t['id']}/move", json={"status": "done"}, headers=auth(admin["token"]))
    assert r.json()["resolved_at"] is not None


# ---------------------------------------------------------------- filters

def test_search_matches_description_not_just_title(client, admin, make_ticket):
    make_ticket(title="Nothing special", description="trivially brute-forceable")
    r = client.get("/tickets/?search=brute", headers=auth(admin["token"]))
    assert len(r.json()) == 1


def test_search_matches_the_ticket_number(client, admin, make_ticket):
    make_ticket(title="Alpha")
    t = make_ticket(title="Beta")
    r = client.get(f"/tickets/?search={t['key']}", headers=auth(admin["token"]))
    assert [x["key"] for x in r.json()] == [t["key"]]


def test_filter_by_status_and_priority(client, admin, make_ticket):
    make_ticket(title="A", status="todo", priority="highest")
    make_ticket(title="B", status="done", priority="low")

    todo = client.get("/tickets/?status=todo", headers=auth(admin["token"])).json()
    assert [t["title"] for t in todo] == ["A"]

    low = client.get("/tickets/?priority=low", headers=auth(admin["token"])).json()
    assert [t["title"] for t in low] == ["B"]


def test_filter_by_label(client, admin, label, make_ticket):
    make_ticket(title="Tagged", label_ids=[label["id"]])
    make_ticket(title="Untagged")
    r = client.get(f"/tickets/?label_id={label['id']}", headers=auth(admin["token"]))
    assert [t["title"] for t in r.json()] == ["Tagged"]


# ---------------------------------------------------------------- activity log

def test_every_field_change_is_logged(client, admin, dev, make_ticket):
    """The old version only logged status/assignee/priority/points — editing a
    title vanished from the history entirely."""
    t = make_ticket(title="Before")
    client.patch(
        f"/tickets/{t['id']}",
        json={"title": "After", "client_name": "Kesari Tours", "priority": "highest"},
        headers=auth(admin["token"]),
    )
    acts = client.get(f"/tickets/{t['id']}/activity", headers=auth(admin["token"])).json()
    actions = {a["action"] for a in acts}
    assert "title_changed" in actions
    assert "client_changed" in actions
    assert "priority_changed" in actions


def test_activity_names_the_assignee_not_a_uuid(client, admin, dev, make_ticket):
    t = make_ticket()
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))
    acts = client.get(f"/tickets/{t['id']}/activity", headers=auth(admin["token"])).json()
    assigned = next(a for a in acts if a["action"] == "assignee_changed")
    assert "Dev Developer" in assigned["details"]


# ---------------------------------------------------------------- permissions

def test_developers_cannot_delete_a_ticket(client, dev, make_ticket):
    t = make_ticket()
    r = client.delete(f"/tickets/{t['id']}", headers=auth(dev["token"]))
    assert r.status_code == 403


def test_managers_can_delete_a_ticket(client, manager, make_ticket):
    t = make_ticket()
    r = client.delete(f"/tickets/{t['id']}", headers=auth(manager["token"]))
    assert r.status_code == 204


# ---------------------------------------------------------------- bulk

def test_bulk_update_applies_to_everything_selected(client, admin, dev, make_ticket):
    ids = [make_ticket(title=f"T{i}", status="backlog")["id"] for i in range(3)]
    r = client.patch(
        "/tickets/bulk",
        json={"ticket_ids": ids, "status": "todo", "priority": "high", "assignee_id": dev["id"]},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 200
    updated = r.json()
    assert len(updated) == 3
    assert all(t["status"] == "todo" and t["priority"] == "high" for t in updated)
    assert all(t["assignee"]["id"] == dev["id"] for t in updated)


def test_bulk_status_move_gives_each_ticket_a_distinct_rank(client, admin, make_ticket):
    """Otherwise the whole batch collides on one rank and the order is arbitrary."""
    ids = [make_ticket(title=f"T{i}", status="backlog")["id"] for i in range(3)]
    r = client.patch(
        "/tickets/bulk", json={"ticket_ids": ids, "status": "todo"}, headers=auth(admin["token"])
    )
    ranks = [t["rank"] for t in r.json()]
    assert len(set(ranks)) == len(ranks)


def test_bulk_labels_are_additive_not_a_replacement(client, admin, dev, label, make_ticket):
    """On a bulk edit you mean 'also tag these Payments', not 'make Payments
    their only label'."""
    other = client.post(
        "/labels/", json={"name": "Urgent", "color": "#EF4444"}, headers=auth(dev["token"])
    ).json()
    t = make_ticket(label_ids=[other["id"]])

    r = client.patch(
        "/tickets/bulk",
        json={"ticket_ids": [t["id"]], "add_label_ids": [label["id"]]},
        headers=auth(admin["token"]),
    )
    names = {l["name"] for l in r.json()[0]["labels"]}
    assert names == {"Urgent", "Payments"}


def test_bulk_clear_assignee(client, admin, dev, make_ticket):
    t = make_ticket(assignee_id=dev["id"])
    r = client.patch(
        "/tickets/bulk",
        json={"ticket_ids": [t["id"]], "clear_assignee": True},
        headers=auth(admin["token"]),
    )
    assert r.json()[0]["assignee"] is None


def test_bulk_rejects_an_empty_selection(client, admin):
    r = client.patch("/tickets/bulk", json={"ticket_ids": []}, headers=auth(admin["token"]))
    assert r.status_code == 422


def test_bulk_delete_is_privileged(client, dev, admin, make_ticket):
    t = make_ticket()
    assert client.post(
        "/tickets/bulk/delete", json={"ticket_ids": [t["id"]]}, headers=auth(dev["token"])
    ).status_code == 403
    assert client.post(
        "/tickets/bulk/delete", json={"ticket_ids": [t["id"]]}, headers=auth(admin["token"])
    ).status_code == 200


def test_duplicate_copies_fields_but_not_history(client, admin, label, make_ticket):
    """A duplicate is a NEW report of the same problem, not a clone of how far
    the original got."""
    t = make_ticket(title="AMEX bug", status="done", label_ids=[label["id"]], story_points=5)
    r = client.post(f"/tickets/{t['id']}/duplicate", headers=auth(admin["token"]))
    assert r.status_code == 201
    copy = r.json()

    assert copy["title"] == "AMEX bug (copy)"
    assert copy["key"] != t["key"]
    assert copy["story_points"] == 5
    assert [l["name"] for l in copy["labels"]] == ["Payments"]
    assert copy["status"] == "todo"        # not "done"
    assert copy["resolved_at"] is None
