"""
Notifications (audit item 5).

The feature that makes @mentions, watchers and handoffs actually mean something —
before this, all three added you to a list and then nothing told you.

The rules that matter and are easy to get wrong: never notify someone of their
OWN action, and never send two notifications for one event.
"""
from tests.conftest import auth
from tests.test_workflow import (  # noqa: F401 — fixtures
    teams, support, tester, tester2, developer, developer2, raised, handoff,
)


def notes(client, token):
    return client.get("/notifications/", headers=auth(token)).json()


def unread(client, token):
    return client.get("/notifications/unread-count", headers=auth(token)).json()["unread"]


# ---------------------------------------------------------------- assignment

def test_being_handed_a_ticket_notifies_you(client, support, tester, raised):
    """`raised` routes the ticket to the tester — they should hear about it."""
    n = notes(client, tester["token"])
    assert len(n) == 1
    assert n[0]["kind"] == "assigned"
    assert raised["key"] in n[0]["title"]
    assert n[0]["actor"]["full_name"] == "Sam Support"
    assert n[0]["ticket"]["key"] == raised["key"]
    assert n[0]["is_read"] is False


def test_you_are_never_notified_of_your_own_action(client, support, tester, raised):
    """Support raised it, so Support must not get 'you were handed a ticket'."""
    assert notes(client, support["token"]) == []


def test_a_handoff_notifies_the_new_assignee_and_the_watchers(
    client, support, tester, developer, raised
):
    # Support watches it (they'll want to know when it comes back). Then the
    # tester forwards it to the developer.
    client.post(f"/tickets/{raised['id']}/watch", headers=auth(support["token"]))
    handoff(client, tester["token"], raised["id"], "forwarded",
            to_user_id=developer["id"], note="reproduced")

    # Developer: the pointed "it's yours".
    dev_n = notes(client, developer["token"])
    assert any(x["kind"] == "assigned" and raised["key"] in x["title"] for x in dev_n)

    # Support (watcher, not the actor): the generic "it moved".
    sup_n = notes(client, support["token"])
    assert any(x["kind"] == "handoff" for x in sup_n)


def test_the_new_assignee_gets_ONE_notification_not_two(
    client, support, tester, developer, raised
):
    """They're now the assignee AND (if watching) a watcher. A handoff must not
    give them both the pointed 'assigned' and the generic 'handoff'."""
    client.post(f"/tickets/{raised['id']}/watch", headers=auth(developer["token"]))
    handoff(client, tester["token"], raised["id"], "forwarded",
            to_user_id=developer["id"], note="repro")

    dev_n = notes(client, developer["token"])
    for_this = [x for x in dev_n if x["ticket"] and x["ticket"]["key"] == raised["key"]]
    assert len(for_this) == 1
    assert for_this[0]["kind"] == "assigned"


def test_assigning_from_the_edit_form_also_notifies(client, admin, dev, make_ticket):
    """Direct assignment, no workflow involved."""
    t = make_ticket(title="Plain ticket")
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))

    n = notes(client, dev["token"])
    assert len(n) == 1
    assert n[0]["kind"] == "assigned"
    assert t["key"] in n[0]["title"]


# ---------------------------------------------------------------- comments

def test_a_mention_notifies_you(client, admin, dev, make_ticket):
    t = make_ticket()
    client.post(
        f"/tickets/{t['id']}/comments/",
        json={"body": f"@{dev['full_name']} take a look", "mention_user_ids": [dev["id"]]},
        headers=auth(admin["token"]),
    )
    n = notes(client, dev["token"])
    assert len(n) == 1
    assert n[0]["kind"] == "mentioned"
    assert "take a look" in n[0]["body"]


def test_a_comment_notifies_watchers_but_not_the_author(client, admin, dev, dev2, make_ticket):
    t = make_ticket()
    client.post(f"/tickets/{t['id']}/watch", headers=auth(dev["token"]))
    client.post(f"/tickets/{t['id']}/watch", headers=auth(dev2["token"]))

    # dev2 comments.
    client.post(f"/tickets/{t['id']}/comments/", json={"body": "an update"}, headers=auth(dev2["token"]))

    assert any(x["kind"] == "commented" for x in notes(client, dev["token"]))  # the other watcher
    assert notes(client, dev2["token"]) == []                                   # the author, silent


def test_a_mentioned_watcher_gets_the_mention_not_a_generic_comment(
    client, admin, dev, make_ticket
):
    """A mention outranks 'someone commented on a ticket you watch'. One
    notification, the pointed one."""
    t = make_ticket()
    client.post(f"/tickets/{t['id']}/watch", headers=auth(dev["token"]))

    client.post(
        f"/tickets/{t['id']}/comments/",
        json={"body": f"@{dev['full_name']} thoughts?", "mention_user_ids": [dev["id"]]},
        headers=auth(admin["token"]),
    )
    n = notes(client, dev["token"])
    assert len(n) == 1
    assert n[0]["kind"] == "mentioned"


# ---------------------------------------------------------------- read state

def test_unread_count_and_marking(client, admin, dev, make_ticket):
    t = make_ticket()
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))
    assert unread(client, dev["token"]) == 1

    nid = notes(client, dev["token"])[0]["id"]
    assert client.post(f"/notifications/{nid}/read", headers=auth(dev["token"])).status_code == 204
    assert unread(client, dev["token"]) == 0


def test_mark_all_read(client, admin, dev, make_ticket):
    for i in range(3):
        t = make_ticket(title=f"T{i}")
        client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))
    assert unread(client, dev["token"]) == 3

    r = client.post("/notifications/read-all", headers=auth(dev["token"]))
    assert r.json()["unread"] == 0
    assert unread(client, dev["token"]) == 0


def test_you_cannot_read_someone_elses_notification(client, admin, dev, dev2, make_ticket):
    t = make_ticket()
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))
    nid = notes(client, dev["token"])[0]["id"]

    # 404, not 403 — its existence isn't dev2's business.
    assert client.post(f"/notifications/{nid}/read", headers=auth(dev2["token"])).status_code == 404
    assert unread(client, dev["token"]) == 1  # untouched


def test_notifications_are_private_to_their_recipient(client, admin, dev, make_ticket):
    t = make_ticket()
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))

    assert len(notes(client, dev["token"])) == 1
    assert notes(client, admin["token"]) == []   # the actor sees nothing


def test_the_notification_is_a_snapshot_and_survives_a_retitle(
    client, admin, dev, make_ticket
):
    """Denormalised on purpose: the title is what was true when it happened."""
    t = make_ticket(title="Original")
    client.patch(f"/tickets/{t['id']}", json={"assignee_id": dev["id"]}, headers=auth(admin["token"]))
    original_title = notes(client, dev["token"])[0]["title"]

    client.patch(f"/tickets/{t['id']}", json={"title": "Renamed entirely"}, headers=auth(admin["token"]))

    # The notification still says what it said; only the LINK follows the ticket.
    n = notes(client, dev["token"])[0]
    assert n["title"] == original_title
    assert n["ticket"]["title"] == "Renamed entirely"
