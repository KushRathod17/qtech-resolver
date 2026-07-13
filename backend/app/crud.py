import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .security import hash_password

# Gap left between adjacent cards. Dropping a card between two neighbours
# averages their ranks, so a big gap means many inserts before the floats
# get too close together to split.
RANK_GAP = 1024.0


# ---------- User CRUD ----------
def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user(db: Session, user_id: uuid.UUID) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_all_users(db: Session) -> list[models.User]:
    return db.query(models.User).order_by(models.User.full_name).all()


def count_users(db: Session) -> int:
    return db.query(models.User).count()


def create_user(db: Session, user_in: schemas.UserCreate, role: models.UserRole) -> models.User:
    db_user = models.User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        role=role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def set_user_role(db: Session, user: models.User, role: models.UserRole) -> models.User:
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user: models.User, changes: schemas.UserUpdate) -> models.User:
    for field, value in changes.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: models.User, new_password: str) -> models.User:
    user.hashed_password = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return user


OPEN_STATUSES = (models.TicketStatus.BACKLOG, models.TicketStatus.TODO)
WIP_STATUSES = (models.TicketStatus.IN_PROGRESS, models.TicketStatus.CODE_REVIEW)


def user_stats(db: Session, user_id: uuid.UUID) -> dict:
    tickets = db.query(models.Ticket).filter(models.Ticket.assignee_id == user_id).all()

    def count(statuses):
        return sum(1 for t in tickets if t.status in statuses)

    return {
        "open": count(OPEN_STATUSES),
        "in_progress": count(WIP_STATUSES),
        "done": count((models.TicketStatus.DONE,)),
        "total": len(tickets),
        # The honest measure of load: points still on their plate, not ticket count.
        "story_points_open": sum(
            t.story_points or 0
            for t in tickets
            if t.status in OPEN_STATUSES + WIP_STATUSES
        ),
    }


# ---------- Activity log ----------
def log_activity(db: Session, ticket_id: uuid.UUID, actor_id: uuid.UUID, action: str, details: str = None):
    """Stages a log entry. The caller commits, so the log and the change it
    describes land in the same transaction (or neither does)."""
    db.add(models.ActivityLog(ticket_id=ticket_id, actor_id=actor_id, action=action, details=details))


def get_activity_log(db: Session, ticket_id: uuid.UUID) -> list[models.ActivityLog]:
    return (
        db.query(models.ActivityLog)
        .options(joinedload(models.ActivityLog.actor))
        .filter(models.ActivityLog.ticket_id == ticket_id)
        .order_by(models.ActivityLog.created_at)
        .all()
    )


# ---------- Label CRUD ----------
def get_labels(db: Session) -> list[models.Label]:
    return db.query(models.Label).order_by(models.Label.name).all()


def get_label(db: Session, label_id: uuid.UUID) -> models.Label | None:
    return db.query(models.Label).filter(models.Label.id == label_id).first()


def get_label_by_name(db: Session, name: str) -> models.Label | None:
    return db.query(models.Label).filter(func.lower(models.Label.name) == name.lower()).first()


def create_label(db: Session, label_in: schemas.LabelCreate) -> models.Label:
    label = models.Label(name=label_in.name, color=label_in.color)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


def update_label(db: Session, label: models.Label, label_in: schemas.LabelUpdate) -> models.Label:
    for field, value in label_in.model_dump(exclude_unset=True).items():
        setattr(label, field, value)
    db.commit()
    db.refresh(label)
    return label


def delete_label(db: Session, label: models.Label) -> None:
    db.delete(label)
    db.commit()


# ---------- Sprint CRUD ----------
def get_sprints(db: Session) -> list[models.Sprint]:
    return db.query(models.Sprint).order_by(models.Sprint.created_at.desc()).all()


def get_sprint(db: Session, sprint_id: uuid.UUID) -> models.Sprint | None:
    return db.query(models.Sprint).filter(models.Sprint.id == sprint_id).first()


