import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    DEVELOPER = "developer"


class TicketStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketType(str, enum.Enum):
    BUG = "bug"
    TASK = "task"
    FEATURE = "feature"
    IMPROVEMENT = "improvement"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.DEVELOPER)
    created_at = Column(DateTime, default=datetime.utcnow)

    tickets_assigned = relationship("Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id")
    comments = relationship("Comment", back_populates="author")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), nullable=False, default=TicketStatus.TODO)
    priority = Column(SAEnum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    ticket_type = Column(SAEnum(TicketType), nullable=False, default=TicketType.TASK)
    due_date = Column(DateTime, nullable=True)

    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = relationship("User", back_populates="tickets_assigned", foreign_keys=[assignee_id])
    comments = relationship("Comment", back_populates="ticket", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="ticket", cascade="all, delete-orphan")


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