"""
SLA clocks.

The SLA is DERIVED on every read, never stored. These tests exist because the
failure mode is silent: a wrong clock still returns 200 and still renders.
"""
from datetime import datetime, timedelta

import pytest

from app import models
from tests.conftest import auth


def age_ticket(db, ticket_id, hours):
    """Backdate created_at so the clock has actually run."""
    t = db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()
    t.created_at = datetime.utcnow() - timedelta(hours=hours)
    db.commit()


def test_priority_without_a_policy_has_no_sla(client, admin, make_ticket):
    """Only the top two priorities are tracked. A team that puts an SLA on
    'lowest' ends up ignoring all of them."""
    t = make_ticket(priority="low")
    assert t["sla"] is None


def test_highest_priority_has_a_four_hour_target(client, admin, make_ticket):
    t = make_ticket(priority="highest")
    assert t["sla"]["threshold_hours"] == 4
    assert t["sla"]["breached"] is False


def test_a_ticket_past_its_target_is_breached(client, admin, db, make_ticket):
    t = make_ticket(priority="highest")  # 4h target
    age_ticket(db, t["id"], hours=9)

    fresh = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert fresh["sla"]["breached"] is True
    assert fresh["sla"]["remaining_seconds"] < 0


def test_a_ticket_inside_its_target_is_not_breached(client, admin, db, make_ticket):
    t = make_ticket(priority="high")  # 8h target
    age_ticket(db, t["id"], hours=7)

    fresh = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert fresh["sla"]["breached"] is False
    assert 0 < fresh["sla"]["remaining_seconds"] < 3700  # under an hour left


def test_resolving_freezes_the_clock(client, admin, db, make_ticket):
    """The bug this guards against: a ticket closed comfortably inside its
    window keeps ageing against `now` and eventually reports as breached
    forever.

    So: a ticket raised 10 days ago and resolved 1 hour later, against a 4h
    target, MET its SLA — even though 10 days of wall-clock time have since
    passed. If the clock measured to `now` instead of to `resolved_at`, this
    would read as breached by 240 hours.
    """
    t = make_ticket(priority="highest")  # 4h target
    client.patch(f"/tickets/{t['id']}", json={"status": "done"}, headers=auth(admin["token"]))

    row = db.query(models.Ticket).filter(models.Ticket.id == t["id"]).first()
    row.created_at = datetime.utcnow() - timedelta(days=10)
    row.resolved_at = row.created_at + timedelta(hours=1)  # closed within the window
    db.commit()

    later = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert later["sla"]["stopped"] is True
    assert later["sla"]["breached"] is False, "the clock kept running after resolution"
    # Elapsed is creation -> resolution (1h), not creation -> now (10 days).
    assert abs(later["sla"]["elapsed_seconds"] - 3600) < 5


def test_a_ticket_resolved_too_late_still_reports_as_missed(client, admin, db, make_ticket):
    """Freezing the clock must not turn a genuine miss into a pass."""
    t = make_ticket(priority="highest")  # 4h target
    client.patch(f"/tickets/{t['id']}", json={"status": "done"}, headers=auth(admin["token"]))

    row = db.query(models.Ticket).filter(models.Ticket.id == t["id"]).first()
    row.created_at = datetime.utcnow() - timedelta(days=10)
    row.resolved_at = row.created_at + timedelta(hours=9)  # took 9h against a 4h target
    db.commit()

    later = client.get(f"/tickets/{t['id']}", headers=auth(admin["token"])).json()
    assert later["sla"]["stopped"] is True
    assert later["sla"]["breached"] is True


def test_reopening_restarts_the_clock(client, admin, make_ticket):
    t = make_ticket(priority="highest")
    client.patch(f"/tickets/{t['id']}", json={"status": "done"}, headers=auth(admin["token"]))

    reopened = client.patch(
        f"/tickets/{t['id']}", json={"status": "in_progress"}, headers=auth(admin["token"])
    ).json()
    assert reopened["resolved_at"] is None
    assert reopened["sla"]["stopped"] is False


@pytest.mark.parametrize("route", ["edit", "drag", "bulk"])
def test_every_path_to_done_stops_the_clock(client, admin, make_ticket, route):
    """The clock must not depend on HOW you closed the ticket."""
    t = make_ticket(priority="highest")
    headers = auth(admin["token"])

    if route == "edit":
        r = client.patch(f"/tickets/{t['id']}", json={"status": "done"}, headers=headers)
        body = r.json()
    elif route == "drag":
        r = client.patch(f"/tickets/{t['id']}/move", json={"status": "done"}, headers=headers)
        body = r.json()
    else:
        r = client.patch(
            "/tickets/bulk", json={"ticket_ids": [t["id"]], "status": "done"}, headers=headers
        )
        body = r.json()[0]

    assert body["resolved_at"] is not None, f"{route} did not stamp resolved_at"
    assert body["sla"]["stopped"] is True, f"{route} did not stop the clock"


def test_breached_filter(client, admin, db, make_ticket):
    late = make_ticket(title="Late", priority="highest")
    make_ticket(title="On time", priority="highest")
    age_ticket(db, late["id"], hours=9)

    breached = client.get("/tickets/?breached=true", headers=auth(admin["token"])).json()
    assert [t["title"] for t in breached] == ["Late"]

    fine = client.get("/tickets/?breached=false", headers=auth(admin["token"])).json()
    assert "Late" not in [t["title"] for t in fine]


def test_sla_targets_are_configurable(client, manager, admin, make_ticket):
    """'Critical' means 4 hours to one team and 1 hour to another."""
    r = client.patch("/sla/highest", json={"threshold_hours": 1}, headers=auth(manager["token"]))
    assert r.status_code == 200

    t = make_ticket(priority="highest")
    assert t["sla"]["threshold_hours"] == 1


def test_an_sla_can_be_switched_off(client, manager, admin, make_ticket):
    client.patch("/sla/highest", json={"threshold_hours": None}, headers=auth(manager["token"]))
    t = make_ticket(priority="highest")
    assert t["sla"] is None


def test_developers_cannot_change_sla_targets(client, dev):
    r = client.patch("/sla/highest", json={"threshold_hours": 999}, headers=auth(dev["token"]))
    assert r.status_code == 403