def create_sprint(db: Session, sprint_in: schemas.SprintCreate) -> models.Sprint:
    sprint = models.Sprint(**sprint_in.model_dump())
    db.add(sprint)
    db.commit()
    db.refresh(sprint)
    return sprint


def update_sprint(db: Session, sprint: models.Sprint, sprint_in: schemas.SprintUpdate) -> models.Sprint:
    for field, value in sprint_in.model_dump(exclude_unset=True).items():
        setattr(sprint, field, value)
    db.commit()
    db.refresh(sprint)
    return sprint


def delete_sprint(db: Session, sprint: models.Sprint) -> None:
    db.delete(sprint)
    db.commit()


# ---------- Reporting ----------
def _completion_dates(db: Session, tickets: list[models.Ticket]) -> dict[uuid.UUID, date]:
    """When did each ticket actually reach `done`?

    Taken from the activity log rather than updated_at, because updated_at moves
    on any edit — retitling a finished ticket would otherwise silently redraw
    the burndown. A ticket can bounce out of done and back, so the *last*
    transition into done wins.
    """
    if not tickets:
        return {}

    ids = [t.id for t in tickets]
    rows = (
        db.query(models.ActivityLog)
        .filter(
            models.ActivityLog.ticket_id.in_(ids),
            models.ActivityLog.action == "status_changed",
            models.ActivityLog.details.ilike("%-> done"),
        )
        .order_by(models.ActivityLog.created_at)
        .all()
    )

    done_at: dict[uuid.UUID, date] = {}
    for row in rows:
        done_at[row.ticket_id] = row.created_at.date()

    # Only count tickets that are still in done; one that was reopened has a
    # historical transition but isn't complete now.
    return {
        t.id: done_at[t.id]
        for t in tickets
        if t.status == models.TicketStatus.DONE and t.id in done_at
    }


def sprint_stats(db: Session, sprint: models.Sprint) -> dict:
    tickets = get_tickets(db, sprint_id=sprint.id)
    done = [t for t in tickets if t.status == models.TicketStatus.DONE]
    return {
        "total_points": sum(t.story_points or 0 for t in tickets),
        "completed_points": sum(t.story_points or 0 for t in done),
        "total_tickets": len(tickets),
        "completed_tickets": len(done),
    }


def sprint_burndown(db: Session, sprint: models.Sprint) -> dict:
    tickets = get_tickets(db, sprint_id=sprint.id)
    total = sum(t.story_points or 0 for t in tickets)

    start = sprint.start_date or (sprint.created_at.date() if sprint.created_at else date.today())
    end = sprint.end_date or start
    if end < start:
        end = start

    done_at = _completion_dates(db, tickets)
    points_done_on = {}
    for ticket in tickets:
        if ticket.id in done_at:
            points_done_on.setdefault(done_at[ticket.id], 0)
            points_done_on[done_at[ticket.id]] += ticket.story_points or 0

    span = (end - start).days
    today = date.today()

    series = []
    remaining = float(total)
    for offset in range(span + 1):
        day = start + timedelta(days=offset)
        remaining -= points_done_on.get(day, 0)
        # A straight line from total on day 0 to zero on the final day.
        ideal = total - (total * offset / span) if span else 0.0
        series.append({
            "date": day,
            # Don't draw the "actual" line into the future — flat-lining it
            # there reads as a stalled sprint rather than one still running.
            "remaining": remaining,
            "ideal": round(ideal, 2),
            "is_projection": day > today,
        })

    return {"sprint": sprint, "total_points": total, "points": series}


def velocity(db: Session) -> dict:
    sprints = sorted(get_sprints(db), key=lambda s: (s.start_date or date.min, s.created_at))

    entries = []
    for sprint in sprints:
        tickets = get_tickets(db, sprint_id=sprint.id)
        done = [t for t in tickets if t.status == models.TicketStatus.DONE]
        entries.append({
            "sprint_id": sprint.id,
            "sprint_name": sprint.name,
            "state": sprint.state,
            "committed_points": sum(t.story_points or 0 for t in tickets),
            "completed_points": sum(t.story_points or 0 for t in done),
        })

    # Average only over finished sprints — an in-flight sprint would drag the
    # mean down purely because it isn't over yet.
    finished = [e for e in entries if e["state"] == models.SprintState.COMPLETED]
    average = sum(e["completed_points"] for e in finished) / len(finished) if finished else 0.0

    return {"sprints": entries, "average_velocity": round(average, 1)}


