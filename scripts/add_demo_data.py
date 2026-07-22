"""
Adds a richer, CONNECTED set of demo data to your LIVE QTech Resolver org --
purely additively, through the same public API the app itself uses, never
touching the database directly. Nothing existing is modified or deleted.

Unlike a flat list of unrelated tickets, this builds a small web of things
that actually reference each other, so teammates can see how the pieces of
the app connect:

  - A sprint ("Sample Sprint 1"), with several tickets pulled into it.
  - 3 demo labels, reused across tickets.
  - A HUB ticket ("Sample: Checkout & Payments Overhaul") with 3 other tickets
    linked underneath it via parent_ticket_id -- open the hub and you'll see
    them listed; open one of the children and you'll see the hub referenced
    back.
  - A SUBTASK under one of those children, showing the parent/subtask
    relationship (distinct from the hub/linked-ticket relationship above).
  - Comments on two tickets, showing the discussion thread.
  - If your org already has teams set up (Contact/Support, Testing/QA,
    Development) with at least one person on Testing/QA, one ticket is routed
    straight into the cross-team workflow at creation time -- so teammates can
    see a ticket that's actually "with" a team, not just sitting on the board.
    This step is skipped cleanly if no such team/member exists yet; it's a
    bonus, not a requirement.

Every ticket and label is titled/named with a "Sample" prefix specifically so
it's trivially easy to find and bulk-delete later (Issues page -> search
"Sample:" -> select all -> delete; Settings for labels/sprints).

This is NOT the same thing as backend/seed.py -- that one drops and rebuilds
the whole database and must only ever be pointed at a local dev database.
This script only ever ADDS things over the network, as your own admin
account, exactly like clicking around the UI yourself.

Usage:
    cd scripts
    pip install requests --break-system-packages   # if you don't have it
    python add_demo_data.py

You'll be prompted for your admin email and password interactively -- this
script never stores them anywhere, and they're typed straight into your own
terminal, not shared with anyone else.
"""
import getpass
import sys
from datetime import date, timedelta

import requests

API_BASE = "https://qtech-resolver-backend.onrender.com"


def login():
    email = input("Admin email: ").strip()
    password = getpass.getpass("Password: ")
    r = requests.post(
        f"{API_BASE}/auth/login",
        data={"username": email, "password": password},
    )
    if r.status_code != 200:
        print(f"Login failed ({r.status_code}): {r.text}")
        sys.exit(1)
    return r.json()["access_token"]


def api(method, path, token, ok=(200, 201), **kwargs):
    r = requests.request(
        method, f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
    )
    if r.status_code not in ok:
        print(f"  ! {method} {path} -> {r.status_code}: {r.text}")
        return None
    return r.json() if r.text else True


