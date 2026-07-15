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

# ---------- Organization ----------
# Every row below belongs to this one tenant -- seed.py only ever builds a
# single demo workspace.
import secrets as _secrets
org = models.Organization(
    name="QTech Software",
    key_prefix="QTR",
    join_code=_secrets.token_hex(4).upper(),
)
db.add(org)
db.commit()
db.refresh(org)
print(f"  org: {org.name}  join code: {org.join_code}")

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
        organization_id=org.id,
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
    name: crud.create_label(db, schemas.LabelCreate(name=name, color=color), org.id)
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
), org.id)
print(f"  sprint: {sprint.name}")

# ---------- Hub ticket (the old "Epic" concept is now just a ticket other
# tickets link under via parent_tag_id) ----------
epic = crud.create_ticket(db, schemas.TicketCreate(
    title="Checkout & Payments Overhaul",
    description="Umbrella ticket for the Q3 payments work.",
    ticket_type=TicketType.TASK,
    status=TicketStatus.IN_PROGRESS,
    priority=TicketPriority.HIGH,
    label_ids=[labels["Payments"].id],
), created_by_id=admin.id, organization_id=org.id)
print(f"  hub: {epic.key} {epic.title}")

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

done_in_sprint = []
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
        parent_ticket_id=epic.id if "Payments" in label_names else None,
        due_date=now + timedelta(days=due_offset),
        label_ids=[labels[n].id for n in label_names],
    ), created_by_id=priya.id, organization_id=org.id)
    if tstatus == TicketStatus.DONE:
        done_in_sprint.append(t)
    print(f"  {t.key:<8} {t.status.value:<12} {t.title}")

# These were seeded straight into `done`, so they never logged a transition —
# and the burndown reads completion from the activity log. Without this the
# active sprint's line would sit flat at full points.
for offset, t in enumerate(done_in_sprint):
    db.add(models.ActivityLog(
        organization_id=org.id,
        ticket_id=t.id,
        actor_id=arjun.id,
        action="status_changed",
        details="code_review -> done",
        created_at=datetime.combine(
            sprint.start_date + timedelta(days=1 + offset), datetime.min.time()
        ),
    ))
db.commit()


# ---------- Historical sprints, so Reports has something real to plot ----------
# Velocity needs finished sprints; a burndown needs to know *when* each ticket
# hit done. We backdate the activity log rather than faking a chart series, so
# the reports are computed from the same data path as the live sprint.
history = [
    ("Sprint 11", 21, 18, 38, 24),   # name, committed, completed, days ago start, end
    ("Sprint 12", 26, 26, 24, 10),
    ("Sprint 13", 24, 16, 18, 4),
]

for name, committed, completed, start_ago, end_ago in history:
    past = crud.create_sprint(db, schemas.SprintCreate(
        name=name,
        goal=f"Historical sprint — {completed}/{committed} points delivered.",
        state=SprintState.COMPLETED,
        start_date=today - timedelta(days=start_ago),
        end_date=today - timedelta(days=end_ago),
    ), org.id)

    remaining_done = completed
    remaining_total = committed
    n = 0
    while remaining_total > 0:
        pts = min(5, remaining_total)
        finish = pts <= remaining_done
        n += 1

        t = crud.create_ticket(db, schemas.TicketCreate(
            title=f"{name} — work item {n}",
            description="Delivered in a previous sprint.",
            ticket_type=TicketType.TASK,
            status=TicketStatus.DONE if finish else TicketStatus.TODO,
            priority=TicketPriority.MEDIUM,
            story_points=pts,
            assignee_id=[arjun.id, sara.id, priya.id][n % 3],
            sprint_id=past.id,
            label_ids=[labels["Payments"].id],
        ), created_by_id=priya.id, organization_id=org.id)

        if finish:
            remaining_done -= pts
            # Spread completions across the sprint window so the burndown
            # descends in steps instead of dropping off a cliff on day one.
            span = start_ago - end_ago
            day = past.start_date + timedelta(days=min(span, 1 + (n * span) // 6))
            db.add(models.ActivityLog(
                organization_id=org.id,
                ticket_id=t.id,
                actor_id=priya.id,
                action="status_changed",
                details="in_progress -> done",
                created_at=datetime.combine(day, datetime.min.time()),
            ))
        remaining_total -= pts

    db.commit()
    print(f"  sprint: {name:<10} completed {completed}/{committed} pts")

db.close()
print("\nDone. Log in as kanishk@qtechsoftware.com / password123")