# ---------- Components ----------
def get_components(db: Session) -> list[models.Component]:
    return db.query(models.Component).order_by(models.Component.name).all()


def get_component(db: Session, component_id: uuid.UUID) -> models.Component | None:
    return db.query(models.Component).filter(models.Component.id == component_id).first()


def get_component_by_name(db: Session, name: str) -> models.Component | None:
    return db.query(models.Component).filter(
        func.lower(models.Component.name) == name.lower()
    ).first()


def create_component(db: Session, payload: schemas.ComponentCreate) -> models.Component:
    component = models.Component(**payload.model_dump())
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


def update_component(
    db: Session, component: models.Component, payload: schemas.ComponentUpdate
) -> models.Component:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.commit()
    db.refresh(component)
    return component


def delete_component(db: Session, component: models.Component) -> None:
    db.delete(component)
    db.commit()


def component_stats(db: Session) -> list[dict]:
    """Per-component load, including how many tickets are past their SLA — the
    'which product is on fire right now' view."""
    policies = get_sla_policies(db)
    rows = []

    for component in get_components(db):
        tickets = db.query(models.Ticket).filter(
            models.Ticket.component_id == component.id
        ).all()
        open_tickets = [t for t in tickets if t.status != models.TicketStatus.DONE]
        rows.append({
            "id": component.id,
            "name": component.name,
            "description": component.description,
            "color": component.color,
            "lead": component.lead,
            "open_tickets": len(open_tickets),
            "total_tickets": len(tickets),
            "breached": sum(1 for t in tickets if _sla_for(t, policies) and _sla_for(t, policies)["breached"]),
        })
    return rows


# ---------- SLA ----------
def get_sla_policies(db: Session) -> dict[models.TicketPriority, int | None]:
    return {
        row.priority: row.threshold_hours
        for row in db.query(models.SLAPolicy).all()
    }


def list_sla_policies(db: Session) -> list[models.SLAPolicy]:
    return db.query(models.SLAPolicy).all()


def set_sla_policy(
    db: Session, priority: models.TicketPriority, threshold_hours: int | None
) -> models.SLAPolicy:
    policy = db.query(models.SLAPolicy).filter(models.SLAPolicy.priority == priority).first()
    if policy:
        policy.threshold_hours = threshold_hours
    else:
        policy = models.SLAPolicy(priority=priority, threshold_hours=threshold_hours)
        db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def _sla_for(ticket: models.Ticket, policies: dict) -> dict | None:
    """The live clock for one ticket, or None if its priority has no SLA.

    Derived on read, never stored: a stored 'breached' flag is wrong the instant
    the clock passes the threshold, and would need a cron job to stay true.
    """
    threshold = policies.get(ticket.priority)
    if not threshold:
        return None

    # A resolved ticket's clock is frozen at the moment it was resolved —
    # otherwise a ticket closed well inside its window keeps ageing and
    # eventually reports as breached forever.
    end = ticket.resolved_at if ticket.status == models.TicketStatus.DONE else None
    stopped = end is not None
    if end is None:
        end = datetime.utcnow()

    elapsed = int((end - (ticket.created_at or end)).total_seconds())
    limit = threshold * 3600
    return {
        "threshold_hours": threshold,
        "elapsed_seconds": max(elapsed, 0),
        "remaining_seconds": limit - elapsed,
        "breached": elapsed > limit,
        "stopped": stopped,
    }


