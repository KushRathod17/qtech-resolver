"""
The cases where a regression is a vulnerability rather than a bug.

Everything here failed, or could have failed, at some point during the build.
"""
from pathlib import Path

from tests.conftest import auth

ATTACHMENTS = Path(__file__).resolve().parent.parent / "uploads" / "attachments"


# ---------------------------------------------------------------- attachments

def test_a_malicious_filename_cannot_escape_the_upload_directory(client, admin, make_ticket):
    """The client's filename is a label, never a path. Without this, an upload
    named ../../../../x writes outside the upload directory."""
    t = make_ticket()
    r = client.post(
        f"/tickets/{t['id']}/attachments",
        files={"file": ("../../../../pwned.txt", b"payload", "text/plain")},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201

    stored = r.json()["url"].rsplit("/", 1)[-1]
    assert "/" not in stored and "\\" not in stored and ".." not in stored

    escaped = (ATTACHMENTS / ".." / ".." / ".." / ".." / "pwned.txt").resolve()
    assert not escaped.exists(), f"file escaped to {escaped}"
    assert (ATTACHMENTS / stored).is_file()

    client.delete(f"/tickets/{t['id']}/attachments/{r.json()['id']}", headers=auth(admin["token"]))


def test_an_empty_file_is_rejected(client, admin, make_ticket):
    t = make_ticket()
    r = client.post(
        f"/tickets/{t['id']}/attachments",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 400


def test_you_cannot_delete_someone_elses_attachment(client, dev, dev2, make_ticket):
    t = make_ticket(token=dev["token"])
    att = client.post(
        f"/tickets/{t['id']}/attachments",
        files={"file": ("mine.txt", b"mine", "text/plain")},
        headers=auth(dev["token"]),
    ).json()

    assert client.delete(
        f"/tickets/{t['id']}/attachments/{att['id']}", headers=auth(dev2["token"])
    ).status_code == 403

    assert client.delete(
        f"/tickets/{t['id']}/attachments/{att['id']}", headers=auth(dev["token"])
    ).status_code == 204


def test_deleting_an_attachment_removes_the_file_from_disk(client, admin, make_ticket):
    t = make_ticket()
    att = client.post(
        f"/tickets/{t['id']}/attachments",
        files={"file": ("bye.txt", b"bye", "text/plain")},
        headers=auth(admin["token"]),
    ).json()
    stored = ATTACHMENTS / att["url"].rsplit("/", 1)[-1]
    assert stored.is_file()

    client.delete(f"/tickets/{t['id']}/attachments/{att['id']}", headers=auth(admin["token"]))
    assert not stored.exists(), "row deleted but the file leaked on disk"


# ---------------------------------------------------------------- avatars

def test_avatar_upload_rejects_a_non_image_by_content_type(client, dev):
    """Checked by content type, not by trusting the file extension."""
    r = client.post(
        "/users/me/avatar",
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
        headers=auth(dev["token"]),
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- saved filters

def test_saved_filter_strips_unknown_keys(client, dev):
    """A saved filter is replayed straight into the board query, so an
    unbounded dict would let anything be smuggled through."""
    r = client.post(
        "/filters/",
        json={"name": "Junk", "query": {"priority": "high", "evil_key": "DROP TABLE"}},
        headers=auth(dev["token"]),
    )
    assert r.status_code == 201
    assert r.json()["query"] == {"priority": "high"}


def test_an_empty_saved_filter_is_rejected(client, dev):
    r = client.post("/filters/", json={"name": "Nothing", "query": {}}, headers=auth(dev["token"]))
    assert r.status_code == 400


def test_saved_filters_are_private(client, dev, dev2):
    mine = client.post(
        "/filters/",
        json={"name": "Mine", "query": {"priority": "highest"}},
        headers=auth(dev["token"]),
    ).json()

    theirs = client.get("/filters/", headers=auth(dev2["token"])).json()
    assert mine["id"] not in [f["id"] for f in theirs]

    # 404, not 403 — its existence isn't their business either.
    assert client.delete(f"/filters/{mine['id']}", headers=auth(dev2["token"])).status_code == 404


# ---------------------------------------------------------------- labels

def test_any_user_can_create_a_label(client, dev):
    """A support engineer mid-escalation shouldn't file a request to get
    'OTRAMS-Booking' added."""
    r = client.post(
        "/labels/", json={"name": "OTRAMS-Booking", "color": "#3E7BFA"}, headers=auth(dev["token"])
    )
    assert r.status_code == 201


def test_creating_a_duplicate_label_returns_the_existing_one(client, dev, label):
    """Two people triaging the same incident will both try to create it. That
    isn't an error worth showing anyone."""
    r = client.post(
        "/labels/", json={"name": "payments", "color": "#FF0000"}, headers=auth(dev["token"])
    )
    assert r.status_code == 201
    assert r.json()["id"] == label["id"]
    assert r.json()["color"] == label["color"]  # the original colour survives


def test_developers_cannot_delete_a_label(client, dev, label):
    """Deleting rewrites every ticket already carrying it."""
    r = client.delete(f"/labels/{label['id']}", headers=auth(dev["token"]))
    assert r.status_code == 403


def test_a_bad_hex_colour_is_rejected(client, dev):
    r = client.post("/labels/", json={"name": "Nope", "color": "red"}, headers=auth(dev["token"]))
    assert r.status_code == 422


# ---------------------------------------------------------------- watchers / mentions

def test_a_mention_makes_you_a_watcher(client, admin, dev, make_ticket):
    """A mention you don't follow is decoration — you'd never see the reply."""
    t = make_ticket()
    r = client.post(
        f"/tickets/{t['id']}/comments/",
        json={"body": f"@{dev['full_name']} can you look?", "mention_user_ids": [dev["id"]]},
        headers=auth(admin["token"]),
    )
    assert r.status_code == 201

    fresh = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert [w["id"] for w in fresh["watchers"]] == [dev["id"]]

    watching = client.get("/tickets/?watching=true", headers=auth(dev["token"])).json()
    assert [x["id"] for x in watching] == [t["id"]]


def test_mentioning_twice_does_not_duplicate_the_watcher(client, admin, dev, make_ticket):
    t = make_ticket()
    for _ in range(2):
        client.post(
            f"/tickets/{t['id']}/comments/",
            json={"body": "bump", "mention_user_ids": [dev["id"]]},
            headers=auth(admin["token"]),
        )
    fresh = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert len(fresh["watchers"]) == 1


def test_one_persons_watch_list_is_not_anothers(client, admin, dev, dev2, make_ticket):
    t = make_ticket()
    client.post(f"/tickets/{t['id']}/watch", headers=auth(dev["token"]))

    assert client.get("/tickets/?watching=true", headers=auth(dev["token"])).json() != []
    assert client.get("/tickets/?watching=true", headers=auth(dev2["token"])).json() == []


def test_a_comment_without_mentions_still_works(client, admin, make_ticket):
    """Backwards compatibility: mention_user_ids is optional."""
    t = make_ticket()
    r = client.post(
        f"/tickets/{t['id']}/comments/", json={"body": "plain"}, headers=auth(admin["token"])
    )
    assert r.status_code == 201


# The Components feature (and its /components/ endpoint) was removed in favor
# of a plain `product` string field on the ticket -- there's no create/delete
# lifecycle left to test here. See models.py's `product` column comment.
