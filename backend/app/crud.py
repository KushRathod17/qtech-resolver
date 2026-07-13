import uuid
from datetime import date, timedelta
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
    search: Optional[str] = None,
) -> list[models.Ticket]:
    query = _ticket_query(db)

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
    if search:
        term = f"%{search}%"
        # Search the description too — the old version only matched titles.
        query = query.filter(
            or_(
                models.Ticket.title.ilike(term),
                models.Ticket.description.ilike(term),
            )
        )

    return query.order_by(models.Ticket.rank, models.Ticket.created_at.desc()).all()


def get_ticket(db: Session, ticket_id: uuid.UUID) -> models.Ticket | None:
    return _ticket_query(db).filter(models.Ticket.id == ticket_id).first()


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

    db.add(db_ticket)
    db.flush()  # assigns id + ticket_number so the log can reference them
    log_activity(db, db_ticket.id, created_by_id, "created", f"Created {db_ticket.key}")
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


def update_ticket(
    db: Session, ticket: models.Ticket, ticket_in: schemas.TicketUpdate, actor_id: uuid.UUID
) -> models.Ticket:
    update_data = ticket_in.model_dump(exclude_unset=True)
    label_ids = update_data.pop("label_ids", None)

    if "status" in update_data and update_data["status"] != ticket.status:
        log_activity(db, ticket.id, actor_id, "status_changed",
                     f"{ticket.status.value} -> {update_data['status'].value}")
        # Moving column via the edit form (not drag) — send it to the top.
        ticket.rank = _top_rank(db, update_data["status"])

    if "assignee_id" in update_data and update_data["assignee_id"] != ticket.assignee_id:
        new_assignee = get_user(db, update_data["assignee_id"]) if update_data["assignee_id"] else None
        log_activity(db, ticket.id, actor_id, "assigned",
                     f"Assigned to {new_assignee.full_name}" if new_assignee else "Unassigned")

    if "priority" in update_data and update_data["priority"] != ticket.priority:
        log_activity(db, ticket.id, actor_id, "priority_changed",
                     f"{ticket.priority.value} -> {update_data['priority'].value}")

    if "story_points" in update_data and update_data["story_points"] != ticket.story_points:
        log_activity(db, ticket.id, actor_id, "estimated",
                     f"{ticket.story_points or '-'} -> {update_data['story_points'] or '-'} points")

    for field, value in update_data.items():
        setattr(ticket, field, value)

    if label_ids is not None:
        ticket.labels = _resolve_labels(db, label_ids)
        log_activity(db, ticket.id, actor_id, "labels_changed",
                     ", ".join(l.name for l in ticket.labels) or "Labels cleared")

    db.commit()
    db.refresh(ticket)
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
        ticket.status = move.status

    ticket.rank = new_rank
    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket: models.Ticket) -> None:
    db.delete(ticket)
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