def _epic_progress(db: Session, epic: models.Ticket) -> dict:
    """'6/10 done' for an epic, derived from its children on every read."""
    children = db.query(models.Ticket).filter(models.Ticket.epic_id == epic.id).all()
    done = [c for c in children if c.status == models.TicketStatus.DONE]

    points_total = sum(c.story_points or 0 for c in children)
    points_done = sum(c.story_points or 0 for c in done)

    # Prefer points when the epic is estimated — a 13-point story finishing is
    # more progress than a 1-point one, and a ticket count hides that.
    if points_total:
        percent = round(points_done / points_total * 100)
    elif children:
        percent = round(len(done) / len(children) * 100)
    else:
        percent = 0

    return {
        "done": len(done),
        "total": len(children),
        "points_done": points_done,
        "points_total": points_total,
        "percent": percent,
    }


def attach_derived(db: Session, tickets: list[models.Ticket]) -> list[models.Ticket]:
    """Hang the computed SLA clock and epic progress off each ticket so
    TicketOut can serialise them. Neither is ever stored."""
    policies = get_sla_policies(db)
    for ticket in tickets:
        ticket.sla = _sla_for(ticket, policies)
        ticket.progress = (
            _epic_progress(db, ticket)
            if ticket.ticket_type == models.TicketType.EPIC
            else None
        )
    return tickets


# Kept as an alias: several call sites predate epic progress.
attach_sla = attach_derived


def _sync_resolved_at(ticket: models.Ticket, new_status: models.TicketStatus) -> None:
    """Stamp resolved_at on the way into done; clear it on the way back out, so
    a reopened ticket restarts its clock rather than staying frozen."""
    if new_status == models.TicketStatus.DONE and ticket.resolved_at is None:
        ticket.resolved_at = datetime.utcnow()
    elif new_status != models.TicketStatus.DONE:
        ticket.resolved_at = None


# ---------- Ticket CRUD ----------
def _ticket_query(db: Session):
    return db.query(models.Ticket).options(
        joinedload(models.Ticket.assignee),
        joinedload(models.Ticket.reporter),
    )


def get_tickets(
    db: Session,
    status: Optional[models.TicketStatus] = None,
    assignee_id: Optional[uuid.UUID] = None,
    priority: Optional[models.TicketPriority] = None,
    ticket_type: Optional[models.TicketType] = None,
    sprint_id: Optional[uuid.UUID] = None,
    epic_id: Optional[uuid.UUID] = None,
    label_id: Optional[uuid.UUID] = None,
    component_id: Optional[uuid.UUID] = None,
    client_name: Optional[str] = None,
    breached: Optional[bool] = None,
    watcher_id: Optional[uuid.UUID] = None,
    include_subtasks: bool = False,
    search: Optional[str] = None,
) -> list[models.Ticket]:
    query = _ticket_query(db)

    # Sub-tasks live inside their parent, not as loose cards on the board.
    # Showing them at top level would double-count the work.
    if not include_subtasks:
        query = query.filter(models.Ticket.parent_id.is_(None))

    if status is not None:
        query = query.filter(models.Ticket.status == status)
    if assignee_id is not None:
        query = query.filter(models.Ticket.assignee_id == assignee_id)
    if priority is not None:
        query = query.filter(models.Ticket.priority == priority)
    if ticket_type is not None:
        query = query.filter(models.Ticket.ticket_type == ticket_type)
    if sprint_id is not None:
        query = query.filter(models.Ticket.sprint_id == sprint_id)
    if epic_id is not None:
        query = query.filter(models.Ticket.epic_id == epic_id)
    if label_id is not None:
        query = query.filter(models.Ticket.labels.any(models.Label.id == label_id))
    if component_id is not None:
        query = query.filter(models.Ticket.component_id == component_id)
    if watcher_id is not None:
        query = query.filter(models.Ticket.watchers.any(models.User.id == watcher_id))
    if client_name:
        query = query.filter(models.Ticket.client_name.ilike(f"%{client_name}%"))
    if search:
        term = f"%{search}%"
        # Title, description, and the ticket key — support engineers paste keys.
        conditions = [
            models.Ticket.title.ilike(term),
            models.Ticket.description.ilike(term),
            models.Ticket.client_name.ilike(term),
        ]
        digits = "".join(ch for ch in search if ch.isdigit())
        if digits:
            conditions.append(models.Ticket.ticket_number == int(digits))
        query = query.filter(or_(*conditions))

    rows = query.order_by(models.Ticket.rank, models.Ticket.created_at.desc()).all()
    attach_derived(db, rows)

    # Breach is computed, not a column, so this filter has to happen in Python.
    if breached is not None:
        rows = [t for t in rows if bool(t.sla and t.sla["breached"]) is breached]

    return rows


