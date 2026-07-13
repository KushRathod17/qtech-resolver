"""
Rebuild the database and fill it with demo data.

    cd backend
    venv\\Scripts\\activate
    python seed.py

DESTRUCTIVE: drops every table and recreates it from the models. Only ever
point this at a local dev database.
"""
from datetime import datetime, timedelta, date

from app.database import Base, engine, SessionLocal
from app import models, crud, schemas
from app.models import (
    UserRole, TicketStatus, TicketPriority, TicketType, SprintState,
)

print("Dropping and recreating all tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()

# ---------- Users ----------
people = [
    ("kanishk@qtechsoftware.com", "Kanishk Sharma", UserRole.ADMIN),
    ("priya@qtechsoftware.com", "Priya Nair", UserRole.MANAGER),
    ("arjun@qtechsoftware.com", "Arjun Mehta", UserRole.DEVELOPER),
    ("sara@qtechsoftware.com", "Sara Iqbal", UserRole.DEVELOPER),
]
users = {}
for email, name, role in people:
    users[email] = crud.create_user(
        db,
        schemas.UserCreate(email=email, full_name=name, password="password123"),
        role=role,
    )
    print(f"  user: {name:<16} {role.value:<10} password123")

admin = users["kanishk@qtechsoftware.com"]
priya = users["priya@qtechsoftware.com"]
arjun = users["arjun@qtechsoftware.com"]
sara = users["sara@qtechsoftware.com"]

# ---------- Labels ----------
label_specs = [
    ("Space Travel Partners", "#8B5CF6"),
    ("Local Mars Office", "#F59E0B"),
    ("Payments", "#10B981"),
    ("Infrastructure", "#3B82F6"),
    ("Tech Debt", "#EF4444"),
    ("Design", "#EC4899"),
]
labels = {
    name: crud.create_label(db, schemas.LabelCreate(name=name, color=color))
    for name, color in label_specs
}
print(f"  {len(labels)} labels")

# ---------- Sprint ----------
today = date.today()
sprint = crud.create_sprint(db, schemas.SprintCreate(
    name="Sprint 14",
    goal="Ship the new checkout flow and clear the auth backlog.",
    state=SprintState.ACTIVE,
    start_date=today - timedelta(days=4),
    end_date=today + timedelta(days=10),
))
print(f"  sprint: {sprint.name}")

# ---------- Epic ----------
epic = crud.create_ticket(db, schemas.TicketCreate(
    title="Checkout & Payments Overhaul",
    description="Umbrella epic for the Q3 payments work.",
    ticket_type=TicketType.EPIC,
    status=TicketStatus.IN_PROGRESS,
    priority=TicketPriority.HIGH,
    label_ids=[labels["Payments"].id],
), created_by_id=admin.id)
print(f"  epic: {epic.key} {epic.title}")

# ---------- Tickets ----------
now = datetime.utcnow()
specs = [
    ("Add Apple Pay to checkout", "Shoppers drop off at the card form. Apple Pay should cut a step.",
     TicketType.STORY, TicketStatus.TODO, TicketPriority.HIGH, 5, arjun,
     ["Payments", "Space Travel Partners"], 6),
    ("Card form rejects valid AMEX numbers", "15-digit AMEX fails Luhn check. Regression from #212.",
     TicketType.BUG, TicketStatus.IN_PROGRESS, TicketPriority.HIGHEST, 3, sara,
     ["Payments"], 2),
    ("Migrate session store to Redis", "In-memory sessions die on every deploy.",
     TicketType.TASK, TicketStatus.IN_PROGRESS, TicketPriority.MEDIUM, 8, arjun,
     ["Infrastructure", "Tech Debt"], 9),
    ("Password reset email never arrives", "SMTP creds expired in staging.",
     TicketType.BUG, TicketStatus.CODE_REVIEW, TicketPriority.HIGH, 2, sara,
     ["Infrastructure"], 1),
    ("Redesign the empty-board state", "Right now a new board is just a blank grid.",
     TicketType.STORY, TicketStatus.CODE_REVIEW, TicketPriority.LOW, 3, priya,
     ["Design", "Local Mars Office"], 12),
    ("Rate-limit the login endpoint", "No throttling — trivially brute-forceable.",
     TicketType.TASK, TicketStatus.DONE, TicketPriority.HIGHEST, 5, arjun,
     ["Infrastructure"], -3),
    ("Add story points to the ticket model", "Needed before velocity reporting.",
     TicketType.TASK, TicketStatus.DONE, TicketPriority.MEDIUM, 2, sara,
     ["Tech Debt"], -6),
    ("Bulk-select tickets on the board", "Shift-click to multi-select, then bulk change status.",
     TicketType.STORY, TicketStatus.BACKLOG, TicketPriority.LOW, 8, None,
     ["Design"], 20),
    ("Investigate slow board load with 500+ tickets", "Board takes ~4s to paint at scale.",
     TicketType.BUG, TicketStatus.BACKLOG, TicketPriority.MEDIUM, 5, None,
     ["Tech Debt"], 25),
]

for title, desc, ttype, tstatus, prio, points, assignee, label_names, due_offset in specs:
    t = crud.create_ticket(db, schemas.TicketCreate(
        title=title,
        description=desc,
        ticket_type=ttype,
        status=tstatus,
        priority=prio,
        story_points=points,
        assignee_id=assignee.id if assignee else None,
        sprint_id=sprint.id,
        epic_id=epic.id if "Payments" in label_names else None,
        due_date=now + timedelta(days=due_offset),
        label_ids=[labels[n].id for n in label_names],
    ), created_by_id=priya.id)
    print(f"  {t.key:<8} {t.status.value:<12} {t.title}")

db.close()
print("\nDone. Log in as kanishk@qtechsoftware.com / password123")
