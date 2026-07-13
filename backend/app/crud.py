import uuid
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