def get_ticket(db: Session, ticket_id: uuid.UUID) -> models.Ticket | None:
    ticket = _ticket_query(db).filter(models.Ticket.id == ticket_id).first()
    if ticket:
        attach_sla(db, [ticket])
    return ticket


def get_client_names(db: Session) -> list[str]:
    rows = (
        db.query(models.Ticket.client_name)
        .filter(models.Ticket.client_name.isnot(None))
        .distinct()
        .order_by(models.Ticket.client_name)
        .all()
    )
    return [r[0] for r in rows]


def _resolve_labels(db: Session, label_ids: list[uuid.UUID]) -> list[models.Label]:
    if not label_ids:
        return []
    return db.query(models.Label).filter(models.Label.id.in_(label_ids)).all()


def _top_rank(db: Session, status: models.TicketStatus) -> float:
    """New cards land at the top of their column."""
    lowest = db.query(func.min(models.Ticket.rank)).filter(models.Ticket.status == status).scalar()
    return RANK_GAP if lowest is None else lowest - RANK_GAP


def create_ticket(db: Session, ticket_in: schemas.TicketCreate, created_by_id: uuid.UUID) -> models.Ticket:
    data = ticket_in.model_dump(exclude={"label_ids"})
    db_ticket = models.Ticket(
        **data,
        created_by_id=created_by_id,
        rank=_top_rank(db, ticket_in.status),
    )
    db_ticket.labels = _resolve_labels(db, ticket_in.label_ids)

    _sync_resolved_at(db_ticket, ticket_in.status)

    db.add(db_ticket)
    db.flush()  # assigns id + ticket_number so the log can reference them
    log_activity(db, db_ticket.id, created_by_id, "created", f"Created {db_ticket.key}")
    db.commit()
    db.refresh(db_ticket)
    attach_sla(db, [db_ticket])
    return db_ticket


# How each field reads in the activity feed. Anything listed here is tracked;
# the old version only logged status, assignee, priority and points, so an edit
# to the title or the client silently vanished from the history.
TRACKED_FIELDS = {
    "title": "title",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "ticket_type": "type",
    "story_points": "story points",
    "assignee_id": "assignee",
    "sprint_id": "sprint",
    "epic_id": "epic",
    "parent_id": "parent",
    "component_id": "component",
    "client_name": "client",
    "due_date": "due date",
}


def _display(db: Session, field: str, value) -> str:
    """Render a field value the way a human would say it, not as a raw UUID."""
    if value is None or value == "":
        return "none"
    if field == "assignee_id":
        user = get_user(db, value)
        return user.full_name if user else "unknown"
    if field == "component_id":
        component = get_component(db, value)
        return component.name if component else "unknown"
    if field == "sprint_id":
        sprint = get_sprint(db, value)
        return sprint.name if sprint else "unknown"
    if field in ("epic_id", "parent_id"):
        other = db.query(models.Ticket).filter(models.Ticket.id == value).first()
        return other.key if other else "unknown"
    if hasattr(value, "value"):  # an enum
        return value.value
    if field == "description":
        text = str(value)
        return (text[:40] + "…") if len(text) > 40 else text
    return str(value)


