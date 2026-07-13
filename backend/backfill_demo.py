"""
One-off, NON-destructive: give the existing seeded tickets a component and a
client, and age a couple of them so the SLA states are actually visible.

Drops nothing — safe to run against a database with real accounts in it.

    cd backend
    venv\\Scripts\\activate
    python backfill_demo.py
"""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app import models

db = SessionLocal()

components = {c.name: c for c in db.query(models.Component).all()}
if not components:
    raise SystemExit("No components found — run 'alembic upgrade head' first.")

# Real-ish travel-agency clients, mapped onto the seeded tickets.
PLAN = {
    "Add Apple Pay to checkout":                    ("OTRAMS-Payments",  "Kesari Tours"),
    "Card form rejects valid AMEX numbers":         ("OTRAMS-Payments",  "Thomas Cook India"),
    "Migrate session store to Redis":               ("OTRAMS-Booking",   None),
    "Password reset email never arrives":           ("OTRAMS-Booking",   "Veena World"),
    "Redesign the empty-board state":               ("Bizinso-Custom",   None),
    "Rate-limit the login endpoint":                ("RateNet-API",      None),
    "Add story points to the ticket model":         ("Bizinso-Custom",   None),
    "Bulk-select tickets on the board":             ("Bizinso-Custom",   None),
    "Investigate slow board load with 500+ tickets": ("RateNet-API",     "SOTC Travel"),
    "Checkout & Payments Overhaul":                 ("OTRAMS-Payments",  None),
}

now = datetime.utcnow()
touched = 0

for ticket in db.query(models.Ticket).all():
    spec = PLAN.get(ticket.title)
    if not spec:
        # Everything else (the historical sprint filler) goes to RateNet.
        ticket.component_id = components["RateNet-API"].id
        continue

    component_name, client = spec
    ticket.component_id = components[component_name].id
    ticket.client_name = client
    touched += 1

# Age two open, high-severity tickets so the board shows a live breach and a
# near-miss. SLA is 4h for highest and 8h for high.
def age(title, hours):
    t = db.query(models.Ticket).filter(models.Ticket.title == title).first()
    if t:
        t.created_at = now - timedelta(hours=hours)
        print(f"  aged {t.key:<7} {hours}h  ({t.priority.value})")

age("Card form rejects valid AMEX numbers", 9)   # highest, 4h target -> BREACHED
age("Add Apple Pay to checkout", 7)              # high, 8h target -> at risk
age("Password reset email never arrives", 2)     # high, 8h target -> comfortable

db.commit()
db.close()

print(f"\nBackfilled {touched} tickets with components and clients. Nothing was dropped.")
