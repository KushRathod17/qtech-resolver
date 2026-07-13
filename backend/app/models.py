import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Date, ForeignKey, Integer, Float,
    Table, Sequence, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref

from .database import Base

# Prefix for human-readable ticket keys, e.g. QTR-25. Jira's single best UX
# feature is that every ticket has a short ID a human can say out loud.
TICKET_KEY_PREFIX = "QTR"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"


class TicketStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    CODE_REVIEW = "code_review"
    DONE = "done"


class TicketPriority(str, enum.Enum):
    HIGHEST = "highest"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOWEST = "lowest"


class TicketType(str, enum.Enum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SUBTASK = "subtask"


class SprintState(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


# Many-to-many: a ticket can carry several labels, a label spans many tickets.
ticket_labels = Table(
    "ticket_labels",
    Base.metadata,
    Column("ticket_id", UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", UUID(as_uuid=True), ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.DEVELOPER)
    # Null means "fall back to generated initials", which is the common case.
    avatar_url = Column(String, nullable=True)
    theme = Column(String, nullable=False, server_default="dark")
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets_assigned = relationship("Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id")
    tickets_reported = relationship("Ticket", back_populates="reporter", foreign_keys="Ticket.created_by_id")
    comments = relationship("Comment", back_populates="author")


class Label(Base):
    __tablename__ = "labels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    color = Column(String, nullable=False, default="#4C9AFF")  # hex, drives the chip colour
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets = relationship("Ticket", secondary=ticket_labels, back_populates="labels")


class Component(Base):
    """A part of the system a ticket belongs to — OTRAMS-Booking, RateNet-API,
    rePUSHTI. This is what stops a support queue spanning several products from
    blurring into one undifferentiated list."""
    __tablename__ = "components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    color = Column(String, nullable=False, default="#3E7BFA")
    # Who picks this up by default when nobody is assigned.
    lead_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    lead = relationship("User", foreign_keys=[lead_id])
    tickets = relationship("Ticket", back_populates="component")


class SLAPolicy(Base):
    """How long a ticket of a given priority may sit before it is breached.

    Configurable rather than hardcoded, because "critical" means four hours to
    one team and one hour to another.
    """
    __tablename__ = "sla_policies"

    priority = Column(SAEnum(TicketPriority), primary_key=True)
    # Null means this priority has no SLA — most teams only track the top ones.
    threshold_hours = Column(Integer, nullable=True)


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    goal = Column(Text, nullable=True)
    state = Column(SAEnum(SprintState), nullable=False, default=SprintState.PLANNED)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets = relationship("Ticket", back_populates="sprint")


# Drives the human-readable key. A DB sequence guarantees no two concurrent
# inserts can claim the same number, which a SELECT MAX(...)+1 cannot.
ticket_number_seq = Sequence("ticket_number_seq", start=1)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_number = Column(
        Integer, ticket_number_seq,
        server_default=ticket_number_seq.next_value(),
        unique=True, nullable=False, index=True,
    )

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), nullable=False, default=TicketStatus.TODO, index=True)
    priority = Column(SAEnum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    ticket_type = Column(SAEnum(TicketType), nullable=False, default=TicketType.TASK)
    story_points = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)

    # The external travel agency / company that raised this, distinct from the
    # internal reporter. A support ticket has both: a colleague who filed it and
    # a client who is waiting on it.
    client_name = Column(String, nullable=True, index=True)

    # When the ticket reached done. Freezes the SLA clock — without this, a
    # ticket closed inside its window would keep "ageing" and eventually show as
    # breached forever.
    resolved_at = Column(DateTime, nullable=True)

    # Position within its board column. Floats let us drop a card between two
    # neighbours by averaging their ranks — no need to renumber the column.
    rank = Column(Float, nullable=False, default=0.0)

    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sprint_id = Column(UUID(as_uuid=True), ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    component_id = Column(UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True)
    # An epic is itself a Ticket (type=epic); children point back at it.
    epic_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True)

    # A sub-task's parent. Distinct from epic_id: an epic groups a body of work
    # loosely, a parent OWNS its sub-tasks — delete the parent and they go too.
    parent_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("User", back_populates="tickets_assigned", foreign_keys=[assignee_id])
    reporter = relationship("User", back_populates="tickets_reported", foreign_keys=[created_by_id])
    sprint = relationship("Sprint", back_populates="tickets")
    component = relationship("Component", back_populates="tickets", lazy="joined")
    epic = relationship(
        "Ticket", remote_side=[id], foreign_keys=[epic_id], backref="epic_children"
    )
    subtasks = relationship(
        "Ticket",
        foreign_keys=[parent_id],
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Ticket.rank",
        backref=backref("parent", remote_side=[id]),
    )
    labels = relationship("Label", secondary=ticket_labels, back_populates="tickets", lazy="selectin")
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="ticket", cascade="all, delete-orphan")

    @property
    def key(self) -> str:
        return f"{TICKET_KEY_PREFIX}-{self.ticket_number}"


class Comment(Base):
    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User", back_populates="comments")


class ActivityLog(Base):
    """
    Tracks every meaningful change to a ticket (status change, assignment,
    priority change, etc.) so there's a visible audit trail.
    """
    __tablename__ = "activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)  # e.g. "status_changed", "assigned", "created"
    details = Column(Text, nullable=True)    # e.g. "todo -> in_progress"
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="activity_logs")
    actor = relationship("User")