def update_ticket(
    db: Session, ticket: models.Ticket, ticket_in: schemas.TicketUpdate, actor_id: uuid.UUID
) -> models.Ticket:
    update_data = ticket_in.model_dump(exclude_unset=True)
    label_ids = update_data.pop("label_ids", None)

    for field, new_value in update_data.items():
        old_value = getattr(ticket, field)
        if new_value == old_value or field not in TRACKED_FIELDS:
            continue

        log_activity(
            db, ticket.id, actor_id, f"{TRACKED_FIELDS[field]}_changed",
            f"{_display(db, field, old_value)} -> {_display(db, field, new_value)}",
        )

    if "status" in update_data and update_data["status"] != ticket.status:
        # Moving column via the edit form (not drag) — send it to the top.
        ticket.rank = _top_rank(db, update_data["status"])
        _sync_resolved_at(ticket, update_data["status"])

    for field, value in update_data.items():
        setattr(ticket, field, value)

    if label_ids is not None:
        before = {l.name for l in ticket.labels}
        ticket.labels = _resolve_labels(db, label_ids)
        after = {l.name for l in ticket.labels}
        if before != after:
            log_activity(db, ticket.id, actor_id, "labels_changed",
                         ", ".join(sorted(after)) or "Labels cleared")

    db.commit()
    db.refresh(ticket)
    attach_sla(db, [ticket])
    return ticket


def create_subtask(
    db: Session, parent: models.Ticket, payload: schemas.SubtaskCreate, created_by_id: uuid.UUID
) -> models.Ticket:
    subtask = models.Ticket(
        title=payload.title,
        ticket_type=models.TicketType.SUBTASK,
        status=models.TicketStatus.TODO,
        # Inherited from the parent, so a sub-task lands in the right product,
        # sprint and client context without anyone re-entering it.
        priority=parent.priority,
        assignee_id=payload.assignee_id or parent.assignee_id,
        component_id=parent.component_id,
        client_name=parent.client_name,
        sprint_id=parent.sprint_id,
        parent_id=parent.id,
        created_by_id=created_by_id,
        rank=_top_rank(db, models.TicketStatus.TODO),
    )
    db.add(subtask)
    db.flush()
    log_activity(db, parent.id, created_by_id, "subtask_added", subtask.title)
    db.commit()
    db.refresh(subtask)
    attach_derived(db, [subtask])
    return subtask


# Copied on duplicate. Deliberately excludes status, rank, resolved_at and the
# history — a duplicate is a NEW report of the same problem, not a clone of how
# far the original got.
DUPLICATE_FIELDS = (
    "title", "description", "priority", "ticket_type", "story_points",
    "assignee_id", "sprint_id", "epic_id", "component_id", "client_name",
    "due_date",
)


def duplicate_ticket(db: Session, ticket: models.Ticket, created_by_id: uuid.UUID) -> models.Ticket:
    copy = models.Ticket(
        **{f: getattr(ticket, f) for f in DUPLICATE_FIELDS},
        created_by_id=created_by_id,
        status=models.TicketStatus.TODO,
        rank=_top_rank(db, models.TicketStatus.TODO),
    )
    copy.title = f"{ticket.title} (copy)"
    copy.labels = list(ticket.labels)

    db.add(copy)
    db.flush()
    log_activity(db, copy.id, created_by_id, "created", f"Duplicated from {ticket.key}")
    db.commit()
    db.refresh(copy)
    attach_derived(db, [copy])
    return copy


def convert_to_epic(db: Session, ticket: models.Ticket, actor_id: uuid.UUID) -> models.Ticket:
    old_type = ticket.ticket_type.value
    ticket.ticket_type = models.TicketType.EPIC
    ticket.epic_id = None  # an epic can't belong to another epic

    # An epic can't own sub-tasks, so its sub-tasks are promoted to full tickets
    # that belong to the new epic. Otherwise they'd be orphaned by the cascade.
    for subtask in list(ticket.subtasks):
        subtask.parent_id = None
        subtask.epic_id = ticket.id
        subtask.ticket_type = models.TicketType.TASK

    log_activity(db, ticket.id, actor_id, "type_changed", f"{old_type} -> epic")
    db.commit()
    db.refresh(ticket)
    attach_derived(db, [ticket])
    return ticket