def main():
    print(f"Adding connected demo data to {API_BASE}\n")
    token = login()
    print("\nLogged in.\n")

    today = date.today()

    # ---------- Labels ----------
    print("Creating labels...")
    label_specs = [
        ("Sample: Payments", "#10B981"),
        ("Sample: Infrastructure", "#3B82F6"),
        ("Sample: Design", "#EC4899"),
    ]
    labels = {}
    for name, color in label_specs:
        lbl = api("POST", "/labels/", token, json={"name": name, "color": color})
        if lbl:
            labels[name] = lbl["id"]
            print(f"  label: {name}")

    # ---------- Sprint ----------
    print("\nCreating a sprint...")
    sprint = api("POST", "/sprints/", token, json={
        "name": "Sample Sprint 1",
        "goal": "Demo sprint -- ship the new checkout flow and clear the auth backlog.",
        "state": "active",
        "start_date": (today - timedelta(days=4)).isoformat(),
        "end_date": (today + timedelta(days=10)).isoformat(),
    })
    sprint_id = sprint["id"] if sprint else None
    if sprint:
        print(f"  sprint: {sprint['name']}")

    # ---------- Optional: find a Testing/QA team + member for a live workflow example ----------
    route_to_user_id = None
    teams = api("GET", "/teams/", token) or []
    testing_team = next((t for t in teams if t["kind"] == "testing"), None)
    if testing_team:
        members = api("GET", f"/teams/{testing_team['id']}/members", token) or []
        if members:
            route_to_user_id = members[0]["id"]
            print(f"\nFound a Testing/QA team member ({members[0]['full_name']}) -- "
                  f"one ticket will be routed into the live workflow.")
    if not route_to_user_id:
        print("\nNo Testing/QA team member found -- skipping the workflow-routing example "
              "(everything else still gets created normally).")

    # ---------- The hub ticket everything else links under ----------
    print("\nCreating the hub ticket...")
    hub = api("POST", "/tickets/", token, json={
        "title": "Sample: Checkout & Payments Overhaul",
        "description": "Umbrella ticket for the demo payments work -- open this to see the "
                        "3 tickets linked underneath it.",
        "ticket_type": "task",
        "status": "in_progress",
        "priority": "high",
        "label_ids": [labels.get("Sample: Payments")] if labels.get("Sample: Payments") else [],
        "sprint_id": sprint_id,
    })
    if not hub:
        print("Couldn't create the hub ticket -- stopping.")
        return
    print(f"  hub: {hub['key']}  {hub['title']}")

    # ---------- Children linked under the hub ----------
    print("\nCreating tickets linked under the hub...")
    child_specs = [
        {
            "title": "Sample: Add Apple Pay to checkout",
            "description": "Shoppers drop off at the card form. Apple Pay should cut a step.",
            "ticket_type": "task", "status": "todo", "priority": "high", "estimated_hours": 5,
            "label_ids": [labels.get("Sample: Payments")] if labels.get("Sample: Payments") else [],
            "sprint_id": sprint_id,
            "parent_ticket_id": hub["id"],
            **({"route_to_user_id": route_to_user_id, "route_note": "Ready for a first pass."}
               if route_to_user_id else {}),
        },
        {
            "title": "Sample: Card form rejects valid AMEX numbers",
            "description": "15-digit AMEX fails Luhn check. Regression from a recent release.",
            "ticket_type": "bug", "status": "in_progress", "priority": "highest", "estimated_hours": 3,
            "steps_to_reproduce": "1. Go to checkout\n2. Enter a valid 15-digit AMEX\n3. Submit",
            "expected_behavior": "Payment succeeds.",
            "actual_behavior": "Form shows 'Invalid card number'.",
            "label_ids": [labels.get("Sample: Payments")] if labels.get("Sample: Payments") else [],
            "sprint_id": sprint_id,
            "parent_ticket_id": hub["id"],
        },
        {
            "title": "Sample: Redesign the empty-checkout state",
            "description": "Right now an empty cart is just a blank page -- no guidance back to the catalog.",
            "ticket_type": "task", "status": "code_review", "priority": "low", "estimated_hours": 3,
            "label_ids": [labels.get("Sample: Design")] if labels.get("Sample: Design") else [],
            "parent_ticket_id": hub["id"],
        },
    ]
    children = []
    for spec in child_specs:
        t = api("POST", "/tickets/", token, json=spec)
        if t:
            children.append(t)
            note = " (routed into workflow)" if spec.get("route_to_user_id") else ""
            print(f"  {t['key']:<8} {t['status']:<12} {t['title']}{note}")

    # ---------- A subtask under one of the children ----------
    if children:
        print("\nAdding a subtask...")
        parent_for_subtask = children[0]
        st = api("POST", f"/tickets/{parent_for_subtask['id']}/subtasks", token, json={
            "title": "Sample: Write the Apple Pay integration tests",
        })
        if st:
            print(f"  subtask {st['key']} under {parent_for_subtask['key']}")

    # ---------- Standalone tickets, for variety across the rest of the board ----------
    print("\nCreating a few standalone tickets for board variety...")
    standalone_specs = [
        {
            "title": "Sample: Migrate session store to Redis",
            "description": "In-memory sessions die on every deploy.",
            "ticket_type": "task", "status": "in_progress", "priority": "medium", "estimated_hours": 8,
            "label_ids": [labels.get("Sample: Infrastructure")] if labels.get("Sample: Infrastructure") else [],
        },
        {
            "title": "Sample: Rate-limit the login endpoint",
            "description": "No throttling on failed logins -- already fixed, kept here as a done example.",
            "ticket_type": "task", "status": "done", "priority": "high", "estimated_hours": 5,
            "label_ids": [labels.get("Sample: Infrastructure")] if labels.get("Sample: Infrastructure") else [],
        },
        {
            "title": "Sample: Bulk-select tickets on the board",
            "description": "Shift-click to multi-select, then bulk change status.",
            "ticket_type": "task", "status": "backlog", "priority": "low", "estimated_hours": 8,
            "label_ids": [labels.get("Sample: Design")] if labels.get("Sample: Design") else [],
        },
    ]
    standalones = []
    for spec in standalone_specs:
        t = api("POST", "/tickets/", token, json=spec)
        if t:
            standalones.append(t)
            print(f"  {t['key']:<8} {t['status']:<12} {t['title']}")

    # ---------- Comments, so the discussion thread isn't empty ----------
    print("\nAdding comments...")
    comment_targets = [
        (hub, "Kicking this off -- linked tickets below cover the checkout work for this sprint."),
    ]
    if children:
        comment_targets.append(
            (children[0], "Started on this. Apple Pay JS SDK is in, working through the button states now.")
        )
    for ticket, body in comment_targets:
        c = api("POST", f"/tickets/{ticket['id']}/comments/", token, json={"body": body})
        if c:
            print(f"  comment on {ticket['key']}")

    total = 1 + len(children) + len(standalones) + (1 if children else 0)
    print(f"\nDone -- created 1 hub, {len(children)} linked children, "
          f"{'1 subtask, ' if children else ''}{len(standalones)} standalone tickets, "
          f"{len(labels)} labels, and 1 sprint.")
    print("Everything is titled/named with a 'Sample' prefix, so you can find and clean it")
    print("up later: Issues page -> search 'Sample:' -> select all -> Delete. Labels and the")
    print("sprint can be removed from Settings / the Sprints page the same way.")


if __name__ == "__main__":
    main()
