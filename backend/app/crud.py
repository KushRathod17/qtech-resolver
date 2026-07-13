import uuid
from sqlalchemy.orm import Session

from . import models, schemas
from .security import hash_password


# ---------- User CRUD ----------
def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def get_all_users(db: Session) -> list[models.User]:
    return db.query(models.User).all()


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


# ---------- Activity log helper ----------
def log_activity(db: Session, ticket_id: uuid.UUID, actor_id: uuid.UUID, action: str, details: str = None):
    entry = models.ActivityLog(ticket_id=ticket_id, actor_id=actor_id, action=action, details=details)
    db.add(entry)
    db.commit()


# ---------- Ticket CRUD ----------
def get_tickets(db: Session, assignee_id: uuid.UUID = None, search: str = None) -> list[models.Ticket]:
    query = db.query(models.Ticket)
    if assignee_id:
        query = query.filter(models.Ticket.assignee_id == assignee_id)
    if search:
        query = query.filter(models.Ticket.title.ilike(f"%{search}%"))
    return query.order_by(models.Ticket.created_at.desc()).all()


def get_ticket(db: Session, ticket_id: uuid.UUID) -> models.Ticket | None:
    return db.query(models.Ticket).filter(models.Ticket.id == ticket_id).first()


def create_ticket(db: Session, ticket_in: schemas.TicketCreate, created_by_id: uuid.UUID) -> models.Ticket:
    db_ticket = models.Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        assignee_id=ticket_in.assignee_id,
        priority=ticket_in.priority,
        ticket_type=ticket_in.ticket_type,
        due_date=ticket_in.due_date,
        created_by_id=created_by_id,
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    log_activity(db, db_ticket.id, created_by_id, "created", f"Ticket '{db_ticket.title}' created")
    return db_ticket


def update_ticket(db: Session, ticket: models.Ticket, ticket_in: schemas.TicketUpdate, actor_id: uuid.UUID) -> models.Ticket:
    update_data = ticket_in.model_dump(exclude_unset=True)

    # Log meaningful changes before applying them
    if "status" in update_data and update_data["status"] != ticket.status:
        log_activity(db, ticket.id, actor_id, "status_changed", f"{ticket.status.value} -> {update_data['status'].value}")
    if "assignee_id" in update_data and update_data["assignee_id"] != ticket.assignee_id:
        log_activity(db, ticket.id, actor_id, "assigned", f"Assignee changed")
    if "priority" in update_data and update_data["priority"] != ticket.priority:
        log_activity(db, ticket.id, actor_id, "priority_changed", f"{ticket.priority.value} -> {update_data['priority'].value}")

    for field, value in update_data.items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket: models.Ticket) -> None:
    db.delete(ticket)
    db.commit()


def get_activity_log(db: Session, ticket_id: uuid.UUID) -> list[models.ActivityLog]:
    return db.query(models.ActivityLog).filter(models.ActivityLog.ticket_id == ticket_id).order_by(models.ActivityLog.created_at).all()


# ---------- Comment CRUD ----------
def create_comment(db: Session, ticket_id: uuid.UUID, author_id: uuid.UUID, comment_in: schemas.CommentCreate) -> models.Comment:
    db_comment = models.Comment(
        ticket_id=ticket_id,
        author_id=author_id,
        body=comment_in.body,
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def get_comments_for_ticket(db: Session, ticket_id: uuid.UUID) -> list[models.Comment]:
    return db.query(models.Comment).filter(models.Comment.ticket_id == ticket_id).order_by(models.Comment.created_at).all()