def bulk_update_tickets(
    db: Session, bulk: schemas.TicketBulkUpdate, actor_id: uuid.UUID
) -> list[models.Ticket]:
    """Apply one change set to many tickets in a single transaction.

    Either the whole batch lands or none of it does — a half-applied bulk edit
    is worse than a failed one, because you can't tell what to retry.
    """
    tickets = _ticket_query(db).filter(models.Ticket.id.in_(bulk.ticket_ids)).all()
    if not tickets:
        return []

    add_labels = _resolve_labels(db, bulk.add_label_ids)
    remove_ids = set(bulk.remove_label_ids)

    # Every ticket moving to the same column would otherwise collide on one
    # rank; walk the gap so they stack in the order they were selected.
    next_rank = _top_rank(db, bulk.status) if bulk.status else None

    for ticket in tickets:
        if bulk.status and bulk.status != ticket.status:
            log_activity(db, ticket.id, actor_id, "status_changed",
                         f"{ticket.status.value} -> {bulk.status.value}")
            _sync_resolved_at(ticket, bulk.status)
            ticket.status = bulk.status
            ticket.rank = next_rank
            next_rank -= RANK_GAP

        if bulk.priority and bulk.priority != ticket.priority:
            log_activity(db, ticket.id, actor_id, "priority_changed",
                         f"{ticket.priority.value} -> {bulk.priority.value}")
            ticket.priority = bulk.priority

        if bulk.ticket_type and bulk.ticket_type != ticket.ticket_type:
            ticket.ticket_type = bulk.ticket_type

        if bulk.story_points is not None and bulk.story_points != ticket.story_points:
            log_activity(db, ticket.id, actor_id, "estimated",
                         f"{ticket.story_points or '-'} -> {bulk.story_points} points")
            ticket.story_points = bulk.story_points

        if bulk.clear_assignee:
            if ticket.assignee_id is not None:
                log_activity(db, ticket.id, actor_id, "assigned", "Unassigned")
                ticket.assignee_id = None
        elif bulk.assignee_id and bulk.assignee_id != ticket.assignee_id:
            assignee = get_user(db, bulk.assignee_id)
            log_activity(db, ticket.id, actor_id, "assigned",
                         f"Assigned to {assignee.full_name}" if assignee else "Assigned")
            ticket.assignee_id = bulk.assignee_id

        if bulk.clear_sprint:
            ticket.sprint_id = None
        elif bulk.sprint_id:
            ticket.sprint_id = bulk.sprint_id

        if bulk.clear_component:
            ticket.component_id = None
        elif bulk.component_id and bulk.component_id != ticket.component_id:
            component = get_component(db, bulk.component_id)
            log_activity(db, ticket.id, actor_id, "component_changed",
                         component.name if component else "unknown")
            ticket.component_id = bulk.component_id

        if bulk.client_name is not None and bulk.client_name != ticket.client_name:
            log_activity(db, ticket.id, actor_id, "client_changed", bulk.client_name or "none")
            ticket.client_name = bulk.client_name

        if add_labels or remove_ids:
            current = {l.id: l for l in ticket.labels}
            for label in add_labels:
                current[label.id] = label
            for label_id in remove_ids:
                current.pop(label_id, None)

            if set(current) != {l.id for l in ticket.labels}:
                ticket.labels = list(current.values())
                log_activity(db, ticket.id, actor_id, "labels_changed",
                             ", ".join(l.name for l in ticket.labels) or "Labels cleared")

    db.commit()
    for ticket in tickets:
        db.refresh(ticket)
    attach_sla(db, tickets)
    return tickets


def bulk_delete_tickets(db: Session, ticket_ids: list[uuid.UUID]) -> int:
    tickets = db.query(models.Ticket).filter(models.Ticket.id.in_(ticket_ids)).all()
    for ticket in tickets:
        db.delete(ticket)
    db.commit()
    return len(tickets)


