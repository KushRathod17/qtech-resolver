"""
Adds a handful of realistic-looking sample tickets to your LIVE QTech Resolver
org, purely additively -- through the same public API the app itself uses,
never touching the database directly. Nothing existing is modified or deleted.

Every ticket this creates is titled with a "Sample: " prefix specifically so
it's trivially easy to find and bulk-delete later from the Issues page (search
"Sample:", select all, delete) once your teammates don't need it anymore.

This is NOT the same thing as backend/seed.py -- that one drops and rebuilds
the whole database and must only ever be pointed at a local dev database.
This script only ever ADDS a few tickets over the network, as your own admin
account, exactly like clicking "New ticket" in the UI several times.

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


def api(method, path, token, **kwargs):
    r = requests.request(
        method, f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs
    )
    if r.status_code >= 400:
        print(f"  ! {method} {path} -> {r.status_code}: {r.text}")
        return None
    return r.json() if r.text else None


# Demo tickets spanning every status/priority/type so teammates see the full
# range of what the board and reports can show -- not just a wall of "To Do".
DEMO_TICKETS = [
    {
        "title": "Sample: Add Apple Pay to checkout",
        "description": "Shoppers drop off at the card form. Apple Pay should cut a step.",
        "ticket_type": "task", "status": "todo", "priority": "high", "story_points": 5,
    },
    {
        "title": "Sample: Card form rejects valid AMEX numbers",
        "description": "15-digit AMEX fails Luhn check. Regression from a recent release.",
        "ticket_type": "bug", "status": "in_progress", "priority": "high", "story_points": 3,
        "steps_to_reproduce": "1. Go to checkout\n2. Enter a valid 15-digit AMEX\n3. Submit",
        "expected_behavior": "Payment succeeds.",
        "actual_behavior": "Form shows 'Invalid card number'.",
    },
    {
        "title": "Sample: Migrate session store to Redis",
        "description": "In-memory sessions die on every deploy.",
        "ticket_type": "task", "status": "in_progress", "priority": "medium", "story_points": 8,
    },
    {
        "title": "Sample: Password reset email never arrives",
        "description": "SMTP creds expired in staging.",
        "ticket_type": "bug", "status": "code_review", "priority": "high", "story_points": 2,
        "steps_to_reproduce": "1. Click 'Forgot password'\n2. Enter email\n3. Check inbox",
        "expected_behavior": "Reset email arrives within a minute.",
        "actual_behavior": "No email ever arrives.",
    },
    {
        "title": "Sample: Redesign the empty-board state",
        "description": "Right now a new board is just a blank grid -- no guidance for a new user.",
        "ticket_type": "task", "status": "code_review", "priority": "low", "story_points": 3,
    },
    {
        "title": "Sample: Rate-limit the login endpoint",
        "description": "No throttling on failed logins -- already fixed, kept here as a done example.",
        "ticket_type": "task", "status": "done", "priority": "high", "story_points": 5,
    },
    {
        "title": "Sample: Bulk-select tickets on the board",
        "description": "Shift-click to multi-select, then bulk change status.",
        "ticket_type": "task", "status": "backlog", "priority": "low", "story_points": 8,
    },
    {
        "title": "Sample: Investigate slow board load with 500+ tickets",
        "description": "Board takes ~4s to paint once a project has a lot of history.",
        "ticket_type": "bug", "status": "backlog", "priority": "medium", "story_points": 5,
        "steps_to_reproduce": "1. Open a board with 500+ tickets\n2. Time the initial paint",
        "expected_behavior": "Loads in well under a second.",
        "actual_behavior": "Takes ~4 seconds.",
    },
]


def main():
    print(f"Adding demo data to {API_BASE}\n")
    token = login()
    print("\nLogged in. Creating sample tickets...\n")

    created = []
    for spec in DEMO_TICKETS:
        t = api("POST", "/tickets/", token, json=spec)
        if t:
            created.append(t)
            print(f"  {t['key']:<8} {t['status']:<12} {t['title']}")

    print(f"\nDone -- created {len(created)}/{len(DEMO_TICKETS)} sample tickets.")
    print("They're all titled 'Sample: ...' so you can find and bulk-delete them later")
    print("from the Issues page (search 'Sample:', select all, Delete) whenever your")
    print("teammates don't need them anymore.")


if __name__ == "__main__":
    main()