def move_ticket(db: Session, ticket: models.Ticket, move: schemas.TicketMove, actor_id: uuid.UUID) -> models.Ticket:
    """Drag-and-drop: set the column, and position between two neighbours."""
    before = get_ticket(db, move.before_id) if move.before_id else None
    after = get_ticket(db, move.after_id) if move.after_id else None

    if before and after:
        new_rank = (before.rank + after.rank) / 2
    elif before:                      # dropped below `before`, at the bottom
        new_rank = before.rank + RANK_GAP
    elif after:                       # dropped above `after`, at the top
        new_rank = after.rank - RANK_GAP
    else:                             # empty column
        new_rank = RANK_GAP

    if move.status != ticket.status:
        log_activity(db, ticket.id, actor_id, "status_changed",
                     f"{ticket.status.value} -> {move.status.value}")
        # Dragging a card to Done must stop its SLA clock, exactly as the edit
        # form does — otherwise the clock depends on how you closed the ticket.
        _sync_resolved_at(ticket, move.status)
        ticket.status = move.status

    ticket.rank = new_rank
    db.commit()
    db.refresh(ticket)
    attach_sla(db, [ticket])
    return ticket


def delete_ticket(db: Session, ticket: models.Ticket) -> None:
    db.delete(ticket)
    db.commit()


# ---------- Watchers ----------
def watch_ticket(db: Session, ticket: models.Ticket, user: models.User) -> models.Ticket:
    if user not in ticket.watchers:
        ticket.watchers.append(user)
        db.commit()
        db.refresh(ticket)
    return ticket


def unwatch_ticket(db: Session, ticket: models.Ticket, user: models.User) -> models.Ticket:
    if user in ticket.watchers:
        ticket.watchers.remove(user)
        db.commit()
        db.refresh(ticket)
    return ticket


# ---------- Attachments ----------
def create_attachment(
    db: Session,
    ticket: models.Ticket,
    uploader_id: uuid.UUID,
    filename: str,
    stored_name: str,
    content_type: str,
    size_bytes: int,
) -> models.Attachment:
    attachment = models.Attachment(
        ticket_id=ticket.id,
        uploaded_by_id=uploader_id,
        filename=filename,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    log_activity(db, ticket.id, uploader_id, "attached", filename)
    db.commit()
    db.refresh(attachment)
    return attachment


def get_attachment(db: Session, attachment_id: uuid.UUID) -> models.Attachment | None:
    return db.query(models.Attachment).filter(models.Attachment.id == attachment_id).first()


def delete_attachment(db: Session, attachment: models.Attachment) -> None:
    db.delete(attachment)
    db.commit()


# ---------- Saved filters ----------
def get_saved_filters(db: Session, user_id: uuid.UUID) -> list[models.SavedFilter]:
    return (
        db.query(models.SavedFilter)
        .filter(models.SavedFilter.user_id == user_id)
        .order_by(models.SavedFilter.pinned.desc(), models.SavedFilter.created_at)
        .all()
    )


def get_saved_filter(db: Session, filter_id: uuid.UUID) -> models.SavedFilter | None:
    return db.query(models.SavedFilter).filter(models.SavedFilter.id == filter_id).first()


def create_saved_filter(
    db: Session, user_id: uuid.UUID, payload: schemas.SavedFilterCreate
) -> models.SavedFilter:
    saved = models.SavedFilter(user_id=user_id, **payload.model_dump())
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def update_saved_filter(
    db: Session, saved: models.SavedFilter, payload: schemas.SavedFilterUpdate
) -> models.SavedFilter:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(saved, field, value)
    db.commit()
    db.refresh(saved)
    return saved


def delete_saved_filter(db: Session, saved: models.SavedFilter) -> None:
    db.delete(saved)
    db.commit()


# ---------- Comment CRUD ----------
def create_comment(
    db: Session, ticket_id: uuid.UUID, author_id: uuid.UUID, comment_in: schemas.CommentCreate
) -> models.Comment:
    db_comment = models.Comment(ticket_id=ticket_id, author_id=author_id, body=comment_in.body)
    db.add(db_comment)
    log_activity(db, ticket_id, author_id, "commented", comment_in.body[:80])
    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_comments_for_ticket(db: Session, ticket_id: uuid.UUID) -> list[models.Comment]:
    return (
        db.query(models.Comment)
        .options(joinedload(models.Comment.author))
        .filter(models.Comment.ticket_id == ticket_id)
        .order_by(models.Comment.created_at)
        .all()
    )
